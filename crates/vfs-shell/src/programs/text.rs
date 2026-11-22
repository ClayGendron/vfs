//! The text programs: `cat`, `head`, `tail`, `wc`, `cut`, `sort`, `uniq`,
//! `tr` and `tee`, each a transform of its input that prints what GNU
//! coreutils prints.

use std::cmp::Ordering;

use super::{Prog, describe, split_args};
use crate::machine::{EntryKind, Flow, HostError};

/// The operands, or standard input when there are none.
fn operands_or_stdin(operands: Vec<String>) -> Vec<String> {
    if operands.is_empty() {
        vec!["-".to_owned()]
    } else {
        operands
    }
}

/// Read one operand; a directory is an error, as reading one is.
async fn read_operand(prog: &mut Prog<'_>, name: &str) -> Result<Result<Vec<u8>, HostError>, Flow> {
    if name != "-"
        && !name.starts_with("/dev/")
        && let Some((EntryKind::Directory, _)) = prog.stat(name).await?
    {
        return Ok(Err(HostError::IsADirectory));
    }
    prog.file(name).await
}

/// Lines of `bytes`, each with its newline if it had one.
fn lines(bytes: &[u8]) -> Vec<&[u8]> {
    bytes.split_inclusive(|b| *b == b'\n').collect()
}

fn strip_newline(line: &[u8]) -> &[u8] {
    line.strip_suffix(b"\n").unwrap_or(line)
}

// ---------------------------------------------------------------------------
// cat
// ---------------------------------------------------------------------------

pub async fn cat(prog: &mut Prog<'_>, args: &[String]) -> Result<i32, Flow> {
    let (options, operands) = split_args(args);
    let mut number = false;
    let mut nonblank = false;
    let mut squeeze = false;
    let mut ends = false;
    let mut tabs = false;
    let mut visible = false;
    for option in &options {
        for flag in option.trim_start_matches('-').chars() {
            match flag {
                'n' => number = true,
                'b' => nonblank = true,
                's' => squeeze = true,
                'E' => ends = true,
                'T' => tabs = true,
                'v' => visible = true,
                'A' => {
                    visible = true;
                    ends = true;
                    tabs = true;
                }
                'e' => {
                    visible = true;
                    ends = true;
                }
                't' => {
                    visible = true;
                    tabs = true;
                }
                'u' => {}
                other => {
                    prog.err(&format!("invalid option -- '{other}'")).await?;
                    prog.sh
                        .error_text("Try 'cat --help' for more information.\n")
                        .await?;
                    return Ok(1);
                }
            }
        }
    }
    let plain = !(number || nonblank || squeeze || ends || tabs || visible);
    let mut status = 0;
    let mut line_number = 0u64;
    let mut last_blank = false;
    let mut at_line_start = true;
    for name in operands_or_stdin(operands) {
        if plain && name == "-" {
            while let Some(chunk) = prog.stdin_chunk().await? {
                prog.out(&chunk).await?;
            }
            continue;
        }
        let bytes = match read_operand(prog, &name).await? {
            Ok(bytes) => bytes,
            Err(error) => {
                prog.err(&format!("{}: {}", name, describe(error))).await?;
                status = 1;
                continue;
            }
        };
        if plain {
            prog.out(&bytes).await?;
            continue;
        }
        let mut out = Vec::new();
        for line in lines(&bytes) {
            let body = strip_newline(line);
            let has_newline = line.len() > body.len();
            let blank = body.is_empty() && has_newline;
            if squeeze && blank && last_blank {
                continue;
            }
            last_blank = blank;
            if at_line_start && (number && !nonblank || nonblank && !blank) {
                line_number = line_number.saturating_add(1);
                out.extend_from_slice(format!("{line_number:6}\t").as_bytes());
            }
            for &byte in body {
                if tabs && byte == b'\t' {
                    out.extend_from_slice(b"^I");
                } else if visible && byte != b'\t' {
                    show_byte(&mut out, byte);
                } else {
                    out.push(byte);
                }
            }
            if has_newline {
                if ends {
                    out.push(b'$');
                }
                out.push(b'\n');
            }
            at_line_start = has_newline;
        }
        prog.out(&out).await?;
    }
    Ok(status)
}

fn show_byte(out: &mut Vec<u8>, byte: u8) {
    match byte {
        0..=31 => {
            out.push(b'^');
            out.push(byte.wrapping_add(64));
        }
        127 => out.extend_from_slice(b"^?"),
        128..=159 => {
            out.extend_from_slice(b"M-^");
            out.push(byte.wrapping_sub(128).wrapping_add(64));
        }
        160..=254 => {
            out.extend_from_slice(b"M-");
            out.push(byte.wrapping_sub(128));
        }
        255 => out.extend_from_slice(b"M-^?"),
        _ => out.push(byte),
    }
}

// ---------------------------------------------------------------------------
// head and tail
// ---------------------------------------------------------------------------

/// A count for `head` and `tail`: how many, and whether it counts from the other end.
struct Count {
    value: u64,
    lines: bool,
    /// `head -n -N` (all but the last N) or `tail -n +N` (from line N).
    other_end: bool,
}

fn parse_size(text: &str) -> Option<u64> {
    let (digits, multiplier) = match text.find(|c: char| !c.is_ascii_digit()) {
        Some(at) => {
            let suffix = text.get(at..).unwrap_or_default();
            let multiplier: u64 = match suffix {
                "b" => 512,
                "k" | "K" | "KiB" => 1024,
                "kB" | "KB" => 1000,
                "M" | "MiB" => 1 << 20,
                "MB" => 1_000_000,
                "G" | "GiB" => 1 << 30,
                "GB" => 1_000_000_000,
                _ => return None,
            };
            (text.get(..at).unwrap_or_default(), multiplier)
        }
        None => (text, 1),
    };
    digits.parse::<u64>().ok()?.checked_mul(multiplier)
}

/// Parse `head`'s and `tail`'s options: the count, whether headers are forced or hidden, and operands.
async fn head_tail_options(
    prog: &mut Prog<'_>,
    args: &[String],
    tail: bool,
) -> Result<Result<(Count, Option<bool>, Vec<String>), i32>, Flow> {
    let mut count = Count {
        value: 10,
        lines: true,
        other_end: false,
    };
    let mut headers = None;
    let mut operands = Vec::new();
    let mut index = 0usize;
    let mut done = false;
    while let Some(arg) = args.get(index) {
        index = index.saturating_add(1);
        if done || !arg.starts_with('-') || arg == "-" {
            operands.push(arg.clone());
            continue;
        }
        if arg == "--" {
            done = true;
            continue;
        }
        let flags = arg.get(1..).unwrap_or_default();
        if flags.chars().next().is_some_and(|c| c.is_ascii_digit()) {
            count.value = flags.parse().unwrap_or(10);
            continue;
        }
        let chars = flags.char_indices();
        for (at, flag) in chars {
            match flag {
                'n' | 'c' => {
                    let rest = flags.get(at.saturating_add(1)..).unwrap_or_default();
                    let value = if rest.is_empty() {
                        let value = args.get(index).cloned().unwrap_or_default();
                        index = index.saturating_add(1);
                        value
                    } else {
                        rest.to_owned()
                    };
                    let (other_end, digits) =
                        match (value.strip_prefix('-'), value.strip_prefix('+')) {
                            (Some(rest), _) => (!tail, rest.to_owned()),
                            (_, Some(rest)) => (tail, rest.to_owned()),
                            _ => (false, value.clone()),
                        };
                    match parse_size(&digits) {
                        Some(parsed) => {
                            count = Count {
                                value: parsed,
                                lines: flag == 'n',
                                other_end,
                            };
                        }
                        None => {
                            let what = if flag == 'n' { "lines" } else { "bytes" };
                            prog.err(&format!("invalid number of {what}: ‘{value}’"))
                                .await?;
                            return Ok(Err(1));
                        }
                    }
                    break;
                }
                'q' => headers = Some(false),
                'v' => headers = Some(true),
                'f' | 'F' if tail => {}
                other => {
                    prog.err(&format!("invalid option -- '{other}'")).await?;
                    let name = prog.name.clone();
                    prog.sh
                        .error_text(&format!("Try '{name} --help' for more information.\n"))
                        .await?;
                    return Ok(Err(1));
                }
            }
        }
    }
    Ok(Ok((count, headers, operands_or_stdin(operands))))
}

pub async fn head(prog: &mut Prog<'_>, args: &[String]) -> Result<i32, Flow> {
    let (count, headers, operands) = match head_tail_options(prog, args, false).await? {
        Ok(parsed) => parsed,
        Err(status) => return Ok(status),
    };
    let show_headers = headers.unwrap_or(operands.len() > 1);
    let mut status = 0;
    let mut first = true;
    for name in operands {
        // Standard input is read only as far as it is needed.
        let bytes = if name == "-" && !count.other_end {
            let mut bytes = Vec::new();
            loop {
                if enough(&bytes, &count) {
                    break;
                }
                match prog.stdin_chunk().await? {
                    Some(chunk) => bytes.extend_from_slice(&chunk),
                    None => break,
                }
            }
            bytes
        } else {
            match read_operand(prog, &name).await? {
                Ok(bytes) => bytes,
                Err(error) => {
                    let message = if error == HostError::IsADirectory {
                        format!("error reading '{name}': Is a directory")
                    } else {
                        format!("cannot open '{}' for reading: {}", name, describe(error))
                    };
                    prog.err(&message).await?;
                    status = 1;
                    continue;
                }
            }
        };
        if show_headers {
            let shown = if name == "-" {
                "'standard input'".to_owned()
            } else {
                name.clone()
            };
            let header = format!("{}==> {} <==\n", if first { "" } else { "\n" }, shown);
            prog.out(header.as_bytes()).await?;
        }
        first = false;
        let selected = head_select(&bytes, &count);
        prog.out(&selected).await?;
    }
    Ok(status)
}

fn enough(bytes: &[u8], count: &Count) -> bool {
    if count.lines {
        u64::try_from(bytes.iter().filter(|b| **b == b'\n').count()).unwrap_or(u64::MAX)
            >= count.value
    } else {
        bytes.len() as u64 >= count.value
    }
}

fn head_select(bytes: &[u8], count: &Count) -> Vec<u8> {
    let n = usize::try_from(count.value).unwrap_or(usize::MAX);
    if count.lines {
        let all = lines(bytes);
        let keep = if count.other_end {
            all.len().saturating_sub(n)
        } else {
            n.min(all.len())
        };
        all.get(..keep).unwrap_or_default().concat()
    } else {
        let keep = if count.other_end {
            bytes.len().saturating_sub(n)
        } else {
            n.min(bytes.len())
        };
        bytes.get(..keep).unwrap_or_default().to_vec()
    }
}

pub async fn tail(prog: &mut Prog<'_>, args: &[String]) -> Result<i32, Flow> {
    let (count, headers, operands) = match head_tail_options(prog, args, true).await? {
        Ok(parsed) => parsed,
        Err(status) => return Ok(status),
    };
    let show_headers = headers.unwrap_or(operands.len() > 1);
    let mut status = 0;
    let mut first = true;
    for name in operands {
        let bytes = match read_operand(prog, &name).await? {
            Ok(bytes) => bytes,
            Err(error) => {
                let message = if error == HostError::IsADirectory {
                    format!("error reading '{name}': Is a directory")
                } else {
                    format!("cannot open '{}' for reading: {}", name, describe(error))
                };
                prog.err(&message).await?;
                status = 1;
                continue;
            }
        };
        if show_headers {
            let shown = if name == "-" {
                "standard input".to_owned()
            } else {
                name.clone()
            };
            let header = format!("{}==> {} <==\n", if first { "" } else { "\n" }, shown);
            prog.out(header.as_bytes()).await?;
        }
        first = false;
        let n = usize::try_from(count.value).unwrap_or(usize::MAX);
        let selected = if count.lines {
            let all = lines(&bytes);
            let from = if count.other_end {
                n.saturating_sub(1).min(all.len())
            } else {
                all.len().saturating_sub(n)
            };
            all.get(from..).unwrap_or_default().concat()
        } else {
            let from = if count.other_end {
                n.saturating_sub(1).min(bytes.len())
            } else {
                bytes.len().saturating_sub(n)
            };
            bytes.get(from..).unwrap_or_default().to_vec()
        };
        prog.out(&selected).await?;
    }
    Ok(status)
}

// ---------------------------------------------------------------------------
// wc
// ---------------------------------------------------------------------------

#[derive(Clone, Copy, Default)]
struct Counts {
    lines: u64,
    words: u64,
    chars: u64,
    bytes: u64,
    longest: u64,
}

fn count(bytes: &[u8]) -> Counts {
    let text = String::from_utf8_lossy(bytes);
    let mut counts = Counts {
        bytes: bytes.len() as u64,
        ..Counts::default()
    };
    let mut in_word = false;
    let mut width = 0u64;
    for ch in text.chars() {
        counts.chars = counts.chars.saturating_add(1);
        match ch {
            '\n' => {
                counts.lines = counts.lines.saturating_add(1);
                counts.longest = counts.longest.max(width);
                width = 0;
            }
            '\t' => width = (width / 8).saturating_add(1).saturating_mul(8),
            _ => width = width.saturating_add(1),
        }
        if ch.is_whitespace() {
            in_word = false;
        } else if !in_word {
            in_word = true;
            counts.words = counts.words.saturating_add(1);
        }
    }
    counts.longest = counts.longest.max(width);
    counts
}

pub async fn wc(prog: &mut Prog<'_>, args: &[String]) -> Result<i32, Flow> {
    let (options, operands) = split_args(args);
    let (mut l, mut w, mut c, mut m, mut big) = (false, false, false, false, false);
    for option in &options {
        match option.as_str() {
            "--lines" => l = true,
            "--words" => w = true,
            "--bytes" => c = true,
            "--chars" => m = true,
            "--max-line-length" => big = true,
            _ => {
                for flag in option.trim_start_matches('-').chars() {
                    match flag {
                        'l' => l = true,
                        'w' => w = true,
                        'c' => c = true,
                        'm' => m = true,
                        'L' => big = true,
                        other => {
                            prog.err(&format!("invalid option -- '{other}'")).await?;
                            prog.sh
                                .error_text("Try 'wc --help' for more information.\n")
                                .await?;
                            return Ok(1);
                        }
                    }
                }
            }
        }
    }
    if !(l || w || c || m || big) {
        l = true;
        w = true;
        c = true;
    }
    let columns = [l, w, m, c, big].iter().filter(|x| **x).count();
    let named = !operands.is_empty();
    let operands = operands_or_stdin(operands);
    let mut results: Vec<(Option<Counts>, String)> = Vec::new();
    let mut status = 0;
    let mut total_size = 0u64;
    let mut any_stream = false;
    for name in &operands {
        if name == "-" {
            any_stream = true;
        }
        match read_operand(prog, name).await? {
            Ok(bytes) => {
                total_size = total_size.saturating_add(bytes.len() as u64);
                results.push((Some(count(&bytes)), name.clone()));
            }
            Err(error) => {
                prog.err(&format!("{}: {}", name, describe(error))).await?;
                status = 1;
                if error == HostError::IsADirectory {
                    results.push((Some(Counts::default()), name.clone()));
                } else {
                    results.push((None, name.clone()));
                }
            }
        }
    }
    let width = if columns == 1 && operands.len() <= 1 {
        1
    } else {
        let digits = total_size.to_string().len();
        if any_stream {
            digits.max(7)
        } else {
            digits.max(1)
        }
    };
    let format = |counts: &Counts, name: Option<&str>| -> String {
        let mut fields = Vec::new();
        for (on, value) in [
            (l, counts.lines),
            (w, counts.words),
            (m, counts.chars),
            (c, counts.bytes),
            (big, counts.longest),
        ] {
            if on {
                fields.push(format!("{value:>width$}"));
            }
        }
        let mut line = fields.join(" ");
        if let Some(name) = name {
            line.push(' ');
            line.push_str(name);
        }
        line.push('\n');
        line
    };
    let mut total = Counts::default();
    let mut out = String::new();
    for (counts, name) in &results {
        let Some(counts) = counts else { continue };
        total.lines = total.lines.saturating_add(counts.lines);
        total.words = total.words.saturating_add(counts.words);
        total.chars = total.chars.saturating_add(counts.chars);
        total.bytes = total.bytes.saturating_add(counts.bytes);
        total.longest = total.longest.max(counts.longest);
        out.push_str(&format(counts, if named { Some(name) } else { None }));
    }
    if operands.len() > 1 {
        out.push_str(&format(&total, Some("total")));
    }
    prog.out(out.as_bytes()).await?;
    Ok(status)
}

// ---------------------------------------------------------------------------
// cut
// ---------------------------------------------------------------------------

/// Ranges of a cut list, 1-based and inclusive; `None` as the end is open.
fn parse_list(text: &str) -> Result<Vec<(usize, Option<usize>)>, String> {
    let mut ranges = Vec::new();
    for piece in text.split([',', ' ']) {
        if piece.is_empty() {
            return Err("invalid byte, character or field list".to_owned());
        }
        let (start, end) = match piece.split_once('-') {
            Some((a, b)) => {
                let start = if a.is_empty() {
                    1
                } else {
                    a.parse::<usize>()
                        .map_err(|_| format!("invalid field value ‘{a}’"))?
                };
                let end = if b.is_empty() {
                    None
                } else {
                    Some(
                        b.parse::<usize>()
                            .map_err(|_| format!("invalid field value ‘{b}’"))?,
                    )
                };
                if a.is_empty() && b.is_empty() {
                    return Err("invalid range with no endpoint: -".to_owned());
                }
                (start, end)
            }
            None => {
                let n = piece
                    .parse::<usize>()
                    .map_err(|_| format!("invalid field value ‘{piece}’"))?;
                (n, Some(n))
            }
        };
        if start == 0 {
            return Err(if text.contains('-') {
                "fields and positions are numbered from 1".to_owned()
            } else {
                "fields are numbered from 1".to_owned()
            });
        }
        if end.is_some_and(|e| e < start) {
            return Err("invalid decreasing range".to_owned());
        }
        ranges.push((start, end));
    }
    Ok(ranges)
}

fn selected(ranges: &[(usize, Option<usize>)], position: usize) -> bool {
    ranges
        .iter()
        .any(|(start, end)| position >= *start && end.is_none_or(|e| position <= e))
}

pub async fn cut(prog: &mut Prog<'_>, args: &[String]) -> Result<i32, Flow> {
    let mut mode: Option<char> = None;
    let mut list = String::new();
    let mut delimiter = '\t';
    let mut only_delimited = false;
    let mut complement = false;
    let mut output_delimiter: Option<String> = None;
    let mut operands = Vec::new();
    let mut index = 0usize;
    while let Some(arg) = args.get(index) {
        index = index.saturating_add(1);
        if let Some(value) = arg.strip_prefix("--output-delimiter=") {
            output_delimiter = Some(value.to_owned());
            continue;
        }
        match arg.as_str() {
            "--complement" => complement = true,
            "-s" | "--only-delimited" => only_delimited = true,
            "-n" => {}
            _ if arg.starts_with('-') && arg.len() > 1 => {
                let flag = arg.chars().nth(1).unwrap_or('-');
                let rest = arg.get(2..).unwrap_or_default().to_owned();
                let value = if rest.is_empty() {
                    let value = args.get(index).cloned().unwrap_or_default();
                    index = index.saturating_add(1);
                    value
                } else {
                    rest
                };
                match flag {
                    'b' | 'c' | 'f' => {
                        mode = Some(flag);
                        list = value;
                    }
                    'd' => {
                        let mut chars = value.chars();
                        let first = chars.next();
                        if chars.next().is_some() {
                            prog.err("the delimiter must be a single character").await?;
                            prog.sh
                                .error_text("Try 'cut --help' for more information.\n")
                                .await?;
                            return Ok(1);
                        }
                        delimiter = first.unwrap_or('\0');
                    }
                    other => {
                        prog.err(&format!("invalid option -- '{other}'")).await?;
                        prog.sh
                            .error_text("Try 'cut --help' for more information.\n")
                            .await?;
                        return Ok(1);
                    }
                }
            }
            _ => operands.push(arg.clone()),
        }
    }
    let Some(mode) = mode else {
        prog.err("you must specify a list of bytes, characters, or fields")
            .await?;
        prog.sh
            .error_text("Try 'cut --help' for more information.\n")
            .await?;
        return Ok(1);
    };
    let ranges = match parse_list(&list) {
        Ok(ranges) => ranges,
        Err(message) => {
            prog.err(&message).await?;
            prog.sh
                .error_text("Try 'cut --help' for more information.\n")
                .await?;
            return Ok(1);
        }
    };
    let mut status = 0;
    for name in operands_or_stdin(operands) {
        let bytes = match read_operand(prog, &name).await? {
            Ok(bytes) => bytes,
            Err(error) => {
                prog.err(&format!("{}: {}", name, describe(error))).await?;
                status = 1;
                continue;
            }
        };
        let mut out: Vec<u8> = Vec::new();
        for line in lines(&bytes) {
            let body = strip_newline(line);
            let pick = |position: usize| selected(&ranges, position) != complement;
            match mode {
                'b' => {
                    for (i, byte) in body.iter().enumerate() {
                        if pick(i.saturating_add(1)) {
                            out.push(*byte);
                        }
                    }
                }
                'c' => {
                    let text = String::from_utf8_lossy(body);
                    for (i, ch) in text.chars().enumerate() {
                        if pick(i.saturating_add(1)) {
                            let mut buffer = [0u8; 4];
                            out.extend_from_slice(ch.encode_utf8(&mut buffer).as_bytes());
                        }
                    }
                }
                _ => {
                    let text = String::from_utf8_lossy(body).into_owned();
                    if !text.contains(delimiter) {
                        if !only_delimited {
                            out.extend_from_slice(body);
                            out.push(b'\n');
                        }
                        continue;
                    }
                    let joiner = output_delimiter
                        .clone()
                        .unwrap_or_else(|| delimiter.to_string());
                    let fields: Vec<&str> = text.split(delimiter).collect();
                    let kept: Vec<&str> = fields
                        .iter()
                        .enumerate()
                        .filter(|(i, _)| pick(i.saturating_add(1)))
                        .map(|(_, f)| *f)
                        .collect();
                    out.extend_from_slice(kept.join(&joiner).as_bytes());
                }
            }
            out.push(b'\n');
        }
        prog.out(&out).await?;
    }
    Ok(status)
}

// ---------------------------------------------------------------------------
// sort
// ---------------------------------------------------------------------------

#[derive(Clone, Default)]
struct KeyOptions {
    numeric: bool,
    general: bool,
    human: bool,
    reverse: bool,
    fold: bool,
    blanks: bool,
    dictionary: bool,
    version: bool,
    month: bool,
}

#[derive(Clone)]
struct Key {
    start_field: usize,
    start_char: usize,
    end_field: Option<usize>,
    end_char: usize,
    options: KeyOptions,
    has_options: bool,
}

fn parse_key(spec: &str) -> Option<Key> {
    let (start, end) = match spec.split_once(',') {
        Some((a, b)) => (a, Some(b)),
        None => (spec, None),
    };
    let parse_pos = |text: &str| -> Option<(usize, usize, KeyOptions, bool)> {
        let digits_end = text
            .find(|c: char| !c.is_ascii_digit() && c != '.')
            .unwrap_or(text.len());
        let pos = text.get(..digits_end)?;
        let flags = text.get(digits_end..)?;
        let (field, char_index) = match pos.split_once('.') {
            Some((f, c)) => (f.parse().ok()?, c.parse().ok()?),
            None => (pos.parse().ok()?, 0),
        };
        let mut options = KeyOptions::default();
        for flag in flags.chars() {
            match flag {
                'n' => options.numeric = true,
                'g' => options.general = true,
                'h' => options.human = true,
                'r' => options.reverse = true,
                'f' => options.fold = true,
                'b' => options.blanks = true,
                'd' => options.dictionary = true,
                'V' => options.version = true,
                'M' => options.month = true,
                _ => return None,
            }
        }
        Some((field, char_index, options, !flags.is_empty()))
    };
    let (start_field, start_char, mut options, mut has_options) = parse_pos(start)?;
    if start_field == 0 {
        return None;
    }
    let (end_field, end_char) = match end {
        Some(end) => {
            let (field, char_index, end_options, end_has) = parse_pos(end)?;
            if end_has {
                has_options = true;
                options.numeric |= end_options.numeric;
                options.reverse |= end_options.reverse;
                options.fold |= end_options.fold;
                options.general |= end_options.general;
                options.human |= end_options.human;
                options.version |= end_options.version;
            }
            (Some(field), char_index)
        }
        None => (None, 0),
    };
    Some(Key {
        start_field,
        start_char,
        end_field,
        end_char,
        options,
        has_options,
    })
}

/// The fields of a line: with a separator, split on it; without, each field takes its leading blanks.
fn sort_fields(line: &str, separator: Option<char>) -> Vec<(usize, usize)> {
    let chars: Vec<char> = line.chars().collect();
    let mut fields = Vec::new();
    match separator {
        Some(sep) => {
            let mut start = 0usize;
            for (i, c) in chars.iter().enumerate() {
                if *c == sep {
                    fields.push((start, i));
                    start = i.saturating_add(1);
                }
            }
            fields.push((start, chars.len()));
        }
        None => {
            let mut i = 0usize;
            while i < chars.len() {
                let start = i;
                while chars.get(i).is_some_and(|c| *c == ' ' || *c == '\t') {
                    i = i.saturating_add(1);
                }
                while chars.get(i).is_some_and(|c| *c != ' ' && *c != '\t') {
                    i = i.saturating_add(1);
                }
                fields.push((start, i));
            }
        }
    }
    fields
}

fn key_text(line: &str, key: &Key, separator: Option<char>, blanks: bool) -> String {
    let chars: Vec<char> = line.chars().collect();
    let fields = sort_fields(line, separator);
    let skip_blanks = |mut at: usize| {
        while chars.get(at).is_some_and(|c| *c == ' ' || *c == '\t') {
            at = at.saturating_add(1);
        }
        at
    };
    let start = match fields.get(key.start_field.saturating_sub(1)) {
        Some((s, e)) => {
            let base = if blanks || key.options.blanks {
                skip_blanks(*s)
            } else {
                *s
            };
            if key.start_char > 0 {
                base.saturating_add(key.start_char.saturating_sub(1))
                    .min(*e)
            } else {
                base
            }
        }
        None => chars.len(),
    };
    let end = match key.end_field {
        None => chars.len(),
        Some(field) => match fields.get(field.saturating_sub(1)) {
            Some((s, e)) => {
                if key.end_char == 0 {
                    *e
                } else {
                    let base = if blanks || key.options.blanks {
                        skip_blanks(*s)
                    } else {
                        *s
                    };
                    base.saturating_add(key.end_char).min(*e)
                }
            }
            None => chars.len(),
        },
    };
    chars
        .get(start..end.max(start))
        .unwrap_or_default()
        .iter()
        .collect()
}

fn numeric_value(text: &str) -> f64 {
    let trimmed = text.trim_start_matches([' ', '\t']);
    let mut end = 0usize;
    let mut seen_digit = false;
    let mut seen_point = false;
    for (i, c) in trimmed.char_indices() {
        if i == 0 && c == '-' {
            end = i.saturating_add(1);
            continue;
        }
        if c.is_ascii_digit() {
            seen_digit = true;
            end = i.saturating_add(1);
        } else if c == '.' && !seen_point {
            seen_point = true;
            end = i.saturating_add(1);
        } else {
            break;
        }
    }
    if !seen_digit {
        return 0.0;
    }
    trimmed
        .get(..end)
        .and_then(|t| t.parse::<f64>().ok())
        .unwrap_or(0.0)
}

fn human_value(text: &str) -> f64 {
    let trimmed = text.trim();
    let number = numeric_value(trimmed);
    let suffix = trimmed
        .trim_start_matches(|c: char| c.is_ascii_digit() || c == '.' || c == '-')
        .chars()
        .next();
    let power = match suffix {
        Some('K' | 'k') => 1,
        Some('M') => 2,
        Some('G') => 3,
        Some('T') => 4,
        Some('P') => 5,
        Some('E') => 6,
        _ => 0,
    };
    number * 1024f64.powi(power)
}

fn compare_keys(a: &str, b: &str, options: &KeyOptions) -> Ordering {
    let ordering = if options.numeric {
        numeric_value(a)
            .partial_cmp(&numeric_value(b))
            .unwrap_or(Ordering::Equal)
    } else if options.general {
        let parse = |t: &str| t.trim().parse::<f64>().unwrap_or(f64::NEG_INFINITY);
        parse(a).partial_cmp(&parse(b)).unwrap_or(Ordering::Equal)
    } else if options.human {
        human_value(a)
            .partial_cmp(&human_value(b))
            .unwrap_or(Ordering::Equal)
    } else if options.version {
        version_compare(a, b)
    } else {
        let prepare = |t: &str| -> String {
            let mut out: String = if options.dictionary {
                t.chars()
                    .filter(|c| c.is_alphanumeric() || c.is_whitespace())
                    .collect()
            } else {
                t.to_owned()
            };
            if options.fold {
                out = out.to_uppercase();
            }
            out
        };
        prepare(a).as_bytes().cmp(prepare(b).as_bytes())
    };
    if options.reverse {
        ordering.reverse()
    } else {
        ordering
    }
}

fn version_compare(a: &str, b: &str) -> Ordering {
    let pieces = |t: &str| -> Vec<(bool, String)> {
        let mut out: Vec<(bool, String)> = Vec::new();
        for c in t.chars() {
            let digit = c.is_ascii_digit();
            match out.last_mut() {
                Some((d, s)) if *d == digit => s.push(c),
                _ => out.push((digit, c.to_string())),
            }
        }
        out
    };
    let (pa, pb) = (pieces(a), pieces(b));
    for (x, y) in pa.iter().zip(pb.iter()) {
        let ordering = if x.0 && y.0 {
            x.1.parse::<u128>()
                .unwrap_or(0)
                .cmp(&y.1.parse::<u128>().unwrap_or(0))
        } else {
            x.1.cmp(&y.1)
        };
        if ordering != Ordering::Equal {
            return ordering;
        }
    }
    pa.len().cmp(&pb.len())
}

pub async fn sort(prog: &mut Prog<'_>, args: &[String]) -> Result<i32, Flow> {
    let mut global = KeyOptions::default();
    let mut keys: Vec<Key> = Vec::new();
    let mut separator: Option<char> = None;
    let mut unique = false;
    let mut stable = false;
    let mut check = false;
    let mut output: Option<String> = None;
    let mut zero = false;
    let mut operands = Vec::new();
    let mut index = 0usize;
    let mut done = false;
    while let Some(arg) = args.get(index) {
        index = index.saturating_add(1);
        if done || !arg.starts_with('-') || arg == "-" {
            operands.push(arg.clone());
            continue;
        }
        match arg.as_str() {
            "--" => {
                done = true;
                continue;
            }
            "--numeric-sort" => global.numeric = true,
            "--reverse" => global.reverse = true,
            "--unique" => unique = true,
            "--ignore-case" => global.fold = true,
            _ if arg.starts_with("--key=") => {
                if let Some(key) = parse_key(arg.get(6..).unwrap_or_default()) {
                    keys.push(key);
                }
            }
            _ if arg.starts_with("--field-separator=") => {
                separator = arg.get(18..).and_then(|s| s.chars().next())
            }
            _ => {
                let flags = arg.get(1..).unwrap_or_default();
                for (at, flag) in flags.char_indices() {
                    let rest = flags
                        .get(at.saturating_add(1)..)
                        .unwrap_or_default()
                        .to_owned();
                    let mut value = || {
                        if rest.is_empty() {
                            let v = args.get(index).cloned().unwrap_or_default();
                            index = index.saturating_add(1);
                            v
                        } else {
                            rest.clone()
                        }
                    };
                    match flag {
                        'n' => global.numeric = true,
                        'g' => global.general = true,
                        'h' => global.human = true,
                        'r' => global.reverse = true,
                        'f' => global.fold = true,
                        'b' => global.blanks = true,
                        'd' => global.dictionary = true,
                        'V' => global.version = true,
                        'M' => global.month = true,
                        'u' => unique = true,
                        's' => stable = true,
                        'c' | 'C' => check = true,
                        'z' => zero = true,
                        'k' => {
                            let spec = value();
                            match parse_key(&spec) {
                                Some(key) => keys.push(key),
                                None => {
                                    prog.err(&format!("invalid number at field start: invalid count at start of ‘{spec}’")).await?;
                                    return Ok(2);
                                }
                            }
                            break;
                        }
                        't' => {
                            separator = value().chars().next();
                            break;
                        }
                        'o' => {
                            output = Some(value());
                            break;
                        }
                        'S' | 'T' => {
                            let _ = value();
                            break;
                        }
                        other => {
                            prog.err(&format!("invalid option -- '{other}'")).await?;
                            prog.sh
                                .error_text("Try 'sort --help' for more information.\n")
                                .await?;
                            return Ok(2);
                        }
                    }
                }
            }
        }
    }
    let mut all_lines: Vec<String> = Vec::new();
    let mut origins: Vec<String> = Vec::new();
    let terminator = if zero { b'\0' } else { b'\n' };
    for name in operands_or_stdin(operands) {
        let bytes = match read_operand(prog, &name).await? {
            Ok(bytes) => bytes,
            Err(error) => {
                prog.err(&format!("cannot read: {}: {}", name, describe(error)))
                    .await?;
                return Ok(2);
            }
        };
        let text = String::from_utf8_lossy(&bytes).into_owned();
        let mut pieces: Vec<&str> = text.split(char::from(terminator)).collect();
        if pieces.last().is_some_and(|last| last.is_empty()) {
            pieces.pop();
        }
        for piece in pieces {
            all_lines.push(piece.to_owned());
            origins.push(name.clone());
        }
    }
    let compare = |a: &str, b: &str| -> Ordering {
        if keys.is_empty() {
            let ordering = compare_keys(
                &if global.blanks {
                    a.trim_start().to_owned()
                } else {
                    a.to_owned()
                },
                &if global.blanks {
                    b.trim_start().to_owned()
                } else {
                    b.to_owned()
                },
                &global,
            );
            if ordering != Ordering::Equal || stable || unique {
                return ordering;
            }
        } else {
            for key in &keys {
                let options = if key.has_options {
                    key.options.clone()
                } else {
                    KeyOptions {
                        reverse: global.reverse,
                        ..global.clone()
                    }
                };
                let options = if key.has_options && global.reverse && !key.options.reverse {
                    KeyOptions {
                        reverse: false,
                        ..options
                    }
                } else {
                    options
                };
                let ka = key_text(a, key, separator, global.blanks);
                let kb = key_text(b, key, separator, global.blanks);
                let ordering = compare_keys(&ka, &kb, &options);
                if ordering != Ordering::Equal {
                    return ordering;
                }
            }
            if stable || unique {
                return Ordering::Equal;
            }
        }
        // The last resort: the whole lines, byte by byte.
        let ordering = a.as_bytes().cmp(b.as_bytes());
        if global.reverse {
            ordering.reverse()
        } else {
            ordering
        }
    };
    if check {
        for (i, pair) in all_lines.windows(2).enumerate() {
            if let [a, b] = pair {
                let ordering = compare(a, b);
                if ordering == Ordering::Greater || (unique && ordering == Ordering::Equal) {
                    let origin = origins
                        .get(i.saturating_add(1))
                        .cloned()
                        .unwrap_or_default();
                    let shown = if origin == "-" {
                        "-".to_owned()
                    } else {
                        origin
                    };
                    prog.err(&format!(
                        "{}:{}: disorder: {}",
                        shown,
                        i.saturating_add(2),
                        b
                    ))
                    .await?;
                    return Ok(1);
                }
            }
        }
        return Ok(0);
    }
    all_lines.sort_by(|a, b| compare(a, b));
    if unique {
        all_lines.dedup_by(|b, a| compare(a, b) == Ordering::Equal);
    }
    let mut out = Vec::new();
    for line in all_lines {
        out.extend_from_slice(line.as_bytes());
        out.push(terminator);
    }
    match output {
        Some(path) => {
            if let Err(error) = prog.write_file(&path, out).await? {
                prog.err(&format!("open failed: {}: {}", path, describe(error)))
                    .await?;
                return Ok(2);
            }
        }
        None => prog.out(&out).await?,
    }
    Ok(0)
}

// ---------------------------------------------------------------------------
// uniq
// ---------------------------------------------------------------------------

pub async fn uniq(prog: &mut Prog<'_>, args: &[String]) -> Result<i32, Flow> {
    let mut counted = false;
    let mut repeated = false;
    let mut unique_only = false;
    let mut ignore_case = false;
    let mut skip_fields = 0usize;
    let mut skip_chars = 0usize;
    let mut compare_chars: Option<usize> = None;
    let mut all_repeated = false;
    let mut operands = Vec::new();
    let mut index = 0usize;
    while let Some(arg) = args.get(index) {
        index = index.saturating_add(1);
        if !arg.starts_with('-') || arg == "-" {
            operands.push(arg.clone());
            continue;
        }
        let flags = arg.get(1..).unwrap_or_default();
        for (at, flag) in flags.char_indices() {
            let rest = flags
                .get(at.saturating_add(1)..)
                .unwrap_or_default()
                .to_owned();
            let mut value = || {
                if rest.is_empty() {
                    let v = args.get(index).cloned().unwrap_or_default();
                    index = index.saturating_add(1);
                    v
                } else {
                    rest.clone()
                }
            };
            match flag {
                'c' => counted = true,
                'd' => repeated = true,
                'D' => all_repeated = true,
                'u' => unique_only = true,
                'i' => ignore_case = true,
                'f' => {
                    skip_fields = value().parse().unwrap_or(0);
                    break;
                }
                's' => {
                    skip_chars = value().parse().unwrap_or(0);
                    break;
                }
                'w' => {
                    compare_chars = value().parse().ok();
                    break;
                }
                other => {
                    prog.err(&format!("invalid option -- '{other}'")).await?;
                    prog.sh
                        .error_text("Try 'uniq --help' for more information.\n")
                        .await?;
                    return Ok(1);
                }
            }
        }
    }
    let input = operands.first().cloned().unwrap_or_else(|| "-".to_owned());
    let bytes = match read_operand(prog, &input).await? {
        Ok(bytes) => bytes,
        Err(error) => {
            prog.err(&format!("{}: {}", input, describe(error))).await?;
            return Ok(1);
        }
    };
    let text = String::from_utf8_lossy(&bytes).into_owned();
    let mut items: Vec<&str> = text.split('\n').collect();
    if items.last().is_some_and(|l| l.is_empty()) {
        items.pop();
    }
    let key = |line: &str| -> String {
        let mut rest = line;
        for _ in 0..skip_fields {
            rest = rest.trim_start_matches([' ', '\t']);
            rest = rest.trim_start_matches(|c: char| c != ' ' && c != '\t');
        }
        let mut key: String = rest.chars().skip(skip_chars).collect();
        if let Some(n) = compare_chars {
            key = key.chars().take(n).collect();
        }
        if ignore_case {
            key = key.to_lowercase();
        }
        key
    };
    let mut groups: Vec<(usize, Vec<&str>)> = Vec::new();
    for line in items {
        match groups.last_mut() {
            Some((count, members))
                if members.first().is_some_and(|first| key(first) == key(line)) =>
            {
                *count = count.saturating_add(1);
                members.push(line);
            }
            _ => groups.push((1, vec![line])),
        }
    }
    let mut out = String::new();
    for (count, members) in groups {
        if repeated && count < 2 || unique_only && count > 1 || all_repeated && count < 2 {
            continue;
        }
        if all_repeated {
            for member in members {
                out.push_str(member);
                out.push('\n');
            }
            continue;
        }
        let first = members.first().copied().unwrap_or_default();
        if counted {
            out.push_str(&format!("{count:7} {first}\n"));
        } else {
            out.push_str(first);
            out.push('\n');
        }
    }
    match operands.get(1) {
        Some(path) => {
            if let Err(error) = prog.write_file(path, out.into_bytes()).await? {
                prog.err(&format!("{}: {}", path, describe(error))).await?;
                return Ok(1);
            }
        }
        None => prog.out(out.as_bytes()).await?,
    }
    Ok(0)
}

// ---------------------------------------------------------------------------
// tr
// ---------------------------------------------------------------------------

/// Expand a `tr` set: escapes, ranges, classes and `[c*n]` repeats.
fn tr_set(text: &str) -> Result<Vec<char>, String> {
    let chars: Vec<char> = text.chars().collect();
    let mut out: Vec<char> = Vec::new();
    let mut index = 0usize;
    let read_char = |index: &mut usize| -> Option<char> {
        let ch = *chars.get(*index)?;
        *index = index.saturating_add(1);
        if ch != '\\' {
            return Some(ch);
        }
        let Some(&next) = chars.get(*index) else {
            return Some('\\');
        };
        *index = index.saturating_add(1);
        Some(match next {
            'n' => '\n',
            't' => '\t',
            'r' => '\r',
            'a' => '\u{7}',
            'b' => '\u{8}',
            'f' => '\u{c}',
            'v' => '\u{b}',
            '\\' => '\\',
            '0'..='7' => {
                let mut value = next.to_digit(8).unwrap_or(0);
                for _ in 0..2 {
                    match chars.get(*index).and_then(|c| c.to_digit(8)) {
                        Some(d) => {
                            value = value.saturating_mul(8).saturating_add(d);
                            *index = index.saturating_add(1);
                        }
                        None => break,
                    }
                }
                char::from_u32(value).unwrap_or('\0')
            }
            other => other,
        })
    };
    while index < chars.len() {
        if chars.get(index) == Some(&'[') && chars.get(index.saturating_add(1)) == Some(&':') {
            let rest: String = chars
                .get(index.saturating_add(2)..)
                .unwrap_or_default()
                .iter()
                .collect();
            if let Some(end) = rest.find(":]") {
                let name = rest.get(..end).unwrap_or_default();
                let members: Vec<char> = (0u8..=127)
                    .map(char::from)
                    .filter(|c| crate::machine::pattern::named_class(name, *c))
                    .collect();
                if members.is_empty()
                    && !matches!(
                        name,
                        "alpha"
                            | "digit"
                            | "alnum"
                            | "upper"
                            | "lower"
                            | "space"
                            | "blank"
                            | "punct"
                            | "print"
                            | "graph"
                            | "cntrl"
                            | "xdigit"
                    )
                {
                    return Err(format!("invalid character class ‘{name}’"));
                }
                out.extend(members);
                index = index
                    .saturating_add(2)
                    .saturating_add(end)
                    .saturating_add(2);
                continue;
            }
        }
        if chars.get(index) == Some(&'[') && chars.get(index.saturating_add(2)) == Some(&'*') {
            let rest: String = chars
                .get(index.saturating_add(3)..)
                .unwrap_or_default()
                .iter()
                .collect();
            if let Some(end) = rest.find(']') {
                let ch = chars.get(index.saturating_add(1)).copied().unwrap_or(' ');
                let count: usize = rest.get(..end).unwrap_or_default().parse().unwrap_or(0);
                out.extend(std::iter::repeat_n(
                    ch,
                    count.max(if count == 0 { 0 } else { 1 }),
                ));
                if count == 0 {
                    out.push('\u{F8FF}');
                }
                index = index
                    .saturating_add(3)
                    .saturating_add(end)
                    .saturating_add(1);
                continue;
            }
        }
        let Some(ch) = read_char(&mut index) else {
            break;
        };
        if chars.get(index) == Some(&'-') && index.saturating_add(1) < chars.len() {
            let mut probe = index.saturating_add(1);
            if let Some(end) = read_char(&mut probe) {
                if end < ch {
                    return Err(format!(
                        "range-endpoints of ‘{ch}-{end}’ are in reverse collating sequence order"
                    ));
                }
                let (a, b) = (u32::from(ch), u32::from(end));
                out.extend((a..=b).filter_map(char::from_u32));
                index = probe;
                continue;
            }
        }
        out.push(ch);
    }
    Ok(out)
}

pub async fn tr(prog: &mut Prog<'_>, args: &[String]) -> Result<i32, Flow> {
    let mut delete = false;
    let mut squeeze = false;
    let mut complement = false;
    let mut truncate = false;
    let mut sets = Vec::new();
    for arg in args {
        if arg.starts_with('-') && arg.len() > 1 && sets.is_empty() {
            for flag in arg.get(1..).unwrap_or_default().chars() {
                match flag {
                    'd' => delete = true,
                    's' => squeeze = true,
                    'c' | 'C' => complement = true,
                    't' => truncate = true,
                    other => {
                        prog.err(&format!("invalid option -- '{other}'")).await?;
                        prog.sh
                            .error_text("Try 'tr --help' for more information.\n")
                            .await?;
                        return Ok(1);
                    }
                }
            }
            continue;
        }
        sets.push(arg.clone());
    }
    let wanted = if delete && squeeze {
        2
    } else if delete || (squeeze && sets.len() < 2) {
        1
    } else {
        2
    };
    if sets.len() < wanted {
        let message = if sets.is_empty() {
            "missing operand".to_owned()
        } else {
            format!(
                "missing operand after ‘{}’",
                sets.last().cloned().unwrap_or_default()
            )
        };
        prog.err(&message).await?;
        prog.sh
            .error_text("Try 'tr --help' for more information.\n")
            .await?;
        return Ok(1);
    }
    if sets.len() > wanted {
        prog.err(&format!(
            "extra operand ‘{}’",
            sets.get(wanted).cloned().unwrap_or_default()
        ))
        .await?;
        prog.sh
            .error_text("Try 'tr --help' for more information.\n")
            .await?;
        return Ok(1);
    }
    let first = match tr_set(sets.first().map_or("", String::as_str)) {
        Ok(set) => set,
        Err(message) => {
            prog.err(&message).await?;
            return Ok(1);
        }
    };
    let mut second = match sets.get(1).map(|s| tr_set(s)).transpose() {
        Ok(set) => set.unwrap_or_default(),
        Err(message) => {
            prog.err(&message).await?;
            return Ok(1);
        }
    };
    let bytes = prog.stdin_all().await?;
    let text = String::from_utf8_lossy(&bytes);
    let in_first = |c: char| first.contains(&c) != complement;
    let mut out = String::new();
    let mut last: Option<char> = None;
    if delete {
        let squeeze_set = second.clone();
        for c in text.chars() {
            if in_first(c) {
                continue;
            }
            if squeeze && squeeze_set.contains(&c) && last == Some(c) {
                continue;
            }
            out.push(c);
            last = Some(c);
        }
    } else if sets.len() == 1 {
        for c in text.chars() {
            if squeeze && in_first(c) && last == Some(c) {
                continue;
            }
            out.push(c);
            last = Some(c);
        }
    } else {
        let filler = second.iter().position(|c| *c == '\u{F8FF}');
        if let Some(at) = filler {
            let ch = at
                .checked_sub(1)
                .and_then(|i| second.get(i))
                .copied()
                .unwrap_or(' ');
            let need = first.len().saturating_sub(second.len().saturating_sub(1));
            let mut expanded: Vec<char> = second.get(..at).unwrap_or_default().to_vec();
            expanded.extend(std::iter::repeat_n(ch, need));
            expanded.extend(second.get(at.saturating_add(1)..).unwrap_or_default());
            second = expanded;
        }
        if truncate {
            second.truncate(first.len());
        }
        let map = |c: char| -> char {
            if complement {
                return second.last().copied().unwrap_or(c);
            }
            match first.iter().rposition(|x| *x == c) {
                Some(at) => second.get(at).or(second.last()).copied().unwrap_or(c),
                None => c,
            }
        };
        let upper_lower = sets.first().is_some_and(|s| s.contains("[:lower:]"))
            && sets.get(1).is_some_and(|s| s.contains("[:upper:]"));
        let lower_upper = sets.first().is_some_and(|s| s.contains("[:upper:]"))
            && sets.get(1).is_some_and(|s| s.contains("[:lower:]"));
        for c in text.chars() {
            let mapped = if upper_lower && c.is_ascii_lowercase() {
                c.to_ascii_uppercase()
            } else if lower_upper && c.is_ascii_uppercase() {
                c.to_ascii_lowercase()
            } else if in_first(c) {
                map(c)
            } else {
                c
            };
            if squeeze && second.contains(&mapped) && last == Some(mapped) && in_first(c) {
                continue;
            }
            out.push(mapped);
            last = Some(mapped);
        }
    }
    prog.out(out.as_bytes()).await?;
    Ok(0)
}

// ---------------------------------------------------------------------------
// tee
// ---------------------------------------------------------------------------

pub async fn tee(prog: &mut Prog<'_>, args: &[String]) -> Result<i32, Flow> {
    let mut append = false;
    let mut files = Vec::new();
    for arg in args {
        match arg.as_str() {
            "-a" | "--append" => append = true,
            "-i" | "-p" => {}
            _ => files.push(arg.clone()),
        }
    }
    let mut bytes = Vec::new();
    while let Some(chunk) = prog.stdin_chunk().await? {
        prog.out(&chunk).await?;
        bytes.extend_from_slice(&chunk);
    }
    let mut status = 0;
    for file in files {
        let absolute = prog.abs(&file);
        crate::machine::exec::sync_path(prog.sh, &absolute).await?;
        let reply = prog
            .request(crate::machine::Request::Write {
                path: absolute,
                data: bytes.clone(),
                mode: if append {
                    crate::machine::WriteMode::Append
                } else {
                    crate::machine::WriteMode::Truncate
                },
            })
            .await?;
        if let crate::machine::Reply::Error(error) = reply {
            prog.err(&format!("{}: {}", file, describe(error))).await?;
            status = 1;
        }
    }
    Ok(status)
}
