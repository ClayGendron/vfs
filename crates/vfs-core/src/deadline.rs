//! The deadline every bounded kernel takes, the cadence a sequential loop
//! reads the clock by, and the one parallel batch skeleton.
//!
//! A host hands a kernel a budget in seconds. [`Deadline::after`] turns it
//! into an absolute instant once, at the call's entry, and the kernel asks
//! only [`Deadline::past`] from then on. The conversion is checked: no
//! budget is no deadline, a negative or NaN budget is a zero budget, and a
//! budget past what an instant can hold is no deadline, so no budget a
//! host can send panics.
//!
//! [`par_batch`] spreads a batch's items across threads and reads the
//! deadline before each one: an item is a whole body or a whole row, so
//! the clock is read per item and not every [`CHECK_EVERY`]th. A
//! sequential loop over small items reads it every [`CHECK_EVERY`]th.

use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

use rayon::prelude::*;

/// Items a sequential loop takes between two reads of the clock.
pub const CHECK_EVERY: usize = 64;

/// An absolute instant a kernel stops at, or none.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Deadline(Option<Instant>);

impl Deadline {
    /// The deadline *budget* seconds from now.
    ///
    /// No budget is no deadline; a negative or NaN budget is a zero budget;
    /// a budget past what an instant can hold is no deadline.
    pub fn after(budget: Option<f64>) -> Self {
        let Some(seconds) = budget else {
            return Self::never();
        };
        let span = Duration::try_from_secs_f64(seconds.max(0.0)).ok();
        Self(span.and_then(|span| Instant::now().checked_add(span)))
    }

    /// The deadline at *instant*.
    pub fn at(instant: Instant) -> Self {
        Self(Some(instant))
    }

    /// No deadline: it is never past.
    pub fn never() -> Self {
        Self(None)
    }

    /// Whether the instant has passed; no deadline never passes.
    pub fn past(self) -> bool {
        self.0.is_some_and(|at| {
            #[cfg(test)]
            CLOCK_READS.with(|reads| reads.set(reads.get() + 1));
            Instant::now() > at
        })
    }
}

#[cfg(test)]
thread_local! {
    /// Clock reads the deadlines on this thread have made; compiled into test builds alone.
    static CLOCK_READS: std::cell::Cell<usize> = const { std::cell::Cell::new(0) };
}

/// The clock reads this thread's deadlines have made so far: a cadence test counts by the difference.
#[cfg(test)]
pub(crate) fn clock_reads() -> usize {
    CLOCK_READS.with(std::cell::Cell::get)
}

/// Batch results plus whether every item finished before the deadline.
#[derive(Debug)]
pub struct BatchOutcome<T> {
    pub results: Vec<T>,
    pub completed: bool,
}

/// Every item's result across threads, in item order.
///
/// The deadline is read before each item. An item started after it answers
/// `skipped()` and `run` is not called for it; otherwise `run(item)`
/// answers the result and whether the item finished. An item skipped or
/// unfinished flips `completed` off.
pub fn par_batch<I: Sync, T: Send>(
    items: &[I],
    deadline: Deadline,
    skipped: impl Fn() -> T + Sync,
    run: impl Fn(&I) -> (T, bool) + Sync,
) -> BatchOutcome<T> {
    let completed = AtomicBool::new(true);
    let results = items
        .par_iter()
        .map(|item| {
            let (result, finished) = if deadline.past() {
                (skipped(), false)
            } else {
                run(item)
            };
            if !finished {
                completed.store(false, Ordering::Relaxed);
            }
            result
        })
        .collect();
    BatchOutcome {
        results,
        completed: completed.load(Ordering::Relaxed),
    }
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::AtomicUsize;

    use super::*;

    fn already_past() -> Deadline {
        Deadline::at(Instant::now() - Duration::from_secs(1))
    }

    #[test]
    fn a_deadline_is_past_only_after_its_instant() {
        assert!(already_past().past());
        assert!(!Deadline::at(Instant::now() + Duration::from_secs(60)).past());
        assert!(!Deadline::never().past());
    }

    #[test]
    fn a_deadline_reads_the_clock_once_per_question_and_never_without_an_instant() {
        let before = clock_reads();
        assert!(!Deadline::never().past());
        assert_eq!(clock_reads() - before, 0);
        assert!(already_past().past());
        assert!(already_past().past());
        assert_eq!(clock_reads() - before, 2);
    }

    #[test]
    fn after_no_budget_is_no_deadline() {
        assert_eq!(Deadline::after(None), Deadline::never());
    }

    #[test]
    fn after_a_huge_budget_is_no_deadline() {
        for budget in [1e300, f64::INFINITY] {
            let deadline = Deadline::after(Some(budget));
            assert_eq!(deadline, Deadline::never(), "budget {budget}");
            assert!(!deadline.past());
        }
    }

    #[test]
    fn after_a_negative_or_nan_budget_is_a_zero_budget() {
        for budget in [-5.0, f64::NEG_INFINITY, f64::NAN, 0.0] {
            assert_ne!(
                Deadline::after(Some(budget)),
                Deadline::never(),
                "budget {budget}"
            );
        }
    }

    #[test]
    fn par_batch_runs_every_item_before_the_deadline() {
        let items: Vec<u64> = (0..100).collect();
        let outcome = par_batch(&items, Deadline::never(), || 0, |item| (item * 2, true));
        assert_eq!(
            outcome.results,
            items.iter().map(|item| item * 2).collect::<Vec<_>>()
        );
        assert!(outcome.completed);
        let empty = par_batch(&[] as &[u64], already_past(), || 0, |item| (*item, true));
        assert!(empty.results.is_empty());
        assert!(empty.completed);
    }

    #[test]
    fn par_batch_skips_items_past_the_deadline() {
        let items: Vec<u64> = (0..100).collect();
        let ran = AtomicUsize::new(0);
        let outcome = par_batch(
            &items,
            already_past(),
            || u64::MAX,
            |item| {
                ran.fetch_add(1, Ordering::Relaxed);
                (*item, true)
            },
        );
        assert_eq!(outcome.results, vec![u64::MAX; 100]);
        assert!(!outcome.completed);
        assert_eq!(ran.load(Ordering::Relaxed), 0);
    }

    #[test]
    fn par_batch_flips_completed_for_an_unfinished_item() {
        let items: Vec<u64> = (0..100).collect();
        let outcome = par_batch(
            &items,
            Deadline::never(),
            || u64::MAX,
            |item| (*item, *item != 37),
        );
        assert_eq!(outcome.results, items);
        assert!(!outcome.completed);
    }

    #[test]
    fn par_batch_is_thread_count_invariant() {
        let items: Vec<u64> = (0..1_000).collect();
        let sequential: Vec<u64> = items.iter().map(|item| item * item).collect();
        for threads in [1, 8] {
            let pool = rayon::ThreadPoolBuilder::new()
                .num_threads(threads)
                .build()
                .expect("pool builds");
            let outcome = pool
                .install(|| par_batch(&items, Deadline::never(), || 0, |item| (item * item, true)));
            assert_eq!(outcome.results, sequential);
            assert!(outcome.completed);
        }
    }
}
