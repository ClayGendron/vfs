//! The vfs engine: byte-trigram extraction, posting-list building, grep
//! match verification, structure-aware chunk spans, and the lexical (BM25)
//! tokenizer, block-posting builder and scorer.
//!
//! This crate is the throughput core behind the vfs gram index and the
//! semantic chunker. It holds no policy: inputs are UTF-8 bytes prepared by
//! the host language (pre-folded and newline-normalized on the gram paths),
//! outputs are exact wire shapes the host defines — posting blobs (a varint
//! count header followed by LEB128 varints of strictly positive doc-id
//! deltas) and chunk byte-spans with line ranges. Every host binding —
//! Python today, JavaScript and native Rust surfaces later — talks to these
//! types; the `python` cargo feature adds the pyo3 module and nothing else.

mod chunk;
mod grams;
mod lexical;
mod lexical_tables;
mod postings;
mod verify;

#[cfg(feature = "python")]
mod python;

pub use chunk::{GRAMMAR_NAMES, SpanRow, split_batch};
pub use grams::{GRAM_SIZE, GramExtractor};
pub use lexical::{
    BLOCK_SIZE, BM25_B, BM25_K1, BlockRow, DrainedLexical, LexicalAccumulator, LexicalError, PYTHON_VERSION,
    ScoreBlock, SummaryRow, UNICODE_VERSION, casefolds, char_classes, score, tokenize,
};
pub use postings::{AddDocError, DrainedPostings, PostingRow, PostingsAccumulator};
pub use verify::{BatchOutcome, Hit, Matcher, PatternError, count_batch, hits_batch};
