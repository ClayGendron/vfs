//! GNU `sed`, as a pure function over input already read.

use std::collections::BTreeMap;

/// What a `sed` run produced.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct SedOutput {
    pub stdout: Vec<u8>,
    pub stderr: Vec<u8>,
    pub status: i32,
    /// Files to write whole: `-i` results and `w` targets, by the path as given.
    pub writes: Vec<(String, Vec<u8>)>,
}

/// The files `sed` will read for `args` (operands, `-` for standard input,
/// and the targets of `r` and `R`), or the output of a usage error.
pub fn inputs(args: &[String]) -> Result<Vec<String>, SedOutput> {
    let _ = args;
    Err(SedOutput {
        stderr: b"sed: not yet implemented\n".to_vec(),
        status: 1,
        ..SedOutput::default()
    })
}

/// Run `sed` over files already read: each name from [`inputs`] maps to its
/// bytes or the error text a read of it gave.
pub fn run(
    args: &[String],
    stdin: &[u8],
    files: &BTreeMap<String, Result<Vec<u8>, String>>,
) -> SedOutput {
    let _ = (args, stdin, files);
    SedOutput::default()
}
