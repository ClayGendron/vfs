//! A counting global allocator: every `alloc` and `realloc` the bench's
//! thread issues is counted, so a variant's allocations per body are a
//! fact and not a guess. Single-threaded bench; relaxed atomics suffice.

use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::atomic::{AtomicU64, Ordering};

pub struct Counting;

pub static ALLOCS: AtomicU64 = AtomicU64::new(0);
pub static REALLOCS: AtomicU64 = AtomicU64::new(0);
pub static BYTES: AtomicU64 = AtomicU64::new(0);

unsafe impl GlobalAlloc for Counting {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        ALLOCS.fetch_add(1, Ordering::Relaxed);
        BYTES.fetch_add(layout.size() as u64, Ordering::Relaxed);
        unsafe { System.alloc(layout) }
    }

    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) }
    }

    unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, new_size: usize) -> *mut u8 {
        REALLOCS.fetch_add(1, Ordering::Relaxed);
        BYTES.fetch_add(new_size as u64, Ordering::Relaxed);
        unsafe { System.realloc(ptr, layout, new_size) }
    }
}

#[derive(Clone, Copy, Debug, Default)]
pub struct Snapshot {
    pub allocs: u64,
    pub reallocs: u64,
    pub bytes: u64,
}

pub fn snapshot() -> Snapshot {
    Snapshot {
        allocs: ALLOCS.load(Ordering::Relaxed),
        reallocs: REALLOCS.load(Ordering::Relaxed),
        bytes: BYTES.load(Ordering::Relaxed),
    }
}

pub fn delta(before: Snapshot, after: Snapshot) -> Snapshot {
    Snapshot {
        allocs: after.allocs - before.allocs,
        reallocs: after.reallocs - before.reallocs,
        bytes: after.bytes - before.bytes,
    }
}
