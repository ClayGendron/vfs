//! The hub every part of a running line shares: the requests it has asked
//! and the replies it has been given, its pipes, its output, its counted
//! bytes and its slice. A future here never wakes anything: the machine
//! polls until nothing moves, so a pending future is simply polled again.

use std::cell::RefCell;
use std::collections::{BTreeMap, VecDeque};
use std::future::Future;
use std::pin::Pin;
use std::rc::Rc;
use std::task::{Context, Poll};

use super::{Fatal, Reply, Request, RequestKey};

/// Bytes a pipe holds before its writer waits.
pub const PIPE_CAPACITY: usize = 64 * 1024;

/// Which stream of the line's own output a chunk belongs to.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Stream {
    Stdout,
    Stderr,
}

pub struct Hub {
    pub requests: Vec<(RequestKey, Request)>,
    pub outstanding: BTreeMap<RequestKey, ()>,
    pub replies: BTreeMap<RequestKey, Reply>,
    pub output: Vec<(Stream, Vec<u8>)>,
    pub progress: bool,
    pub memory_used: usize,
    pub memory_limit: usize,
    pub ticks: u64,
    pub slice_end: u64,
    pub slice: u64,
    pub yielded: bool,
    pub loop_iterations: u64,
    pub loop_limit: u64,
    pub cancelled: bool,
    pub fatal: Option<Fatal>,
    /// The files open for writing, so a read of one writes its bytes first.
    pub writers: Vec<std::rc::Weak<RefCell<super::files::FileWriter>>>,
    /// Each job's exit status by its pid, once it has one.
    pub job_status: BTreeMap<u32, Option<i32>>,
    /// The status of the last command substitution, for a command of assignments alone.
    pub last_sub_status: Option<i32>,
    /// How deep in command substitutions the walk is, for `set -x`.
    pub sub_depth: u32,
}

pub type HubRef = Rc<RefCell<Hub>>;

impl Hub {
    pub fn new(memory_limit: usize, slice: u64, loop_limit: u64) -> Hub {
        Hub {
            requests: Vec::new(),
            outstanding: BTreeMap::new(),
            replies: BTreeMap::new(),
            output: Vec::new(),
            progress: false,
            memory_used: 0,
            memory_limit,
            ticks: 0,
            slice_end: slice,
            slice,
            yielded: false,
            loop_iterations: 0,
            loop_limit,
            cancelled: false,
            fatal: None,
            writers: Vec::new(),
            job_status: BTreeMap::new(),
            last_sub_status: None,
            sub_depth: 0,
        }
    }

    /// Count `bytes` more held, or refuse when the budget would be passed.
    pub fn charge(&mut self, bytes: usize) -> Result<(), Fatal> {
        let used = self.memory_used.saturating_add(bytes);
        if used > self.memory_limit {
            return Err(Fatal::Budget("memory", self.memory_limit as u64));
        }
        self.memory_used = used;
        Ok(())
    }

    pub fn release(&mut self, bytes: usize) {
        self.memory_used = self.memory_used.saturating_sub(bytes);
    }

    /// Whether `bytes` more would fit, without counting them.
    pub fn fits(&self, bytes: usize) -> Result<(), Fatal> {
        if self.memory_used.saturating_add(bytes) > self.memory_limit {
            return Err(Fatal::Budget("memory", self.memory_limit as u64));
        }
        Ok(())
    }

    pub fn emit(&mut self, stream: Stream, bytes: &[u8]) -> Result<(), Fatal> {
        if bytes.is_empty() {
            return Ok(());
        }
        self.charge(bytes.len())?;
        self.progress = true;
        if let Some((last, buffer)) = self.output.last_mut()
            && *last == stream
        {
            buffer.extend_from_slice(bytes);
            return Ok(());
        }
        self.output.push((stream, bytes.to_vec()));
        Ok(())
    }

    pub fn tick(&mut self) {
        self.ticks = self.ticks.saturating_add(1);
    }

    pub fn count_iteration(&mut self) -> Result<(), Fatal> {
        self.loop_iterations = self.loop_iterations.saturating_add(1);
        if self.loop_iterations > self.loop_limit {
            return Err(Fatal::Budget("loop_iterations", self.loop_limit));
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Host calls and the slice
// ---------------------------------------------------------------------------

/// Ask the host for something, and wait for its reply.
pub fn host_call(hub: &HubRef, key: RequestKey, request: Request) -> HostCall {
    HostCall {
        hub: Rc::clone(hub),
        key,
        request: Some(request),
    }
}

pub struct HostCall {
    hub: HubRef,
    key: RequestKey,
    request: Option<Request>,
}

impl Future for HostCall {
    type Output = Result<Reply, Fatal>;

    fn poll(self: Pin<&mut Self>, _cx: &mut Context<'_>) -> Poll<Self::Output> {
        let this = self.get_mut();
        let mut hub = this.hub.borrow_mut();
        if let Some(fatal) = hub.fatal.clone() {
            return Poll::Ready(Err(fatal));
        }
        if let Some(request) = this.request.take() {
            hub.outstanding.insert(this.key.clone(), ());
            hub.requests.push((this.key.clone(), request));
            hub.progress = true;
            return Poll::Pending;
        }
        match hub.replies.remove(&this.key) {
            Some(reply) => {
                hub.outstanding.remove(&this.key);
                hub.progress = true;
                Poll::Ready(Ok(reply))
            }
            None => Poll::Pending,
        }
    }
}

/// A point where a long run hands control back when its slice is spent.
pub fn checkpoint(hub: &HubRef) -> Checkpoint {
    Checkpoint {
        hub: Rc::clone(hub),
        waited: false,
    }
}

pub struct Checkpoint {
    hub: HubRef,
    waited: bool,
}

impl Future for Checkpoint {
    type Output = Result<(), Fatal>;

    fn poll(self: Pin<&mut Self>, _cx: &mut Context<'_>) -> Poll<Self::Output> {
        let this = self.get_mut();
        let mut hub = this.hub.borrow_mut();
        if let Some(fatal) = hub.fatal.clone() {
            return Poll::Ready(Err(fatal));
        }
        if hub.cancelled {
            return Poll::Ready(Err(Fatal::Cancelled));
        }
        hub.tick();
        if this.waited || hub.ticks < hub.slice_end {
            return Poll::Ready(Ok(()));
        }
        this.waited = true;
        hub.yielded = true;
        Poll::Pending
    }
}

// ---------------------------------------------------------------------------
// Pipes
// ---------------------------------------------------------------------------

pub struct PipeState {
    buffer: VecDeque<u8>,
    writers: usize,
    readers: usize,
    hub: HubRef,
}

/// A pipe's write end. Clones count as writers; the last one dropped ends the stream.
pub struct WriteEnd {
    pipe: Rc<RefCell<PipeState>>,
}

/// A pipe's read end. When the last one is dropped, writes fail as a broken pipe.
pub struct ReadEnd {
    pipe: Rc<RefCell<PipeState>>,
}

pub fn pipe(hub: &HubRef) -> (ReadEnd, WriteEnd) {
    let pipe = Rc::new(RefCell::new(PipeState {
        buffer: VecDeque::new(),
        writers: 1,
        readers: 1,
        hub: Rc::clone(hub),
    }));
    (
        ReadEnd {
            pipe: Rc::clone(&pipe),
        },
        WriteEnd { pipe },
    )
}

impl Clone for WriteEnd {
    fn clone(&self) -> Self {
        let mut state = self.pipe.borrow_mut();
        state.writers = state.writers.saturating_add(1);
        WriteEnd {
            pipe: Rc::clone(&self.pipe),
        }
    }
}

impl Drop for WriteEnd {
    fn drop(&mut self) {
        if let Ok(mut state) = self.pipe.try_borrow_mut() {
            state.writers = state.writers.saturating_sub(1);
            if let Ok(mut hub) = state.hub.try_borrow_mut() {
                hub.progress = true;
            }
        }
    }
}

impl Clone for ReadEnd {
    fn clone(&self) -> Self {
        let mut state = self.pipe.borrow_mut();
        state.readers = state.readers.saturating_add(1);
        ReadEnd {
            pipe: Rc::clone(&self.pipe),
        }
    }
}

impl Drop for ReadEnd {
    fn drop(&mut self) {
        if let Ok(mut state) = self.pipe.try_borrow_mut() {
            state.readers = state.readers.saturating_sub(1);
            if state.readers == 0 {
                let held = state.buffer.len();
                state.buffer.clear();
                if let Ok(mut hub) = state.hub.try_borrow_mut() {
                    hub.release(held);
                    hub.progress = true;
                }
            }
        }
    }
}

/// What a write to a pipe came to.
pub enum Written {
    All,
    Broken,
}

impl WriteEnd {
    /// Write all of `bytes`, waiting while the pipe is full.
    pub async fn write(&self, bytes: &[u8]) -> Result<Written, Fatal> {
        let mut rest = bytes;
        while !rest.is_empty() {
            let wrote = PipeWrite {
                end: self,
                bytes: rest,
            }
            .await?;
            match wrote {
                None => return Ok(Written::Broken),
                Some(count) => rest = rest.get(count..).unwrap_or_default(),
            }
        }
        Ok(Written::All)
    }
}

struct PipeWrite<'a> {
    end: &'a WriteEnd,
    bytes: &'a [u8],
}

impl Future for PipeWrite<'_> {
    type Output = Result<Option<usize>, Fatal>;

    fn poll(self: Pin<&mut Self>, _cx: &mut Context<'_>) -> Poll<Self::Output> {
        let mut state = self.end.pipe.borrow_mut();
        if state.readers == 0 {
            return Poll::Ready(Ok(None));
        }
        let room = PIPE_CAPACITY.saturating_sub(state.buffer.len());
        if room == 0 {
            return Poll::Pending;
        }
        let count = room.min(self.bytes.len());
        let chunk = self.bytes.get(..count).unwrap_or_default();
        let hub = Rc::clone(&state.hub);
        let mut hub = hub.borrow_mut();
        if let Err(fatal) = hub.charge(count) {
            return Poll::Ready(Err(fatal));
        }
        hub.progress = true;
        state.buffer.extend(chunk.iter().copied());
        Poll::Ready(Ok(Some(count)))
    }
}

impl ReadEnd {
    /// Up to `max` bytes, waiting for some; empty at the end of the stream.
    pub fn read(&self, max: usize) -> PipeRead<'_> {
        PipeRead {
            end: self,
            max,
            until: None,
        }
    }

    /// Bytes up to and including `delimiter`, or to the end of the stream.
    pub fn read_until(&self, delimiter: u8, max: usize) -> PipeRead<'_> {
        PipeRead {
            end: self,
            max,
            until: Some(delimiter),
        }
    }
}

pub struct PipeRead<'a> {
    end: &'a ReadEnd,
    max: usize,
    until: Option<u8>,
}

impl Future for PipeRead<'_> {
    type Output = Vec<u8>;

    fn poll(self: Pin<&mut Self>, _cx: &mut Context<'_>) -> Poll<Vec<u8>> {
        let mut state = self.end.pipe.borrow_mut();
        if state.buffer.is_empty() {
            if state.writers == 0 {
                return Poll::Ready(Vec::new());
            }
            return Poll::Pending;
        }
        let count = match self.until {
            Some(delimiter) => match state.buffer.iter().position(|byte| *byte == delimiter) {
                Some(at) => at.saturating_add(1).min(self.max),
                None if state.writers == 0 || state.buffer.len() >= self.max => {
                    state.buffer.len().min(self.max)
                }
                None => return Poll::Pending,
            },
            None => state.buffer.len().min(self.max),
        };
        let taken: Vec<u8> = state.buffer.drain(..count).collect();
        let hub = Rc::clone(&state.hub);
        let mut hub = hub.borrow_mut();
        hub.release(taken.len());
        hub.progress = true;
        Poll::Ready(taken)
    }
}

// ---------------------------------------------------------------------------
// Joining futures
// ---------------------------------------------------------------------------

pub type Task<'a, T> = Pin<Box<dyn Future<Output = T> + 'a>>;

/// Poll every future in order until all are done; results in the same order.
pub struct JoinAll<'a, T> {
    tasks: Vec<Option<Task<'a, T>>>,
    results: Vec<Option<T>>,
}

pub fn join_all<T>(tasks: Vec<Task<'_, T>>) -> JoinAll<'_, T> {
    let results = tasks.iter().map(|_| None).collect();
    JoinAll {
        tasks: tasks.into_iter().map(Some).collect(),
        results,
    }
}

// The results are never pinned: only the boxed tasks are polled in place.
impl<T> Unpin for JoinAll<'_, T> {}

impl<T> Future for JoinAll<'_, T> {
    type Output = Vec<T>;

    fn poll(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Vec<T>> {
        let this = self.get_mut();
        let mut pending = false;
        for (slot, result) in this.tasks.iter_mut().zip(this.results.iter_mut()) {
            if let Some(task) = slot {
                match task.as_mut().poll(cx) {
                    Poll::Ready(value) => {
                        *result = Some(value);
                        *slot = None;
                    }
                    Poll::Pending => pending = true,
                }
            }
        }
        if pending {
            return Poll::Pending;
        }
        Poll::Ready(this.results.iter_mut().filter_map(Option::take).collect())
    }
}
