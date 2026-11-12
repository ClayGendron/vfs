//! The overlay-counts kernel spike: the vfs lexical tokenizer's loop with the
//! per-term `String` allocation removed, counting a body's tokens and the
//! term frequency of each query term as it goes.
//!
//! The scanning, folding and identifier-splitting rules are the same as
//! `crates/vfs-core/src/lexical.rs` (`tokenize`): each word run is emitted
//! whole, and its parts when there are more than one; a term shorter than
//! two chars or longer than 64 bytes is dropped. The only difference is
//! what happens to a folded term: instead of `terms.push(scratch.clone())`
//! it is counted and compared against the query terms in place.
//! `lexical_tables` is the engine's own generated table file, included by
//! path so the two cannot disagree on a class or a fold.

use std::collections::HashMap;

use crate::lexical_tables::{CASEFOLD, DIGIT, LOWER, UPPER, WORD};

const MIN_TERM_CHARS: usize = 2;
const MAX_TERM_BYTES: usize = 64;

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

fn fold_into(raw: &[char], out: &mut String) {
    out.clear();
    for &ch in raw {
        if ch.is_ascii() {
            out.push(ch.to_ascii_lowercase());
            continue;
        }
        let ch = if ch == '\u{131}' || ch == '\u{130}' { 'i' } else { ch };
        match CASEFOLD.binary_search_by_key(&(ch as u32), |&(cp, _)| cp) {
            Ok(i) => out.push_str(CASEFOLD[i].1),
            Err(_) => out.push(ch),
        }
    }
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

/// Run the tokenizer over `content`, handing every folded term to `sink`
/// as a borrowed `&str` that is valid only for the call.
fn for_each_term(content: &str, chars: &mut Vec<char>, scratch: &mut String, mut sink: impl FnMut(&str)) {
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
        if scratch.chars().count() >= MIN_TERM_CHARS && scratch.len() <= MAX_TERM_BYTES {
            sink(scratch);
        }
        if parts.len() > 1 {
            for part in parts.iter() {
                fold_into(part, scratch);
                if scratch.chars().count() >= MIN_TERM_CHARS && scratch.len() <= MAX_TERM_BYTES {
                    sink(scratch);
                }
            }
        }
    }
}

/// One body's token count and the term frequency of each query term, in the
/// terms' order: the fused form, no per-token allocation, no dictionary.
pub fn count_terms(content: &str, terms: &[&str], chars: &mut Vec<char>, scratch: &mut String) -> (u32, Vec<u32>) {
    let mut total = 0u32;
    let mut tfs = vec![0u32; terms.len()];
    for_each_term(content, chars, scratch, |term| {
        total += 1;
        for (position, query) in terms.iter().enumerate() {
            if term == *query {
                tfs[position] += 1;
            }
        }
    });
    (total, tfs)
}

/// The dictionary form: the fused tokenizer feeding a `HashMap<String, u32>`
/// of every distinct token, then the query terms looked up. This is what a
/// Rust `Counter(tokens)` costs.
pub fn count_terms_dictionary(content: &str, terms: &[&str], chars: &mut Vec<char>, scratch: &mut String) -> (u32, Vec<u32>) {
    let mut total = 0u32;
    let mut counts: HashMap<String, u32> = HashMap::new();
    for_each_term(content, chars, scratch, |term| {
        total += 1;
        match counts.get_mut(term) {
            Some(count) => *count += 1,
            None => {
                counts.insert(term.to_owned(), 1);
            }
        }
    });
    let tfs = terms.iter().map(|query| counts.get(*query).copied().unwrap_or(0)).collect();
    (total, tfs)
}

/// A headroom probe, not the proposal: for an all-ASCII body, the same
/// rules over bytes with no `Vec<char>`, no fold buffer and no allocation
/// per term; a body with any non-ASCII byte takes the generic path. The
/// query terms must already be folded, as the verb's are.
pub fn count_terms_ascii(content: &str, terms: &[&str], chars: &mut Vec<char>, scratch: &mut String) -> (u32, Vec<u32>) {
    if !content.is_ascii() {
        return count_terms(content, terms, chars, scratch);
    }
    let bytes = content.as_bytes();
    let mut total = 0u32;
    let mut tfs = vec![0u32; terms.len()];
    let mut parts: Vec<&[u8]> = Vec::new();
    let emit = |piece: &[u8], total: &mut u32, tfs: &mut Vec<u32>| {
        if piece.len() >= MIN_TERM_CHARS && piece.len() <= MAX_TERM_BYTES {
            *total += 1;
            for (position, query) in terms.iter().enumerate() {
                if piece.eq_ignore_ascii_case(query.as_bytes()) {
                    tfs[position] += 1;
                }
            }
        }
    };
    let mut i = 0;
    while i < bytes.len() {
        let b = bytes[i];
        if !(b.is_ascii_alphanumeric() || b == b'_') {
            i += 1;
            continue;
        }
        let start = i;
        while i < bytes.len() && (bytes[i].is_ascii_alphanumeric() || bytes[i] == b'_') {
            i += 1;
        }
        let run = &bytes[start..i];
        parts.clear();
        for piece in run.split(|&c| c == b'_') {
            if piece.is_empty() {
                continue;
            }
            if piece[0].is_ascii_digit() {
                parts.push(piece);
                continue;
            }
            let mut from = 0;
            for index in 1..piece.len() {
                let previous = piece[index - 1];
                let boundary = previous.is_ascii_lowercase()
                    || previous.is_ascii_digit()
                    || (previous.is_ascii_uppercase() && index + 1 < piece.len() && piece[index + 1].is_ascii_lowercase());
                if piece[index].is_ascii_uppercase() && boundary {
                    parts.push(&piece[from..index]);
                    from = index;
                }
            }
            parts.push(&piece[from..]);
        }
        emit(run, &mut total, &mut tfs);
        if parts.len() > 1 {
            for part in parts.iter() {
                emit(part, &mut total, &mut tfs);
            }
        }
    }
    (total, tfs)
}

/// The batch shape the overlay wants: per query term, the `(doc_id, tf, dl)`
/// postings in doc order, plus the summed document length. `docs` must be
/// in increasing doc-id order, as `_overlay` sorts them.
pub fn overlay_postings(docs: &[(i64, &str)], terms: &[&str]) -> (Vec<Vec<(i64, u32, u32)>>, u64) {
    let mut per_term: Vec<Vec<(i64, u32, u32)>> = (0..terms.len()).map(|_| Vec::new()).collect();
    let mut total_dl = 0u64;
    let mut chars = Vec::new();
    let mut scratch = String::new();
    for &(doc_id, content) in docs {
        let (dl, tfs) = count_terms(content, terms, &mut chars, &mut scratch);
        total_dl += u64::from(dl);
        for (position, tf) in tfs.into_iter().enumerate() {
            if tf > 0 {
                per_term[position].push((doc_id, tf, dl));
            }
        }
    }
    (per_term, total_dl)
}
