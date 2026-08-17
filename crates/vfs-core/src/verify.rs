//! The shared match authority: pattern compilation and per-line hit finding.
//!
//! This module owns what "matches" means for grep across every language
//! surface. A pattern is parsed to the regex-syntax HIR, transformed to
//! honor the per-line law — `\n` is removed from every character class, a
//! pattern that can only match a line terminator is refused — then wrapping
//! `.*`/`.*?` runs are stripped (a line contains a match of `.*X.*` exactly
//! when it contains a match of `X`, and the wrapped form defeats the regex
//! engine's literal prefilter), and the result is compiled for byte
//! haystacks. Matching never pre-splits content into lines: the body is
//! scanned whole, and each match's enclosing line is recovered around it.
//!
//! Hits carry 1-based line numbers and the byte span of their context
//! block (the hit line extended `before`/`after` line boundaries, clamped
//! to the body). Inverted matching iterates lines and selects the
//! non-matching ones — no occurrence scan can find non-matches. Batch
//! entry points fan bodies across threads and honor a deadline between
//! bodies, reporting whether every body was verified.

use std::fmt;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Instant;

use memchr::{memchr, memchr_iter, memrchr};
use rayon::prelude::*;
use regex::bytes::Regex;
use regex_syntax::hir::{
    Capture, Class, ClassBytesRange, ClassUnicode, ClassUnicodeRange, Hir, HirKind, Literal,
    Repetition,
};

/// Why a pattern was refused: not in the grep pattern language.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PatternError {
    /// The regex-syntax parser rejected it (syntax error, backreference,
    /// look-around, or any other construct outside the crate language).
    Syntax(String),
    /// The pattern can only match a line terminator (a literal `\n`, or a
    /// class reduced to nothing once `\n` is removed).
    LineTerminator,
}

impl fmt::Display for PatternError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            PatternError::Syntax(message) => f.write_str(message),
            PatternError::LineTerminator => f.write_str("pattern matches a line terminator"),
        }
    }
}

impl std::error::Error for PatternError {}

/// One matched (or, inverted, unmatched) line: 1-based line numbers and the
/// byte span of the context block covering lines `start_line..=end_line`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Hit {
    pub start_line: u32,
    pub end_line: u32,
    pub match_line: u32,
    pub span: (usize, usize),
}

/// Batch results plus whether every body was verified before the deadline.
#[derive(Debug)]
pub struct BatchOutcome<T> {
    pub results: Vec<T>,
    pub completed: bool,
}

/// The compiled authority for one pattern.
#[derive(Debug)]
pub struct Matcher {
    regex: Regex,
}

impl Matcher {
    /// Compile `pattern` under the per-line law. The pattern arrives fully
    /// assembled (escaping and word-wrapping are host policy).
    pub fn new(pattern: &str, case_insensitive: bool) -> Result<Self, PatternError> {
        let hir = regex_syntax::ParserBuilder::new()
            .case_insensitive(case_insensitive)
            .multi_line(true)
            .dot_matches_new_line(false)
            .build()
            .parse(pattern)
            .map_err(|err| PatternError::Syntax(err.to_string()))?;
        let hir = strip_line_terminators(hir)?;
        let hir = strip_wrapping_dot_stars(hir);
        let regex = regex::bytes::RegexBuilder::new(&hir.to_string())
            .build()
            .map_err(|err| PatternError::Syntax(err.to_string()))?;
        Ok(Self { regex })
    }

    /// Count matched lines (non-matching lines when `invert`), stopping at
    /// `cap` when given.
    pub fn count_lines(&self, hay: &[u8], cap: Option<u64>, invert: bool) -> u64 {
        let mut count = 0u64;
        self.each_hit_line(hay, invert, |_, _, _| {
            count += 1;
            cap.is_none_or(|cap| count < cap)
        });
        count
    }

    /// The hit lines with their context spans, capped at `cap` when given.
    pub fn hit_lines(
        &self,
        hay: &[u8],
        before: u32,
        after: u32,
        cap: Option<u64>,
        invert: bool,
    ) -> Vec<Hit> {
        let mut hits: Vec<Hit> = Vec::new();
        self.each_hit_line(hay, invert, |ls, le, line_no| {
            hits.push(extend_context(hay, ls, le, line_no, before, after));
            cap.is_none_or(|cap| (hits.len() as u64) < cap)
        });
        hits
    }

    /// Drive `emit(line_start, line_end, line_no)` over each hit line in
    /// order; `emit` returns false to stop early.
    fn each_hit_line(&self, hay: &[u8], invert: bool, mut emit: impl FnMut(usize, usize, u32) -> bool) {
        if invert {
            for (ls, le, line_no) in LineRanges::new(hay) {
                if !self.regex.is_match(&hay[ls..le]) && !emit(ls, le, line_no) {
                    return;
                }
            }
            return;
        }
        let mut last_start = usize::MAX;
        let mut cursor = 0usize;
        let mut line_no = 1u32;
        for found in self.regex.find_iter(hay) {
            let ls = memrchr(b'\n', &hay[..found.start()]).map_or(0, |i| i + 1);
            if ls >= hay.len() {
                // An empty match after a trailing terminator: the position
                // is past the last real line (no phantom line exists there).
                continue;
            }
            if ls == last_start {
                continue;
            }
            last_start = ls;
            let le = memchr(b'\n', &hay[found.end()..]).map_or(hay.len(), |i| found.end() + i);
            line_no += memchr_iter(b'\n', &hay[cursor..ls]).count() as u32;
            cursor = ls;
            if !emit(ls, le, line_no) {
                return;
            }
        }
    }
}

/// `count_lines` across bodies in parallel; bodies started after `deadline`
/// are skipped (counted as zero) and flip `completed` off.
pub fn count_batch<B: AsRef<[u8]> + Sync>(
    matcher: &Matcher,
    bodies: &[B],
    cap: Option<u64>,
    invert: bool,
    deadline: Option<Instant>,
) -> BatchOutcome<u64> {
    let completed = AtomicBool::new(true);
    let results = bodies
        .par_iter()
        .map(|body| {
            if deadline.is_some_and(|at| Instant::now() > at) {
                completed.store(false, Ordering::Relaxed);
                return 0;
            }
            matcher.count_lines(body.as_ref(), cap, invert)
        })
        .collect();
    BatchOutcome { results, completed: completed.load(Ordering::Relaxed) }
}

/// `hit_lines` across bodies in parallel; bodies started after `deadline`
/// are skipped (empty hits) and flip `completed` off.
pub fn hits_batch<B: AsRef<[u8]> + Sync>(
    matcher: &Matcher,
    bodies: &[B],
    before: u32,
    after: u32,
    cap: Option<u64>,
    invert: bool,
    deadline: Option<Instant>,
) -> BatchOutcome<Vec<Hit>> {
    let completed = AtomicBool::new(true);
    let results = bodies
        .par_iter()
        .map(|body| {
            if deadline.is_some_and(|at| Instant::now() > at) {
                completed.store(false, Ordering::Relaxed);
                return Vec::new();
            }
            matcher.hit_lines(body.as_ref(), before, after, cap, invert)
        })
        .collect();
    BatchOutcome { results, completed: completed.load(Ordering::Relaxed) }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/// The line law as an iterator: `(start, end, 1-based number)` per line,
/// splitting on `\n` only, no phantom line after a trailing terminator.
struct LineRanges<'a> {
    hay: &'a [u8],
    pos: usize,
    line_no: u32,
}

impl<'a> LineRanges<'a> {
    fn new(hay: &'a [u8]) -> Self {
        Self { hay, pos: 0, line_no: 0 }
    }
}

impl Iterator for LineRanges<'_> {
    type Item = (usize, usize, u32);

    fn next(&mut self) -> Option<(usize, usize, u32)> {
        if self.pos >= self.hay.len() {
            return None;
        }
        let start = self.pos;
        let end = memchr(b'\n', &self.hay[start..]).map_or(self.hay.len(), |i| start + i);
        self.pos = end + 1;
        self.line_no += 1;
        Some((start, end, self.line_no))
    }
}

/// Extend a hit line's bounds by up to `before`/`after` line boundaries,
/// clamped to the body, and stamp the context's line-number range.
fn extend_context(hay: &[u8], ls: usize, le: usize, line_no: u32, before: u32, after: u32) -> Hit {
    let mut context_start = ls;
    let mut back = 0u32;
    while back < before && context_start > 0 {
        context_start = memrchr(b'\n', &hay[..context_start - 1]).map_or(0, |i| i + 1);
        back += 1;
    }
    let mut context_end = le;
    let mut forward = 0u32;
    while forward < after && context_end + 1 < hay.len() {
        context_end =
            memchr(b'\n', &hay[context_end + 1..]).map_or(hay.len(), |i| context_end + 1 + i);
        forward += 1;
    }
    Hit {
        start_line: line_no - back,
        end_line: line_no + forward,
        match_line: line_no,
        span: (context_start, context_end),
    }
}

/// Remove `\n` from every class; refuse a pattern that can only match a
/// line terminator (a `\n` literal, or a class emptied by the removal).
fn strip_line_terminators(hir: Hir) -> Result<Hir, PatternError> {
    Ok(match hir.into_kind() {
        HirKind::Empty => Hir::empty(),
        HirKind::Literal(Literal(bytes)) => {
            if bytes.contains(&b'\n') {
                return Err(PatternError::LineTerminator);
            }
            Hir::literal(bytes)
        }
        HirKind::Class(Class::Unicode(class)) => {
            let ranges: Vec<ClassUnicodeRange> =
                class.ranges().iter().flat_map(split_unicode_range).collect();
            if ranges.is_empty() {
                return Err(PatternError::LineTerminator);
            }
            Hir::class(Class::Unicode(ClassUnicode::new(ranges)))
        }
        HirKind::Class(Class::Bytes(class)) => {
            let ranges: Vec<ClassBytesRange> =
                class.ranges().iter().flat_map(split_byte_range).collect();
            if ranges.is_empty() {
                return Err(PatternError::LineTerminator);
            }
            Hir::class(Class::Bytes(regex_syntax::hir::ClassBytes::new(ranges)))
        }
        HirKind::Look(look) => Hir::look(look),
        HirKind::Repetition(rep) => Hir::repetition(Repetition {
            min: rep.min,
            max: rep.max,
            greedy: rep.greedy,
            sub: Box::new(strip_line_terminators(*rep.sub)?),
        }),
        HirKind::Capture(cap) => Hir::capture(Capture {
            index: cap.index,
            name: cap.name,
            sub: Box::new(strip_line_terminators(*cap.sub)?),
        }),
        HirKind::Concat(subs) => Hir::concat(
            subs.into_iter().map(strip_line_terminators).collect::<Result<Vec<_>, _>>()?,
        ),
        HirKind::Alternation(subs) => Hir::alternation(
            subs.into_iter().map(strip_line_terminators).collect::<Result<Vec<_>, _>>()?,
        ),
    })
}

fn split_unicode_range(range: &ClassUnicodeRange) -> Vec<ClassUnicodeRange> {
    let (lo, hi) = (range.start(), range.end());
    if lo > '\n' || hi < '\n' {
        return vec![*range];
    }
    let mut pieces = Vec::new();
    if lo <= '\u{09}' {
        pieces.push(ClassUnicodeRange::new(lo, '\u{09}'));
    }
    if hi >= '\u{0B}' {
        pieces.push(ClassUnicodeRange::new('\u{0B}', hi));
    }
    pieces
}

fn split_byte_range(range: &ClassBytesRange) -> Vec<ClassBytesRange> {
    let (lo, hi) = (range.start(), range.end());
    if lo > b'\n' || hi < b'\n' {
        return vec![*range];
    }
    let mut pieces = Vec::new();
    if lo <= 0x09 {
        pieces.push(ClassBytesRange::new(lo, 0x09));
    }
    if hi >= 0x0B {
        pieces.push(ClassBytesRange::new(0x0B, hi));
    }
    pieces
}

/// Strip leading/trailing `.*`/`.*?` at the top level: with `\n` excluded
/// from `.`, a line contains a match of `.*X.*` exactly when it contains a
/// match of `X`, and the wrapped form defeats literal prefilters.
fn strip_wrapping_dot_stars(hir: Hir) -> Hir {
    if is_dot_star(&hir) {
        return Hir::empty();
    }
    let HirKind::Concat(subs) = hir.kind() else {
        return hir;
    };
    let keep_from = subs.iter().take_while(|sub| is_dot_star(sub)).count();
    let keep_to = subs.len() - subs.iter().rev().take_while(|sub| is_dot_star(sub)).count();
    if keep_from == 0 && keep_to == subs.len() {
        return hir;
    }
    if keep_from >= keep_to {
        return Hir::empty();
    }
    let HirKind::Concat(subs) = hir.into_kind() else {
        unreachable!("kind checked above");
    };
    Hir::concat(subs.into_iter().take(keep_to).skip(keep_from).collect())
}

/// `.*` or `.*?`: an unbounded min-0 repetition of the dot class.
fn is_dot_star(hir: &Hir) -> bool {
    let HirKind::Repetition(rep) = hir.kind() else {
        return false;
    };
    if rep.min != 0 || rep.max.is_some() {
        return false;
    }
    let HirKind::Class(Class::Unicode(class)) = rep.sub.kind() else {
        return false;
    };
    let dot = [
        ClassUnicodeRange::new('\u{0}', '\u{09}'),
        ClassUnicodeRange::new('\u{0B}', '\u{10FFFF}'),
    ];
    class.ranges() == dot
}

#[cfg(test)]
mod tests {
    use super::*;

    fn hits(pattern: &str, ci: bool, hay: &str) -> Vec<u32> {
        let matcher = Matcher::new(pattern, ci).expect("pattern compiles");
        matcher.hit_lines(hay.as_bytes(), 0, 0, None, false).iter().map(|h| h.match_line).collect()
    }

    #[test]
    fn literal_finds_lines() {
        assert_eq!(hits("kfree", false, "a\nkfree(p);\nkfreed\n"), vec![2, 3]);
    }

    #[test]
    fn word_boundary_rejects_prefix_hits() {
        assert_eq!(hits(r"\b(?:kfree)\b", false, "kfreed\nkfree(p);\n"), vec![2]);
    }

    #[test]
    fn anchor_is_per_line() {
        assert_eq!(hits("^inc", false, "inc a\n#inc b\ninc c"), vec![1, 3]);
    }

    #[test]
    fn case_insensitive_flag() {
        assert_eq!(hits("copyright", true, "COPYRIGHT x\nnope\nCopyRight\n"), vec![1, 3]);
    }

    #[test]
    fn wrapped_dot_stars_reduce_to_inner() {
        let wrapped = Matcher::new(".*alloc_page.*", false).unwrap();
        let plain = Matcher::new("alloc_page", false).unwrap();
        let hay = b"x alloc_page(y)\nnothing\nalloc_pages\n".as_slice();
        assert_eq!(wrapped.hit_lines(hay, 0, 0, None, false), plain.hit_lines(hay, 0, 0, None, false));
    }

    #[test]
    fn class_newline_is_stripped() {
        assert_eq!(hits("a[\n b]c", false, "a c\nabc\na\nc\n"), vec![1, 2]);
    }

    #[test]
    fn newline_only_patterns_refuse() {
        assert_eq!(Matcher::new("foo\nbar", false).unwrap_err(), PatternError::LineTerminator);
        assert_eq!(Matcher::new(r"[\n]", false).unwrap_err(), PatternError::LineTerminator);
    }

    #[test]
    fn crate_language_refusals_are_syntax_errors() {
        assert!(matches!(Matcher::new(r"(a)\1", false), Err(PatternError::Syntax(_))));
        assert!(matches!(Matcher::new(r"a(?=b)", false), Err(PatternError::Syntax(_))));
        assert!(matches!(Matcher::new(r"a(?<=b)", false), Err(PatternError::Syntax(_))));
    }

    #[test]
    fn empty_pattern_matches_every_line() {
        assert_eq!(hits("", false, "a\n\nb\n"), vec![1, 2, 3]);
    }

    #[test]
    fn empty_line_anchor_pattern() {
        assert_eq!(hits("^$", false, "a\n\nb\n\n"), vec![2, 4]);
    }

    #[test]
    fn trailing_terminator_grows_no_line() {
        assert_eq!(hits(".", false, "a\nb\n"), vec![1, 2]);
        assert_eq!(hits(".", false, "a\nb"), vec![1, 2]);
        assert!(hits(".", false, "").is_empty());
    }

    #[test]
    fn context_spans_clamp_to_body() {
        let matcher = Matcher::new("c", false).unwrap();
        let hay = b"a\nb\nc\nd\ne\n".as_slice();
        let hit = &matcher.hit_lines(hay, 2, 2, None, false)[0];
        assert_eq!((hit.start_line, hit.match_line, hit.end_line), (1, 3, 5));
        assert_eq!(&hay[hit.span.0..hit.span.1], b"a\nb\nc\nd\ne");
        let hit = &matcher.hit_lines(b"c\nd\n", 3, 3, None, false)[0];
        assert_eq!((hit.start_line, hit.match_line, hit.end_line), (1, 1, 2));
    }

    #[test]
    fn cap_stops_hits_and_counts() {
        let matcher = Matcher::new("x", false).unwrap();
        let hay = b"x\nx\nx\nx\n".as_slice();
        assert_eq!(matcher.hit_lines(hay, 0, 0, Some(2), false).len(), 2);
        assert_eq!(matcher.count_lines(hay, Some(1), false), 1);
        assert_eq!(matcher.count_lines(hay, None, false), 4);
    }

    #[test]
    fn invert_selects_non_matching_lines() {
        assert_eq!(
            Matcher::new("x", false)
                .unwrap()
                .hit_lines(b"x\ny\nx\nz\n", 0, 0, None, true)
                .iter()
                .map(|h| h.match_line)
                .collect::<Vec<_>>(),
            vec![2, 4]
        );
    }

    #[test]
    fn multiple_matches_one_line_dedupe() {
        assert_eq!(hits("x", false, "x x x\nx\n"), vec![1, 2]);
    }

    #[test]
    fn batch_output_is_identical_across_pool_widths() {
        let matcher = Matcher::new(r"ab?c", false).unwrap();
        let bodies: Vec<Vec<u8>> = (0..64)
            .map(|i| {
                let mut body = Vec::new();
                for line in 0..(i % 7) * 40 {
                    if (line + i) % 3 == 0 {
                        body.extend_from_slice(b"xx abc yy\n");
                    } else {
                        body.extend_from_slice(b"nothing here\n");
                    }
                }
                body
            })
            .collect();
        let sequential_counts: Vec<u64> =
            bodies.iter().map(|b| matcher.count_lines(b, Some(9), false)).collect();
        let sequential_hits: Vec<Vec<Hit>> =
            bodies.iter().map(|b| matcher.hit_lines(b, 1, 2, Some(9), false)).collect();
        for threads in [1, 8] {
            let pool =
                rayon::ThreadPoolBuilder::new().num_threads(threads).build().expect("pool builds");
            let counts = pool.install(|| count_batch(&matcher, &bodies, Some(9), false, None));
            assert_eq!(counts.results, sequential_counts);
            let hits = pool.install(|| hits_batch(&matcher, &bodies, 1, 2, Some(9), false, None));
            assert_eq!(hits.results, sequential_hits);
        }
    }

    #[test]
    fn batch_reports_counts_and_completion() {
        let matcher = Matcher::new("x", false).unwrap();
        let bodies: Vec<&[u8]> = vec![b"x\n", b"y\n", b"x\nx\n"];
        let outcome = count_batch(&matcher, &bodies, None, false, None);
        assert_eq!(outcome.results, vec![1, 0, 2]);
        assert!(outcome.completed);
        let expired = Instant::now() - std::time::Duration::from_secs(1);
        let outcome = count_batch(&matcher, &bodies, None, false, Some(expired));
        assert!(!outcome.completed);
    }
}
