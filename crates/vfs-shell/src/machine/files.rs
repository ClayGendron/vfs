//! Files over requests. A file opened for reading is read in chunks as it
//! is consumed. A file opened for writing is truncated or created when it is
//! opened, as bash does, and its bytes are held and written in one request
//! when the redirection that opened it ends, or when the held bytes reach a
//! chunk; a read of the same path writes them first, so the line sees its
//! own writes.

use std::cell::RefCell;
use std::rc::{Rc, Weak};

use super::io::HubRef;
use super::{Fatal, HostError, Reply, Request, RequestKey, WriteMode};

/// Bytes read or written in one request.
pub const CHUNK: usize = 64 * 1024;

/// Bytes held whole, read from the front.
pub struct ReadBuffer {
    pub data: Vec<u8>,
    pub pos: usize,
    hub: HubRef,
}

impl ReadBuffer {
    pub fn new(hub: &HubRef, data: Vec<u8>) -> Result<Rc<RefCell<ReadBuffer>>, Fatal> {
        hub.borrow_mut().charge(data.len())?;
        Ok(Rc::new(RefCell::new(ReadBuffer {
            data,
            pos: 0,
            hub: Rc::clone(hub),
        })))
    }

    pub fn rest(&self) -> &[u8] {
        self.data.get(self.pos..).unwrap_or_default()
    }

    pub fn advance(&mut self, count: usize) {
        self.pos = self.pos.saturating_add(count).min(self.data.len());
    }
}

impl Drop for ReadBuffer {
    fn drop(&mut self) {
        if let Ok(mut hub) = self.hub.try_borrow_mut() {
            hub.release(self.data.len());
        }
    }
}

/// A file read in chunks.
pub struct FileReader {
    pub path: String,
    pub offset: u64,
    pub chunk: Vec<u8>,
    pub pos: usize,
    pub eof: bool,
    hub: HubRef,
}

impl FileReader {
    pub fn new(
        hub: &HubRef,
        path: String,
        first: Vec<u8>,
        eof: bool,
    ) -> Result<Rc<RefCell<FileReader>>, Fatal> {
        hub.borrow_mut().charge(first.len())?;
        let offset = first.len() as u64;
        Ok(Rc::new(RefCell::new(FileReader {
            path,
            offset,
            chunk: first,
            pos: 0,
            eof,
            hub: Rc::clone(hub),
        })))
    }

    pub fn rest(&self) -> &[u8] {
        self.chunk.get(self.pos..).unwrap_or_default()
    }

    pub fn advance(&mut self, count: usize) {
        self.pos = self.pos.saturating_add(count).min(self.chunk.len());
    }

    /// Read the next chunk once this one is consumed. Returns false at the end.
    pub async fn refill(
        reader: &Rc<RefCell<FileReader>>,
        hub: &HubRef,
        key: RequestKey,
    ) -> Result<bool, Fatal> {
        let (path, offset) = {
            let this = reader.borrow();
            if this.pos < this.chunk.len() {
                return Ok(true);
            }
            if this.eof {
                return Ok(false);
            }
            (this.path.clone(), this.offset)
        };
        let reply = super::io::host_call(
            hub,
            key,
            Request::Read {
                path,
                offset,
                length: CHUNK as u64,
            },
        )
        .await?;
        let mut this = reader.borrow_mut();
        let (bytes, eof) = match reply {
            Reply::Data { bytes, eof } => (bytes, eof),
            _ => (Vec::new(), true),
        };
        let mut hub = this.hub.borrow_mut();
        hub.release(this.chunk.len());
        hub.charge(bytes.len())?;
        drop(hub);
        this.offset = this.offset.saturating_add(bytes.len() as u64);
        this.eof = eof || bytes.is_empty();
        this.chunk = bytes;
        this.pos = 0;
        Ok(!this.chunk.is_empty())
    }
}

impl Drop for FileReader {
    fn drop(&mut self) {
        if let Ok(mut hub) = self.hub.try_borrow_mut() {
            hub.release(self.chunk.len());
        }
    }
}

/// A file being written: bytes held until the next flush. Nothing is written when it opens: its
/// first flush creates, truncates or appends to the file with the bytes held, in one request.
pub struct FileWriter {
    pub path: String,
    buffer: Vec<u8>,
    /// How the first write treats the file; `None` once it has been written.
    pending: Option<WriteMode>,
    pub error: Option<HostError>,
    hub: HubRef,
}

impl FileWriter {
    /// A writer for `path`, already judged openable, that writes nothing until its first flush.
    pub fn open(hub: &HubRef, path: String, mode: WriteMode) -> Rc<RefCell<FileWriter>> {
        let writer = Rc::new(RefCell::new(FileWriter {
            path,
            buffer: Vec::new(),
            pending: Some(mode),
            error: None,
            hub: Rc::clone(hub),
        }));
        let mut hub = hub.borrow_mut();
        hub.writers.retain(|weak| weak.strong_count() > 0);
        hub.writers.push(Rc::downgrade(&writer));
        writer
    }

    /// Hold `bytes`; true when a chunk is held and should be written.
    pub fn push(&mut self, hub: &HubRef, bytes: &[u8]) -> Result<bool, Fatal> {
        hub.borrow_mut().charge(bytes.len())?;
        self.buffer.extend_from_slice(bytes);
        Ok(self.buffer.len() >= CHUNK)
    }

    /// Whether a flush would write: bytes are held, or the file is not yet created or truncated.
    pub fn is_dirty(&self) -> bool {
        !self.buffer.is_empty() || self.pending.is_some()
    }

    /// Write what is held as one request: the opening mode the first time, appending after.
    pub async fn flush(
        writer: &Rc<RefCell<FileWriter>>,
        hub: &HubRef,
        key: RequestKey,
    ) -> Result<(), Fatal> {
        let (path, data, mode) = {
            let mut this = writer.borrow_mut();
            if !this.is_dirty() {
                return Ok(());
            }
            let data = std::mem::take(&mut this.buffer);
            this.hub.borrow_mut().release(data.len());
            let mode = this.pending.take().unwrap_or(WriteMode::Append);
            (this.path.clone(), data, mode)
        };
        let reply = super::io::host_call(hub, key, Request::Write { path, data, mode }).await?;
        if let Reply::Error(error) = reply {
            writer.borrow_mut().error = Some(error);
        }
        Ok(())
    }
}

impl Drop for FileWriter {
    fn drop(&mut self) {
        if let Ok(mut hub) = self.hub.try_borrow_mut() {
            hub.release(self.buffer.len());
        }
    }
}

/// The writers holding bytes for `path`, or for any path when `path` is `None`.
pub fn dirty_writers(hub: &HubRef, path: Option<&str>) -> Vec<Rc<RefCell<FileWriter>>> {
    hub.borrow()
        .writers
        .iter()
        .filter_map(Weak::upgrade)
        .filter(|writer| {
            writer.try_borrow().is_ok_and(|this| {
                this.is_dirty()
                    && path.is_none_or(|path| this.path == path || this.path.starts_with(path))
            })
        })
        .collect()
}
