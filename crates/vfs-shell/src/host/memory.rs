//! A tree of files held in memory that answers every request a machine asks.

use std::collections::{BTreeMap, BTreeSet};

use crate::machine::{
    Config, Entry, EntryKind, HostError, Machine, ProgramKind, Reply, Request, RequestKey, Status,
    Stream, WriteMode,
};
use crate::programs;

/// The epoch second `time` answers with, so a run is a function of its line.
pub const FIXED_TIME: i64 = 1_700_000_000;

#[derive(Clone, Debug, PartialEq, Eq)]
enum Node {
    File(Vec<u8>),
    Directory,
}

/// What a line printed and how it ended.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Outcome {
    pub stdout: Vec<u8>,
    pub stderr: Vec<u8>,
    pub status: i32,
    /// Every request the line asked, in order.
    pub requests: Vec<String>,
    /// When a budget or a fault ended the line: why.
    pub ended: Option<String>,
    /// The `PIPESTATUS` of each pipeline of the line's top level that ran.
    pub statuses: Vec<Vec<i32>>,
}

/// A program the host runs itself: its arguments and the whole of its standard input in, and
/// its standard output, its standard error and its status out.
pub type HostProgram = fn(&[String], &[u8]) -> (Vec<u8>, Vec<u8>, i32);

#[derive(Clone, Debug)]
pub struct MemoryHost {
    nodes: BTreeMap<String, Node>,
    random: u64,
    /// The programs this host runs itself, by name.
    programs: BTreeMap<String, HostProgram>,
    /// The names this host refuses to run: the status and the message the line prints.
    refusals: BTreeMap<String, (i32, String)>,
    /// The names this host hands back to the library's program of the same name at each start.
    handed_back: BTreeSet<String>,
    /// Each running program by the key of its start: its program, its arguments, its input so far.
    running: BTreeMap<RequestKey, (HostProgram, Vec<String>, Vec<u8>)>,
    /// The most bytes one read answers with, to move chunk boundaries.
    pub read_chunk: Option<u64>,
    /// Answer each step's requests last first, to move arrival order.
    pub reverse_replies: bool,
    /// Refuse the write to a path that has had this many writes before it, as a rights change
    /// or another caller's file would: `("/f", 0)` refuses the first write to `/f`.
    pub refuse_write: Option<(String, usize)>,
    /// How many writes each path has been asked for.
    writes: BTreeMap<String, usize>,
}

impl Default for MemoryHost {
    fn default() -> Self {
        MemoryHost::new()
    }
}

impl MemoryHost {
    pub fn new() -> MemoryHost {
        let mut nodes = BTreeMap::new();
        nodes.insert("/".to_owned(), Node::Directory);
        MemoryHost {
            nodes,
            random: 12345,
            programs: BTreeMap::new(),
            refusals: BTreeMap::new(),
            handed_back: BTreeSet::new(),
            running: BTreeMap::new(),
            read_chunk: None,
            reverse_replies: false,
            refuse_write: None,
            writes: BTreeMap::new(),
        }
    }

    /// Run `name` as this host's own program.
    pub fn add_program(&mut self, name: &str, program: HostProgram) {
        self.programs.insert(name.to_owned(), program);
    }

    /// Refuse to run `name`: the line prints `message` and the command exits with `status`.
    pub fn refuse_program(&mut self, name: &str, status: i32, message: &str) {
        self.refusals
            .insert(name.to_owned(), (status, message.to_owned()));
    }

    /// Answer a start of `name` by handing it back to the library's program of that name.
    pub fn hand_back_program(&mut self, name: &str) {
        self.handed_back.insert(name.to_owned());
    }

    /// Add a directory and its parents.
    pub fn add_dir(&mut self, path: &str) {
        let mut current = String::new();
        for part in path.split('/').filter(|p| !p.is_empty()) {
            current.push('/');
            current.push_str(part);
            self.nodes.entry(current.clone()).or_insert(Node::Directory);
        }
    }

    /// Add a file, making its directory.
    pub fn add_file(&mut self, path: &str, bytes: &[u8]) {
        if let Some((parent, _)) = path.rsplit_once('/') {
            self.add_dir(parent);
        }
        self.nodes
            .insert(path.to_owned(), Node::File(bytes.to_vec()));
    }

    /// Whether anything, a file or a directory, stands at `path`.
    pub fn exists(&self, path: &str) -> bool {
        self.nodes.contains_key(path)
    }

    pub fn file(&self, path: &str) -> Option<&[u8]> {
        match self.nodes.get(path) {
            Some(Node::File(bytes)) => Some(bytes),
            _ => None,
        }
    }

    /// The configuration a line gets here: every library program mounted.
    pub fn config(&self) -> Config {
        Config {
            programs: programs::NAMES
                .iter()
                .map(|name| ((*name).to_owned(), ProgramKind::Library))
                .collect(),
            ..Config::default()
        }
    }

    /// Run `source` to its end, answering every request.
    pub fn run(&mut self, source: &str, config: Config) -> Outcome {
        let mut outcome = Outcome::default();
        let mut machine = match Machine::new(source, config) {
            Ok(machine) => machine,
            Err(error) => {
                let message = match error {
                    crate::machine::StartError::Parse(parse) => parse.message(),
                    crate::machine::StartError::Budget(which, limit) => {
                        format!("{which} budget of {limit} exceeded")
                    }
                };
                outcome.stderr = format!("bash: {message}\n").into_bytes();
                outcome.status = 2;
                return outcome;
            }
        };
        let mut replies = Vec::new();
        loop {
            let step = machine.step(std::mem::take(&mut replies));
            for (stream, bytes) in step.output {
                match stream {
                    Stream::Stdout => outcome.stdout.extend_from_slice(&bytes),
                    Stream::Stderr => outcome.stderr.extend_from_slice(&bytes),
                }
            }
            for (key, request) in step.requests {
                outcome.requests.push(format!("{key} {request:?}"));
                let reply = self.answer_keyed(&key, &request);
                replies.push((key, reply));
            }
            if self.reverse_replies {
                replies.reverse();
            }
            outcome.statuses.extend(step.statuses);
            match step.status {
                Status::Running => {}
                Status::Done(status) => {
                    outcome.status = status;
                    return outcome;
                }
                Status::Ended(fatal, status) => {
                    outcome.status = status;
                    outcome.ended = Some(format!("{fatal:?}"));
                    return outcome;
                }
            }
        }
    }

    fn parent_ok(&self, path: &str) -> Result<(), HostError> {
        let parent = match path.rsplit_once('/') {
            Some(("", _)) => "/",
            Some((parent, _)) => parent,
            None => return Err(HostError::Invalid),
        };
        match self.nodes.get(parent) {
            Some(Node::Directory) => Ok(()),
            Some(Node::File(_)) => Err(HostError::NotADirectory),
            None => Err(HostError::NotFound),
        }
    }

    fn children(&self, path: &str) -> Vec<Entry> {
        let prefix = if path == "/" {
            "/".to_owned()
        } else {
            format!("{path}/")
        };
        self.nodes
            .range(prefix.clone()..)
            .take_while(|(key, _)| key.starts_with(&prefix))
            .filter(|(key, _)| {
                key.len() > prefix.len()
                    && !key.get(prefix.len()..).unwrap_or_default().contains('/')
            })
            .map(|(key, node)| Entry {
                name: key.get(prefix.len()..).unwrap_or_default().to_owned(),
                kind: match node {
                    Node::File(_) => EntryKind::File,
                    Node::Directory => EntryKind::Directory,
                },
            })
            .collect()
    }

    fn subtree(&self, path: &str) -> Vec<String> {
        let prefix = format!("{path}/");
        let mut keys: Vec<String> = vec![path.to_owned()];
        keys.extend(
            self.nodes
                .range(prefix.clone()..)
                .take_while(|(k, _)| k.starts_with(&prefix))
                .map(|(k, _)| k.clone()),
        );
        keys
    }

    /// Answer one request that starts no program.
    pub fn answer(&mut self, request: &Request) -> Reply {
        self.answer_keyed(
            &RequestKey {
                task: Vec::new(),
                ordinal: 0,
            },
            request,
        )
    }

    /// Answer one request, given its key, which names a program it starts.
    pub fn answer_keyed(&mut self, key: &RequestKey, request: &Request) -> Reply {
        match self.answer_inner(key, request) {
            Ok(reply) => reply,
            Err(error) => Reply::Error(error),
        }
    }

    fn answer_inner(&mut self, key: &RequestKey, request: &Request) -> Result<Reply, HostError> {
        match request {
            Request::Start { name, args, .. } => {
                if let Some((status, message)) = self.refusals.get(name) {
                    return Ok(Reply::Refused {
                        status: *status,
                        message: message.clone(),
                    });
                }
                if self.handed_back.contains(name) {
                    return Ok(Reply::Library);
                }
                let program = self.programs.get(name).ok_or(HostError::NotFound)?;
                self.running
                    .insert(key.clone(), (*program, args.clone(), Vec::new()));
                Ok(Reply::Started)
            }
            Request::Feed { program, data, eof } => {
                let (_, _, input) = self.running.get_mut(program).ok_or(HostError::Invalid)?;
                input.extend_from_slice(data);
                if !*eof {
                    return Ok(Reply::Output {
                        stdout: Vec::new(),
                        stderr: Vec::new(),
                        status: None,
                    });
                }
                let (run, args, input) = self.running.remove(program).ok_or(HostError::Invalid)?;
                let (stdout, stderr, status) = run(&args, &input);
                Ok(Reply::Output {
                    stdout,
                    stderr,
                    status: Some(status),
                })
            }
            Request::Read {
                path,
                offset,
                length,
            } => match self.nodes.get(path) {
                Some(Node::File(bytes)) => {
                    let start = usize::try_from(*offset)
                        .unwrap_or(usize::MAX)
                        .min(bytes.len());
                    let end = start
                        .saturating_add(usize::try_from(*length).unwrap_or(usize::MAX))
                        .min(bytes.len());
                    Ok(Reply::Data {
                        bytes: bytes.get(start..end).unwrap_or_default().to_vec(),
                        eof: end >= bytes.len(),
                    })
                }
                Some(Node::Directory) => Err(HostError::IsADirectory),
                None => Err(HostError::NotFound),
            },
            Request::Write { path, data, mode } => {
                let before = self.writes.get(path).copied().unwrap_or(0);
                self.writes.insert(path.clone(), before.saturating_add(1));
                if self.refuse_write.as_ref() == Some(&(path.clone(), before)) {
                    return Err(HostError::PermissionDenied);
                }
                self.parent_ok(path)?;
                match (self.nodes.get_mut(path), mode) {
                    (Some(Node::Directory), _) => Err(HostError::IsADirectory),
                    (Some(Node::File(_)), WriteMode::CreateNew) => Err(HostError::Exists),
                    (Some(Node::File(bytes)), WriteMode::Append) => {
                        bytes.extend_from_slice(data);
                        Ok(Reply::Done)
                    }
                    (Some(Node::File(bytes)), WriteMode::Truncate) => {
                        *bytes = data.clone();
                        Ok(Reply::Done)
                    }
                    (None, _) => {
                        self.nodes.insert(path.clone(), Node::File(data.clone()));
                        Ok(Reply::Done)
                    }
                }
            }
            Request::Touch { path } => {
                self.parent_ok(path)?;
                self.nodes
                    .entry(path.clone())
                    .or_insert(Node::File(Vec::new()));
                Ok(Reply::Done)
            }
            Request::Stat { path } => match self.nodes.get(path) {
                Some(Node::File(bytes)) => Ok(Reply::Stat {
                    kind: EntryKind::File,
                    size: bytes.len() as u64,
                }),
                Some(Node::Directory) => Ok(Reply::Stat {
                    kind: EntryKind::Directory,
                    size: 4096,
                }),
                None => Err(HostError::NotFound),
            },
            Request::List { path } => match self.nodes.get(path) {
                Some(Node::Directory) => Ok(Reply::Entries(self.children(path))),
                Some(Node::File(_)) => Err(HostError::NotADirectory),
                None => Err(HostError::NotFound),
            },
            Request::Mkdir { path, parents } => {
                if self.nodes.contains_key(path) {
                    return if *parents && self.nodes.get(path) == Some(&Node::Directory) {
                        Ok(Reply::Done)
                    } else {
                        Err(HostError::Exists)
                    };
                }
                if *parents {
                    self.add_dir(path);
                    return Ok(Reply::Done);
                }
                self.parent_ok(path)?;
                self.nodes.insert(path.clone(), Node::Directory);
                Ok(Reply::Done)
            }
            Request::Remove { path, recursive } => match self.nodes.get(path) {
                None => Err(HostError::NotFound),
                Some(Node::File(_)) => {
                    self.nodes.remove(path);
                    Ok(Reply::Done)
                }
                Some(Node::Directory) => {
                    if path == "/" {
                        return Err(HostError::Invalid);
                    }
                    let keys = self.subtree(path);
                    if keys.len() > 1 && !*recursive {
                        return Err(HostError::NotEmpty);
                    }
                    for key in keys {
                        self.nodes.remove(&key);
                    }
                    Ok(Reply::Done)
                }
            },
            Request::Copy {
                from,
                to,
                recursive,
            } => {
                self.parent_ok(to)?;
                match self.nodes.get(from).cloned() {
                    None => Err(HostError::NotFound),
                    Some(Node::File(bytes)) => {
                        if self.nodes.get(to) == Some(&Node::Directory) {
                            return Err(HostError::IsADirectory);
                        }
                        self.nodes.insert(to.clone(), Node::File(bytes));
                        Ok(Reply::Done)
                    }
                    Some(Node::Directory) => {
                        if !*recursive {
                            return Err(HostError::IsADirectory);
                        }
                        if to.starts_with(&format!("{from}/")) || to == from {
                            return Err(HostError::Invalid);
                        }
                        for key in self.subtree(from) {
                            let target =
                                format!("{}{}", to, key.get(from.len()..).unwrap_or_default());
                            if let Some(node) = self.nodes.get(&key).cloned() {
                                self.nodes.insert(target, node);
                            }
                        }
                        Ok(Reply::Done)
                    }
                }
            }
            Request::Move { from, to } => {
                self.parent_ok(to)?;
                if !self.nodes.contains_key(from) {
                    return Err(HostError::NotFound);
                }
                if to.starts_with(&format!("{from}/")) {
                    return Err(HostError::Invalid);
                }
                if self.nodes.get(to) == Some(&Node::Directory)
                    && self.nodes.get(from) != Some(&Node::Directory)
                {
                    return Err(HostError::IsADirectory);
                }
                let keys = self.subtree(from);
                if self.nodes.get(to) == Some(&Node::Directory) {
                    for key in self.subtree(to) {
                        self.nodes.remove(&key);
                    }
                }
                for key in keys {
                    if let Some(node) = self.nodes.remove(&key) {
                        let target = format!("{}{}", to, key.get(from.len()..).unwrap_or_default());
                        self.nodes.insert(target, node);
                    }
                }
                Ok(Reply::Done)
            }
            Request::Value { name } => match name.as_str() {
                "time" => Ok(Reply::Text(FIXED_TIME.to_string())),
                "random" => {
                    self.random = self
                        .random
                        .wrapping_mul(6_364_136_223_846_793_005)
                        .wrapping_add(1_442_695_040_888_963_407);
                    Ok(Reply::Text(((self.random >> 33) % 32768).to_string()))
                }
                _ => Err(HostError::Unsupported),
            },
        }
    }
}
