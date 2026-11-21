//! The builtins: every name bash itself runs, run here with no request
//! except where the builtin touches a file or a stream.

use std::collections::BTreeMap;

use super::exec::{
    self, Ctx, Expanded, Flow, Index, Status, absolute, assign_array, assign_element,
    assign_scalar, call_function, resolve_nameref, run_program, set_value, subscript, write_or_die,
};
use super::expand::{self, Mode, expand_single, split_read};
use super::files::FileReader;
use super::io;
use super::printf;
use super::quote;
use super::shell::{Fd, Options, SHOPT_DEFAULTS, Shell};
use super::vars::{self, AssocMap, Value, Var};
use super::{EntryKind, Reply, Request};
use crate::syntax::ast::{AssignValue, List};
use crate::syntax::is_name;

const BUILTINS: &[&str] = &[
    ":",
    ".",
    "[",
    "alias",
    "bg",
    "bind",
    "break",
    "builtin",
    "caller",
    "cd",
    "command",
    "compgen",
    "complete",
    "compopt",
    "continue",
    "declare",
    "dirs",
    "disown",
    "echo",
    "enable",
    "eval",
    "exec",
    "exit",
    "export",
    "false",
    "fc",
    "fg",
    "getopts",
    "hash",
    "help",
    "history",
    "jobs",
    "kill",
    "let",
    "local",
    "logout",
    "mapfile",
    "popd",
    "printf",
    "pushd",
    "pwd",
    "read",
    "readarray",
    "readonly",
    "return",
    "set",
    "shift",
    "shopt",
    "source",
    "suspend",
    "test",
    "times",
    "trap",
    "true",
    "type",
    "typeset",
    "ulimit",
    "umask",
    "unalias",
    "unset",
    "wait",
];

const SPECIAL: &[&str] = &[
    "break", ":", ".", "continue", "eval", "exec", "exit", "export", "readonly", "return", "set",
    "shift", "times", "trap", "unset",
];

const KEYWORDS: &[&str] = &[
    "if", "then", "else", "elif", "fi", "case", "esac", "for", "select", "while", "until", "do",
    "done", "in", "function", "time", "{", "}", "!", "[[", "]]", "coproc",
];

pub fn is_builtin(name: &str) -> bool {
    BUILTINS.contains(&name)
}

pub fn is_special(name: &str) -> bool {
    SPECIAL.contains(&name)
}

/// Write text to standard output.
async fn out(sh: &mut Shell, text: &str) -> Result<(), Flow> {
    write_or_die(sh, 1, text.as_bytes()).await.map(|_| ())
}

async fn err(sh: &mut Shell, name: &str, message: &str) -> Result<(), Flow> {
    let line = sh.lineno;
    sh.error_text(&format!("bash: line {line}: {name}: {message}\n"))
        .await?;
    Ok(())
}

pub async fn run(
    ctx: &Ctx<'_>,
    sh: &mut Shell,
    name: &str,
    words: Vec<String>,
    args: Vec<Expanded>,
) -> Status {
    let rest: Vec<String> = words.iter().skip(1).cloned().collect();
    match name {
        ":" | "true" => Ok(0),
        "false" => Ok(1),
        "echo" => echo(sh, &rest).await,
        "printf" => printf_builtin(sh, &rest).await,
        "read" => read(sh, &rest).await,
        "mapfile" | "readarray" => mapfile(ctx, sh, name, &rest).await,
        "cd" => cd(sh, &rest).await,
        "pwd" => {
            let cwd = sh.cwd.clone();
            out(sh, &format!("{cwd}\n")).await?;
            Ok(0)
        }
        "declare" | "typeset" | "local" | "export" | "readonly" => {
            declare(ctx, sh, name, args).await
        }
        "unset" => unset(sh, &rest).await,
        "shift" => shift(sh, &rest).await,
        "getopts" => getopts(sh, &rest).await,
        "set" => set(sh, &rest).await,
        "shopt" => shopt(sh, &rest).await,
        "let" => {
            if rest.is_empty() {
                err(sh, "let", "expression expected").await?;
                return Ok(1);
            }
            let mut last = 0;
            for expr in &rest {
                last = match expand::eval_arith(ctx, sh, expr).await {
                    Ok(value) => value,
                    Err(Flow::Discard(code)) => return Ok(code),
                    Err(flow) => return Err(flow),
                };
            }
            Ok(i32::from(last == 0))
        }
        "return" => {
            let status = match rest.first() {
                Some(text) => match parse_status(text) {
                    Some(code) => code,
                    None => {
                        err(sh, "return", &format!("{text}: numeric argument required")).await?;
                        2
                    }
                },
                None => sh.last_status,
            };
            if sh.function_depth == 0 {
                err(
                    sh,
                    "return",
                    "can only `return' from a function or sourced script",
                )
                .await?;
                return Ok(2);
            }
            Err(Flow::Return(status & 0xff))
        }
        "exit" => {
            if rest.len() > 1 {
                err(sh, "exit", "too many arguments").await?;
                return Err(Flow::Exit(1));
            }
            let status = match rest.first() {
                Some(text) => match parse_status(text) {
                    Some(code) => code,
                    None => {
                        err(sh, "exit", &format!("{text}: numeric argument required")).await?;
                        return Ok(2);
                    }
                },
                None => sh.last_status,
            };
            Err(Flow::Exit(status & 0xff))
        }
        "break" | "continue" => {
            let count = match rest.first() {
                Some(text) => match text.parse::<i64>() {
                    Ok(n) if n >= 1 => u32::try_from(n).unwrap_or(u32::MAX),
                    Ok(_) => {
                        err(sh, name, &format!("{text}: loop count out of range")).await?;
                        return Err(Flow::Exit(1));
                    }
                    Err(_) => {
                        err(sh, name, &format!("{text}: numeric argument required")).await?;
                        return Err(Flow::Exit(128));
                    }
                },
                None => 1,
            };
            if sh.loop_depth == 0 {
                err(
                    sh,
                    name,
                    "only meaningful in a `for', `while', or `until' loop",
                )
                .await?;
                return Ok(0);
            }
            let count = count.min(sh.loop_depth);
            Err(if name == "break" {
                Flow::Break(count)
            } else {
                Flow::Continue(count)
            })
        }
        "test" => super::test::test_builtin(sh, "test", &rest).await,
        "[" => {
            if rest.last().map(String::as_str) != Some("]") {
                err(sh, "[", "missing `]'").await?;
                return Ok(2);
            }
            let inner = rest.get(..rest.len().saturating_sub(1)).unwrap_or_default();
            super::test::test_builtin(sh, "[", inner).await
        }
        "type" => type_builtin(sh, &rest).await,
        "command" => command(ctx, sh, &rest).await,
        "builtin" => {
            let Some(target) = rest.first().cloned() else {
                return Ok(0);
            };
            if !is_builtin(&target) {
                err(sh, "builtin", &format!("{target}: not a shell builtin")).await?;
                return Ok(1);
            }
            let words: Vec<String> = rest.clone();
            let args = words.iter().map(|w| Expanded::Field(w.clone())).collect();
            Box::pin(run(ctx, sh, &target, words, args)).await
        }
        "wait" => wait(sh, &rest).await,
        "kill" => {
            err(sh, "kill", "signals are not supported").await?;
            Ok(1)
        }
        "hash" => Ok(0),
        "umask" => {
            if rest.is_empty() {
                out(sh, "0022\n").await?;
            }
            Ok(0)
        }
        "times" => {
            out(sh, "0m0.000s 0m0.000s\n0m0.000s 0m0.000s\n").await?;
            Ok(0)
        }
        "caller" => {
            let depth = rest.first().and_then(|t| t.parse::<usize>().ok());
            let frames = sh.frames.clone();
            match depth {
                None => match frames.last() {
                    Some((_, line)) => {
                        out(sh, &format!("{line} NULL\n")).await?;
                        Ok(0)
                    }
                    None => Ok(1),
                },
                Some(n) => {
                    let index = frames.len().checked_sub(n.saturating_add(1));
                    match index.and_then(|i| frames.get(i)) {
                        Some((_, line)) => {
                            let caller = index
                                .and_then(|i| i.checked_sub(1))
                                .and_then(|i| frames.get(i))
                                .map_or("main".to_owned(), |(name, _)| name.clone());
                            out(sh, &format!("{line} {caller} bash\n")).await?;
                            Ok(0)
                        }
                        None => Ok(1),
                    }
                }
            }
        }
        "dirs" => {
            let mut stack = vec![tilde(sh, &sh.cwd.clone())];
            for dir in sh.dir_stack.clone().iter().rev() {
                stack.push(tilde(sh, dir));
            }
            out(sh, &format!("{}\n", stack.join(" "))).await?;
            Ok(0)
        }
        "pushd" => {
            let Some(target) = rest.first().cloned() else {
                err(sh, "pushd", "no other directory").await?;
                return Ok(1);
            };
            let previous = sh.cwd.clone();
            let status = cd(sh, &[target]).await?;
            if status == 0 {
                sh.dir_stack.push(previous);
                let mut stack = vec![tilde(sh, &sh.cwd.clone())];
                for dir in sh.dir_stack.clone().iter().rev() {
                    stack.push(tilde(sh, dir));
                }
                out(sh, &format!("{}\n", stack.join(" "))).await?;
            }
            Ok(status)
        }
        "popd" => {
            let Some(target) = sh.dir_stack.pop() else {
                err(sh, "popd", "directory stack empty").await?;
                return Ok(1);
            };
            let status = cd(sh, &[target]).await?;
            let mut stack = vec![tilde(sh, &sh.cwd.clone())];
            for dir in sh.dir_stack.clone().iter().rev() {
                stack.push(tilde(sh, dir));
            }
            out(sh, &format!("{}\n", stack.join(" "))).await?;
            Ok(status)
        }
        "enable" | "help" | "bind" | "complete" | "compgen" | "compopt" | "history" | "fc"
        | "ulimit" | "logout" => {
            err(sh, name, "not supported in this shell").await?;
            Ok(1)
        }
        _ => {
            let reason = crate::syntax::REFUSED
                .iter()
                .find(|(refused, _)| *refused == name)
                .map_or("not supported in this shell", |(_, reason)| reason);
            err(sh, name, &format!("refused: {reason}")).await?;
            Err(Flow::Exit(2))
        }
    }
}

fn tilde(sh: &Shell, path: &str) -> String {
    match sh.get_var("HOME") {
        Some(home)
            if !home.is_empty() && (path == home || path.starts_with(&format!("{home}/"))) =>
        {
            format!("~{}", path.get(home.len()..).unwrap_or_default())
        }
        _ => path.to_owned(),
    }
}

fn parse_status(text: &str) -> Option<i32> {
    let trimmed = text.trim();
    let value: i64 = trimmed.parse().ok()?;
    Some(i32::try_from(value & 0xff).unwrap_or(0))
}

// ---------------------------------------------------------------------------
// echo and printf
// ---------------------------------------------------------------------------

async fn echo(sh: &mut Shell, args: &[String]) -> Status {
    let mut newline = true;
    let mut escapes = sh.options.shopt("xpg_echo");
    let mut index = 0;
    if !(sh.options.posix && sh.options.shopt("xpg_echo")) {
        while let Some(arg) = args.get(index) {
            let Some(flags) = arg.strip_prefix('-') else {
                break;
            };
            if flags.is_empty() || !flags.chars().all(|c| matches!(c, 'n' | 'e' | 'E')) {
                break;
            }
            for flag in flags.chars() {
                match flag {
                    'n' => newline = false,
                    'e' => escapes = true,
                    _ => escapes = false,
                }
            }
            index += 1;
        }
    }
    let mut bytes = Vec::new();
    for (n, arg) in args.iter().skip(index).enumerate() {
        if n > 0 {
            bytes.push(b' ');
        }
        if escapes {
            let (decoded, _, stop) = printf::expand_b(arg.as_bytes());
            bytes.extend_from_slice(&decoded);
            if stop {
                write_or_die(sh, 1, &bytes).await?;
                return Ok(0);
            }
        } else {
            bytes.extend_from_slice(arg.as_bytes());
        }
    }
    if newline {
        bytes.push(b'\n');
    }
    if !write_or_die(sh, 1, &bytes).await? {
        err(sh, "echo", "write error: Bad file descriptor").await?;
        return Ok(1);
    }
    Ok(0)
}

async fn printf_builtin(sh: &mut Shell, args: &[String]) -> Status {
    let mut rest = args;
    let mut target = None;
    if rest.first().map(String::as_str) == Some("-v") {
        target = rest.get(1).cloned();
        rest = rest.get(2..).unwrap_or_default();
        if target.is_none() {
            err(sh, "printf", "-v: option requires an argument").await?;
            return Ok(2);
        }
    }
    if rest.first().map(String::as_str) == Some("--") {
        rest = rest.get(1..).unwrap_or_default();
    }
    let Some(format) = rest.first() else {
        err(sh, "printf", "usage: printf [-v var] format [arguments]").await?;
        return Ok(2);
    };
    let needs_time = format.contains("%(");
    let now = if needs_time { host_time(sh).await? } else { 0 };
    let printed = printf::printf(format, rest.get(1..).unwrap_or_default(), now);
    sh.hub.borrow().fits(printed.bytes.len())?;
    for message in &printed.errors {
        err(sh, "printf", message).await?;
    }
    match target {
        Some(name) => {
            let text = String::from_utf8_lossy(&printed.bytes).into_owned();
            match parse_target(&name) {
                Some((base, Some(sub))) => {
                    let index = if sh.vars.get(&base).is_some_and(Var::is_assoc) {
                        Index::Key(sub)
                    } else {
                        Index::Number(super::arith::evaluate(sh, &sub).unwrap_or(0))
                    };
                    assign_element(sh, &base, index, text, false).await?;
                }
                Some((base, None)) => assign_scalar(sh, &base, text, false).await?,
                None => {
                    err(sh, "printf", &format!("`{name}': not a valid identifier")).await?;
                    return Ok(2);
                }
            }
        }
        None => {
            write_or_die(sh, 1, &printed.bytes).await?;
        }
    }
    Ok(printed.status)
}

async fn host_time(sh: &mut Shell) -> Result<i64, Flow> {
    let key = sh.key();
    let reply = io::host_call(
        &sh.hub,
        key,
        Request::Value {
            name: "time".to_owned(),
        },
    )
    .await?;
    Ok(match reply {
        Reply::Text(text) => text.trim().parse().unwrap_or(0),
        _ => 0,
    })
}

/// `name` or `name[sub]`.
fn parse_target(text: &str) -> Option<(String, Option<String>)> {
    if is_name(text) {
        return Some((text.to_owned(), None));
    }
    let open = text.find('[')?;
    let name = text.get(..open)?;
    let sub = text.get(open.saturating_add(1)..)?.strip_suffix(']')?;
    is_name(name).then(|| (name.to_owned(), Some(sub.to_owned())))
}

// ---------------------------------------------------------------------------
// Reading
// ---------------------------------------------------------------------------

/// What one read of a record found.
struct Record {
    bytes: Vec<u8>,
    /// The delimiter ended it, rather than the end of the stream or a count.
    delimited: bool,
    eof: bool,
}

/// Read up to `delimiter` (kept out of the bytes), or `count` characters, from `fd`.
async fn read_record(
    sh: &mut Shell,
    fd: u32,
    delimiter: Option<u8>,
    count: Option<usize>,
) -> Result<Option<Record>, Flow> {
    let Some(source) = sh.fds.get(&fd).cloned() else {
        return Ok(None);
    };
    let mut bytes = Vec::new();
    let mut chars = 0usize;
    let reached = |bytes: &Vec<u8>, chars: usize| {
        count.is_some_and(|n| chars >= n) && !bytes.is_empty() || count == Some(0)
    };
    match source {
        Fd::Buffer(buffer) => {
            let mut buffer = buffer.borrow_mut();
            loop {
                if reached(&bytes, chars) {
                    return Ok(Some(Record {
                        bytes,
                        delimited: false,
                        eof: false,
                    }));
                }
                let Some(&byte) = buffer.rest().first() else {
                    return Ok(Some(Record {
                        bytes,
                        delimited: false,
                        eof: true,
                    }));
                };
                buffer.advance(1);
                if Some(byte) == delimiter {
                    return Ok(Some(Record {
                        bytes,
                        delimited: true,
                        eof: false,
                    }));
                }
                if byte & 0xc0 != 0x80 {
                    chars = chars.saturating_add(1);
                }
                bytes.push(byte);
                if count.is_some_and(|n| chars >= n) && !continues_utf8(buffer.rest()) {
                    return Ok(Some(Record {
                        bytes,
                        delimited: false,
                        eof: false,
                    }));
                }
            }
        }
        Fd::FileIn(reader) => loop {
            let next = reader.borrow().rest().first().copied();
            let byte = match next {
                Some(byte) => byte,
                None => {
                    let key = sh.key();
                    if !FileReader::refill(&reader, &sh.hub, key).await? {
                        return Ok(Some(Record {
                            bytes,
                            delimited: false,
                            eof: true,
                        }));
                    }
                    continue;
                }
            };
            reader.borrow_mut().advance(1);
            if Some(byte) == delimiter {
                return Ok(Some(Record {
                    bytes,
                    delimited: true,
                    eof: false,
                }));
            }
            if byte & 0xc0 != 0x80 {
                chars = chars.saturating_add(1);
            }
            bytes.push(byte);
            if count.is_some_and(|n| chars >= n) && !continues_utf8(reader.borrow().rest()) {
                return Ok(Some(Record {
                    bytes,
                    delimited: false,
                    eof: false,
                }));
            }
        },
        Fd::PipeIn(end) => loop {
            if count == Some(0) {
                return Ok(Some(Record {
                    bytes,
                    delimited: false,
                    eof: false,
                }));
            }
            let chunk = match delimiter {
                Some(d) if count.is_none() => end.read_until(d, usize::MAX).await,
                _ => end.read(1).await,
            };
            if chunk.is_empty() {
                return Ok(Some(Record {
                    bytes,
                    delimited: false,
                    eof: true,
                }));
            }
            sh.hub
                .borrow()
                .fits(bytes.len().saturating_add(chunk.len()))?;
            for byte in chunk {
                if Some(byte) == delimiter {
                    return Ok(Some(Record {
                        bytes,
                        delimited: true,
                        eof: false,
                    }));
                }
                if byte & 0xc0 != 0x80 {
                    chars = chars.saturating_add(1);
                }
                bytes.push(byte);
            }
            if count.is_some_and(|n| chars >= n) {
                return Ok(Some(Record {
                    bytes,
                    delimited: false,
                    eof: false,
                }));
            }
        },
        Fd::Terminal(_) | Fd::Null => Ok(Some(Record {
            bytes,
            delimited: false,
            eof: true,
        })),
        Fd::PipeOut(_) | Fd::FileOut(_) => Ok(None),
    }
}

fn continues_utf8(rest: &[u8]) -> bool {
    rest.first().is_some_and(|b| b & 0xc0 == 0x80)
}

async fn read(sh: &mut Shell, args: &[String]) -> Status {
    let mut raw = false;
    let mut array: Option<String> = None;
    let mut delimiter = Some(b'\n');
    let mut count: Option<usize> = None;
    let mut exact = false;
    let mut prompt: Option<String> = None;
    let mut fd = 0u32;
    let mut names = Vec::new();
    let mut index = 0;
    while let Some(arg) = args.get(index) {
        index += 1;
        if names.is_empty() && arg.starts_with('-') && arg.len() > 1 && arg != "--" {
            let mut flags = arg.chars().skip(1);
            while let Some(flag) = flags.next() {
                let rest: String = flags.clone().collect();
                let mut value = || -> Option<String> {
                    if rest.is_empty() {
                        let v = args.get(index).cloned();
                        index += 1;
                        v
                    } else {
                        Some(rest.clone())
                    }
                };
                match flag {
                    'r' => raw = true,
                    's' | 'e' => {}
                    'a' => {
                        array = value();
                        break;
                    }
                    'd' => {
                        delimiter = Some(value().unwrap_or_default().bytes().next().unwrap_or(0));
                        break;
                    }
                    'n' | 'N' => {
                        let text = value().unwrap_or_default();
                        match text.parse::<usize>() {
                            Ok(n) => count = Some(n),
                            Err(_) => {
                                err(sh, "read", &format!("{text}: invalid number")).await?;
                                return Ok(1);
                            }
                        }
                        exact = flag == 'N';
                        break;
                    }
                    'p' => {
                        prompt = value();
                        break;
                    }
                    't' => {
                        let _ = value();
                        break;
                    }
                    'i' => {
                        let _ = value();
                        break;
                    }
                    'u' => {
                        let text = value().unwrap_or_default();
                        match text.parse::<u32>() {
                            Ok(n) => fd = n,
                            Err(_) => {
                                err(
                                    sh,
                                    "read",
                                    &format!("{text}: invalid file descriptor specification"),
                                )
                                .await?;
                                return Ok(1);
                            }
                        }
                        break;
                    }
                    other => {
                        err(sh, "read", &format!("-{other}: invalid option")).await?;
                        err_usage(sh, "read", "read [-Eers] [-a array] [-d delim] [-i text] [-n nchars] [-N nchars] [-p prompt] [-t timeout] [-u fd] [name ...]").await?;
                        return Ok(2);
                    }
                }
            }
            continue;
        }
        if arg == "--" && names.is_empty() {
            continue;
        }
        names.push(arg.clone());
    }
    for name in names.iter().chain(array.iter()) {
        if parse_target(name).is_none() {
            err(sh, "read", &format!("`{name}': not a valid identifier")).await?;
            return Ok(1);
        }
    }
    if let Some(prompt) = prompt {
        sh.error_text(&prompt).await?;
    }
    if exact {
        delimiter = None;
    }
    // Read a record, joining lines ended by a backslash when not raw.
    let mut text: Vec<u8> = Vec::new();
    let mut eof;
    let mut escaped_positions: Vec<usize> = Vec::new();
    loop {
        let Some(record) = read_record(
            sh,
            fd,
            delimiter,
            count.map(|n| n.saturating_sub(text.len())),
        )
        .await?
        else {
            err(
                sh,
                "read",
                &format!("{fd}: invalid file descriptor: Bad file descriptor"),
            )
            .await?;
            return Ok(1);
        };
        eof = record.eof && !record.delimited;
        if raw || exact {
            text.extend_from_slice(&record.bytes);
            break;
        }
        // Process backslashes: a backslash escapes the next byte and is removed.
        let mut bytes = record.bytes.iter().copied().peekable();
        let mut continued = false;
        while let Some(byte) = bytes.next() {
            if byte == b'\\' {
                match bytes.next() {
                    Some(next) => {
                        escaped_positions.push(text.len());
                        text.push(next);
                    }
                    None => {
                        if record.delimited && delimiter == Some(b'\n') {
                            continued = true;
                        }
                    }
                }
            } else {
                text.push(byte);
            }
        }
        if continued {
            continue;
        }
        break;
    }
    let line = String::from_utf8_lossy(&text).into_owned();
    let ifs = sh.ifs().unwrap_or_default();
    let ifs = if sh.vars.get("IFS").is_none() {
        " \t\n".to_owned()
    } else {
        ifs
    };
    if let Some(name) = array {
        let fields = if exact {
            vec![line]
        } else {
            split_escaped(&line, &ifs, 0, &escaped_positions)
        };
        let map: BTreeMap<i64, String> = fields
            .into_iter()
            .enumerate()
            .map(|(i, v)| (i64::try_from(i).unwrap_or(0), v))
            .collect();
        set_value(sh, &name, Value::Indexed(map))?;
        if let Some(var) = sh.vars.get_mut(&name) {
            var.attrs &= !vars::ASSOC;
        }
    } else if names.is_empty() {
        let value = if exact || raw && false { line } else { line };
        assign_scalar(sh, "REPLY", value, false).await?;
    } else if exact {
        let mut names_iter = names.iter();
        if let Some(first) = names_iter.next() {
            assign_scalar(sh, first, line, false).await?;
        }
        for name in names_iter {
            assign_scalar(sh, name, String::new(), false).await?;
        }
    } else {
        let fields = split_escaped(&line, &ifs, names.len(), &escaped_positions);
        for (n, name) in names.iter().enumerate() {
            let value = fields.get(n).cloned().unwrap_or_default();
            match parse_target(name) {
                Some((base, Some(sub))) => {
                    let index = if sh.vars.get(&base).is_some_and(Var::is_assoc) {
                        Index::Key(sub)
                    } else {
                        Index::Number(super::arith::evaluate(sh, &sub).unwrap_or(0))
                    };
                    assign_element(sh, &base, index, value, false).await?;
                }
                _ => assign_scalar(sh, name, value, false).await?,
            }
        }
    }
    Ok(i32::from(eof))
}

/// Split a read line, where escaped characters never delimit.
fn split_escaped(line: &str, ifs: &str, max: usize, escaped: &[usize]) -> Vec<String> {
    if escaped.is_empty() {
        return split_read(line, ifs, max);
    }
    // Replace escaped IFS characters by private-use stand-ins while splitting.
    let mut marked = String::new();
    let mut byte_index = 0usize;
    let mut stand_ins = BTreeMap::new();
    for ch in line.chars() {
        if escaped.contains(&byte_index) && ifs.contains(ch) {
            let stand_in = char::from_u32(
                0xF0000u32.saturating_add(u32::try_from(stand_ins.len()).unwrap_or(0)),
            )
            .unwrap_or(ch);
            stand_ins.insert(stand_in, ch);
            marked.push(stand_in);
        } else {
            marked.push(ch);
        }
        byte_index = byte_index.saturating_add(ch.len_utf8());
    }
    split_read(&marked, ifs, max)
        .into_iter()
        .map(|field| {
            field
                .chars()
                .map(|c| stand_ins.get(&c).copied().unwrap_or(c))
                .collect()
        })
        .collect()
}

async fn err_usage(sh: &mut Shell, name: &str, usage: &str) -> Result<(), Flow> {
    sh.error_text(&format!("{name}: usage: {usage}\n")).await?;
    Ok(())
}

async fn mapfile(ctx: &Ctx<'_>, sh: &mut Shell, name: &str, args: &[String]) -> Status {
    let mut trim = false;
    let mut count: Option<usize> = None;
    let mut skip = 0usize;
    let mut origin: Option<i64> = None;
    let mut delimiter = b'\n';
    let mut fd = 0u32;
    let mut callback: Option<String> = None;
    let mut quantum = 5000usize;
    let mut target = "MAPFILE".to_owned();
    let mut index = 0;
    while let Some(arg) = args.get(index) {
        index += 1;
        let mut value = || {
            let v = args.get(index).cloned().unwrap_or_default();
            index += 1;
            v
        };
        match arg.as_str() {
            "-t" => trim = true,
            "-n" => count = value().parse().ok().filter(|n| *n > 0),
            "-s" => skip = value().parse().unwrap_or(0),
            "-O" => origin = value().parse().ok(),
            "-d" => delimiter = value().bytes().next().unwrap_or(0),
            "-u" => fd = value().parse().unwrap_or(0),
            "-C" => callback = Some(value()),
            "-c" => quantum = value().parse().unwrap_or(5000).max(1),
            other => target = other.to_owned(),
        }
    }
    let mut map = match origin {
        Some(_) => match sh.vars.get(&target).and_then(|v| v.value.clone()) {
            Some(Value::Indexed(map)) => map,
            _ => BTreeMap::new(),
        },
        None => BTreeMap::new(),
    };
    let mut next = origin.unwrap_or(0);
    let mut read_lines = 0usize;
    let mut skipped = 0usize;
    loop {
        if count.is_some_and(|n| read_lines >= n) {
            break;
        }
        let Some(record) = read_record(sh, fd, Some(delimiter), None).await? else {
            err(
                sh,
                name,
                &format!("{fd}: invalid file descriptor: Bad file descriptor"),
            )
            .await?;
            return Ok(1);
        };
        if record.bytes.is_empty() && !record.delimited {
            break;
        }
        if skipped < skip {
            skipped += 1;
            continue;
        }
        let mut line = String::from_utf8_lossy(&record.bytes).into_owned();
        if record.delimited && !trim {
            line.push(char::from(delimiter));
        }
        if let Some(callback) = &callback {
            if read_lines % quantum == 0 && read_lines > 0 || quantum == 1 {
                let words = vec![callback.clone(), next.to_string(), line.clone()];
                let call: Vec<String> = callback
                    .split_whitespace()
                    .map(str::to_owned)
                    .chain(words.into_iter().skip(1))
                    .collect();
                if let Some(def) = sh
                    .functions
                    .get(call.first().map_or("", String::as_str))
                    .cloned()
                {
                    call_function(ctx, sh, &def, call).await?;
                }
            }
        }
        map.insert(next, line);
        next = next.saturating_add(1);
        read_lines += 1;
        if !record.delimited {
            break;
        }
    }
    set_value(sh, &target, Value::Indexed(map))?;
    Ok(0)
}

// ---------------------------------------------------------------------------
// cd
// ---------------------------------------------------------------------------

async fn is_directory(sh: &mut Shell, path: &str) -> Result<Option<bool>, Flow> {
    let key = sh.key();
    let reply = io::host_call(
        &sh.hub,
        key,
        Request::Stat {
            path: path.to_owned(),
        },
    )
    .await?;
    Ok(match reply {
        Reply::Stat { kind, .. } => Some(kind == EntryKind::Directory),
        _ => None,
    })
}

async fn cd(sh: &mut Shell, args: &[String]) -> Status {
    let mut rest: Vec<&String> = args
        .iter()
        .filter(|a| !matches!(a.as_str(), "-L" | "-P" | "-e" | "-@"))
        .collect();
    if rest.first().is_some_and(|a| a.as_str() == "--") {
        rest.remove(0);
    }
    if rest.len() > 1 {
        err(sh, "cd", "too many arguments").await?;
        return Ok(2);
    }
    let mut print = false;
    let target = match rest.first() {
        None => match sh.get_var("HOME") {
            Some(home) => home,
            None => {
                err(sh, "cd", "HOME not set").await?;
                return Ok(1);
            }
        },
        Some(arg) if arg.as_str() == "-" => match sh.get_var("OLDPWD") {
            Some(old) => {
                print = true;
                old
            }
            None => {
                err(sh, "cd", "OLDPWD not set").await?;
                return Ok(1);
            }
        },
        Some(arg) => (*arg).clone(),
    };
    if target.is_empty() {
        err(sh, "cd", "null directory").await?;
        return Ok(1);
    }
    let mut destination = None;
    if !target.starts_with('/')
        && !target.starts_with("./")
        && !target.starts_with("../")
        && target != "."
        && target != ".."
    {
        if let Some(cdpath) = sh.get_var("CDPATH") {
            for entry in cdpath.split(':') {
                let candidate = if entry.is_empty() {
                    format!("{}/{}", sh.cwd, target)
                } else {
                    format!("{entry}/{target}")
                };
                let full = absolute(sh, &candidate);
                if is_directory(sh, &full).await? == Some(true) {
                    if !entry.is_empty() {
                        print = true;
                    }
                    destination = Some(full);
                    break;
                }
            }
        }
    }
    let full = match destination {
        Some(full) => full,
        None => {
            let logical = if target.starts_with('/') {
                if target.starts_with("//") && !target.starts_with("///") {
                    format!("/{}", exec::normalize(&target))
                } else {
                    exec::normalize(&target)
                }
            } else {
                absolute(sh, &target)
            };
            match is_directory(sh, &exec::normalize(&logical)).await? {
                Some(true) => logical,
                Some(false) => {
                    err(sh, "cd", &format!("{target}: Not a directory")).await?;
                    return Ok(1);
                }
                None => {
                    err(sh, "cd", &format!("{target}: No such file or directory")).await?;
                    return Ok(1);
                }
            }
        }
    };
    let old = sh.cwd.clone();
    sh.cwd = full.trim_start_matches("//").to_owned();
    if !sh.cwd.starts_with('/') {
        sh.cwd = full.clone();
    }
    let shown = full.replace("///", "/");
    sh.cwd = exec::normalize(&shown);
    let pwd = if shown.starts_with("//") && !shown.starts_with("///") {
        format!("/{}", sh.cwd)
    } else {
        sh.cwd.clone()
    };
    set_value(sh, "OLDPWD", Value::Scalar(old))?;
    set_value(sh, "PWD", Value::Scalar(pwd.clone()))?;
    if print {
        out(sh, &format!("{pwd}\n")).await?;
    }
    Ok(0)
}

// ---------------------------------------------------------------------------
// Declarations
// ---------------------------------------------------------------------------

async fn declare(ctx: &Ctx<'_>, sh: &mut Shell, name: &str, args: Vec<Expanded>) -> Status {
    let mut args = args.into_iter();
    args.next();
    let mut set_attrs: u16 = 0;
    let mut clear_attrs: u16 = 0;
    let mut print = false;
    let mut functions = false;
    let mut function_names = false;
    let mut global = false;
    let mut operands: Vec<Expanded> = Vec::new();
    let mut options_done = false;
    match name {
        "export" => set_attrs |= vars::EXPORT,
        "readonly" => set_attrs |= vars::READONLY,
        _ => {}
    }
    for arg in args {
        if let Expanded::Field(text) = &arg {
            if !options_done && text == "--" {
                options_done = true;
                continue;
            }
            if !options_done && (text.starts_with('-') || text.starts_with('+')) && text.len() > 1 {
                let adding = text.starts_with('-');
                for flag in text.chars().skip(1) {
                    let bit = match flag {
                        'a' => vars::INDEXED,
                        'A' => vars::ASSOC,
                        'i' => vars::INTEGER,
                        'l' => vars::LOWER,
                        'u' => vars::UPPER,
                        'r' => vars::READONLY,
                        'x' => vars::EXPORT,
                        'n' => vars::NAMEREF,
                        't' => vars::TRACE,
                        'c' => vars::CAPITALIZE,
                        'p' => {
                            print = true;
                            0
                        }
                        'f' => {
                            functions = true;
                            0
                        }
                        'F' => {
                            function_names = true;
                            0
                        }
                        'g' => {
                            global = true;
                            0
                        }
                        'I' => 0,
                        other => {
                            err(sh, name, &format!("-{other}: invalid option")).await?;
                            return Ok(2);
                        }
                    };
                    if adding {
                        set_attrs |= bit;
                    } else {
                        clear_attrs |= bit;
                    }
                }
                continue;
            }
        }
        options_done = true;
        operands.push(arg);
    }
    if name == "local" && sh.function_depth == 0 {
        err(sh, "local", "can only be used in a function").await?;
        return Ok(1);
    }
    if functions || function_names {
        return print_functions(sh, &operands, function_names).await;
    }
    if operands.is_empty() {
        if print || set_attrs != 0 || matches!(name, "export" | "readonly") {
            return list_declarations(sh, name, set_attrs).await;
        }
        return list_declarations(sh, name, 0).await;
    }
    let local = (name == "local"
        || (sh.function_depth > 0 && matches!(name, "declare" | "typeset")))
        && !global;
    let mut status = 0;
    for operand in operands {
        let (var_name, value): (String, Option<Pending>) = match operand {
            Expanded::Assign(assignment) => {
                let pending = match &assignment.value {
                    AssignValue::Scalar(word) => Pending::Scalar(
                        expand_single(ctx, sh, word, Mode::Assignment).await?,
                        assignment.append,
                        assignment.index.clone(),
                    ),
                    AssignValue::Array(elements) => {
                        Pending::Array(elements.clone(), assignment.append)
                    }
                };
                (assignment.name.clone(), Some(pending))
            }
            Expanded::Field(text) => match text.split_once('=') {
                Some((lhs, rhs)) => {
                    let (lhs, append) = match lhs.strip_suffix('+') {
                        Some(base) => (base.to_owned(), true),
                        None => (lhs.to_owned(), false),
                    };
                    (lhs, Some(Pending::Scalar(rhs.to_owned(), append, None)))
                }
                None => (text, None),
            },
        };
        let (base, sub) = match parse_target(&var_name) {
            Some(parts) => parts,
            None => {
                err(sh, name, &format!("`{var_name}': not a valid identifier")).await?;
                status = 1;
                continue;
            }
        };
        if print {
            match sh.vars.get(&base) {
                Some(var) => {
                    let text = quote::declaration(&base, var);
                    out(sh, &format!("{text}\n")).await?;
                }
                None => {
                    err(sh, name, &format!("{base}: not found")).await?;
                    status = 1;
                }
            }
            continue;
        }
        let existing = sh.vars.get(&base).cloned();
        if existing.as_ref().is_some_and(|v| v.has(vars::READONLY))
            && (value.is_some() || clear_attrs & vars::READONLY != 0)
        {
            err(sh, name, &format!("{base}: readonly variable")).await?;
            status = 1;
            continue;
        }
        if set_attrs & vars::ASSOC != 0
            && existing
                .as_ref()
                .is_some_and(|v| v.is_array() && !v.is_assoc())
        {
            err(
                sh,
                name,
                &format!("{base}: cannot convert indexed to associative array"),
            )
            .await?;
            status = 1;
            continue;
        }
        if set_attrs & vars::INDEXED != 0 && existing.as_ref().is_some_and(Var::is_assoc) {
            err(
                sh,
                name,
                &format!("{base}: cannot convert associative to indexed array"),
            )
            .await?;
            status = 1;
            continue;
        }
        // Make the variable where it belongs.
        if local {
            let current = sh.vars.get(&base).cloned();
            let here = sh.vars.is_local_here(&base);
            if let Some(var) = sh.vars.local(&base) {
                if !here {
                    if let Some(current) = current {
                        if sh.options.shopt("localvar_inherit") {
                            *var = current;
                        } else {
                            var.attrs = current.attrs & (vars::EXPORT);
                        }
                    }
                }
            }
        } else if global && sh.vars.get(&base).is_none() {
            sh.vars.global.entry(base.clone()).or_insert(Var {
                value: None,
                attrs: 0,
            });
        } else {
            sh.vars.entry(&base);
        }
        let var = if global {
            sh.vars.global.get_mut(&base)
        } else {
            sh.vars.get_mut(&base)
        };
        if let Some(var) = var {
            var.attrs |= set_attrs & !vars::READONLY;
            var.attrs &= !(clear_attrs & !vars::INDEXED & !vars::ASSOC);
            if set_attrs & vars::LOWER != 0 {
                var.attrs &= !vars::UPPER;
            }
            if set_attrs & vars::UPPER != 0 {
                var.attrs &= !vars::LOWER;
            }
            if set_attrs & vars::ASSOC != 0 && var.value.is_none() {
                var.value = None;
            }
            if set_attrs & vars::INDEXED != 0 {
                if let Some(Value::Scalar(text)) = var.value.clone() {
                    var.value = Some(Value::Indexed(BTreeMap::from([(0, text)])));
                }
            }
            if set_attrs & vars::LOWER != 0 || set_attrs & vars::UPPER != 0 {
                if let Some(Value::Scalar(text)) = &var.value {
                    let changed = if set_attrs & vars::LOWER != 0 {
                        text.to_lowercase()
                    } else {
                        text.to_uppercase()
                    };
                    var.value = Some(Value::Scalar(changed));
                }
            }
        }
        match value {
            Some(Pending::Scalar(text, append, index)) => {
                if set_attrs & vars::NAMEREF != 0 {
                    set_value(sh, &base, Value::Scalar(text))?;
                } else if let Some(sub) = sub.or_else(|| index.and_then(|w| w.static_text())) {
                    let index = if sh.vars.get(&base).is_some_and(Var::is_assoc) {
                        Index::Key(sub)
                    } else {
                        Index::Number(super::arith::evaluate(sh, &sub).unwrap_or(0))
                    };
                    assign_element(sh, &base, index, text, append).await?;
                } else if sh.vars.get(&base).is_some_and(|v| v.has(vars::ASSOC))
                    && text.starts_with('(')
                {
                    status = 1;
                } else {
                    match assign_scalar(sh, &base, text, append).await {
                        Ok(()) => {}
                        Err(Flow::CommandFailed(code)) => status = code,
                        Err(Flow::Return(code)) => status = code,
                        Err(flow) => return Err(flow),
                    }
                }
            }
            Some(Pending::Array(elements, append)) => {
                if sh.vars.get(&base).is_some_and(|v| v.has(vars::ASSOC))
                    && sh.vars.get(&base).is_some_and(|v| v.value.is_none())
                {
                    set_value(sh, &base, Value::Assoc(AssocMap::new()))?;
                }
                assign_array(ctx, sh, &base, &elements, append).await?;
            }
            None => {
                if set_attrs & vars::ASSOC != 0
                    && sh.vars.get(&base).is_some_and(|v| v.value.is_none())
                {
                    // Declared, still unset.
                }
            }
        }
        if set_attrs & vars::READONLY != 0 {
            if let Some(var) = sh.vars.get_mut(&base) {
                var.attrs |= vars::READONLY;
            }
        }
    }
    Ok(status)
}

enum Pending {
    Scalar(String, bool, Option<crate::syntax::ast::Word>),
    Array(Vec<crate::syntax::ast::ArrayElement>, bool),
}

async fn list_declarations(sh: &mut Shell, name: &str, attrs: u16) -> Status {
    let mut lines = String::new();
    for var_name in sh.vars.names() {
        let Some(var) = sh.vars.get(&var_name) else {
            continue;
        };
        if attrs != 0 && var.attrs & attrs == 0 {
            continue;
        }
        if name == "export" && var.value.is_none() && !var.has(vars::EXPORT) {
            continue;
        }
        lines.push_str(&quote::declaration(&var_name, var));
        lines.push('\n');
    }
    out(sh, &lines).await?;
    Ok(0)
}

async fn print_functions(sh: &mut Shell, operands: &[Expanded], names_only: bool) -> Status {
    let names: Vec<String> = if operands.is_empty() {
        sh.functions.keys().cloned().collect()
    } else {
        operands
            .iter()
            .map(|op| match op {
                Expanded::Field(text) => text.clone(),
                Expanded::Assign(a) => a.name.clone(),
            })
            .collect()
    };
    let mut status = 0;
    for name in names {
        match sh.functions.get(&name).cloned() {
            Some(def) => {
                let text = if names_only {
                    format!("declare -f {name}\n")
                } else {
                    format!("{}\n", super::deparse::function(&def, &sh.source))
                };
                out(sh, &text).await?;
            }
            None => status = 1,
        }
    }
    Ok(status)
}

async fn unset(sh: &mut Shell, args: &[String]) -> Status {
    let mut functions = false;
    let mut variables = false;
    let mut nameref = false;
    let mut status = 0;
    for arg in args {
        match arg.as_str() {
            "-f" => {
                functions = true;
                continue;
            }
            "-v" => {
                variables = true;
                continue;
            }
            "-n" => {
                nameref = true;
                continue;
            }
            _ => {}
        }
        if functions && !variables {
            sh.functions.remove(arg);
            continue;
        }
        match parse_target(arg) {
            Some((base, Some(sub))) => {
                let base = resolve_nameref(sh, &base);
                if let Some(var) = sh.vars.get(&base) {
                    if var.has(vars::READONLY) {
                        err(
                            sh,
                            "unset",
                            &format!("{base}: cannot unset: readonly variable"),
                        )
                        .await?;
                        status = 1;
                        continue;
                    }
                }
                let is_assoc = sh.vars.get(&base).is_some_and(Var::is_assoc);
                if sub == "@" || sub == "*" {
                    sh.vars.unset(&base);
                    continue;
                }
                let index = if is_assoc {
                    None
                } else {
                    Some(super::arith::evaluate(sh, &sub).unwrap_or(0))
                };
                if let Some(var) = sh.vars.get_mut(&base) {
                    match (&mut var.value, index) {
                        (Some(Value::Assoc(map)), _) => {
                            map.remove(&sub);
                        }
                        (Some(Value::Indexed(map)), Some(mut n)) => {
                            if n < 0 {
                                n = map
                                    .keys()
                                    .next_back()
                                    .map_or(0, |k| k.saturating_add(1))
                                    .saturating_add(n);
                            }
                            map.remove(&n);
                        }
                        (Some(Value::Scalar(_)), Some(0)) => {
                            var.value = None;
                        }
                        _ => {}
                    }
                }
            }
            Some((base, None)) => {
                let target = if nameref {
                    base.clone()
                } else {
                    resolve_nameref(sh, &base)
                };
                if let Some(var) = sh.vars.get(&target) {
                    if var.has(vars::READONLY) {
                        err(
                            sh,
                            "unset",
                            &format!("{target}: cannot unset: readonly variable"),
                        )
                        .await?;
                        status = 1;
                        continue;
                    }
                    let footprint = var.footprint();
                    sh.hub.borrow_mut().release(footprint);
                    sh.vars.unset(&target);
                } else if !variables && sh.functions.contains_key(&target) {
                    sh.functions.remove(&target);
                } else {
                    sh.vars.unset(&target);
                }
            }
            None => {
                if !arg.contains('-') {
                    err(sh, "unset", &format!("`{arg}': not a valid identifier")).await?;
                    status = 1;
                }
            }
        }
    }
    Ok(status)
}

// ---------------------------------------------------------------------------
// Positional parameters and options
// ---------------------------------------------------------------------------

async fn shift(sh: &mut Shell, args: &[String]) -> Status {
    let count = match args.first() {
        Some(text) => match text.parse::<i64>() {
            Ok(n) if n >= 0 => usize::try_from(n).unwrap_or(usize::MAX),
            Ok(_) => {
                err(sh, "shift", &format!("{text}: shift count out of range")).await?;
                return Ok(1);
            }
            Err(_) => {
                err(sh, "shift", &format!("{text}: numeric argument required")).await?;
                return Ok(2);
            }
        },
        None => 1,
    };
    if count > sh.positional.len() {
        if sh.options.shopt("shift_verbose") {
            err(sh, "shift", &format!("{count}: shift count out of range")).await?;
        }
        return Ok(1);
    }
    sh.positional.drain(..count);
    Ok(0)
}

async fn getopts(sh: &mut Shell, args: &[String]) -> Status {
    let (Some(spec), Some(name)) = (args.first().cloned(), args.get(1).cloned()) else {
        err(sh, "getopts", "usage: getopts optstring name [arg ...]").await?;
        return Ok(2);
    };
    let params: Vec<String> = if args.len() > 2 {
        args.get(2..).unwrap_or_default().to_vec()
    } else {
        sh.positional.clone()
    };
    let silent = spec.starts_with(':');
    let spec_chars: Vec<char> = spec.trim_start_matches(':').chars().collect();
    let mut optind: usize = sh
        .get_var("OPTIND")
        .and_then(|v| v.parse().ok())
        .unwrap_or(1)
        .max(1);
    if sh.getopts_char > 0 && optind != sh.getopts_optind {
        sh.getopts_char = 0;
    }
    let finish = |sh: &mut Shell, optind: usize| {
        sh.getopts_optind = optind;
        sh.set_plain("OPTIND", &optind.to_string());
    };
    let Some(current) = params.get(optind.saturating_sub(1)).cloned() else {
        sh.getopts_char = 0;
        finish(sh, optind);
        assign_scalar(sh, &name, "?".to_owned(), false).await?;
        return Ok(1);
    };
    if sh.getopts_char == 0 {
        if current == "--" {
            sh.getopts_char = 0;
            finish(sh, optind.saturating_add(1));
            assign_scalar(sh, &name, "?".to_owned(), false).await?;
            return Ok(1);
        }
        if !current.starts_with('-') || current == "-" {
            finish(sh, optind);
            assign_scalar(sh, &name, "?".to_owned(), false).await?;
            return Ok(1);
        }
        sh.getopts_char = 1;
    }
    let chars: Vec<char> = current.chars().collect();
    let Some(&option) = chars.get(sh.getopts_char) else {
        sh.getopts_char = 0;
        finish(sh, optind.saturating_add(1));
        return Box::pin(getopts(sh, args)).await;
    };
    sh.getopts_char = sh.getopts_char.saturating_add(1);
    let at_end = sh.getopts_char >= chars.len();
    if at_end {
        sh.getopts_char = 0;
        optind = optind.saturating_add(1);
    }
    let position = spec_chars.iter().position(|c| *c == option && *c != ':');
    match position {
        None => {
            finish(sh, optind);
            if silent {
                assign_scalar(sh, &name, "?".to_owned(), false).await?;
                set_value(sh, "OPTARG", Value::Scalar(option.to_string()))?;
            } else {
                sh.error_text(&format!(
                    "bash: line {}: illegal option -- {}\n",
                    sh.lineno, option
                ))
                .await?;
                assign_scalar(sh, &name, "?".to_owned(), false).await?;
                sh.vars.unset("OPTARG");
            }
            Ok(0)
        }
        Some(at) => {
            let takes_argument = spec_chars.get(at.saturating_add(1)) == Some(&':');
            if takes_argument {
                let argument = if !at_end {
                    let rest: String = chars
                        .get(sh.getopts_char..)
                        .unwrap_or_default()
                        .iter()
                        .collect();
                    sh.getopts_char = 0;
                    optind = optind.saturating_add(1);
                    Some(rest)
                } else {
                    let value = params.get(optind.saturating_sub(1)).cloned();
                    if value.is_some() {
                        optind = optind.saturating_add(1);
                    }
                    value
                };
                finish(sh, optind);
                match argument {
                    Some(argument) => {
                        set_value(sh, "OPTARG", Value::Scalar(argument))?;
                        assign_scalar(sh, &name, option.to_string(), false).await?;
                    }
                    None => {
                        if silent {
                            assign_scalar(sh, &name, ":".to_owned(), false).await?;
                            set_value(sh, "OPTARG", Value::Scalar(option.to_string()))?;
                        } else {
                            sh.error_text(&format!(
                                "bash: line {}: option requires an argument -- {}\n",
                                sh.lineno, option
                            ))
                            .await?;
                            assign_scalar(sh, &name, "?".to_owned(), false).await?;
                            sh.vars.unset("OPTARG");
                        }
                    }
                }
            } else {
                finish(sh, optind);
                assign_scalar(sh, &name, option.to_string(), false).await?;
                sh.vars.unset("OPTARG");
            }
            Ok(0)
        }
    }
}

async fn set(sh: &mut Shell, args: &[String]) -> Status {
    if args.is_empty() {
        let mut lines = String::new();
        for name in sh.vars.names() {
            if let Some(var) = sh.vars.get(&name) {
                if let Some(Value::Scalar(text)) = &var.value {
                    lines.push_str(&format!("{}={}\n", name, quote::trace(text)));
                }
            }
        }
        out(sh, &lines).await?;
        return Ok(0);
    }
    let mut index = 0;
    while let Some(arg) = args.get(index) {
        index += 1;
        if arg == "--" {
            sh.positional = args.get(index..).unwrap_or_default().to_vec();
            return Ok(0);
        }
        if arg == "-" {
            sh.options.xtrace = false;
            sh.options.verbose = false;
            if index < args.len() {
                sh.positional = args.get(index..).unwrap_or_default().to_vec();
            }
            return Ok(0);
        }
        let (on, flags) = match arg.strip_prefix('-') {
            Some(flags) => (true, flags),
            None => match arg.strip_prefix('+') {
                Some(flags) => (false, flags),
                None => {
                    sh.positional = args
                        .get(index.saturating_sub(1)..)
                        .unwrap_or_default()
                        .to_vec();
                    return Ok(0);
                }
            },
        };
        for flag in flags.chars() {
            if flag == 'o' {
                match args.get(index) {
                    Some(name) => {
                        index += 1;
                        match sh.options.set_option(name) {
                            Some(slot) => *slot = on,
                            None => {
                                err(sh, "set", &format!("{name}: invalid option name")).await?;
                                return Ok(2);
                            }
                        }
                    }
                    None => {
                        list_set_options(sh, on).await?;
                    }
                }
                continue;
            }
            match Options::letter_name(flag).and_then(|name| sh.options.set_option(name)) {
                Some(slot) => *slot = on,
                None => {
                    if flag != 'H' {
                        err(sh, "set", &format!("-{flag}: invalid option")).await?;
                        return Ok(2);
                    }
                }
            }
        }
    }
    Ok(0)
}

async fn list_set_options(sh: &mut Shell, verbose: bool) -> Result<(), Flow> {
    let mut lines = String::new();
    for name in Options::set_names() {
        let on = sh.options.get_set_option(name).unwrap_or(false);
        if verbose {
            lines.push_str(&format!(
                "{:<15}\t{}\n",
                name,
                if on { "on" } else { "off" }
            ));
        } else {
            lines.push_str(&format!("set {}o {}\n", if on { "-" } else { "+" }, name));
        }
    }
    out(sh, &lines).await
}

async fn shopt(sh: &mut Shell, args: &[String]) -> Status {
    let mut set_on = None;
    let mut quiet = false;
    let mut print = false;
    let mut set_style = false;
    let mut names = Vec::new();
    for arg in args {
        match arg.as_str() {
            "-s" => set_on = Some(true),
            "-u" => set_on = Some(false),
            "-q" => quiet = true,
            "-p" => print = true,
            "-o" => set_style = true,
            other => names.push(other.to_owned()),
        }
    }
    let mut status = 0;
    if set_style {
        for name in &names {
            match set_on {
                Some(on) => match sh.options.set_option(name) {
                    Some(slot) => *slot = on,
                    None => {
                        err(sh, "shopt", &format!("{name}: invalid option name")).await?;
                        status = 1;
                    }
                },
                None => {
                    let on = sh.options.get_set_option(name);
                    match on {
                        Some(on) => {
                            if !quiet {
                                let text = if print {
                                    format!("set {}o {}\n", if on { "-" } else { "+" }, name)
                                } else {
                                    format!("{:<15}\t{}\n", name, if on { "on" } else { "off" })
                                };
                                out(sh, &text).await?;
                            }
                            if !on {
                                status = 1;
                            }
                        }
                        None => {
                            err(sh, "shopt", &format!("{name}: invalid option name")).await?;
                            status = 1;
                        }
                    }
                }
            }
        }
        return Ok(status);
    }
    let all: Vec<&str> = SHOPT_DEFAULTS.iter().map(|(name, _)| *name).collect();
    let selected: Vec<String> = if names.is_empty() {
        all.iter().map(|s| (*s).to_owned()).collect()
    } else {
        names.clone()
    };
    for name in selected {
        let Some(known) = all.iter().find(|n| **n == name).copied() else {
            err(sh, "shopt", &format!("{name}: invalid shell option name")).await?;
            status = 1;
            continue;
        };
        match set_on {
            Some(on) => {
                if names.is_empty() {
                    continue;
                }
                sh.options.shopt.insert(known, on);
            }
            None => {
                let on = sh.options.shopt(known);
                if names.is_empty() && print == false && quiet {
                    continue;
                }
                if !quiet {
                    let text = if print {
                        format!("shopt {} {}\n", if on { "-s" } else { "-u" }, known)
                    } else {
                        format!("{:<20}\t{}\n", known, if on { "on" } else { "off" })
                    };
                    out(sh, &text).await?;
                }
                if !on {
                    status = 1;
                }
            }
        }
    }
    if set_on.is_some() && names.is_empty() {
        // `shopt -s` alone lists the options that are on.
        for name in all {
            let on = sh.options.shopt(name);
            if Some(on) == set_on {
                out(
                    sh,
                    &format!("{:<20}\t{}\n", name, if on { "on" } else { "off" }),
                )
                .await?;
            }
        }
        return Ok(0);
    }
    Ok(status)
}

// ---------------------------------------------------------------------------
// type, command, wait
// ---------------------------------------------------------------------------

async fn type_builtin(sh: &mut Shell, args: &[String]) -> Status {
    let mut terse = false;
    let mut all = false;
    let mut path_only = false;
    let mut names = Vec::new();
    for arg in args {
        match arg.as_str() {
            "-t" => terse = true,
            "-a" => all = true,
            "-p" | "-P" => path_only = true,
            "-f" => {}
            other => names.push(other.to_owned()),
        }
    }
    let mut status = 0;
    for name in names {
        let mut found = false;
        if KEYWORDS.contains(&name.as_str()) && !path_only {
            out(
                sh,
                &if terse {
                    "keyword\n".to_owned()
                } else {
                    format!("{name} is a shell keyword\n")
                },
            )
            .await?;
            found = true;
            if !all {
                continue;
            }
        }
        if let Some(def) = sh.functions.get(&name).cloned() {
            if !path_only {
                let text = if terse {
                    "function\n".to_owned()
                } else {
                    format!(
                        "{name} is a function\n{}\n",
                        super::deparse::function(&def, &sh.source)
                    )
                };
                out(sh, &text).await?;
                found = true;
                if !all {
                    continue;
                }
            }
        }
        if is_builtin(&name) && !path_only {
            out(
                sh,
                &if terse {
                    "builtin\n".to_owned()
                } else {
                    format!("{name} is a shell builtin\n")
                },
            )
            .await?;
            found = true;
            if !all {
                continue;
            }
        }
        if sh.programs.contains_key(&name) {
            let path = format!("/usr/bin/{name}");
            let text = if terse {
                "file\n".to_owned()
            } else if path_only {
                format!("{path}\n")
            } else {
                format!("{name} is {path}\n")
            };
            out(sh, &text).await?;
            found = true;
        }
        if !found {
            if !terse && !path_only {
                err(sh, "type", &format!("{name}: not found")).await?;
            }
            status = 1;
        }
    }
    Ok(status)
}

async fn command(ctx: &Ctx<'_>, sh: &mut Shell, args: &[String]) -> Status {
    let mut describe = None;
    let mut index = 0;
    while let Some(arg) = args.get(index) {
        match arg.as_str() {
            "-v" => describe = Some(false),
            "-V" => describe = Some(true),
            "-p" => {}
            "--" => {
                index += 1;
                break;
            }
            _ => break,
        }
        index += 1;
    }
    let rest: Vec<String> = args.get(index..).unwrap_or_default().to_vec();
    if let Some(verbose) = describe {
        let source = sh.source.clone();
        let mut status = 0;
        for name in &rest {
            let line = if sh.functions.contains_key(name) {
                if verbose {
                    format!(
                        "{name} is a function\n{}\n",
                        sh.functions
                            .get(name)
                            .map(|d| super::deparse::function(d, &source))
                            .unwrap_or_default()
                    )
                } else {
                    format!("{name}\n")
                }
            } else if KEYWORDS.contains(&name.as_str()) {
                if verbose {
                    format!("{name} is a shell keyword\n")
                } else {
                    format!("{name}\n")
                }
            } else if is_builtin(name) {
                if verbose {
                    format!("{name} is a shell builtin\n")
                } else {
                    format!("{name}\n")
                }
            } else if sh.programs.contains_key(name) {
                if verbose {
                    format!("{name} is /usr/bin/{name}\n")
                } else {
                    format!("/usr/bin/{name}\n")
                }
            } else {
                if verbose {
                    err(sh, "command", &format!("{name}: not found")).await?;
                }
                status = 1;
                continue;
            };
            out(sh, &line).await?;
        }
        return Ok(status);
    }
    let Some(name) = rest.first().cloned() else {
        return Ok(0);
    };
    if is_builtin(&name) {
        let args = rest.iter().map(|w| Expanded::Field(w.clone())).collect();
        return Box::pin(run(ctx, sh, &name, rest, args)).await;
    }
    run_program(ctx, sh, &name, rest).await
}

async fn wait(sh: &mut Shell, args: &[String]) -> Status {
    let mut targets = Vec::new();
    let mut any = false;
    let mut store: Option<String> = None;
    let mut index = 0;
    while let Some(arg) = args.get(index) {
        index += 1;
        match arg.as_str() {
            "-n" => any = true,
            "-f" => {}
            "-p" => {
                store = args.get(index).cloned();
                index += 1;
            }
            other => targets.push(other.to_owned()),
        }
    }
    let jobs = sh.jobs.clone();
    let pids: Vec<u32> = if targets.is_empty() {
        jobs.iter().map(|job| job.pid).collect()
    } else {
        let mut pids = Vec::new();
        for target in &targets {
            let pid = if let Some(number) = target.strip_prefix('%') {
                number
                    .parse::<usize>()
                    .ok()
                    .and_then(|n| jobs.iter().find(|j| j.id == n))
                    .map(|j| j.pid)
            } else {
                target.parse::<u32>().ok()
            };
            match pid {
                Some(pid) if sh.hub.borrow().job_status.contains_key(&pid) => pids.push(pid),
                _ => {
                    err(
                        sh,
                        "wait",
                        &format!("pid {target} is not a child of this shell"),
                    )
                    .await?;
                    return Ok(127);
                }
            }
        }
        pids
    };
    let hub = sh.hub.clone();
    let mut status = 0;
    if any {
        let done = std::future::poll_fn(|_| {
            let hub = hub.borrow();
            match pids.iter().find_map(|pid| {
                hub.job_status
                    .get(pid)
                    .copied()
                    .flatten()
                    .map(|s| (*pid, s))
            }) {
                Some(found) => std::task::Poll::Ready(Some(found)),
                None if pids.is_empty() => std::task::Poll::Ready(None),
                None => std::task::Poll::Pending,
            }
        })
        .await;
        return match done {
            Some((pid, code)) => {
                if let Some(name) = store {
                    set_value(sh, &name, Value::Scalar(pid.to_string()))?;
                }
                sh.jobs.retain(|job| job.pid != pid);
                Ok(code)
            }
            None => Ok(127),
        };
    }
    for pid in &pids {
        let code =
            std::future::poll_fn(
                |_| match hub.borrow().job_status.get(pid).copied().flatten() {
                    Some(code) => std::task::Poll::Ready(code),
                    None => std::task::Poll::Pending,
                },
            )
            .await;
        status = code;
        if let Some(name) = &store {
            set_value(sh, name, Value::Scalar(pid.to_string()))?;
        }
    }
    if targets.is_empty() {
        sh.jobs.clear();
        return Ok(0);
    }
    Ok(status)
}

/// `select name in words; do list; done`: a menu on standard error, a choice from standard input.
pub async fn run_select(
    ctx: &Ctx<'_>,
    sh: &mut Shell,
    name: &str,
    items: Vec<String>,
    body: &List,
) -> Status {
    let mut status = 0;
    loop {
        let mut menu = String::new();
        for (index, item) in items.iter().enumerate() {
            menu.push_str(&format!("{}) {}\n", index.saturating_add(1), item));
        }
        sh.error_text(&menu).await?;
        let prompt = sh.get_var("PS3").unwrap_or_else(|| "#? ".to_owned());
        sh.error_text(&prompt).await?;
        let Some(record) = read_record(sh, 0, Some(b'\n'), None).await? else {
            return Ok(1);
        };
        if record.eof && record.bytes.is_empty() {
            sh.error_text("\n").await?;
            return Ok(1);
        }
        let reply = String::from_utf8_lossy(&record.bytes).into_owned();
        set_value(sh, "REPLY", Value::Scalar(reply.clone()))?;
        let choice = reply
            .trim()
            .parse::<usize>()
            .ok()
            .and_then(|n| n.checked_sub(1))
            .and_then(|n| items.get(n))
            .cloned();
        assign_scalar(sh, name, choice.unwrap_or_default(), false).await?;
        match exec::exec_list(ctx, sh, body).await {
            Ok(code) => status = code,
            Err(Flow::Break(_)) => return Ok(status),
            Err(Flow::Continue(_)) => {}
            Err(flow) => return Err(flow),
        }
        if record.eof {
            return Ok(status);
        }
    }
}

/// Keep unused helpers referenced for future builtins.
#[allow(dead_code)]
fn unused(ctx: &Ctx<'_>, sh: &mut Shell, word: &crate::syntax::ast::Word) {
    let _ = (ctx, sh, word, subscript);
}
