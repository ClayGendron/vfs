//! Hosts. [`MemoryHost`] is the reference host: a tree of files in memory,
//! with every library program mounted. It is what the conformance corpus
//! runs against with no other host and no Python.

mod memory;

pub use memory::{MemoryHost, Outcome};
