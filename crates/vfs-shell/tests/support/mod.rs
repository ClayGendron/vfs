//! The corpus: every case under `tests/shell/cases`, its record, and the
//! lists that say which cases may fail and which differ from bash on purpose.
//! Shared by the corpus test and the score example.
#![allow(
    dead_code,
    clippy::unwrap_used,
    clippy::expect_used,
    clippy::panic,
    clippy::indexing_slicing
)]
#![allow(clippy::arithmetic_side_effects, clippy::string_slice)]

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

pub fn repo_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap()
}

pub fn shell_dir() -> PathBuf {
    repo_root().join("tests/shell")
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Tier {
    Language,
    Program,
}

/// What a run printed and the status it ended with.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Outcome {
    pub stdout: Vec<u8>,
    pub stderr: Vec<u8>,
    pub status: i32,
}

#[derive(Clone, Debug)]
pub struct Case {
    /// `<area>/<name>`, the case's name everywhere.
    pub name: String,
    pub area: String,
    pub source: String,
    pub tier: Tier,
    pub seed_world: bool,
    pub stderr_exact: bool,
    /// What bash did.
    pub record: Outcome,
    /// The shell's own answer, for a deliberate difference.
    pub delta: Option<Outcome>,
}

impl Case {
    /// The answer this shell is held to.
    pub fn expected(&self) -> &Outcome {
        self.delta.as_ref().unwrap_or(&self.record)
    }

    /// Whether `got` matches: stdout and status exactly, stderr as empty or not unless asked.
    pub fn judge(&self, got: &Outcome) -> Result<(), String> {
        let want = self.expected();
        if got.stdout != want.stdout {
            return Err(format!(
                "stdout differs\n--- want\n{}\n--- got\n{}",
                String::from_utf8_lossy(&want.stdout),
                String::from_utf8_lossy(&got.stdout)
            ));
        }
        if got.status != want.status {
            return Err(format!(
                "status: want {}, got {}\nstderr: {}",
                want.status,
                got.status,
                String::from_utf8_lossy(&got.stderr)
            ));
        }
        if self.stderr_exact {
            if got.stderr != want.stderr {
                return Err(format!(
                    "stderr differs\n--- want\n{}\n--- got\n{}",
                    String::from_utf8_lossy(&want.stderr),
                    String::from_utf8_lossy(&got.stderr)
                ));
            }
        } else if got.stderr.is_empty() != want.stderr.is_empty() {
            return Err(format!(
                "stderr: want {}, got {:?}",
                if want.stderr.is_empty() {
                    "empty"
                } else {
                    "some"
                },
                String::from_utf8_lossy(&got.stderr)
            ));
        }
        Ok(())
    }
}

pub fn load_cases() -> Vec<Case> {
    load_cases_from(&shell_dir().join("cases"))
}

/// Every case under `root`, laid out as the corpus is.
pub fn load_cases_from(root: &std::path::Path) -> Vec<Case> {
    let root = root.to_path_buf();
    let mut scripts = Vec::new();
    collect(&root, &mut scripts);
    scripts.sort();
    scripts
        .into_iter()
        .map(|path| {
            let rel = path.strip_prefix(&root).unwrap().with_extension("");
            let name = rel.to_string_lossy().replace('\\', "/");
            let area = rel
                .parent()
                .map(|p| p.to_string_lossy().into_owned())
                .unwrap_or_default();
            let source = fs::read_to_string(&path).unwrap();
            let header: Vec<&str> = source
                .lines()
                .take_while(|line| line.starts_with('#'))
                .collect();
            let tier = if header.iter().any(|line| line.trim() == "# tier: program") {
                Tier::Program
            } else {
                Tier::Language
            };
            let seed_world = header.iter().any(|line| line.trim() == "# world: seed");
            let stderr_exact = header.iter().any(|line| line.trim() == "# stderr: exact");
            let record = read_outcome(&path.with_extension("json")).unwrap_or_else(|| {
                panic!("case {name} has no record; run scripts/shell_record.py")
            });
            let delta = read_outcome(&path.with_extension("shell.json"));
            Case {
                name,
                area,
                source: source.trim_end_matches('\n').to_owned(),
                tier,
                seed_world,
                stderr_exact,
                record,
                delta,
            }
        })
        .collect()
}

fn collect(dir: &Path, out: &mut Vec<PathBuf>) {
    for entry in fs::read_dir(dir).unwrap() {
        let path = entry.unwrap().path();
        if path.is_dir() {
            collect(&path, out);
        } else if path.extension().is_some_and(|ext| ext == "sh") {
            out.push(path);
        }
    }
}

fn read_outcome(path: &Path) -> Option<Outcome> {
    let text = fs::read_to_string(path).ok()?;
    let object = parse_json_object(&text);
    let stream = |key: &str| -> Vec<u8> {
        if let Some(text) = object.get(key) {
            return text.as_bytes().to_vec();
        }
        if let Some(encoded) = object.get(&format!("{key}_base64")) {
            return base64_decode(encoded);
        }
        Vec::new()
    };
    Some(Outcome {
        stdout: stream("stdout"),
        stderr: stream("stderr"),
        status: object
            .get("status")
            .and_then(|s| s.parse().ok())
            .unwrap_or(-1),
    })
}

/// Names listed one to a line in a file under `tests/shell`, with `#` comments.
pub fn read_list(file: &str) -> BTreeMap<String, String> {
    let Ok(text) = fs::read_to_string(shell_dir().join(file)) else {
        return BTreeMap::new();
    };
    text.lines()
        .map(|line| line.trim())
        .filter(|line| !line.is_empty() && !line.starts_with('#'))
        .map(|line| match line.split_once(char::is_whitespace) {
            Some((name, reason)) => (name.to_owned(), reason.trim().to_owned()),
            None => (line.to_owned(), String::new()),
        })
        .collect()
}

pub fn known_failures() -> BTreeSet<String> {
    read_list("known_failures.txt").into_keys().collect()
}

/// The seed tree, as relative paths and their bytes.
pub fn seed_world() -> Vec<(String, Vec<u8>)> {
    let root = shell_dir().join("world");
    let mut files = Vec::new();
    walk_world(&root, &root, &mut files);
    files.sort();
    files
}

fn walk_world(root: &Path, dir: &Path, out: &mut Vec<(String, Vec<u8>)>) {
    for entry in fs::read_dir(dir).unwrap() {
        let path = entry.unwrap().path();
        let rel = path
            .strip_prefix(root)
            .unwrap()
            .to_string_lossy()
            .into_owned();
        if path.is_dir() {
            out.push((format!("{rel}/"), Vec::new()));
            walk_world(root, &path, out);
        } else {
            out.push((rel, fs::read(&path).unwrap()));
        }
    }
}

/// Every case's verdict, the score by area, and what disagrees with the known-failures list.
pub struct Score {
    pub by_area: BTreeMap<String, (usize, usize)>,
    pub passed: usize,
    pub total: usize,
    pub unlisted_failures: Vec<(String, String)>,
    pub listed_passes: Vec<String>,
    pub failing: Vec<String>,
}

pub fn score(cases: &[Case], run: impl Fn(&Case) -> Result<Outcome, String>) -> Score {
    let known = known_failures();
    let mut by_area: BTreeMap<String, (usize, usize)> = BTreeMap::new();
    let mut passed = 0;
    let mut unlisted_failures = Vec::new();
    let mut listed_passes = Vec::new();
    let mut failing = Vec::new();
    for case in cases {
        let verdict = run(case).and_then(|got| case.judge(&got));
        let entry = by_area.entry(case.area.clone()).or_default();
        entry.1 += 1;
        match verdict {
            Ok(()) => {
                entry.0 += 1;
                passed += 1;
                if known.contains(&case.name) {
                    listed_passes.push(case.name.clone());
                }
            }
            Err(why) => {
                failing.push(case.name.clone());
                if !known.contains(&case.name) {
                    unlisted_failures.push((case.name.clone(), why));
                }
            }
        }
    }
    Score {
        by_area,
        passed,
        total: cases.len(),
        unlisted_failures,
        listed_passes,
        failing,
    }
}

impl Score {
    pub fn report(&self) -> String {
        let mut out = String::new();
        for (area, (pass, total)) in &self.by_area {
            out.push_str(&format!("{area:40} {pass:5} / {total:5}\n"));
        }
        let percent = if self.total == 0 {
            0.0
        } else {
            self.passed as f64 * 100.0 / self.total as f64
        };
        out.push_str(&format!(
            "{:40} {:5} / {:5}  ({percent:.1}%)\n",
            "all", self.passed, self.total
        ));
        out
    }
}

// ---------------------------------------------------------------------------
// A JSON reader for the flat records the recorder writes
// ---------------------------------------------------------------------------

fn parse_json_object(text: &str) -> BTreeMap<String, String> {
    let chars: Vec<char> = text.chars().collect();
    let mut pos = 0;
    let mut out = BTreeMap::new();
    let skip = |pos: &mut usize| {
        while *pos < chars.len() && chars[*pos].is_whitespace() {
            *pos += 1;
        }
    };
    skip(&mut pos);
    assert_eq!(chars.get(pos), Some(&'{'));
    pos += 1;
    loop {
        skip(&mut pos);
        if chars.get(pos) == Some(&'}') {
            break;
        }
        let key = read_string(&chars, &mut pos);
        skip(&mut pos);
        assert_eq!(chars[pos], ':');
        pos += 1;
        skip(&mut pos);
        let value = if chars[pos] == '"' {
            read_string(&chars, &mut pos)
        } else {
            let start = pos;
            while pos < chars.len()
                && !matches!(chars[pos], ',' | '}')
                && !chars[pos].is_whitespace()
            {
                pos += 1;
            }
            chars[start..pos].iter().collect()
        };
        out.insert(key, value);
        skip(&mut pos);
        if chars.get(pos) == Some(&',') {
            pos += 1;
        }
    }
    out
}

fn read_string(chars: &[char], pos: &mut usize) -> String {
    assert_eq!(chars[*pos], '"');
    *pos += 1;
    let mut out = String::new();
    loop {
        let ch = chars[*pos];
        *pos += 1;
        match ch {
            '"' => return out,
            '\\' => {
                let esc = chars[*pos];
                *pos += 1;
                match esc {
                    'n' => out.push('\n'),
                    't' => out.push('\t'),
                    'r' => out.push('\r'),
                    'b' => out.push('\u{8}'),
                    'f' => out.push('\u{c}'),
                    '/' => out.push('/'),
                    '\\' => out.push('\\'),
                    '"' => out.push('"'),
                    'u' => {
                        let hex: String = chars[*pos..*pos + 4].iter().collect();
                        *pos += 4;
                        let mut code = u32::from_str_radix(&hex, 16).unwrap();
                        if (0xD800..0xDC00).contains(&code) && chars.get(*pos) == Some(&'\\') {
                            let low: String = chars[*pos + 2..*pos + 6].iter().collect();
                            *pos += 6;
                            let low = u32::from_str_radix(&low, 16).unwrap();
                            code = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00);
                        }
                        out.push(char::from_u32(code).unwrap_or('\u{fffd}'));
                    }
                    other => out.push(other),
                }
            }
            other => out.push(other),
        }
    }
}

fn base64_decode(text: &str) -> Vec<u8> {
    let value = |c: u8| -> Option<u32> {
        match c {
            b'A'..=b'Z' => Some(u32::from(c - b'A')),
            b'a'..=b'z' => Some(u32::from(c - b'a') + 26),
            b'0'..=b'9' => Some(u32::from(c - b'0') + 52),
            b'+' => Some(62),
            b'/' => Some(63),
            _ => None,
        }
    };
    let mut out = Vec::new();
    let mut buffer = 0u32;
    let mut bits = 0;
    for byte in text.bytes() {
        let Some(v) = value(byte) else { continue };
        buffer = (buffer << 6) | v;
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            out.push(((buffer >> bits) & 0xff) as u8);
        }
    }
    out
}

/// The environment a case runs in, as the recorder gives it to bash.
pub const ENVIRONMENT: &[(&str, &str)] = &[
    ("HOME", "/home/agent"),
    ("PATH", "/usr/local/bin:/usr/bin:/bin"),
    ("LC_ALL", "C.UTF-8"),
    ("TZ", "UTC"),
    ("USER", "agent"),
    ("LOGNAME", "agent"),
    ("TERM", "dumb"),
];

/// Run one case through the shell and its reference host.
pub fn run_case(case: &Case) -> Result<Outcome, String> {
    let mut host = shell::host::MemoryHost::new();
    host.add_dir("/home/agent");
    host.add_dir("/work");
    host.add_dir("/tmp");
    if case.seed_world {
        for (path, bytes) in seed_world() {
            match path.strip_suffix('/') {
                Some(dir) => host.add_dir(&format!("/work/{dir}")),
                None => host.add_file(&format!("/work/{path}"), &bytes),
            }
        }
    }
    let mut config = host.config();
    config.env = ENVIRONMENT
        .iter()
        .map(|(k, v)| ((*k).to_owned(), (*v).to_owned()))
        .collect();
    config.cwd = "/work".to_owned();
    let source = case.source.clone();
    let result =
        std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| host.run(&source, config)));
    match result {
        Ok(outcome) => Ok(Outcome {
            stdout: outcome.stdout,
            stderr: outcome.stderr,
            status: outcome.status,
        }),
        Err(_) => Err("the machine panicked".to_owned()),
    }
}
