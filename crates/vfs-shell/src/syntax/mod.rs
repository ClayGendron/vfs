//! Text to a tree. Nothing here knows how a tree runs.

pub mod arith;
pub mod ast;
mod parser;

pub use parser::{REFUSED, is_name, line_starts, parse};

/// The budgets a parse runs under. A host may set any of them.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ParseLimits {
    pub source_bytes: usize,
    pub tokens: u32,
    pub depth: u32,
    pub pipeline_stages: u32,
}

/// One mebibyte of source.
pub const SOURCE_BYTES: usize = 1 << 20;
pub const TOKENS: u32 = 100_000;
pub const DEPTH: u32 = 200;
pub const PIPELINE_STAGES: u32 = 64;

impl Default for ParseLimits {
    fn default() -> Self {
        ParseLimits {
            source_bytes: SOURCE_BYTES,
            tokens: TOKENS,
            depth: DEPTH,
            pipeline_stages: PIPELINE_STAGES,
        }
    }
}

/// Why a line did not parse.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ParseError {
    /// Malformed text: where it went wrong and what was expected there.
    Syntax(Position, String),
    /// A construct this shell does not run, named with its reason.
    Refused(Position, &'static str, &'static str),
    /// A parse budget was spent: which one, and its limit.
    Budget(&'static str, u64),
}

/// A point in the source.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub struct Position {
    pub line: u32,
    pub column: u32,
    pub offset: u32,
}

impl ParseError {
    /// The message bash would print for it, without the `bash: ` prefix.
    pub fn message(&self) -> String {
        match self {
            ParseError::Syntax(at, what) => format!("line {}: {}", at.line, what),
            ParseError::Refused(at, construct, reason) => {
                format!("line {}: {}: refused: {}", at.line, construct, reason)
            }
            ParseError::Budget(which, limit) => format!("{which} budget of {limit} exceeded"),
        }
    }
}
