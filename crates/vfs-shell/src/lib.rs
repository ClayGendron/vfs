//! A bash interpreter that does no IO.
//!
//! The crate has three parts that point one way. [`syntax`] turns text into
//! a tree and knows nothing of execution. [`machine`] runs a tree and knows
//! nothing of any host: every effect it needs is a request it returns from
//! `step`, which its host answers or refuses on the next call. A host drives
//! the machine; [`host::MemoryHost`] is the reference host, a tree of files
//! held in memory.

pub mod syntax;
