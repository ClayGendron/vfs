//! The bytes that cross the module's boundary: JSON text, with every byte
//! string in base64. A host in any language can speak it with its own JSON.

use shell::machine::{
    Config, Entry, EntryKind, HostError, Limits, ProgramKind, Reply, Request, RequestKey,
    StartError, Status, Step, Stream, WriteMode,
};
use shell::syntax::ParseError;

/// Nesting a document may have; deeper input is refused, never recursed into.
const DEPTH: u32 = 32;

#[derive(Clone, Debug, PartialEq)]
pub enum Json {
    Null,
    Bool(bool),
    Number(f64),
    Text(String),
    List(Vec<Json>),
    Object(Vec<(String, Json)>),
}

impl Json {
    pub fn get(&self, key: &str) -> Option<&Json> {
        match self {
            Json::Object(fields) => fields.iter().find(|(k, _)| k == key).map(|(_, v)| v),
            _ => None,
        }
    }

    pub fn text(&self) -> Option<&str> {
        match self {
            Json::Text(text) => Some(text),
            _ => None,
        }
    }

    pub fn number(&self) -> Option<f64> {
        match self {
            Json::Number(n) => Some(*n),
            _ => None,
        }
    }

    pub fn list(&self) -> &[Json] {
        match self {
            Json::List(items) => items,
            _ => &[],
        }
    }

    pub fn bytes(&self) -> Vec<u8> {
        self.text().map(base64_decode).unwrap_or_default()
    }

    fn u64_or(&self, key: &str, default: u64) -> u64 {
        self.get(key)
            .and_then(Json::number)
            .map_or(default, |n| n.max(0.0) as u64)
    }
}

// ---------------------------------------------------------------------------
// Decoding what the host sends
// ---------------------------------------------------------------------------

/// The line and its configuration.
pub fn decode_start(text: &str) -> Result<(String, Config), String> {
    let doc = parse(text)?;
    let source = doc
        .get("source")
        .and_then(Json::text)
        .unwrap_or_default()
        .to_owned();
    let mut config = Config::default();
    for pair in doc.get("env").map(Json::list).unwrap_or_default() {
        if let [Json::Text(k), Json::Text(v)] = pair.list() {
            config.env.push((k.clone(), v.clone()));
        }
    }
    if let Some(cwd) = doc.get("cwd").and_then(Json::text) {
        config.cwd = cwd.to_owned();
    }
    if let Some(name) = doc.get("name").and_then(Json::text) {
        config.name = name.to_owned();
    }
    config.args = doc
        .get("args")
        .map(Json::list)
        .unwrap_or_default()
        .iter()
        .filter_map(|a| a.text().map(str::to_owned))
        .collect();
    config.stdin = doc.get("stdin").map(Json::bytes).unwrap_or_default();
    config.programs = doc
        .get("programs")
        .map(Json::list)
        .unwrap_or_default()
        .iter()
        .filter_map(|p| p.text().map(|name| (name.to_owned(), ProgramKind::Library)))
        .chain(
            doc.get("host_programs")
                .map(Json::list)
                .unwrap_or_default()
                .iter()
                .filter_map(|p| p.text().map(|name| (name.to_owned(), ProgramKind::Host))),
        )
        .collect();
    config.pid = u32::try_from(doc.u64_or("pid", 1000)).unwrap_or(1000);
    if let Some(limits) = doc.get("limits") {
        let defaults = Limits::default();
        config.limits = Limits {
            memory_bytes: usize::try_from(
                limits.u64_or("memory_bytes", defaults.memory_bytes as u64),
            )
            .unwrap_or(usize::MAX),
            loop_iterations: limits.u64_or("loop_iterations", defaults.loop_iterations),
            function_depth: u32::try_from(
                limits.u64_or("function_depth", u64::from(defaults.function_depth)),
            )
            .unwrap_or(u32::MAX),
            nesting: u32::try_from(limits.u64_or("nesting", u64::from(defaults.nesting)))
                .unwrap_or(u32::MAX),
            slice: limits.u64_or("slice", defaults.slice),
            output_bytes: limits.u64_or("output_bytes", defaults.output_bytes),
            parse: shell::syntax::ParseLimits {
                source_bytes: usize::try_from(
                    limits.u64_or("source_bytes", defaults.parse.source_bytes as u64),
                )
                .unwrap_or(usize::MAX),
                tokens: u32::try_from(limits.u64_or("tokens", u64::from(defaults.parse.tokens)))
                    .unwrap_or(u32::MAX),
                depth: u32::try_from(limits.u64_or("depth", u64::from(defaults.parse.depth)))
                    .unwrap_or(u32::MAX),
                pipeline_stages: u32::try_from(
                    limits.u64_or("pipeline_stages", u64::from(defaults.parse.pipeline_stages)),
                )
                .unwrap_or(u32::MAX),
            },
        };
    }
    Ok((source, config))
}

pub fn parse_key(text: &str) -> Option<RequestKey> {
    let (task, ordinal) = text.split_once('#')?;
    let task = task
        .split('.')
        .map(|n| n.parse::<u32>().ok())
        .collect::<Option<Vec<u32>>>()?;
    Some(RequestKey {
        task,
        ordinal: ordinal.parse().ok()?,
    })
}

fn error_of(name: &str) -> HostError {
    match name {
        "not_found" => HostError::NotFound,
        "not_a_directory" => HostError::NotADirectory,
        "is_a_directory" => HostError::IsADirectory,
        "exists" => HostError::Exists,
        "not_empty" => HostError::NotEmpty,
        "permission_denied" => HostError::PermissionDenied,
        "unsupported" => HostError::Unsupported,
        _ => HostError::Invalid,
    }
}

fn kind_of(name: &str) -> EntryKind {
    if name == "directory" {
        EntryKind::Directory
    } else {
        EntryKind::File
    }
}

/// The replies to what the machine asked.
pub fn decode_replies(text: &str) -> Result<Vec<(RequestKey, Reply)>, String> {
    let doc = parse(text)?;
    let mut replies = Vec::new();
    for item in doc.list() {
        let key = item
            .get("key")
            .and_then(Json::text)
            .and_then(parse_key)
            .ok_or("a reply without a key")?;
        let reply = match item.get("reply").and_then(Json::text).unwrap_or_default() {
            "data" => Reply::Data {
                bytes: item.get("bytes").map(Json::bytes).unwrap_or_default(),
                eof: matches!(item.get("eof"), Some(Json::Bool(true))),
            },
            "done" => Reply::Done,
            "stat" => Reply::Stat {
                kind: kind_of(item.get("kind").and_then(Json::text).unwrap_or_default()),
                size: item.u64_or("size", 0),
            },
            "entries" => Reply::Entries(
                item.get("entries")
                    .map(Json::list)
                    .unwrap_or_default()
                    .iter()
                    .filter_map(|e| {
                        Some(Entry {
                            name: e.get("name")?.text()?.to_owned(),
                            kind: kind_of(e.get("kind").and_then(Json::text).unwrap_or_default()),
                        })
                    })
                    .collect(),
            ),
            "text" => Reply::Text(
                item.get("text")
                    .and_then(Json::text)
                    .unwrap_or_default()
                    .to_owned(),
            ),
            "library" => Reply::Library,
            "started" => Reply::Started,
            "output" => Reply::Output {
                stdout: item.get("stdout").map(Json::bytes).unwrap_or_default(),
                stderr: item.get("stderr").map(Json::bytes).unwrap_or_default(),
                status: item.get("status").and_then(Json::number).map(|n| n as i32),
            },
            "refused" => Reply::Refused {
                status: i32::try_from(item.u64_or("status", 126)).unwrap_or(126),
                message: item
                    .get("message")
                    .and_then(Json::text)
                    .unwrap_or_default()
                    .to_owned(),
            },
            _ => Reply::Error(error_of(
                item.get("error").and_then(Json::text).unwrap_or_default(),
            )),
        };
        replies.push((key, reply));
    }
    Ok(replies)
}

// ---------------------------------------------------------------------------
// Encoding what the machine returns
// ---------------------------------------------------------------------------

pub fn encode_step(step: &Step, memory: usize) -> String {
    let mut out = String::from("{\"output\":[");
    for (index, (stream, bytes)) in step.output.iter().enumerate() {
        if index > 0 {
            out.push(',');
        }
        let fd = if *stream == Stream::Stdout { 1 } else { 2 };
        out.push_str(&format!("[{fd},\"{}\"]", base64_encode(bytes)));
    }
    out.push_str("],\"requests\":[");
    for (index, (key, request)) in step.requests.iter().enumerate() {
        if index > 0 {
            out.push(',');
        }
        out.push_str(&encode_request(key, request));
    }
    out.push_str("],\"status\":");
    match &step.status {
        Status::Running => out.push_str("{\"running\":true}"),
        Status::Done(status) => out.push_str(&format!("{{\"done\":{status}}}")),
        Status::Ended(fatal, status) => {
            out.push_str(&format!(
                "{{\"ended\":{},\"status\":{status}}}",
                quote(&format!("{fatal:?}"))
            ));
        }
    }
    out.push_str(",\"statuses\":[");
    for (index, entry) in step.statuses.iter().enumerate() {
        if index > 0 {
            out.push(',');
        }
        let stages: Vec<String> = entry.iter().map(i32::to_string).collect();
        out.push_str(&format!("[{}]", stages.join(",")));
    }
    out.push_str(&format!("],\"memory\":{memory}}}"));
    out
}

pub fn encode_request(key: &RequestKey, request: &Request) -> String {
    let key = quote(&key.to_string());
    match request {
        Request::Read {
            path,
            open,
            offset,
            length,
        } => {
            format!(
                "{{\"key\":{key},\"op\":\"read\",\"path\":{},\"open\":{},\"offset\":{offset},\"length\":{length}}}",
                quote(path),
                quote(&open.to_string())
            )
        }
        Request::Write { path, data, mode } => {
            let mode = match mode {
                WriteMode::Truncate => "truncate",
                WriteMode::Append => "append",
                WriteMode::CreateNew => "create_new",
            };
            format!(
                "{{\"key\":{key},\"op\":\"write\",\"path\":{},\"data\":\"{}\",\"mode\":\"{mode}\"}}",
                quote(path),
                base64_encode(data)
            )
        }
        Request::Touch { path } => format!(
            "{{\"key\":{key},\"op\":\"touch\",\"path\":{}}}",
            quote(path)
        ),
        Request::Stat { path } => {
            format!("{{\"key\":{key},\"op\":\"stat\",\"path\":{}}}", quote(path))
        }
        Request::List { path } => {
            format!("{{\"key\":{key},\"op\":\"list\",\"path\":{}}}", quote(path))
        }
        Request::Mkdir { path, parents } => {
            format!(
                "{{\"key\":{key},\"op\":\"mkdir\",\"path\":{},\"parents\":{parents}}}",
                quote(path)
            )
        }
        Request::Remove { path, recursive } => {
            format!(
                "{{\"key\":{key},\"op\":\"remove\",\"path\":{},\"recursive\":{recursive}}}",
                quote(path)
            )
        }
        Request::Copy {
            from,
            to,
            recursive,
        } => format!(
            "{{\"key\":{key},\"op\":\"copy\",\"from\":{},\"to\":{},\"recursive\":{recursive}}}",
            quote(from),
            quote(to)
        ),
        Request::Move { from, to } => {
            format!(
                "{{\"key\":{key},\"op\":\"move\",\"from\":{},\"to\":{}}}",
                quote(from),
                quote(to)
            )
        }
        Request::Value { name } => format!(
            "{{\"key\":{key},\"op\":\"value\",\"name\":{}}}",
            quote(name)
        ),
        Request::Start { name, args, cwd } => {
            let args: Vec<String> = args.iter().map(|a| quote(a)).collect();
            format!(
                "{{\"key\":{key},\"op\":\"start\",\"name\":{},\"args\":[{}],\"cwd\":{}}}",
                quote(name),
                args.join(","),
                quote(cwd)
            )
        }
        Request::Feed { program, data, eof } => format!(
            "{{\"key\":{key},\"op\":\"feed\",\"program\":{},\"data\":\"{}\",\"eof\":{eof}}}",
            quote(&program.to_string()),
            base64_encode(data)
        ),
    }
}

/// Why a line could not start, as the module answers `start`.
pub fn encode_start_error(error: &StartError) -> String {
    let (kind, message, line, column) = match error {
        StartError::Parse(ParseError::Syntax(at, message)) => {
            ("syntax", message.clone(), at.line, at.column)
        }
        StartError::Parse(ParseError::Refused(at, construct, reason)) => (
            "refused",
            format!("{construct}: {reason}"),
            at.line,
            at.column,
        ),
        StartError::Parse(ParseError::Budget(which, limit)) | StartError::Budget(which, limit) => (
            "budget",
            format!("{which} budget of {limit} exceeded"),
            0,
            0,
        ),
    };
    format!(
        "{{\"error\":{{\"kind\":\"{kind}\",\"message\":{},\"line\":{line},\"column\":{column}}}}}",
        quote(&message)
    )
}

// ---------------------------------------------------------------------------
// The host's half: what it sends, and how it reads what comes back
// ---------------------------------------------------------------------------

/// The `start` document for a line and its configuration.
pub fn encode_start(source: &str, config: &Config) -> String {
    let pairs: Vec<String> = config
        .env
        .iter()
        .map(|(k, v)| format!("[{},{}]", quote(k), quote(v)))
        .collect();
    let args: Vec<String> = config.args.iter().map(|a| quote(a)).collect();
    let named = |wanted: ProgramKind| -> Vec<String> {
        config
            .programs
            .iter()
            .filter(|(_, kind)| *kind == wanted)
            .map(|(name, _)| quote(name))
            .collect()
    };
    let programs = named(ProgramKind::Library);
    let host_programs = named(ProgramKind::Host);
    let l = &config.limits;
    format!(
        "{{\"source\":{},\"env\":[{}],\"cwd\":{},\"name\":{},\"args\":[{}],\"stdin\":\"{}\",\"programs\":[{}],\"host_programs\":[{}],\"pid\":{},\"limits\":{{\"memory_bytes\":{},\"loop_iterations\":{},\"function_depth\":{},\"nesting\":{},\"slice\":{},\"output_bytes\":{},\"source_bytes\":{},\"tokens\":{},\"depth\":{},\"pipeline_stages\":{}}}}}",
        quote(source),
        pairs.join(","),
        quote(&config.cwd),
        quote(&config.name),
        args.join(","),
        base64_encode(&config.stdin),
        programs.join(","),
        host_programs.join(","),
        config.pid,
        l.memory_bytes,
        l.loop_iterations,
        l.function_depth,
        l.nesting,
        l.slice,
        l.output_bytes,
        l.parse.source_bytes,
        l.parse.tokens,
        l.parse.depth,
        l.parse.pipeline_stages,
    )
}

/// The `step` document for the replies to what the machine asked.
pub fn encode_replies(replies: &[(RequestKey, Reply)]) -> String {
    let items: Vec<String> = replies
        .iter()
        .map(|(key, reply)| {
            let key = quote(&key.to_string());
            match reply {
                Reply::Data { bytes, eof } => format!(
                    "{{\"key\":{key},\"reply\":\"data\",\"bytes\":\"{}\",\"eof\":{eof}}}",
                    base64_encode(bytes)
                ),
                Reply::Done => format!("{{\"key\":{key},\"reply\":\"done\"}}"),
                Reply::Stat { kind, size } => format!(
                    "{{\"key\":{key},\"reply\":\"stat\",\"kind\":\"{}\",\"size\":{size}}}",
                    kind_name(*kind)
                ),
                Reply::Entries(entries) => {
                    let listed: Vec<String> = entries
                        .iter()
                        .map(|e| {
                            format!(
                                "{{\"name\":{},\"kind\":\"{}\"}}",
                                quote(&e.name),
                                kind_name(e.kind)
                            )
                        })
                        .collect();
                    format!(
                        "{{\"key\":{key},\"reply\":\"entries\",\"entries\":[{}]}}",
                        listed.join(",")
                    )
                }
                Reply::Text(text) => format!(
                    "{{\"key\":{key},\"reply\":\"text\",\"text\":{}}}",
                    quote(text)
                ),
                Reply::Error(error) => format!(
                    "{{\"key\":{key},\"reply\":\"error\",\"error\":\"{}\"}}",
                    error_name(*error)
                ),
                Reply::Library => format!("{{\"key\":{key},\"reply\":\"library\"}}"),
                Reply::Started => format!("{{\"key\":{key},\"reply\":\"started\"}}"),
                Reply::Output {
                    stdout,
                    stderr,
                    status,
                } => format!(
                    "{{\"key\":{key},\"reply\":\"output\",\"stdout\":\"{}\",\"stderr\":\"{}\",\"status\":{}}}",
                    base64_encode(stdout),
                    base64_encode(stderr),
                    status.map_or_else(|| "null".to_owned(), |s| s.to_string())
                ),
                Reply::Refused { status, message } => format!(
                    "{{\"key\":{key},\"reply\":\"refused\",\"status\":{status},\"message\":{}}}",
                    quote(message)
                ),
            }
        })
        .collect();
    format!("[{}]", items.join(","))
}

/// How a step ended, as a host reads it back.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum WireStatus {
    Running,
    Done(i32),
    /// Why the line ended outside its own control, as the machine words it, and its status.
    Ended(String, i32),
}

/// One step's answer, as a host reads it back.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct WireStep {
    pub output: Vec<(Stream, Vec<u8>)>,
    pub requests: Vec<(RequestKey, Request)>,
    pub status: WireStatus,
    /// The `PIPESTATUS` of each pipeline of the top level that ended in this step.
    pub statuses: Vec<Vec<i32>>,
    /// Bytes the machine holds, as it counts them.
    pub memory: u64,
}

/// Read what `step` left in the buffer; an `error` document is returned as `Err`.
pub fn decode_step(text: &str) -> Result<WireStep, String> {
    let doc = parse(text)?;
    if let Some(error) = doc.get("error").and_then(Json::text) {
        return Err(error.to_owned());
    }
    let mut output = Vec::new();
    for chunk in doc.get("output").map(Json::list).unwrap_or_default() {
        if let [Json::Number(fd), Json::Text(bytes)] = chunk.list() {
            let stream = if *fd == 2.0 {
                Stream::Stderr
            } else {
                Stream::Stdout
            };
            output.push((stream, base64_decode(bytes)));
        }
    }
    let mut requests = Vec::new();
    for item in doc.get("requests").map(Json::list).unwrap_or_default() {
        requests.push(decode_request(item).ok_or("a request the host cannot read")?);
    }
    let status = doc.get("status").ok_or("a step without a status")?;
    let code = |key: &str| i32::try_from(status.u64_or(key, 1)).unwrap_or(1);
    let status = if let Some(reason) = status.get("ended").and_then(Json::text) {
        WireStatus::Ended(reason.to_owned(), code("status"))
    } else if status.get("done").is_some() {
        WireStatus::Done(code("done"))
    } else {
        WireStatus::Running
    };
    let mut statuses = Vec::new();
    for entry in doc.get("statuses").map(Json::list).unwrap_or_default() {
        let stages: Option<Vec<i32>> = entry
            .list()
            .iter()
            .map(|stage| stage.number().and_then(|n| i32::try_from(n as i64).ok()))
            .collect();
        statuses.push(stages.ok_or("a status the host cannot read")?);
    }
    Ok(WireStep {
        output,
        requests,
        status,
        statuses,
        memory: doc.u64_or("memory", 0),
    })
}

/// One request as `encode_request` wrote it.
pub fn decode_request(item: &Json) -> Option<(RequestKey, Request)> {
    let key = parse_key(item.get("key")?.text()?)?;
    let text = |name: &str| item.get(name).and_then(Json::text).map(str::to_owned);
    let flag = |name: &str| matches!(item.get(name), Some(Json::Bool(true)));
    let request = match item.get("op")?.text()? {
        "read" => Request::Read {
            path: text("path")?,
            open: parse_key(item.get("open")?.text()?)?,
            offset: item.u64_or("offset", 0),
            length: item.u64_or("length", 0),
        },
        "write" => Request::Write {
            path: text("path")?,
            data: item.get("data").map(Json::bytes).unwrap_or_default(),
            mode: match item.get("mode")?.text()? {
                "append" => WriteMode::Append,
                "create_new" => WriteMode::CreateNew,
                _ => WriteMode::Truncate,
            },
        },
        "touch" => Request::Touch {
            path: text("path")?,
        },
        "stat" => Request::Stat {
            path: text("path")?,
        },
        "list" => Request::List {
            path: text("path")?,
        },
        "mkdir" => Request::Mkdir {
            path: text("path")?,
            parents: flag("parents"),
        },
        "remove" => Request::Remove {
            path: text("path")?,
            recursive: flag("recursive"),
        },
        "copy" => Request::Copy {
            from: text("from")?,
            to: text("to")?,
            recursive: flag("recursive"),
        },
        "move" => Request::Move {
            from: text("from")?,
            to: text("to")?,
        },
        "value" => Request::Value {
            name: text("name")?,
        },
        "start" => Request::Start {
            name: text("name")?,
            args: item
                .get("args")
                .map(Json::list)
                .unwrap_or_default()
                .iter()
                .filter_map(|a| a.text().map(str::to_owned))
                .collect(),
            cwd: text("cwd")?,
        },
        "feed" => Request::Feed {
            program: parse_key(&text("program")?)?,
            data: item.get("data").map(Json::bytes).unwrap_or_default(),
            eof: flag("eof"),
        },
        _ => return None,
    };
    Some((key, request))
}

/// Why `start` refused a line: its kind, message, line and column.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct StartRefusal {
    pub kind: String,
    pub message: String,
    pub line: u32,
    pub column: u32,
}

/// Read what `start` left in the buffer: started, or why not.
pub fn decode_started(text: &str) -> Result<(), StartRefusal> {
    let refusal = |kind: &str, message: String| StartRefusal {
        kind: kind.to_owned(),
        message,
        line: 0,
        column: 0,
    };
    let doc = parse(text).map_err(|message| refusal("internal", message))?;
    match doc.get("error") {
        None => Ok(()),
        Some(Json::Text(message)) => Err(refusal("internal", message.clone())),
        Some(error) => Err(StartRefusal {
            kind: error
                .get("kind")
                .and_then(Json::text)
                .unwrap_or("internal")
                .to_owned(),
            message: error
                .get("message")
                .and_then(Json::text)
                .unwrap_or_default()
                .to_owned(),
            line: u32::try_from(error.u64_or("line", 0)).unwrap_or(0),
            column: u32::try_from(error.u64_or("column", 0)).unwrap_or(0),
        }),
    }
}

fn kind_name(kind: EntryKind) -> &'static str {
    match kind {
        EntryKind::Directory => "directory",
        EntryKind::File => "file",
    }
}

fn error_name(error: HostError) -> &'static str {
    match error {
        HostError::NotFound => "not_found",
        HostError::NotADirectory => "not_a_directory",
        HostError::IsADirectory => "is_a_directory",
        HostError::Exists => "exists",
        HostError::NotEmpty => "not_empty",
        HostError::PermissionDenied => "permission_denied",
        HostError::Unsupported => "unsupported",
        HostError::Invalid => "invalid",
    }
}

/// A JSON string literal.
pub fn quote(text: &str) -> String {
    let mut out = String::from("\"");
    for ch in text.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if u32::from(c) < 0x20 => out.push_str(&format!("\\u{:04x}", u32::from(c))),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

// ---------------------------------------------------------------------------
// A small JSON reader
// ---------------------------------------------------------------------------

pub fn parse(text: &str) -> Result<Json, String> {
    let chars: Vec<char> = text.chars().collect();
    let mut reader = Reader {
        chars: &chars,
        pos: 0,
    };
    let value = reader.value(0)?;
    reader.blank();
    if reader.pos < chars.len() {
        return Err("trailing text after the document".to_owned());
    }
    Ok(value)
}

struct Reader<'a> {
    chars: &'a [char],
    pos: usize,
}

impl Reader<'_> {
    fn peek(&self) -> Option<char> {
        self.chars.get(self.pos).copied()
    }

    fn bump(&mut self) {
        self.pos = self.pos.saturating_add(1);
    }

    fn blank(&mut self) {
        while self.peek().is_some_and(char::is_whitespace) {
            self.bump();
        }
    }

    fn eat(&mut self, ch: char) -> Result<(), String> {
        self.blank();
        if self.peek() == Some(ch) {
            self.bump();
            Ok(())
        } else {
            Err(format!("expected `{ch}` at {}", self.pos))
        }
    }

    fn value(&mut self, depth: u32) -> Result<Json, String> {
        if depth > DEPTH {
            return Err("document nested too deep".to_owned());
        }
        self.blank();
        match self.peek() {
            Some('{') => {
                self.bump();
                let mut fields = Vec::new();
                self.blank();
                if self.peek() == Some('}') {
                    self.bump();
                    return Ok(Json::Object(fields));
                }
                loop {
                    self.blank();
                    let key = self.string()?;
                    self.eat(':')?;
                    let value = self.value(depth.saturating_add(1))?;
                    fields.push((key, value));
                    self.blank();
                    match self.peek() {
                        Some(',') => self.bump(),
                        Some('}') => {
                            self.bump();
                            return Ok(Json::Object(fields));
                        }
                        _ => return Err(format!("expected `,` or `}}` at {}", self.pos)),
                    }
                }
            }
            Some('[') => {
                self.bump();
                let mut items = Vec::new();
                self.blank();
                if self.peek() == Some(']') {
                    self.bump();
                    return Ok(Json::List(items));
                }
                loop {
                    items.push(self.value(depth.saturating_add(1))?);
                    self.blank();
                    match self.peek() {
                        Some(',') => self.bump(),
                        Some(']') => {
                            self.bump();
                            return Ok(Json::List(items));
                        }
                        _ => return Err(format!("expected `,` or `]` at {}", self.pos)),
                    }
                }
            }
            Some('"') => Ok(Json::Text(self.string()?)),
            Some('t') => self.word("true", Json::Bool(true)),
            Some('f') => self.word("false", Json::Bool(false)),
            Some('n') => self.word("null", Json::Null),
            Some(_) => {
                let start = self.pos;
                while self
                    .peek()
                    .is_some_and(|c| c.is_ascii_digit() || matches!(c, '-' | '+' | '.' | 'e' | 'E'))
                {
                    self.bump();
                }
                let text: String = self
                    .chars
                    .get(start..self.pos)
                    .unwrap_or_default()
                    .iter()
                    .collect();
                text.parse::<f64>()
                    .map(Json::Number)
                    .map_err(|_| format!("bad number at {start}"))
            }
            None => Err("unexpected end of the document".to_owned()),
        }
    }

    fn word(&mut self, word: &str, value: Json) -> Result<Json, String> {
        for expected in word.chars() {
            if self.peek() != Some(expected) {
                return Err(format!("bad literal at {}", self.pos));
            }
            self.bump();
        }
        Ok(value)
    }

    fn string(&mut self) -> Result<String, String> {
        if self.peek() != Some('"') {
            return Err(format!("expected a string at {}", self.pos));
        }
        self.bump();
        let mut out = String::new();
        loop {
            let Some(ch) = self.peek() else {
                return Err("an unterminated string".to_owned());
            };
            self.bump();
            match ch {
                '"' => return Ok(out),
                '\\' => {
                    let Some(escape) = self.peek() else {
                        return Err("an unterminated escape".to_owned());
                    };
                    self.bump();
                    match escape {
                        'n' => out.push('\n'),
                        't' => out.push('\t'),
                        'r' => out.push('\r'),
                        'b' => out.push('\u{8}'),
                        'f' => out.push('\u{c}'),
                        'u' => {
                            let hex: String = self
                                .chars
                                .get(self.pos..self.pos.saturating_add(4))
                                .unwrap_or_default()
                                .iter()
                                .collect();
                            self.pos = self.pos.saturating_add(4);
                            let code = u32::from_str_radix(&hex, 16)
                                .map_err(|_| "a bad \\u escape".to_owned())?;
                            out.push(char::from_u32(code).unwrap_or('\u{fffd}'));
                        }
                        other => out.push(other),
                    }
                }
                other => out.push(other),
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Base64
// ---------------------------------------------------------------------------

const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

/// Each byte's sextet, or `INVALID` for a byte that is no base64 digit: one lookup per byte.
// Built at compile time, where an index out of range fails the build and never a call.
#[allow(clippy::indexing_slicing, clippy::arithmetic_side_effects)]
const DECODE: [u8; 256] = {
    let mut table = [INVALID; 256];
    let mut index = 0;
    while index < ALPHABET.len() {
        table[ALPHABET[index] as usize] = index as u8;
        index += 1;
    }
    table
};
const INVALID: u8 = 0xff;

pub fn base64_encode(bytes: &[u8]) -> String {
    let mut out = String::with_capacity(bytes.len().div_ceil(3).saturating_mul(4));
    for chunk in bytes.chunks(3) {
        let b0 = u32::from(chunk.first().copied().unwrap_or(0));
        let b1 = u32::from(chunk.get(1).copied().unwrap_or(0));
        let b2 = u32::from(chunk.get(2).copied().unwrap_or(0));
        let n = (b0 << 16) | (b1 << 8) | b2;
        for (index, shift) in [18u32, 12, 6, 0].iter().enumerate() {
            if index <= chunk.len() {
                let sextet = usize::try_from((n >> shift) & 63).unwrap_or(0);
                out.push(char::from(ALPHABET.get(sextet).copied().unwrap_or(b'A')));
            } else {
                out.push('=');
            }
        }
    }
    out
}

pub fn base64_decode(text: &str) -> Vec<u8> {
    let mut out = Vec::with_capacity((text.len() / 4).saturating_mul(3));
    let mut buffer = 0u32;
    let mut bits = 0u32;
    for byte in text.bytes() {
        let value = DECODE.get(usize::from(byte)).copied().unwrap_or(INVALID);
        if value == INVALID {
            continue;
        }
        buffer = (buffer << 6) | u32::from(value);
        bits = bits.saturating_add(6);
        if bits >= 8 {
            bits = bits.saturating_sub(8);
            out.push(u8::try_from((buffer >> bits) & 0xff).unwrap_or(0));
        }
    }
    out
}
