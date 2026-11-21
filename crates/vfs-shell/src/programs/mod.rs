//! The programs the crate ships: pure text transforms over chunks, and file
//! programs written against the machine's own requests, so one
//! implementation serves every host that mounts them.

use crate::machine::{Ctx, Flow, Shell};

/// Every program name the library implements.
pub const NAMES: &[&str] = &[];

/// Run a library program, or `None` when the library has no such name.
pub async fn run(
    _ctx: &Ctx<'_>,
    _sh: &mut Shell,
    _name: &str,
    _words: Vec<String>,
) -> Result<Option<i32>, Flow> {
    Ok(None)
}
