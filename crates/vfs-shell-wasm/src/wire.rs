//! The bytes that cross the module's boundary: JSON text, with every byte
//! string in base64. A host in any language can speak it with its own JSON.

use shell::machine::{
    Config, Entry, EntryKind, HostError, Limits, ProgramKind, Reply, Request, RequestKey, Status,
    Step, Stream, WriteMode,
};

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
            slice: limits.u64_or("slice", defaults.slice),
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
    out.push_str(&format!(",\"memory\":{memory}}}"));
    out
}

pub fn encode_request(key: &RequestKey, request: &Request) -> String {
    let key = quote(&key.to_string());
    match request {
        Request::Read {
            path,
            offset,
            length,
        } => {
            format!(
                "{{\"key\":{key},\"op\":\"read\",\"path\":{},\"offset\":{offset},\"length\":{length}}}",
                quote(path)
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

pub fn base64_encode(bytes: &[u8]) -> String {
    let mut out = String::new();
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
    let mut out = Vec::new();
    let mut buffer = 0u32;
    let mut bits = 0u32;
    for byte in text.bytes() {
        let Some(value) = ALPHABET.iter().position(|b| *b == byte) else {
            continue;
        };
        buffer = (buffer << 6) | u32::try_from(value).unwrap_or(0);
        bits = bits.saturating_add(6);
        if bits >= 8 {
            bits = bits.saturating_sub(8);
            out.push(u8::try_from((buffer >> bits) & 0xff).unwrap_or(0));
        }
    }
    out
}
