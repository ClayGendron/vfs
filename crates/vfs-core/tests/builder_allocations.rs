//! Allocation pins for the lexical builder: how many fresh blocks `add_doc`
//! asks the allocator for, counted on a fixed corpus. Work is counted, never
//! timed.
//!
//! This binary installs an allocator that forwards to the system one and
//! counts a fresh allocation only on a thread whose `ARMED` flag is set, so
//! the harness's thread and the other test's set-up count nothing. Growing a
//! block in place (`realloc`) is not a fresh allocation and is not counted:
//! the posting streams and the builder's reused buffers grow that way.
//!
//! The corpus is a Zipf draw: `CHUNKS` chunks of about `CHUNK_BYTES` bytes,
//! each word drawn from a list of `WORDS` with the probability of a word
//! falling as one over its rank, from a fixed seed. It is generated here, so
//! the counts are the same on every run and every machine.

use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Mutex, PoisonError};

use vfs_core::LexicalAccumulator;

const SEED: u64 = 7;
const WORDS: usize = 2_000;
const CHUNKS: usize = 200;
const CHUNK_BYTES: usize = 1_500;

/// What a term costs the first time the corpus sees it: its one owned copy
/// and the first push into each of its three posting streams.
const FIRST_SIGHT_ALLOCATIONS: u64 = 4;

/// The allowance per chunk beyond first sight: the scanner's parts vector,
/// one a chunk, and a term's block offsets at its first seal. A string per
/// token would cost about 215 a chunk on this corpus.
const ALLOWANCE_PER_CHUNK: u64 = 2;

// ---------------------------------------------------------------------------
// The counting allocator
// ---------------------------------------------------------------------------

struct CountingAllocator;

#[global_allocator]
static ALLOCATOR: CountingAllocator = CountingAllocator;

static ALLOCATIONS: AtomicU64 = AtomicU64::new(0);

thread_local! {
    static ARMED: Cell<bool> = const { Cell::new(false) };
}

// SAFETY: every request is forwarded to `System` unchanged, so its contract
// holds as given; the count is a side effect that allocates nothing.
unsafe impl GlobalAlloc for CountingAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        if ARMED.get() {
            ALLOCATIONS.fetch_add(1, Ordering::Relaxed);
        }
        unsafe { System.alloc(layout) }
    }

    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) }
    }

    unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, new_size: usize) -> *mut u8 {
        unsafe { System.realloc(ptr, layout, new_size) }
    }
}

/// Held for a measured region: the counter is the process's, so two armed
/// threads at once would read each other's allocations.
static MEASURING: Mutex<()> = Mutex::new(());

/// Arms this thread's flag for as long as it lives, and disarms it on drop,
/// so a panic inside a measured region leaves nothing counting.
struct Armed;

impl Armed {
    fn new() -> Self {
        ARMED.set(true);
        Self
    }
}

impl Drop for Armed {
    fn drop(&mut self) {
        ARMED.set(false);
    }
}

/// The fresh allocations `work` makes on this thread.
fn allocations_during(work: impl FnOnce()) -> u64 {
    let _one_region_at_a_time = MEASURING.lock().unwrap_or_else(PoisonError::into_inner);
    let before = ALLOCATIONS.load(Ordering::Relaxed);
    let armed = Armed::new();
    work();
    drop(armed);
    ALLOCATIONS.load(Ordering::Relaxed) - before
}

// ---------------------------------------------------------------------------
// The corpus
// ---------------------------------------------------------------------------

/// The SplitMix64 generator: a fixed sequence for a fixed seed.
struct SplitMix64(u64);

impl SplitMix64 {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut mixed = self.0;
        mixed = (mixed ^ (mixed >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        mixed = (mixed ^ (mixed >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        mixed ^ (mixed >> 31)
    }

    /// A draw in `[0, 1)` from the top 53 bits, every one of them exact in an `f64`.
    fn unit(&mut self) -> f64 {
        (self.next() >> 11) as f64 / (1u64 << 53) as f64
    }
}

/// `WORDS` distinct words of three consonant-vowel syllables. Each is one
/// lowercase run, so the tokenizer emits it whole and emits nothing else.
fn word_list() -> Vec<String> {
    const CONSONANTS: &[u8] = b"bcdfghjklmnprstvwxyz";
    const VOWELS: &[u8] = b"aeiou";
    let syllables = CONSONANTS.len() * VOWELS.len();
    (0..WORDS)
        .map(|index| {
            let mut word = String::new();
            let mut rest = index;
            for _ in 0..3 {
                let syllable = rest % syllables;
                word.push(CONSONANTS[syllable / VOWELS.len()] as char);
                word.push(VOWELS[syllable % VOWELS.len()] as char);
                rest /= syllables;
            }
            word
        })
        .collect()
}

/// The fixture: each chunk is words drawn by rank, space-separated, until
/// the chunk reaches `CHUNK_BYTES`.
fn zipf_chunks() -> Vec<String> {
    let words = word_list();
    let mut reach = Vec::with_capacity(WORDS);
    let mut total = 0.0f64;
    for rank in 1..=WORDS {
        total += 1.0 / rank as f64;
        reach.push(total);
    }
    let mut draws = SplitMix64(SEED);
    (0..CHUNKS)
        .map(|_| {
            let mut chunk = String::new();
            while chunk.len() < CHUNK_BYTES {
                let at = draws.unit() * total;
                let drawn = reach.partition_point(|&upto| upto <= at).min(WORDS - 1);
                chunk.push_str(&words[drawn]);
                chunk.push(' ');
            }
            chunk
        })
        .collect()
}

/// Feed every chunk in order under the doc ids that follow `after`.
fn feed(builder: &mut LexicalAccumulator, chunks: &[String], after: i64) {
    for (doc_id, chunk) in (after + 1..).zip(chunks) {
        builder.add_doc(doc_id, chunk).expect("doc ids climb");
    }
}

// ---------------------------------------------------------------------------
// The pins
// ---------------------------------------------------------------------------

/// The first pass pays for the vocabulary and little else. Guards against a
/// term's string being built per occurrence, against a fifth allocation for
/// every new term, and against a reused buffer being rebuilt per document.
/// A count of zero would mean the allocator was not counting.
#[test]
fn the_first_pass_pays_four_allocations_a_distinct_term() {
    let chunks = zipf_chunks();
    let mut builder = LexicalAccumulator::new();
    let allocations = allocations_during(|| feed(&mut builder, &chunks, 0));
    let distinct = builder.distinct_terms() as u64;
    let bound = FIRST_SIGHT_ALLOCATIONS * distinct + ALLOWANCE_PER_CHUNK * CHUNKS as u64;
    assert!(
        (1..=bound).contains(&allocations),
        "{allocations} allocations for {distinct} distinct terms over {CHUNKS} chunks; the bound is {bound}"
    );
}

/// The steady state: every term is already interned, so a chunk's words
/// cost no string. Guards against a clone made before the interner lookup,
/// which leaves every row unchanged and puts this pass near 215 a chunk,
/// and against a reused buffer being rebuilt per document, one more a chunk.
#[test]
fn a_second_pass_interns_nothing_and_allocates_under_two_a_chunk() {
    let chunks = zipf_chunks();
    let mut builder = LexicalAccumulator::new();
    feed(&mut builder, &chunks, 0);
    let interned = builder.distinct_terms();
    let allocations = allocations_during(|| feed(&mut builder, &chunks, CHUNKS as i64));
    assert_eq!(builder.distinct_terms(), interned);
    let bound = ALLOWANCE_PER_CHUNK * CHUNKS as u64;
    assert!(allocations < bound, "{allocations} allocations over {CHUNKS} already-seen chunks; the bound is {bound}");
}
