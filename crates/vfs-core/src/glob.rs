//! The glob matcher: a bit-parallel program over the glob language's atoms.
//!
//! The host walks a pattern and hands over its atoms — literals, the two
//! wildcards, classes as code-point ranges, separators and the two forms
//! of `**` — and this module expands them into steps. A match keeps one
//! bit per position between steps: bit `i` set means the subject read so
//! far can be matched by steps `0..i`. Each character shifts the set
//! through the steps that accept it, keeps the stars that accept it, then
//! closes over the stars and the `**/` groups. The match is anchored at
//! the subject's first character and whole.
//!
//! A pass touches only the words up to one past the word of the highest
//! set bit, which starts at most four positions in (the closure before
//! the first character) and rises at most five a character, so a match
//! holds at most `(4 + 5 * bytes) / 64 + 1` words, however long the
//! program. One match costs those words three times to set up, then per
//! character at most four passes over them (the transition, the scan for
//! the highest live word, the group pass and the star pass), two more
//! for a character outside ASCII (its two mask copies), plus that
//! character's non-ASCII literal and class steps within the live words.
//! Nothing depends on how the wildcards are arranged, and nothing
//! backtracks.
//!
//! A [`GlobSet`] holds one call's distinct programs in groups and judges
//! many rows in one call ([`judge_batch`]): rows spread across threads,
//! and a deadline is checked before each row and before every 64th
//! program a row matches, so one batch overruns it by at most 64 matches
//! a thread.

use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Instant;

use rayon::prelude::*;

use crate::verify::BatchOutcome;

/// One atom of the host's program, in pattern order.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Atom {
    /// One literal character.
    Lit(char),
    /// `?`: one character other than `/`.
    One,
    /// `*` inside a component: zero or more characters other than `/`.
    Star,
    /// A class: one character inside the sorted, disjoint ranges.
    Class(Vec<(char, char)>),
    /// A negated class: one character outside the ranges, `/` included.
    NClass(Vec<(char, char)>),
    /// Any one character, `/` included.
    Dot,
    /// Matches nothing.
    Never,
    /// The `/` between components.
    Sep,
    /// A middle `**`: zero segments, or one or more characters ending in `/`.
    Mid,
    /// A final `**`: zero or more of any character.
    Tail,
}

/// A program the host built out of the closure's invariants or a class's order.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProgramError(pub String);

impl std::fmt::Display for ProgramError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for ProgramError {}

/// A compiled glob program; build with [`GlobProgram::new`].
#[derive(Debug, Clone)]
pub struct GlobProgram {
    steps: usize,
    words: usize,
    ascii_accept: Vec<u64>,
    ascii_keep: Vec<u64>,
    wide_accept: Vec<u64>,
    wide_keep: Vec<u64>,
    stars: Vec<u64>,
    group_starts: Vec<u64>,
    wide_steps: Vec<(usize, WideStep)>,
}

impl GlobProgram {
    /// Expand *atoms* into steps and precompute the masks.
    ///
    /// Refuses a star or tail followed by a star, tail or mid, a mid
    /// followed by a mid or tail, and a class whose ranges are not
    /// sorted, disjoint and each `lo <= hi`: the one-pass closure and the
    /// binary search rest on those, so they are checked here, not assumed.
    pub fn new(atoms: &[Atom]) -> Result<GlobProgram, ProgramError> {
        check_atoms(atoms)?;
        let steps = expand(atoms);
        let count = steps.len();
        let words = (count + 1).div_ceil(64);
        let mut program = GlobProgram {
            steps: count,
            words,
            ascii_accept: vec![0; 128 * words],
            ascii_keep: vec![0; 128 * words],
            wide_accept: vec![0; words],
            wide_keep: vec![0; words],
            stars: vec![0; words],
            group_starts: vec![0; words],
            wide_steps: Vec::new(),
        };
        for (index, step) in steps.iter().enumerate() {
            program.place(index, step);
        }
        Ok(program)
    }

    /// Whether *subject* matches the program, whole, from its first character.
    pub fn is_match(&self, subject: &str) -> bool {
        self.match_cost(subject).0
    }

    /// The verdict with the work it took.
    fn match_cost(&self, subject: &str) -> (bool, MatchCost) {
        let mut cost = MatchCost::default();
        // No bit rises past 4 + 5 * chars, and chars <= bytes: the subject bounds the words.
        let live = ((4 + 5 * subject.len()) / 64 + 1).min(self.words);
        let mut state = vec![0u64; live];
        let mut accept = vec![0u64; live];
        let mut keep = vec![0u64; live];
        cost.word_ops += 3 * live;
        state[0] = 1;
        let mut top = 0usize;
        top = self.close(&mut state, top, &mut cost);
        for ch in subject.chars() {
            cost.chars += 1;
            let reach = (top + 1).min(live - 1);
            let (accept_mask, keep_mask): (&[u64], &[u64]) = if (ch as u32) < 128 {
                let row = ch as usize * self.words;
                (&self.ascii_accept[row..row + live], &self.ascii_keep[row..row + live])
            } else {
                self.wide_masks(ch, reach, &mut accept, &mut keep, &mut cost);
                (&accept, &keep)
            };
            let mut carry = 0u64;
            for word in 0..=reach {
                let advanced = state[word] & accept_mask[word];
                state[word] = (advanced << 1) | carry | (state[word] & keep_mask[word]);
                carry = advanced >> 63;
            }
            cost.word_ops += reach + 1;
            match highest_live(&state, reach, &mut cost) {
                Some(word) => top = word,
                None => return (false, cost),
            }
            top = self.close(&mut state, top, &mut cost);
        }
        let last = self.steps / 64;
        (last < live && state[last] >> (self.steps % 64) & 1 == 1, cost)
    }

    /// The group pass, then the star pass; returns the new highest live word.
    fn close(&self, state: &mut [u64], top: usize, cost: &mut MatchCost) -> usize {
        let top = shift_into(state, &self.group_starts, 3, top, cost);
        shift_into(state, &self.stars, 1, top, cost)
    }

    /// The accept and keep masks of one character outside ASCII, up to *reach*.
    fn wide_masks(&self, ch: char, reach: usize, accept: &mut [u64], keep: &mut [u64], cost: &mut MatchCost) {
        accept[..=reach].copy_from_slice(&self.wide_accept[..=reach]);
        keep[..=reach].copy_from_slice(&self.wide_keep[..=reach]);
        cost.word_ops += 2 * (reach + 1);
        let bound = (reach + 1) * 64;
        for (index, step) in &self.wide_steps {
            if *index >= bound {
                break;
            }
            cost.step_reads += 1;
            if step.accepts(ch) {
                accept[index / 64] |= 1 << (index % 64);
            }
        }
    }

    /// Record one step's bit in every mask that names it.
    fn place(&mut self, index: usize, step: &Step) {
        let (word, bit) = (index / 64, 1u64 << (index % 64));
        for code in 0u8..128 {
            let row = code as usize * self.words + word;
            if step.accepts(code as char) {
                self.ascii_accept[row] |= bit;
            }
            if step.keeps(code as char) {
                self.ascii_keep[row] |= bit;
            }
        }
        match step {
            Step::NotSep | Step::Any => self.wide_accept[word] |= bit,
            Step::StarNotSep | Step::StarAny => {
                self.wide_keep[word] |= bit;
                self.stars[word] |= bit;
            }
            Step::Lit(ch) if (*ch as u32) >= 128 => self.wide_steps.push((index, WideStep::Lit(*ch))),
            Step::Class { negated, ranges } => {
                self.wide_steps.push((index, WideStep::Class { negated: *negated, ranges: ranges.clone() }));
            }
            Step::GroupAny => {
                self.wide_accept[word] |= bit;
                self.group_starts[word] |= bit;
            }
            Step::Lit(_) | Step::Never => {}
        }
    }
}

// ---------------------------------------------------------------------------
// The set: one call's programs, judged in batches
// ---------------------------------------------------------------------------

/// The most groups a set holds: one bit each in a verdict word.
pub const MAX_GROUPS: usize = 64;

/// Programs matched before a row checks its deadline again.
const PROGRAMS_PER_CHECK: usize = 64;

/// One call's distinct programs and the groups that name them by index.
///
/// A row's verdict has bit `g` set when some program of group `g`
/// matches its subject: the path for a program that reads the path,
/// the leaf name otherwise. A program shared by two groups is built once.
#[derive(Debug, Clone)]
pub struct GlobSet {
    programs: Vec<(GlobProgram, bool)>,
    groups: Vec<Vec<usize>>,
}

impl GlobSet {
    /// Build every program, or `Ok(None)` once *deadline* passes before one.
    ///
    /// Refuses more than [`MAX_GROUPS`] groups, a group index past the
    /// programs, and any program [`GlobProgram::new`] refuses.
    pub fn build(
        programs: Vec<(Vec<Atom>, bool)>,
        groups: Vec<Vec<usize>>,
        deadline: Option<Instant>,
    ) -> Result<Option<GlobSet>, ProgramError> {
        if groups.len() > MAX_GROUPS {
            return Err(ProgramError(format!("a set holds at most {MAX_GROUPS} groups, got {}", groups.len())));
        }
        if let Some(index) = groups.iter().flatten().find(|index| **index >= programs.len()) {
            return Err(ProgramError(format!("group index {index} is past the {} programs", programs.len())));
        }
        let mut built = Vec::with_capacity(programs.len());
        for (atoms, by_path) in &programs {
            if past(deadline) {
                return Ok(None);
            }
            built.push((GlobProgram::new(atoms)?, *by_path));
        }
        Ok(Some(GlobSet { programs: built, groups }))
    }

    /// The row's verdict word, or `None` when *deadline* passed inside its groups.
    ///
    /// Each group stops at its first match; the deadline is checked before
    /// every 64th program matched, so a row overruns it by at most 64 matches.
    pub fn verdict(&self, path: &str, name: &str, deadline: Option<Instant>) -> Option<u64> {
        self.verdict_with(path, name, || past(deadline)).0
    }

    /// The verdict under an injected deadline check, with the programs matched.
    fn verdict_with(&self, path: &str, name: &str, mut expired: impl FnMut() -> bool) -> (Option<u64>, usize) {
        let mut word = 0u64;
        let mut matched = 0usize;
        for (bit, group) in self.groups.iter().enumerate() {
            for &index in group {
                if matched > 0 && matched.is_multiple_of(PROGRAMS_PER_CHECK) && expired() {
                    return (None, matched);
                }
                matched += 1;
                let (program, by_path) = &self.programs[index];
                if program.is_match(if *by_path { path } else { name }) {
                    word |= 1 << bit;
                    break;
                }
            }
        }
        (Some(word), matched)
    }
}

/// Every row's verdict across threads; a row started after *deadline*, or
/// stopped inside its groups, is `None` and flips `completed` off.
pub fn judge_batch<S: AsRef<str> + Sync>(
    set: &GlobSet,
    rows: &[(S, S)],
    deadline: Option<Instant>,
) -> BatchOutcome<Option<u64>> {
    let completed = AtomicBool::new(true);
    let results = rows
        .par_iter()
        .map(|(path, name)| {
            let verdict = if past(deadline) { None } else { set.verdict(path.as_ref(), name.as_ref(), deadline) };
            if verdict.is_none() {
                completed.store(false, Ordering::Relaxed);
            }
            verdict
        })
        .collect();
    BatchOutcome { results, completed: completed.load(Ordering::Relaxed) }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/// Whether *deadline* has passed; no deadline never passes.
fn past(deadline: Option<Instant>) -> bool {
    deadline.is_some_and(|at| Instant::now() > at)
}

/// The work one match took: characters read, words touched, wide steps read.
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
struct MatchCost {
    chars: usize,
    word_ops: usize,
    step_reads: usize,
}

/// One consuming or self-looping position of the expanded program.
#[derive(Debug, Clone)]
enum Step {
    Lit(char),
    NotSep,
    Any,
    /// The first step of a `**/` group: any character, and the group's skip starts here.
    GroupAny,
    Class { negated: bool, ranges: Vec<(char, char)> },
    Never,
    StarNotSep,
    StarAny,
}

impl Step {
    /// Whether the step consumes *ch* and advances.
    fn accepts(&self, ch: char) -> bool {
        match self {
            Step::Lit(lit) => *lit == ch,
            Step::NotSep => ch != '/',
            Step::Any | Step::GroupAny => true,
            Step::Class { negated, ranges } => in_ranges(ranges, ch) != *negated,
            Step::Never | Step::StarNotSep | Step::StarAny => false,
        }
    }

    /// Whether the step is a star that consumes *ch* and stays.
    fn keeps(&self, ch: char) -> bool {
        match self {
            Step::StarNotSep => ch != '/',
            Step::StarAny => true,
            _ => false,
        }
    }
}

/// A step a character outside ASCII must read at match time.
#[derive(Debug, Clone)]
enum WideStep {
    Lit(char),
    Class { negated: bool, ranges: Vec<(char, char)> },
}

impl WideStep {
    fn accepts(&self, ch: char) -> bool {
        match self {
            WideStep::Lit(lit) => *lit == ch,
            WideStep::Class { negated, ranges } => in_ranges(ranges, ch) != *negated,
        }
    }
}

/// Refuse the atom sequences the one-pass closure and the binary search cannot serve.
fn check_atoms(atoms: &[Atom]) -> Result<(), ProgramError> {
    for pair in atoms.windows(2) {
        let refused = match (&pair[0], &pair[1]) {
            (Atom::Star | Atom::Tail, Atom::Star | Atom::Tail | Atom::Mid) => true,
            (Atom::Mid, Atom::Mid | Atom::Tail) => true,
            _ => false,
        };
        if refused {
            return Err(ProgramError(format!("{:?} may not follow {:?}", pair[1], pair[0])));
        }
    }
    for atom in atoms {
        if let Atom::Class(ranges) | Atom::NClass(ranges) = atom {
            let ordered = ranges.iter().all(|(lo, hi)| lo <= hi) && ranges.windows(2).all(|pair| pair[0].1 < pair[1].0);
            if !ordered {
                return Err(ProgramError("class ranges must be sorted, disjoint, and each lo <= hi".to_string()));
            }
        }
    }
    Ok(())
}

/// The steps of *atoms*; a mid becomes any character, a star over any, and `/`.
fn expand(atoms: &[Atom]) -> Vec<Step> {
    let mut steps = Vec::with_capacity(atoms.len());
    for atom in atoms {
        match atom {
            Atom::Lit(ch) => steps.push(Step::Lit(*ch)),
            Atom::One => steps.push(Step::NotSep),
            Atom::Star => steps.push(Step::StarNotSep),
            Atom::Class(ranges) => steps.push(Step::Class { negated: false, ranges: ranges.clone() }),
            Atom::NClass(ranges) => steps.push(Step::Class { negated: true, ranges: ranges.clone() }),
            Atom::Dot => steps.push(Step::Any),
            Atom::Never => steps.push(Step::Never),
            Atom::Sep => steps.push(Step::Lit('/')),
            Atom::Mid => steps.extend([Step::GroupAny, Step::StarAny, Step::Lit('/')]),
            Atom::Tail => steps.push(Step::StarAny),
        }
    }
    steps
}

/// Whether *ch* falls in the sorted, disjoint *ranges*.
fn in_ranges(ranges: &[(char, char)], ch: char) -> bool {
    let after = ranges.partition_point(|(lo, _)| *lo <= ch);
    after > 0 && ch <= ranges[after - 1].1
}

/// `state |= (state & mask) << by`, over the words up to one past *top*.
///
/// A closure only adds bits, so the new highest live word is *top* or the
/// one past it; no scan is needed.
fn shift_into(state: &mut [u64], mask: &[u64], by: u32, top: usize, cost: &mut MatchCost) -> usize {
    let reach = (top + 1).min(state.len() - 1);
    let mut carry = 0u64;
    for word in 0..=reach {
        let moving = state[word] & mask[word];
        state[word] |= (moving << by) | carry;
        carry = moving >> (64 - by);
    }
    cost.word_ops += reach + 1;
    if state[reach] != 0 { reach } else { top }
}

/// The highest word at or below *reach* with a set bit, each word looked at counted.
fn highest_live(state: &[u64], reach: usize, cost: &mut MatchCost) -> Option<usize> {
    for word in (0..=reach).rev() {
        cost.word_ops += 1;
        if state[word] != 0 {
            return Some(word);
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    fn lits(text: &str) -> Vec<Atom> {
        text.chars().map(|ch| if ch == '/' { Atom::Sep } else { Atom::Lit(ch) }).collect()
    }

    fn program(atoms: Vec<Atom>) -> GlobProgram {
        GlobProgram::new(&atoms).expect("a well-formed program")
    }

    /// The `/**/*a` + `?` x 250 shape: a mid, a star, a literal and many `one`s.
    fn mid_star_shape() -> GlobProgram {
        let mut atoms = vec![Atom::Sep, Atom::Mid, Atom::Star, Atom::Lit('a')];
        atoms.extend(std::iter::repeat_n(Atom::One, 250));
        program(atoms)
    }

    #[test]
    fn the_match_is_anchored_and_whole() {
        let a = program(lits("a"));
        assert!(a.is_match("a"));
        assert!(!a.is_match("ba"));
        assert!(!a.is_match("ab"));
        assert!(!a.is_match(""));
    }

    #[test]
    fn twelve_stars_against_255_a_is_false() {
        let mut atoms = Vec::new();
        for _ in 0..12 {
            atoms.extend([Atom::Star, Atom::Lit('a')]);
        }
        atoms.extend([Atom::Star, Atom::Lit('b')]);
        assert!(!program(atoms).is_match(&"a".repeat(255)));
    }

    #[test]
    fn one_matches_one_wide_character_and_not_two_narrow_ones() {
        let one = program(vec![Atom::One]);
        for wide in ["é", "日", "😀"] {
            assert!(one.is_match(wide), "{wide}");
        }
        assert!(!one.is_match("ab"));
        assert!(!one.is_match("/"));
    }

    #[test]
    fn a_negated_class_matches_the_separator() {
        let not_x = program(vec![Atom::Lit('a'), Atom::NClass(vec![('x', 'x')]), Atom::Lit('b')]);
        assert!(not_x.is_match("a/b"));
        assert!(!not_x.is_match("axb"));
        let class = program(vec![Atom::Class(vec![('a', 'c'), ('é', 'é')])]);
        assert!(class.is_match("b") && class.is_match("é") && !class.is_match("d"));
    }

    #[test]
    fn never_matches_nothing_and_dot_matches_the_separator() {
        assert!(!program(vec![Atom::Never]).is_match("a"));
        assert!(!program(vec![Atom::Never]).is_match(""));
        assert!(program(vec![Atom::Dot]).is_match("/"));
    }

    #[test]
    fn a_mid_spans_zero_segments_and_three() {
        let mut atoms = vec![Atom::Sep, Atom::Mid];
        atoms.extend(lits("x"));
        let deep = program(atoms);
        assert!(deep.is_match("/x"));
        assert!(deep.is_match("/a/b/c/x"));
        assert!(!deep.is_match("/a/bx"));
        let tail = program(vec![Atom::Sep, Atom::Lit('a'), Atom::Sep, Atom::Tail]);
        assert!(tail.is_match("/a/") && tail.is_match("/a/b/c") && !tail.is_match("/a"));
    }

    #[test]
    fn programs_that_break_the_closure_or_the_class_order_are_refused() {
        for atoms in [
            vec![Atom::Star, Atom::Star],
            vec![Atom::Star, Atom::Mid],
            vec![Atom::Tail, Atom::Star],
            vec![Atom::Mid, Atom::Mid],
            vec![Atom::Mid, Atom::Tail],
            vec![Atom::Class(vec![('b', 'a')])],
            vec![Atom::NClass(vec![('a', 'c'), ('b', 'd')])],
        ] {
            assert!(GlobProgram::new(&atoms).is_err(), "{atoms:?}");
        }
        assert!(GlobProgram::new(&[Atom::Mid, Atom::Star]).is_ok());
    }

    /// The transition's carry across a word: 71 literal steps span two words.
    #[test]
    fn a_literal_path_past_one_word_matches_itself() {
        let subject = format!("/{}", "a".repeat(70));
        let long = program(lits(&subject));
        assert!(long.is_match(&subject));
        assert!(!long.is_match(&format!("/{}", "a".repeat(69))));
    }

    /// The star pass's carry: the star sits at bit 63, its skip lands in the next word.
    #[test]
    fn a_star_at_the_end_of_a_word_skips_into_the_next() {
        let mut atoms = lits(&"a".repeat(63));
        atoms.extend([Atom::Star, Atom::Lit('b')]);
        let crossing = program(atoms);
        assert!(crossing.is_match(&format!("{}b", "a".repeat(63))));
        assert!(crossing.is_match(&format!("{}zzb", "a".repeat(63))));
    }

    /// The group pass's carry: a group starting at bit 62 ends at bit 65.
    #[test]
    fn a_group_across_a_word_skips_into_the_next() {
        let mut atoms = lits(&"a".repeat(62));
        atoms.extend([Atom::Mid, Atom::Lit('x')]);
        let crossing = program(atoms);
        assert!(crossing.is_match(&format!("{}x", "a".repeat(62))));
        assert!(crossing.is_match(&format!("{}q/r/x", "a".repeat(62))));
        assert!(!crossing.is_match(&format!("{}qx", "a".repeat(62))));
    }

    /// A `mid` straight after a literal rises five positions a character: the buffers must hold it.
    #[test]
    fn the_live_words_bound_is_tight() {
        let mut opening = Vec::new();
        for _ in 0..12 {
            opening.extend([Atom::Mid, Atom::Star, Atom::Lit('a')]);
        }
        opening.extend([Atom::Mid, Atom::Star]);
        assert!(program(opening).is_match(&"a".repeat(12)));
        let mut rising = Vec::new();
        for _ in 0..100 {
            rising.extend([Atom::Mid, Atom::Star, Atom::Lit('a')]);
        }
        assert!(program(rising).is_match(&"a".repeat(100)));
    }

    #[test]
    fn a_long_program_against_a_short_subject_sets_up_what_the_subject_allows() {
        let long = program(std::iter::repeat_n(Atom::One, 100_000).collect());
        let (matched, cost) = long.match_cost(&"x".repeat(10));
        assert!(!matched);
        assert!(cost.word_ops <= 3 + 4 * 10 + 2, "{cost:?}");
    }

    #[test]
    fn the_mid_star_shape_costs_at_most_four_words_a_character() {
        let shape = mid_star_shape();
        let path = format!("/{}", "x".repeat(999));
        let (matched, cost) = shape.match_cost(&path);
        assert!(!matched);
        assert_eq!(cost.chars, 1_000);
        assert!(cost.word_ops <= 4 * cost.chars * shape.words + 5 * shape.words, "{cost:?}");
    }

    #[test]
    fn the_work_is_linear_in_the_subject() {
        // Three passes a character over at most the program's words, plus the
        // first closure's two; the live words ramp up, so short subjects cost less.
        let shape = mid_star_shape();
        for pairs in [250, 500, 1_000] {
            let cost = shape.match_cost(&format!("/{}", "xa".repeat(pairs))).1;
            assert!(cost.word_ops <= 4 * cost.chars * shape.words + 5 * shape.words, "{cost:?}");
        }
    }

    #[test]
    fn a_pattern_longer_than_the_path_costs_what_the_path_allows() {
        let long = program(std::iter::repeat_n(Atom::One, 100_000).collect());
        let (matched, cost) = long.match_cost(&"x".repeat(1_024));
        assert!(!matched);
        assert!(cost.word_ops <= 1_024 * (5 * 1_024 / 64 + 2), "{cost:?}");
    }

    /// The set's input for one pattern: its atoms and whether it reads the path.
    fn entry(atoms: Vec<Atom>, by_path: bool) -> (Vec<Atom>, bool) {
        (atoms, by_path)
    }

    fn set(programs: Vec<(Vec<Atom>, bool)>, groups: Vec<Vec<usize>>) -> GlobSet {
        GlobSet::build(programs, groups, None).expect("a well-formed set").expect("no deadline")
    }

    /// `*.py` over names, `/src/` + tail over paths, `/` `**/` `app/` tail over paths.
    fn three_groups() -> GlobSet {
        let py = vec![Atom::Star, Atom::Lit('.'), Atom::Lit('p'), Atom::Lit('y')];
        let mut src = lits("/src/");
        src.push(Atom::Tail);
        let mut app = vec![Atom::Sep, Atom::Mid];
        app.extend(lits("app/"));
        app.push(Atom::Tail);
        set(
            vec![entry(py, false), entry(src, true), entry(app, true)],
            vec![vec![0], vec![1], vec![2, 0]],
        )
    }

    #[test]
    fn glob_set_sets_one_bit_per_matching_group() {
        let gates = three_groups();
        assert_eq!(gates.verdict("/src/app/main.py", "main.py", None), Some(0b111));
        assert_eq!(gates.verdict("/src/readme.md", "readme.md", None), Some(0b010));
        assert_eq!(gates.verdict("/lib/a.py", "a.py", None), Some(0b101));
        assert_eq!(gates.verdict("/lib/a.md", "a.md", None), Some(0));
    }

    #[test]
    fn glob_set_reads_the_path_or_the_name_per_program() {
        let name = lits("x");
        let path = lits("/x");
        let gates = set(vec![entry(name, false), entry(path, true)], vec![vec![0], vec![1]]);
        assert_eq!(gates.verdict("/x", "x", None), Some(0b11));
        assert_eq!(gates.verdict("/d/x", "x", None), Some(0b01));
        // A name program never sees the path, a path program never the name.
        assert_eq!(gates.verdict("/x", "y", None), Some(0b10));
    }

    #[test]
    fn glob_set_rows_past_the_deadline_are_unjudged() {
        let gates = three_groups();
        let rows: Vec<(&str, &str)> = vec![("/src/a.py", "a.py"), ("/b.md", "b.md"), ("/app/c", "c")];
        let expired = Instant::now() - std::time::Duration::from_secs(1);
        let outcome = judge_batch(&gates, &rows, Some(expired));
        assert_eq!(outcome.results, vec![None, None, None]);
        assert!(!outcome.completed);
        let outcome = judge_batch(&gates, &rows, None);
        assert!(outcome.results.iter().all(Option::is_some));
        assert!(outcome.completed);
    }

    #[test]
    fn glob_set_a_row_with_many_programs_stops_at_the_deadline() {
        let programs = (0..1_000).map(|_| entry(lits("never-this"), false)).collect();
        let gates = set(programs, vec![(0..1_000).collect()]);
        let mut checks = 0;
        let (verdict, matched) = gates.verdict_with("/a", "a", || {
            checks += 1;
            checks >= 2
        });
        assert_eq!(verdict, None);
        assert!(matched <= 128, "{matched} programs matched past the deadline");
    }

    #[test]
    fn glob_set_a_group_stops_at_its_first_match() {
        let programs = (0..1_000).map(|_| entry(lits("a"), false)).collect();
        let gates = set(programs, vec![(0..1_000).collect()]);
        let (verdict, matched) = gates.verdict_with("/a", "a", || false);
        assert_eq!(verdict, Some(1));
        assert_eq!(matched, 1);
    }

    #[test]
    fn glob_set_build_stops_at_the_deadline() {
        let expired = Instant::now() - std::time::Duration::from_secs(1);
        let built = GlobSet::build(vec![entry(lits("a"), false)], vec![vec![0]], Some(expired));
        assert!(matches!(built, Ok(None)));
    }

    #[test]
    fn glob_set_batch_is_thread_count_invariant() {
        let gates = three_groups();
        let rows: Vec<(String, String)> = (0..1_000)
            .map(|i| {
                let dir = ["src", "src/app", "lib", "app"][i % 4];
                let name = format!("f{i}.{}", ["py", "md", "rs"][i % 3]);
                (format!("/{dir}/{name}"), name)
            })
            .collect();
        let sequential: Vec<Option<u64>> = rows.iter().map(|(path, name)| gates.verdict(path, name, None)).collect();
        for threads in [1, 8] {
            let pool = rayon::ThreadPoolBuilder::new().num_threads(threads).build().expect("pool builds");
            let outcome = pool.install(|| judge_batch(&gates, &rows, None));
            assert_eq!(outcome.results, sequential);
            assert!(outcome.completed);
        }
    }

    #[test]
    fn glob_set_refuses_an_index_out_of_range_and_a_65th_group() {
        let out_of_range = GlobSet::build(vec![entry(lits("a"), false)], vec![vec![1]], None);
        assert!(out_of_range.is_err());
        let too_wide = GlobSet::build(vec![entry(lits("a"), false)], vec![vec![0]; MAX_GROUPS + 1], None);
        assert!(too_wide.is_err());
        assert!(GlobSet::build(vec![entry(lits("a"), false)], vec![vec![0]; MAX_GROUPS], None).is_ok());
        let refused = GlobSet::build(vec![entry(vec![Atom::Star, Atom::Star], false)], vec![vec![0]], None);
        assert!(refused.is_err());
    }

    #[test]
    fn wide_characters_read_at_most_the_wide_steps() {
        let classes = program(std::iter::repeat_n(Atom::Class(vec![('a', 'z')]), 100).collect());
        let (_, cost) = classes.match_cost(&"é".repeat(300));
        assert!(cost.step_reads <= 300 * 100, "{cost:?}");
        // Only the steps within the live words are read, however many classes follow.
        let many = program(std::iter::repeat_n(Atom::Class(vec![('a', 'z'), ('é', 'é')]), 100_000).collect());
        let (matched, cost) = many.match_cost(&"é".repeat(255));
        assert!(!matched);
        let live = (4 + 5 * "é".repeat(255).len()) / 64 + 1;
        assert!(cost.step_reads <= 255 * 64 * live, "{cost:?}");
    }
}
