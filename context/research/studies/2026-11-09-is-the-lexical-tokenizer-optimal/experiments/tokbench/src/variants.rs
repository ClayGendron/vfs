//! The tokenizer's stages and the candidate variants, every one of them a
//! rewrite of the rules in `crates/vfs-core/src/lexical.rs` (`tokenize`):
//! maximal word runs by the generated tables, the run whole and its parts
//! when more than one (split on `_`, then on case change, digit-led pieces
//! whole), Turkic-i pre-fold then the interpreter's casefold, terms under
//! two chars or over 64 bytes dropped, duplicates kept in order.
//!
//! The `stage_*` functions each stop the pipeline one step later, so the
//! difference between neighbours is one stage's cost. The `cand_*`
//! functions are the candidates; `main.rs` asserts each one's output
//! against `vfs_core::tokenize` on every body before timing it.
//! `lexical_tables` is the engine's own generated table file, included by
//! path so no class or fold can disagree.

use crate::lexical_tables::{CASEFOLD, DIGIT, LOWER, UPPER, WORD};

pub const MIN_TERM_CHARS: usize = 2;
pub const MAX_TERM_BYTES: usize = 64;

// ---------------------------------------------------------------------------
// The baseline's class checks and fold, as the engine writes them
// ---------------------------------------------------------------------------

fn in_ranges(table: &[(u32, u32)], ch: char) -> bool {
    let cp = ch as u32;
    table
        .binary_search_by(|&(lo, hi)| {
            if cp < lo {
                std::cmp::Ordering::Greater
            } else if cp > hi {
                std::cmp::Ordering::Less
            } else {
                std::cmp::Ordering::Equal
            }
        })
        .is_ok()
}

#[inline]
fn is_word(ch: char) -> bool {
    if ch.is_ascii() { ch.is_ascii_alphanumeric() || ch == '_' } else { in_ranges(&WORD, ch) }
}

#[inline]
fn is_upper(ch: char) -> bool {
    if ch.is_ascii() { ch.is_ascii_uppercase() } else { in_ranges(&UPPER, ch) }
}

#[inline]
fn is_lower(ch: char) -> bool {
    if ch.is_ascii() { ch.is_ascii_lowercase() } else { in_ranges(&LOWER, ch) }
}

#[inline]
fn is_digit(ch: char) -> bool {
    if ch.is_ascii() { ch.is_ascii_digit() } else { in_ranges(&DIGIT, ch) }
}

#[inline]
fn fold_char(ch: char, out: &mut String) {
    if ch.is_ascii() {
        out.push(ch.to_ascii_lowercase());
        return;
    }
    let ch = if ch == '\u{131}' || ch == '\u{130}' { 'i' } else { ch };
    match CASEFOLD.binary_search_by_key(&(ch as u32), |&(cp, _)| cp) {
        Ok(i) => out.push_str(CASEFOLD[i].1),
        Err(_) => out.push(ch),
    }
}

fn fold_into(raw: &[char], out: &mut String) {
    out.clear();
    for &ch in raw {
        fold_char(ch, out);
    }
}

fn fold_str_into(raw: &str, out: &mut String) {
    out.clear();
    for ch in raw.chars() {
        fold_char(ch, out);
    }
}

#[inline]
fn passes_length(folded: &str) -> bool {
    folded.chars().count() >= MIN_TERM_CHARS && folded.len() <= MAX_TERM_BYTES
}

fn case_boundary(piece: &[char], index: usize) -> bool {
    let previous = piece[index - 1];
    if is_lower(previous) || is_digit(previous) {
        return true;
    }
    is_upper(previous) && index + 1 < piece.len() && is_lower(piece[index + 1])
}

fn identifier_parts<'a>(run: &'a [char], parts: &mut Vec<&'a [char]>) {
    parts.clear();
    for piece in run.split(|&c| c == '_') {
        if piece.is_empty() {
            continue;
        }
        if is_digit(piece[0]) {
            parts.push(piece);
            continue;
        }
        let mut start = 0;
        for index in 1..piece.len() {
            if is_upper(piece[index]) && case_boundary(piece, index) {
                parts.push(&piece[start..index]);
                start = index;
            }
        }
        parts.push(&piece[start..]);
    }
}

// ---------------------------------------------------------------------------
// The profile: the pipeline cut one stage later each time
// ---------------------------------------------------------------------------

/// (i) `Vec<char>` collection only.
pub fn stage_chars(content: &str) -> u64 {
    let chars: Vec<char> = content.chars().collect();
    chars.len() as u64
}

/// (ii) collection plus run scanning with the class checks.
pub fn stage_scan(content: &str) -> u64 {
    let chars: Vec<char> = content.chars().collect();
    let mut acc = 0u64;
    let mut i = 0;
    while i < chars.len() {
        if !is_word(chars[i]) {
            i += 1;
            continue;
        }
        let start = i;
        while i < chars.len() && is_word(chars[i]) {
            i += 1;
        }
        acc += (i - start) as u64 + 1;
    }
    acc
}

/// (iii) plus the identifier split.
pub fn stage_split(content: &str) -> u64 {
    let chars: Vec<char> = content.chars().collect();
    let mut parts: Vec<&[char]> = Vec::new();
    let mut acc = 0u64;
    let mut i = 0;
    while i < chars.len() {
        if !is_word(chars[i]) {
            i += 1;
            continue;
        }
        let start = i;
        while i < chars.len() && is_word(chars[i]) {
            i += 1;
        }
        let run = &chars[start..i];
        identifier_parts(run, &mut parts);
        acc += run.len() as u64 + parts.len() as u64;
    }
    acc
}

/// (iv) plus the fold into the scratch buffer, for the run and its parts.
pub fn stage_fold(content: &str) -> u64 {
    let chars: Vec<char> = content.chars().collect();
    let mut parts: Vec<&[char]> = Vec::new();
    let mut scratch = String::new();
    let mut acc = 0u64;
    let mut i = 0;
    while i < chars.len() {
        if !is_word(chars[i]) {
            i += 1;
            continue;
        }
        let start = i;
        while i < chars.len() && is_word(chars[i]) {
            i += 1;
        }
        let run = &chars[start..i];
        identifier_parts(run, &mut parts);
        fold_into(run, &mut scratch);
        acc += scratch.len() as u64;
        if parts.len() > 1 {
            for part in parts.iter() {
                fold_into(part, &mut scratch);
                acc += scratch.len() as u64;
            }
        }
    }
    acc
}

/// (v) plus the length check; no clone.
pub fn stage_check(content: &str) -> u64 {
    let chars: Vec<char> = content.chars().collect();
    let mut parts: Vec<&[char]> = Vec::new();
    let mut scratch = String::new();
    let mut acc = 0u64;
    let mut i = 0;
    while i < chars.len() {
        if !is_word(chars[i]) {
            i += 1;
            continue;
        }
        let start = i;
        while i < chars.len() && is_word(chars[i]) {
            i += 1;
        }
        let run = &chars[start..i];
        identifier_parts(run, &mut parts);
        fold_into(run, &mut scratch);
        if passes_length(&scratch) {
            acc += scratch.len() as u64;
        }
        if parts.len() > 1 {
            for part in parts.iter() {
                fold_into(part, &mut scratch);
                if passes_length(&scratch) {
                    acc += scratch.len() as u64;
                }
            }
        }
    }
    acc
}

/// (vi) the full function, written here: the engine's `tokenize` stage by
/// stage, so the profile's last step is the clone and nothing else.
pub fn stage_full(content: &str) -> Vec<String> {
    let chars: Vec<char> = content.chars().collect();
    let mut terms = Vec::new();
    let mut parts: Vec<&[char]> = Vec::new();
    let mut scratch = String::new();
    let mut i = 0;
    while i < chars.len() {
        if !is_word(chars[i]) {
            i += 1;
            continue;
        }
        let start = i;
        while i < chars.len() && is_word(chars[i]) {
            i += 1;
        }
        let run = &chars[start..i];
        identifier_parts(run, &mut parts);
        fold_into(run, &mut scratch);
        if passes_length(&scratch) {
            terms.push(scratch.clone());
        }
        if parts.len() > 1 {
            for part in parts.iter() {
                fold_into(part, &mut scratch);
                if passes_length(&scratch) {
                    terms.push(scratch.clone());
                }
            }
        }
    }
    terms
}

// ---------------------------------------------------------------------------
// (a) no Vec<char>: char_indices over the &str, byte-offset slices
// ---------------------------------------------------------------------------

/// The identifier split over a `&str` run: the same rules, the pieces as
/// byte-offset slices, each piece scanned once with one char of lookahead.
fn identifier_parts_str<'a>(run: &'a str, parts: &mut Vec<&'a str>) {
    parts.clear();
    for piece in run.split('_') {
        if piece.is_empty() {
            continue;
        }
        let mut iter = piece.char_indices().peekable();
        let (_, first) = iter.next().expect("non-empty piece");
        if is_digit(first) {
            parts.push(piece);
            continue;
        }
        let mut start = 0;
        let mut previous = first;
        while let Some((offset, current)) = iter.next() {
            if is_upper(current) {
                let boundary = is_lower(previous)
                    || is_digit(previous)
                    || (is_upper(previous) && iter.peek().is_some_and(|&(_, next)| is_lower(next)));
                if boundary {
                    parts.push(&piece[start..offset]);
                    start = offset;
                }
            }
            previous = current;
        }
        parts.push(&piece[start..]);
    }
}

/// Every maximal word run of `content` as a `&str`, in order.
#[inline]
fn for_each_run<'a>(content: &'a str, mut handle: impl FnMut(&'a str)) {
    let mut run_start: Option<usize> = None;
    for (offset, ch) in content.char_indices() {
        if is_word(ch) {
            if run_start.is_none() {
                run_start = Some(offset);
            }
        } else if let Some(start) = run_start.take() {
            handle(&content[start..offset]);
        }
    }
    if let Some(start) = run_start {
        handle(&content[start..]);
    }
}

pub fn cand_a_no_vec_char(content: &str) -> Vec<String> {
    let mut terms = Vec::new();
    let mut parts: Vec<&str> = Vec::new();
    let mut scratch = String::new();
    for_each_run(content, |run| {
        identifier_parts_str(run, &mut parts);
        fold_str_into(run, &mut scratch);
        if passes_length(&scratch) {
            terms.push(scratch.clone());
        }
        if parts.len() > 1 {
            for part in parts.iter() {
                fold_str_into(part, &mut scratch);
                if passes_length(&scratch) {
                    terms.push(scratch.clone());
                }
            }
        }
    });
    terms
}

// ---------------------------------------------------------------------------
// (b) emit through a closure receiving &str: no clone
// ---------------------------------------------------------------------------

/// The baseline's structure (`Vec<char>`, fold buffer, chars().count()
/// check) with the clone replaced by a borrowed hand-off to `sink`.
pub fn cand_b_for_each_term(content: &str, chars: &mut Vec<char>, scratch: &mut String, mut sink: impl FnMut(&str)) {
    chars.clear();
    chars.extend(content.chars());
    let mut parts: Vec<&[char]> = Vec::new();
    let mut i = 0;
    while i < chars.len() {
        if !is_word(chars[i]) {
            i += 1;
            continue;
        }
        let start = i;
        while i < chars.len() && is_word(chars[i]) {
            i += 1;
        }
        let run = &chars[start..i];
        identifier_parts(run, &mut parts);
        fold_into(run, scratch);
        if passes_length(scratch) {
            sink(scratch);
        }
        if parts.len() > 1 {
            for part in parts.iter() {
                fold_into(part, scratch);
                if passes_length(scratch) {
                    sink(scratch);
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// (c) an ASCII fast path per run, on (a)'s scan, in one function
// ---------------------------------------------------------------------------

/// The identifier split of an all-ASCII run over its bytes; the slices are
/// of the `&str`, so every offset is a char boundary.
fn identifier_parts_ascii<'a>(run: &'a str, parts: &mut Vec<&'a str>) {
    parts.clear();
    let bytes = run.as_bytes();
    let mut piece_start = 0;
    for end in 0..=bytes.len() {
        if end < bytes.len() && bytes[end] != b'_' {
            continue;
        }
        let piece = &bytes[piece_start..end];
        let base = piece_start;
        piece_start = end + 1;
        if piece.is_empty() {
            continue;
        }
        if piece[0].is_ascii_digit() {
            parts.push(&run[base..end]);
            continue;
        }
        let mut start = 0;
        for index in 1..piece.len() {
            if !piece[index].is_ascii_uppercase() {
                continue;
            }
            let previous = piece[index - 1];
            let boundary = previous.is_ascii_lowercase()
                || previous.is_ascii_digit()
                || (previous.is_ascii_uppercase() && index + 1 < piece.len() && piece[index + 1].is_ascii_lowercase());
            if boundary {
                parts.push(&run[base + start..base + index]);
                start = index;
            }
        }
        parts.push(&run[base + start..end]);
    }
}

/// The folded form of an ASCII piece: a copy and an in-place lowercase.
/// For ASCII the byte count is the char count, so the check is on bytes.
#[inline]
fn emit_ascii(piece: &str, scratch: &mut String, sink: &mut impl FnMut(&str)) {
    if piece.len() >= MIN_TERM_CHARS && piece.len() <= MAX_TERM_BYTES {
        scratch.clear();
        scratch.push_str(piece);
        scratch.make_ascii_lowercase();
        sink(scratch);
    }
}

/// The general path of one run on (a)'s structure, through a sink; the
/// `check` is the length check in use, so (d) can swap it in.
#[inline]
fn emit_run_general<'a>(
    run: &'a str,
    parts: &mut Vec<&'a str>,
    scratch: &mut String,
    check: fn(&str) -> bool,
    sink: &mut impl FnMut(&str),
) {
    identifier_parts_str(run, parts);
    fold_str_into(run, scratch);
    if check(scratch) {
        sink(scratch);
    }
    if parts.len() > 1 {
        for part in parts.iter() {
            fold_str_into(part, scratch);
            if check(scratch) {
                sink(scratch);
            }
        }
    }
}

pub fn cand_c_ascii_runs(content: &str) -> Vec<String> {
    let mut terms = Vec::new();
    let mut parts: Vec<&str> = Vec::new();
    let mut scratch = String::new();
    let mut sink = |term: &str| terms.push(term.to_owned());
    for_each_run(content, |run| {
        if run.is_ascii() {
            identifier_parts_ascii(run, &mut parts);
            emit_ascii(run, &mut scratch, &mut sink);
            if parts.len() > 1 {
                for part in parts.iter() {
                    emit_ascii(part, &mut scratch, &mut sink);
                }
            }
        } else {
            emit_run_general(run, &mut parts, &mut scratch, passes_length, &mut sink);
        }
    });
    terms
}

// ---------------------------------------------------------------------------
// (d) the length check on bytes, chars counted only when they could differ
// ---------------------------------------------------------------------------

/// A folded term of fewer than two chars has at most four bytes (one
/// char); so a byte length of five or more passes without counting, an
/// all-ASCII short term has as many chars as bytes, and only a short
/// non-ASCII term is counted.
#[inline]
pub fn passes_length_bytes(folded: &str) -> bool {
    let len = folded.len();
    len >= MIN_TERM_CHARS
        && len <= MAX_TERM_BYTES
        && (len > 4 || folded.is_ascii() || folded.chars().count() >= MIN_TERM_CHARS)
}

/// The baseline's structure with (d) as its only change.
pub fn cand_d_byte_length_check(content: &str) -> Vec<String> {
    let chars: Vec<char> = content.chars().collect();
    let mut terms = Vec::new();
    let mut parts: Vec<&[char]> = Vec::new();
    let mut scratch = String::new();
    let mut i = 0;
    while i < chars.len() {
        if !is_word(chars[i]) {
            i += 1;
            continue;
        }
        let start = i;
        while i < chars.len() && is_word(chars[i]) {
            i += 1;
        }
        let run = &chars[start..i];
        identifier_parts(run, &mut parts);
        fold_into(run, &mut scratch);
        if passes_length_bytes(&scratch) {
            terms.push(scratch.clone());
        }
        if parts.len() > 1 {
            for part in parts.iter() {
                fold_into(part, &mut scratch);
                if passes_length_bytes(&scratch) {
                    terms.push(scratch.clone());
                }
            }
        }
    }
    terms
}

// ---------------------------------------------------------------------------
// (e) class checks through a 128-entry ASCII table, then the range search
// ---------------------------------------------------------------------------

const T_WORD: u8 = 1;
const T_UPPER: u8 = 2;
const T_LOWER: u8 = 4;
const T_DIGIT: u8 = 8;

const fn build_ascii_table() -> [u8; 128] {
    let mut table = [0u8; 128];
    let mut i = 0;
    while i < 128 {
        let b = i as u8;
        let mut flags = 0u8;
        if b.is_ascii_digit() {
            flags |= T_WORD | T_DIGIT;
        }
        if b.is_ascii_uppercase() {
            flags |= T_WORD | T_UPPER;
        }
        if b.is_ascii_lowercase() {
            flags |= T_WORD | T_LOWER;
        }
        if b == b'_' {
            flags |= T_WORD;
        }
        table[i] = flags;
        i += 1;
    }
    table
}

static ASCII_TABLE: [u8; 128] = build_ascii_table();

#[inline]
fn t_is_word(ch: char) -> bool {
    let cp = ch as u32;
    if cp < 128 { ASCII_TABLE[cp as usize] & T_WORD != 0 } else { in_ranges(&WORD, ch) }
}

#[inline]
fn t_is_upper(ch: char) -> bool {
    let cp = ch as u32;
    if cp < 128 { ASCII_TABLE[cp as usize] & T_UPPER != 0 } else { in_ranges(&UPPER, ch) }
}

#[inline]
fn t_is_lower(ch: char) -> bool {
    let cp = ch as u32;
    if cp < 128 { ASCII_TABLE[cp as usize] & T_LOWER != 0 } else { in_ranges(&LOWER, ch) }
}

#[inline]
fn t_is_digit(ch: char) -> bool {
    let cp = ch as u32;
    if cp < 128 { ASCII_TABLE[cp as usize] & T_DIGIT != 0 } else { in_ranges(&DIGIT, ch) }
}

fn t_case_boundary(piece: &[char], index: usize) -> bool {
    let previous = piece[index - 1];
    if t_is_lower(previous) || t_is_digit(previous) {
        return true;
    }
    t_is_upper(previous) && index + 1 < piece.len() && t_is_lower(piece[index + 1])
}

fn t_identifier_parts<'a>(run: &'a [char], parts: &mut Vec<&'a [char]>) {
    parts.clear();
    for piece in run.split(|&c| c == '_') {
        if piece.is_empty() {
            continue;
        }
        if t_is_digit(piece[0]) {
            parts.push(piece);
            continue;
        }
        let mut start = 0;
        for index in 1..piece.len() {
            if t_is_upper(piece[index]) && t_case_boundary(piece, index) {
                parts.push(&piece[start..index]);
                start = index;
            }
        }
        parts.push(&piece[start..]);
    }
}

/// The baseline's structure with (e) as its only change.
pub fn cand_e_ascii_class_table(content: &str) -> Vec<String> {
    let chars: Vec<char> = content.chars().collect();
    let mut terms = Vec::new();
    let mut parts: Vec<&[char]> = Vec::new();
    let mut scratch = String::new();
    let mut i = 0;
    while i < chars.len() {
        if !t_is_word(chars[i]) {
            i += 1;
            continue;
        }
        let start = i;
        while i < chars.len() && t_is_word(chars[i]) {
            i += 1;
        }
        let run = &chars[start..i];
        t_identifier_parts(run, &mut parts);
        fold_into(run, &mut scratch);
        if passes_length(&scratch) {
            terms.push(scratch.clone());
        }
        if parts.len() > 1 {
            for part in parts.iter() {
                fold_into(part, &mut scratch);
                if passes_length(&scratch) {
                    terms.push(scratch.clone());
                }
            }
        }
    }
    terms
}

// ---------------------------------------------------------------------------
// (f) the combination: (a) + (b) + (c) + (d) + (e)
// ---------------------------------------------------------------------------

/// Every maximal word run of `content`, the scan through the ASCII table.
#[inline]
fn for_each_run_t<'a>(content: &'a str, mut handle: impl FnMut(&'a str)) {
    let mut run_start: Option<usize> = None;
    for (offset, ch) in content.char_indices() {
        if t_is_word(ch) {
            if run_start.is_none() {
                run_start = Some(offset);
            }
        } else if let Some(start) = run_start.take() {
            handle(&content[start..offset]);
        }
    }
    if let Some(start) = run_start {
        handle(&content[start..]);
    }
}

/// The general (non-ASCII run) identifier split, through the ASCII table.
fn t_identifier_parts_str<'a>(run: &'a str, parts: &mut Vec<&'a str>) {
    parts.clear();
    for piece in run.split('_') {
        if piece.is_empty() {
            continue;
        }
        let mut iter = piece.char_indices().peekable();
        let (_, first) = iter.next().expect("non-empty piece");
        if t_is_digit(first) {
            parts.push(piece);
            continue;
        }
        let mut start = 0;
        let mut previous = first;
        while let Some((offset, current)) = iter.next() {
            if t_is_upper(current) {
                let boundary = t_is_lower(previous)
                    || t_is_digit(previous)
                    || (t_is_upper(previous) && iter.peek().is_some_and(|&(_, next)| t_is_lower(next)));
                if boundary {
                    parts.push(&piece[start..offset]);
                    start = offset;
                }
            }
            previous = current;
        }
        parts.push(&piece[start..]);
    }
}

/// The combined tokenizer: no `Vec<char>`, terms handed to `sink` as
/// borrowed `&str`, an ASCII byte path per all-ASCII run, the byte-first
/// length check, and the ASCII class table. `parts` and `scratch` are
/// the caller's reusable buffers.
pub fn cand_f_for_each_term<'a>(content: &'a str, parts: &mut Vec<&'a str>, scratch: &mut String, mut sink: impl FnMut(&str)) {
    for_each_run_t(content, |run| {
        if run.is_ascii() {
            identifier_parts_ascii(run, parts);
            emit_ascii(run, scratch, &mut sink);
            if parts.len() > 1 {
                for part in parts.iter() {
                    emit_ascii(part, scratch, &mut sink);
                }
            }
        } else {
            t_identifier_parts_str(run, parts);
            fold_str_into(run, scratch);
            if passes_length_bytes(scratch) {
                sink(scratch);
            }
            if parts.len() > 1 {
                for part in parts.iter() {
                    fold_str_into(part, scratch);
                    if passes_length_bytes(scratch) {
                        sink(scratch);
                    }
                }
            }
        }
    });
}

/// (f) with the binding's shape: a `Vec<String>` built from the sink.
pub fn cand_f_to_vec(content: &str) -> Vec<String> {
    let mut terms = Vec::new();
    let mut parts = Vec::new();
    let mut scratch = String::new();
    cand_f_for_each_term(content, &mut parts, &mut scratch, |term| terms.push(term.to_owned()));
    terms
}
