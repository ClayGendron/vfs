//! GNU `grep`: basic, extended or fixed patterns over files, standard input
//! or, with `-r`, directory trees walked through the machine's requests.

use super::{Prog, describe};
use crate::machine::regex::{Regex, Spent, bre_to_ere};
use crate::machine::{EntryKind, Flow, Reply, Request};

#[derive(Default)]
struct Options {
    extended: bool,
    fixed: bool,
    ignore_case: bool,
    invert: bool,
    count: bool,
    files_with: bool,
    files_without: bool,
    number: bool,
    only: bool,
    recursive: bool,
    word: bool,
    line: bool,
    quiet: bool,
    silent: bool,
    with_name: Option<bool>,
    max: Option<u64>,
    after: usize,
    before: usize,
    byte_offset: bool,
}

/// Characters an extended expression treats specially.
const ERE_SPECIAL: &str = "\\.[]()*+?{}|^$";

fn escape_fixed(text: &str) -> String {
    let mut out = String::new();
    for ch in text.chars() {
        if ERE_SPECIAL.contains(ch) {
            out.push('\\');
        }
        out.push(ch);
    }
    out
}

pub async fn grep(prog: &mut Prog<'_>, args: &[String]) -> Result<i32, Flow> {
    let mut options = Options::default();
    let mut patterns: Vec<String> = Vec::new();
    let mut pattern_given = false;
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
        if let Some(long) = arg.strip_prefix("--") {
            let (name, value) = match long.split_once('=') {
                Some((n, v)) => (n, Some(v.to_owned())),
                None => (long, None),
            };
            match name {
                "extended-regexp" => options.extended = true,
                "fixed-strings" => options.fixed = true,
                "basic-regexp" => options.extended = false,
                "ignore-case" => options.ignore_case = true,
                "invert-match" => options.invert = true,
                "count" => options.count = true,
                "files-with-matches" => options.files_with = true,
                "files-without-match" => options.files_without = true,
                "line-number" => options.number = true,
                "only-matching" => options.only = true,
                "recursive" | "dereference-recursive" => options.recursive = true,
                "word-regexp" => options.word = true,
                "line-regexp" => options.line = true,
                "quiet" | "silent" => options.quiet = true,
                "no-messages" => options.silent = true,
                "with-filename" => options.with_name = Some(true),
                "no-filename" => options.with_name = Some(false),
                "regexp" => {
                    patterns.extend(value.unwrap_or_default().split('\n').map(str::to_owned));
                    pattern_given = true;
                }
                "max-count" => options.max = value.and_then(|v| v.parse().ok()),
                "color" | "colour" | "line-buffered" => {}
                _ => {
                    prog.err(&format!("unrecognized option '{arg}'")).await?;
                    prog.sh.error_text("Usage: grep [OPTION]... PATTERNS [FILE]...\nTry 'grep --help' for more information.\n").await?;
                    return Ok(2);
                }
            }
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
                    let v = args.get(index).cloned();
                    index = index.saturating_add(1);
                    v
                } else {
                    Some(rest.clone())
                }
            };
            match flag {
                'E' => options.extended = true,
                'F' => options.fixed = true,
                'G' => options.extended = false,
                'i' | 'y' => options.ignore_case = true,
                'v' => options.invert = true,
                'c' => options.count = true,
                'l' => options.files_with = true,
                'L' => options.files_without = true,
                'n' => options.number = true,
                'o' => options.only = true,
                'r' | 'R' => options.recursive = true,
                'w' => options.word = true,
                'x' => options.line = true,
                'q' => options.quiet = true,
                's' => options.silent = true,
                'h' => options.with_name = Some(false),
                'H' => options.with_name = Some(true),
                'b' => options.byte_offset = true,
                'I' | 'a' | 'U' => {}
                'e' => {
                    patterns.extend(value().unwrap_or_default().split('\n').map(str::to_owned));
                    pattern_given = true;
                    break;
                }
                'f' => {
                    let file = value().unwrap_or_default();
                    match prog.file(&file).await? {
                        Ok(bytes) => {
                            let text = String::from_utf8_lossy(&bytes).into_owned();
                            patterns.extend(text.lines().map(str::to_owned));
                        }
                        Err(error) => {
                            prog.err(&format!("{}: {}", file, describe(error))).await?;
                            return Ok(2);
                        }
                    }
                    pattern_given = true;
                    break;
                }
                'm' => {
                    options.max = value().and_then(|v| v.parse().ok());
                    break;
                }
                'A' | 'B' | 'C' => {
                    let n: usize = value().and_then(|v| v.parse().ok()).unwrap_or(0);
                    if flag != 'B' {
                        options.after = n;
                    }
                    if flag != 'A' {
                        options.before = n;
                    }
                    break;
                }
                other => {
                    prog.err(&format!("invalid option -- '{other}'")).await?;
                    prog.sh.error_text("Usage: grep [OPTION]... PATTERNS [FILE]...\nTry 'grep --help' for more information.\n").await?;
                    return Ok(2);
                }
            }
        }
    }
    if !pattern_given {
        if operands.is_empty() {
            prog.sh.error_text("Usage: grep [OPTION]... PATTERNS [FILE]...\nTry 'grep --help' for more information.\n").await?;
            return Ok(2);
        }
        let first = operands.remove(0);
        patterns.extend(first.split('\n').map(str::to_owned));
    }
    let source = patterns
        .iter()
        .map(|p| {
            let body = if options.fixed {
                escape_fixed(p)
            } else if options.extended {
                p.clone()
            } else {
                bre_to_ere(p)
            };
            if options.line {
                format!("^({body})$")
            } else {
                format!("({body})")
            }
        })
        .collect::<Vec<_>>()
        .join("|");
    let regex = match Regex::new(&source, options.ignore_case) {
        Ok(regex) => regex,
        Err(message) => {
            let shown = message.get(..1).map(str::to_uppercase).unwrap_or_default()
                + message.get(1..).unwrap_or_default();
            prog.err(&shown).await?;
            return Ok(2);
        }
    };
    let explicit = !operands.is_empty();
    if operands.is_empty() {
        operands.push(if options.recursive {
            ".".to_owned()
        } else {
            "-".to_owned()
        });
    }
    // Every file to search, with the name it is shown by.
    let mut targets: Vec<(String, String)> = Vec::new();
    let mut status_error = false;
    for operand in &operands {
        if operand == "-" {
            targets.push(("-".to_owned(), "(standard input)".to_owned()));
            continue;
        }
        match prog.stat(operand).await? {
            Some((EntryKind::Directory, _)) => {
                if !options.recursive {
                    if !options.silent {
                        prog.err(&format!("{operand}: Is a directory")).await?;
                    }
                    status_error = true;
                    continue;
                }
                let shown_root = if !explicit && operand == "." {
                    String::new()
                } else {
                    operand.clone()
                };
                walk(prog, operand, &shown_root, &mut targets).await?;
            }
            Some(_) => targets.push((operand.clone(), operand.clone())),
            None => {
                if !options.silent {
                    prog.err(&format!("{operand}: No such file or directory"))
                        .await?;
                }
                status_error = true;
            }
        }
    }
    let show_name = options
        .with_name
        .unwrap_or(operands.len() > 1 || options.recursive);
    let mut any = false;
    for (path, shown) in targets {
        let bytes = match prog.file(&path).await? {
            Ok(bytes) => bytes,
            Err(error) => {
                if !options.silent {
                    prog.err(&format!("{}: {}", shown, describe(error))).await?;
                }
                status_error = true;
                continue;
            }
        };
        if bytes.contains(&0)
            && !options.count
            && !options.files_with
            && !options.files_without
            && !options.quiet
        {
            let matched = search(&regex, &options, &bytes, &shown, false).selected > 0;
            if matched {
                prog.out(format!("Binary file {shown} matches\n").as_bytes())
                    .await?;
                any = true;
            }
            continue;
        }
        let result = search(
            &regex,
            &options,
            &bytes,
            if show_name { &shown } else { "" },
            show_name,
        );
        if result.spent {
            prog.err(&format!(
                "{shown}: the pattern is too complex to match a line"
            ))
            .await?;
            status_error = true;
            continue;
        }
        if result.selected > 0 {
            any = true;
        }
        if options.quiet {
            if any {
                return Ok(0);
            }
            continue;
        }
        if options.files_with {
            if result.selected > 0 {
                prog.out(format!("{shown}\n").as_bytes()).await?;
            }
            continue;
        }
        if options.files_without {
            if result.selected == 0 {
                prog.out(format!("{shown}\n").as_bytes()).await?;
            }
            continue;
        }
        if options.count {
            let line = if show_name {
                format!("{}:{}\n", shown, result.selected)
            } else {
                format!("{}\n", result.selected)
            };
            prog.out(line.as_bytes()).await?;
            continue;
        }
        prog.out(&result.output).await?;
    }
    if options.files_without {
        // `-L` succeeds when it names a file, in grep 3.5 and later.
    }
    if status_error && !(options.quiet && any) {
        return Ok(2);
    }
    Ok(if any { 0 } else { 1 })
}

/// Walk a directory tree, adding every file below it, in directory order.
async fn walk(
    prog: &mut Prog<'_>,
    root: &str,
    shown_root: &str,
    targets: &mut Vec<(String, String)>,
) -> Result<(), Flow> {
    let mut stack = vec![(root.to_owned(), shown_root.to_owned())];
    while let Some((dir, shown)) = stack.pop() {
        let absolute = prog.abs(&dir);
        crate::machine::exec::sync_path(prog.sh, &absolute).await?;
        let entries = match prog.request(Request::List { path: absolute }).await? {
            Reply::Entries(entries) => entries,
            _ => continue,
        };
        let mut subdirs = Vec::new();
        for entry in entries {
            let path = format!("{}/{}", dir.trim_end_matches('/'), entry.name);
            let display = if shown.is_empty() {
                entry.name.clone()
            } else {
                format!("{}/{}", shown.trim_end_matches('/'), entry.name)
            };
            match entry.kind {
                EntryKind::Directory => subdirs.push((path, display)),
                EntryKind::File => targets.push((path, display)),
            }
        }
        for subdir in subdirs.into_iter().rev() {
            stack.push(subdir);
        }
    }
    Ok(())
}

struct Searched {
    selected: u64,
    output: Vec<u8>,
    /// A line the pattern could not be matched against within its budget.
    spent: bool,
}

/// The matches of a line: each a character range, honouring `-w`.
fn line_matches(
    regex: &Regex,
    options: &Options,
    chars: &[char],
) -> Result<Vec<(usize, usize)>, Spent> {
    let mut found = Vec::new();
    let mut from = 0usize;
    while from <= chars.len() {
        let Some(captures) = regex.find_at(chars, from)? else {
            break;
        };
        let Some(Some((start, end))) = captures.first().copied() else {
            break;
        };
        let accept = if options.word {
            let before = start
                .checked_sub(1)
                .and_then(|i| chars.get(i))
                .is_some_and(|c| is_word(*c));
            let after = chars.get(end).is_some_and(|c| is_word(*c));
            !before && !after && end > start
        } else {
            true
        };
        if accept {
            found.push((start, end));
        }
        from = if end > start {
            if accept { end } else { start.saturating_add(1) }
        } else {
            start.saturating_add(1)
        };
    }
    Ok(found)
}

fn is_word(ch: char) -> bool {
    ch.is_alphanumeric() || ch == '_'
}

fn search(regex: &Regex, options: &Options, bytes: &[u8], name: &str, show_name: bool) -> Searched {
    let text = String::from_utf8_lossy(bytes);
    let mut lines: Vec<&str> = text.split('\n').collect();
    if lines.last().is_some_and(|l| l.is_empty()) {
        lines.pop();
    }
    let mut out = Vec::new();
    let mut selected = 0u64;
    let mut spent = false;
    let mut last_printed: Option<usize> = None;
    let mut after_left = 0usize;
    let context = options.after > 0 || options.before > 0;
    let prefix = |number: usize, separator: char| -> String {
        let mut p = String::new();
        if show_name {
            p.push_str(name);
            p.push(separator);
        }
        if options.number {
            p.push_str(&number.to_string());
            p.push(separator);
        }
        p
    };
    for (index, line) in lines.iter().enumerate() {
        if options.max.is_some_and(|max| selected >= max) {
            if after_left > 0 && !options.only {
                // Trailing context still prints after the last match.
            } else {
                break;
            }
        }
        let chars: Vec<char> = line.chars().collect();
        let Ok(matches) = line_matches(regex, options, &chars) else {
            spent = true;
            break;
        };
        let is_match = !matches.is_empty() != options.invert;
        if is_match && !options.max.is_some_and(|max| selected >= max) {
            selected = selected.saturating_add(1);
            if options.count || options.files_with || options.files_without || options.quiet {
                continue;
            }
            if context {
                let start = index.saturating_sub(options.before);
                let from = match last_printed {
                    Some(last) if last.saturating_add(1) > start => last.saturating_add(1),
                    Some(_) => {
                        out.extend_from_slice(b"--\n");
                        start
                    }
                    None => start,
                };
                for (n, before_line) in lines.iter().enumerate().take(index).skip(from) {
                    out.extend_from_slice(
                        format!("{}{}\n", prefix(n.saturating_add(1), '-'), before_line).as_bytes(),
                    );
                }
            }
            if options.only {
                if !options.invert {
                    for (start, end) in matches {
                        if end > start {
                            let piece: String =
                                chars.get(start..end).unwrap_or_default().iter().collect();
                            out.extend_from_slice(
                                format!("{}{}\n", prefix(index.saturating_add(1), ':'), piece)
                                    .as_bytes(),
                            );
                        }
                    }
                }
            } else {
                out.extend_from_slice(
                    format!("{}{}\n", prefix(index.saturating_add(1), ':'), line).as_bytes(),
                );
            }
            last_printed = Some(index);
            after_left = options.after;
        } else if after_left > 0 && context {
            out.extend_from_slice(
                format!("{}{}\n", prefix(index.saturating_add(1), '-'), line).as_bytes(),
            );
            last_printed = Some(index);
            after_left = after_left.saturating_sub(1);
        } else if options.max.is_some_and(|max| selected >= max) {
            break;
        }
    }
    Searched {
        selected,
        output: out,
        spent,
    }
}
