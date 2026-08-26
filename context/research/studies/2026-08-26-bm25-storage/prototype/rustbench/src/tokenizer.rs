//! A byte-identical port of `vfs.models.lexical.tokenize`, driven by the
//! interpreter's own character classes (`tables.rs`, generated).

use crate::tables::{CASEFOLD, DIGIT, LOWER, UPPER, WORD};

const MIN_TERM_CHARS: usize = 2;
const MAX_TERM_BYTES: usize = 64;

fn in_ranges(table: &[(u32, u32)], ch: char) -> bool {
    let cp = ch as u32;
    let mut lo = 0usize;
    let mut hi = table.len();
    while lo < hi {
        let mid = (lo + hi) / 2;
        let (a, b) = table[mid];
        if cp < a {
            hi = mid;
        } else if cp > b {
            lo = mid + 1;
        } else {
            return true;
        }
    }
    false
}

#[inline]
fn is_word(ch: char) -> bool {
    if ch.is_ascii() {
        ch.is_ascii_alphanumeric() || ch == '_'
    } else {
        in_ranges(&WORD, ch)
    }
}

#[inline]
fn is_upper(ch: char) -> bool {
    if ch.is_ascii() {
        ch.is_ascii_uppercase()
    } else {
        in_ranges(&UPPER, ch)
    }
}

#[inline]
fn is_lower(ch: char) -> bool {
    if ch.is_ascii() {
        ch.is_ascii_lowercase()
    } else {
        in_ranges(&LOWER, ch)
    }
}

#[inline]
fn is_digit(ch: char) -> bool {
    if ch.is_ascii() {
        ch.is_ascii_digit()
    } else {
        in_ranges(&DIGIT, ch)
    }
}

/// `fold_content`: Turkic-i pre-fold, then Python's per-code-point casefold.
fn fold_into(raw: &[char], out: &mut String) {
    out.clear();
    for &ch in raw {
        if ch.is_ascii() {
            out.push(ch.to_ascii_lowercase());
            continue;
        }
        let ch = if ch == '\u{131}' || ch == '\u{130}' { 'i' } else { ch };
        let cp = ch as u32;
        match CASEFOLD.binary_search_by_key(&cp, |&(k, _)| k) {
            Ok(i) => out.push_str(CASEFOLD[i].1),
            Err(_) => out.push(ch),
        }
    }
}

fn emit(terms: &mut Vec<String>, raw: &[char], scratch: &mut String) {
    fold_into(raw, scratch);
    if scratch.chars().count() >= MIN_TERM_CHARS && scratch.len() <= MAX_TERM_BYTES {
        terms.push(scratch.clone());
    }
}

fn case_boundary(piece: &[char], index: usize) -> bool {
    let previous = piece[index - 1];
    if is_lower(previous) || is_digit(previous) {
        return true;
    }
    is_upper(previous) && index + 1 < piece.len() && is_lower(piece[index + 1])
}

/// Split one word run on underscores, then on case changes (as `_identifier_parts`).
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

/// The reference tokenizer: folded terms in order, duplicates kept.
pub fn tokenize(content: &str) -> Vec<String> {
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
        emit(&mut terms, run, &mut scratch);
        if parts.len() > 1 {
            for part in parts.iter() {
                emit(&mut terms, part, &mut scratch);
            }
        }
    }
    terms
}
