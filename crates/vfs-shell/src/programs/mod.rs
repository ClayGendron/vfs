//! The programs the crate ships: text transforms over their input, and file
//! programs written against the machine's own requests, so one
//! implementation serves every host that mounts them. Each prints what its
//! GNU counterpart prints for the same input.

mod files;
mod grep;
pub mod sed;
mod text;

use std::collections::BTreeMap;

use crate::machine::exec::Status;
use crate::machine::exec::{absolute, read_whole, sync_path, write_or_die};
use crate::machine::files::FileReader;
use crate::machine::shell::Fd;
use crate::machine::{Ctx, Flow, HostError, Reply, Request, RequestKey, Shell, io};

/// Every program name the library implements.
pub const NAMES: &[&str] = &[
    "cat", "cp", "cut", "find", "grep", "head", "ls", "mkdir", "mv", "rm", "sed", "sort", "tail",
    "tee", "touch", "tr", "uniq", "wc",
];

/// Run a library program, or `None` when the library has no such name.
pub async fn run(
    ctx: &Ctx<'_>,
    sh: &mut Shell,
    name: &str,
    words: Vec<String>,
) -> Result<Option<i32>, Flow> {
    let _ = ctx;
    let args: Vec<String> = words.into_iter().skip(1).collect();
    let mut prog = Prog {
        sh,
        name: name.to_owned(),
    };
    let status = match name {
        "cat" => text::cat(&mut prog, &args).await?,
        "head" => text::head(&mut prog, &args).await?,
        "tail" => text::tail(&mut prog, &args).await?,
        "wc" => text::wc(&mut prog, &args).await?,
        "cut" => text::cut(&mut prog, &args).await?,
        "sort" => text::sort(&mut prog, &args).await?,
        "uniq" => text::uniq(&mut prog, &args).await?,
        "tr" => text::tr(&mut prog, &args).await?,
        "tee" => text::tee(&mut prog, &args).await?,
        "sed" => run_sed(&mut prog, &args).await?,
        "grep" => grep::grep(&mut prog, &args).await?,
        "ls" => files::ls(&mut prog, &args).await?,
        "find" => files::find(&mut prog, &args).await?,
        "cp" => files::cp(&mut prog, &args).await?,
        "mv" => files::mv(&mut prog, &args).await?,
        "rm" => files::rm(&mut prog, &args).await?,
        "mkdir" => files::mkdir(&mut prog, &args).await?,
        "touch" => files::touch(&mut prog, &args).await?,
        _ => return Ok(None),
    };
    Ok(Some(status))
}

/// Run a program the host runs: feed it standard input a chunk at a time, and write what it
/// writes, until it exits. A host that answers a feed with anything else ends the program.
pub async fn run_host(sh: &mut Shell, name: &str, program: RequestKey) -> Status {
    let mut prog = Prog {
        sh,
        name: name.to_owned(),
    };
    let mut eof = false;
    loop {
        let data = if eof {
            Vec::new()
        } else if let Some(chunk) = prog.stdin_chunk().await? {
            chunk
        } else {
            eof = true;
            Vec::new()
        };
        let feed = Request::Feed {
            program: program.clone(),
            data,
            eof,
        };
        match prog.request(feed).await? {
            Reply::Output {
                stdout,
                stderr,
                status,
            } => {
                prog.out(&stdout).await?;
                if !stderr.is_empty() {
                    write_or_die(prog.sh, 2, &stderr).await?;
                }
                if let Some(status) = status {
                    return Ok(status);
                }
            }
            _ => {
                prog.err("the host ended the program").await?;
                return Ok(1);
            }
        }
    }
}

/// What a program sees of the shell: its streams and its host.
pub struct Prog<'s> {
    pub sh: &'s mut Shell,
    pub name: String,
}

impl Prog<'_> {
    /// Write to standard output; a reader that is gone ends the program as SIGPIPE does.
    pub async fn out(&mut self, bytes: &[u8]) -> Result<(), Flow> {
        if bytes.is_empty() {
            return Ok(());
        }
        write_or_die(self.sh, 1, bytes).await.map(|_| ())
    }

    /// Write `name: message` and a newline to standard error.
    pub async fn err(&mut self, message: &str) -> Result<(), Flow> {
        let text = format!("{}: {}\n", self.name, message);
        self.sh.error_text(&text).await?;
        Ok(())
    }

    pub fn abs(&self, path: &str) -> String {
        absolute(self.sh, path)
    }

    pub async fn request(&mut self, request: Request) -> Result<Reply, Flow> {
        let key = self.sh.key();
        Ok(io::host_call(&self.sh.hub, key, request).await?)
    }

    pub async fn stat(
        &mut self,
        path: &str,
    ) -> Result<Option<(crate::machine::EntryKind, u64)>, Flow> {
        let absolute = self.abs(path);
        sync_path(self.sh, &absolute).await?;
        Ok(
            match self.request(Request::Stat { path: absolute }).await? {
                Reply::Stat { kind, size } => Some((kind, size)),
                _ => None,
            },
        )
    }

    /// The next chunk of standard input, or `None` at its end.
    pub async fn stdin_chunk(&mut self) -> Result<Option<Vec<u8>>, Flow> {
        let Some(source) = self.sh.fds.get(&0).cloned() else {
            return Ok(None);
        };
        match source {
            Fd::Buffer(buffer) => {
                let mut buffer = buffer.borrow_mut();
                let rest = buffer.rest().to_vec();
                if rest.is_empty() {
                    return Ok(None);
                }
                let count = rest.len();
                buffer.advance(count);
                Ok(Some(rest))
            }
            Fd::FileIn(reader) => {
                let rest = reader.borrow().rest().to_vec();
                if !rest.is_empty() {
                    let count = rest.len();
                    reader.borrow_mut().advance(count);
                    return Ok(Some(rest));
                }
                let key = self.sh.key();
                if !FileReader::refill(&reader, &self.sh.hub, key).await? {
                    return Ok(None);
                }
                let rest = reader.borrow().rest().to_vec();
                let count = rest.len();
                reader.borrow_mut().advance(count);
                Ok(Some(rest))
            }
            Fd::PipeIn(end) => {
                let chunk = end.read(crate::machine::io::PIPE_CAPACITY).await;
                if chunk.is_empty() {
                    Ok(None)
                } else {
                    Ok(Some(chunk))
                }
            }
            _ => Ok(None),
        }
    }

    /// All of standard input.
    pub async fn stdin_all(&mut self) -> Result<Vec<u8>, Flow> {
        let mut bytes = Vec::new();
        while let Some(chunk) = self.stdin_chunk().await? {
            self.sh
                .hub
                .borrow()
                .fits(bytes.len().saturating_add(chunk.len()))?;
            bytes.extend_from_slice(&chunk);
        }
        Ok(bytes)
    }

    /// A file's bytes, `-` being standard input.
    pub async fn file(&mut self, path: &str) -> Result<Result<Vec<u8>, HostError>, Flow> {
        if path == "-" || path == "/dev/stdin" {
            return Ok(Ok(self.stdin_all().await?));
        }
        if let Some(number) = path
            .strip_prefix("/dev/fd/")
            .and_then(|n| n.parse::<u32>().ok())
        {
            let saved = self.sh.fds.get(&0).cloned();
            let Some(fd) = self.sh.fds.get(&number).cloned() else {
                return Ok(Err(HostError::NotFound));
            };
            self.sh.fds.insert(0, fd);
            let bytes = self.stdin_all().await;
            match saved {
                Some(fd) => self.sh.fds.insert(0, fd),
                None => self.sh.fds.remove(&0),
            };
            return Ok(Ok(bytes?));
        }
        if path == "/dev/null" {
            return Ok(Ok(Vec::new()));
        }
        let absolute = self.abs(path);
        Ok(read_whole(self.sh, &absolute).await?)
    }

    /// Write a whole file.
    pub async fn write_file(
        &mut self,
        path: &str,
        data: Vec<u8>,
    ) -> Result<Result<(), HostError>, Flow> {
        if path == "/dev/stdout" || path == "-" {
            self.out(&data).await?;
            return Ok(Ok(()));
        }
        if path == "/dev/stderr" {
            write_or_die(self.sh, 2, &data).await?;
            return Ok(Ok(()));
        }
        if path == "/dev/null" {
            return Ok(Ok(()));
        }
        let absolute = self.abs(path);
        sync_path(self.sh, &absolute).await?;
        let reply = self
            .request(Request::Write {
                path: absolute,
                data,
                mode: crate::machine::WriteMode::Truncate,
            })
            .await?;
        Ok(match reply {
            Reply::Error(error) => Err(error),
            _ => Ok(()),
        })
    }
}

/// Split options from operands, GNU style: options may follow operands until `--`.
pub fn split_args(args: &[String]) -> (Vec<String>, Vec<String>) {
    let mut options = Vec::new();
    let mut operands = Vec::new();
    let mut done = false;
    for arg in args {
        if done {
            operands.push(arg.clone());
        } else if arg == "--" {
            done = true;
        } else if arg.starts_with('-') && arg.len() > 1 {
            options.push(arg.clone());
        } else {
            operands.push(arg.clone());
        }
    }
    (options, operands)
}

/// The text a GNU tool prints for a host error on a path.
pub fn describe(error: HostError) -> &'static str {
    error.message()
}

async fn run_sed(prog: &mut Prog<'_>, args: &[String]) -> Result<i32, Flow> {
    // The script is read and compiled first, so a script that is refused reads no operand.
    let scripts = match sed::scripts(args) {
        Ok(scripts) => scripts,
        Err(output) => return sed_failed(prog, &output).await,
    };
    let mut stdin = Vec::new();
    let mut files = BTreeMap::new();
    for name in scripts {
        if name == "-" {
            stdin = prog.stdin_all().await?;
            continue;
        }
        let content = sed_input(prog, &name).await?;
        files.insert(name, content);
    }
    let needed = match sed::inputs(args, &files, &stdin) {
        Ok(needed) => needed,
        Err(output) => return sed_failed(prog, &output).await,
    };
    for name in needed {
        if name == "-" {
            if stdin.is_empty() {
                stdin = prog.stdin_all().await?;
            }
            continue;
        }
        if files.contains_key(&name) {
            continue;
        }
        let content = sed_input(prog, &name).await?;
        files.insert(name, content);
    }
    let output = sed::run(args, &stdin, &files);
    prog.out(&output.stdout).await?;
    if !output.stderr.is_empty() {
        prog.sh.write_fd(2, &output.stderr).await?;
    }
    let mut status = output.status;
    // A refused backup or replacement stops that edit and every later one, as GNU sed exits there.
    let mut stopped = false;
    for write in output.writes {
        if stopped && write.kind != sed::WriteKind::Script {
            continue;
        }
        if let Err(error) = prog.write_file(&write.path, write.data).await? {
            stopped |= write.kind != sed::WriteKind::Script;
            let message = match &write.kind {
                sed::WriteKind::Backup { source } => {
                    format!("cannot rename {}: {}", source, describe(error))
                }
                _ => format!("couldn't open file {}: {}", write.path, describe(error)),
            };
            prog.err(&message).await?;
            status = 4;
        }
    }
    Ok(status)
}

/// What `sed` printed when its options or script were refused, and its status.
async fn sed_failed(prog: &mut Prog<'_>, output: &sed::SedOutput) -> Result<i32, Flow> {
    prog.out(&output.stdout).await?;
    prog.sh.write_fd(2, &output.stderr).await?;
    Ok(output.status)
}

/// One file `sed` reads, or the error text GNU sed prints for it.
async fn sed_input(prog: &mut Prog<'_>, name: &str) -> Result<Result<Vec<u8>, String>, Flow> {
    Ok(match prog.stat(name).await? {
        Some((crate::machine::EntryKind::Directory, _)) => Err("Is a directory".to_owned()),
        _ => prog.file(name).await?.map_err(|e| describe(e).to_owned()),
    })
}
