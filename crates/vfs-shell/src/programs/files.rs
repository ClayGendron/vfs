//! The file programs: `ls`, `find`, `cp`, `mv`, `rm`, `mkdir` and `touch`,
//! written against the machine's own requests, so any host that answers
//! them serves these programs unchanged.

use super::{Prog, describe, split_args};
use crate::machine::{Entry, EntryKind, Flow, HostError, Reply, Request};

async fn list(prog: &mut Prog<'_>, path: &str) -> Result<Result<Vec<Entry>, HostError>, Flow> {
    let absolute = prog.abs(path);
    crate::machine::exec::sync_path(prog.sh, &absolute).await?;
    Ok(
        match prog.request(Request::List { path: absolute }).await? {
            Reply::Entries(entries) => Ok(entries),
            Reply::Error(error) => Err(error),
            _ => Err(HostError::Invalid),
        },
    )
}

fn join(base: &str, name: &str) -> String {
    if base.ends_with('/') {
        format!("{base}{name}")
    } else {
        format!("{base}/{name}")
    }
}

fn basename(path: &str) -> &str {
    path.trim_end_matches('/')
        .rsplit('/')
        .next()
        .unwrap_or(path)
}

async fn done_or(prog: &mut Prog<'_>, request: Request) -> Result<Result<(), HostError>, Flow> {
    Ok(match prog.request(request).await? {
        Reply::Error(error) => Err(error),
        _ => Ok(()),
    })
}

// ---------------------------------------------------------------------------
// ls
// ---------------------------------------------------------------------------

pub async fn ls(prog: &mut Prog<'_>, args: &[String]) -> Result<i32, Flow> {
    let (options, mut operands) = split_args(args);
    let (mut all, mut almost, mut recursive, mut directory, mut reverse, mut classify, mut slash) =
        (false, false, false, false, false, false, false);
    for option in &options {
        match option.as_str() {
            "--all" => all = true,
            "--almost-all" => almost = true,
            "--recursive" => recursive = true,
            "--directory" => directory = true,
            "--reverse" => reverse = true,
            "--classify" => classify = true,
            _ if option.starts_with("--color") => {}
            _ => {
                for flag in option.trim_start_matches('-').chars() {
                    match flag {
                        'a' => all = true,
                        'A' => almost = true,
                        'R' => recursive = true,
                        'd' => directory = true,
                        'r' => reverse = true,
                        'F' => classify = true,
                        'p' => slash = true,
                        '1' | 'C' | 'x' | 'h' | 'N' | 'U' | 'f' => {}
                        other => {
                            prog.err(&format!("invalid option -- '{other}'")).await?;
                            prog.sh
                                .error_text("Try 'ls --help' for more information.\n")
                                .await?;
                            return Ok(2);
                        }
                    }
                }
            }
        }
    }
    if operands.is_empty() {
        operands.push(".".to_owned());
    }
    let mut status = 0;
    let mut files = Vec::new();
    let mut dirs = Vec::new();
    for operand in &operands {
        match prog.stat(operand).await? {
            None => {
                prog.err(&format!(
                    "cannot access '{}': {}",
                    operand,
                    describe(HostError::NotFound)
                ))
                .await?;
                status = 2;
            }
            Some((EntryKind::Directory, _)) if !directory => dirs.push(operand.clone()),
            Some((kind, _)) => files.push((operand.clone(), kind)),
        }
    }
    let decorate = |name: &str, kind: EntryKind| -> String {
        if (classify || slash) && kind == EntryKind::Directory {
            format!("{name}/")
        } else {
            name.to_owned()
        }
    };
    let mut out = String::new();
    files.sort_by(|a, b| a.0.cmp(&b.0));
    if reverse {
        files.reverse();
    }
    for (name, kind) in &files {
        out.push_str(&decorate(name, *kind));
        out.push('\n');
    }
    dirs.sort();
    if reverse {
        dirs.reverse();
    }
    let headers = recursive || operands.len() > 1;
    let mut first = files.is_empty();
    let mut queue: Vec<String> = dirs;
    while !queue.is_empty() {
        let dir = queue.remove(0);
        let entries = match list(prog, &dir).await? {
            Ok(entries) => entries,
            Err(error) => {
                prog.err(&format!(
                    "cannot open directory '{}': {}",
                    dir,
                    describe(error)
                ))
                .await?;
                status = 2;
                continue;
            }
        };
        let mut names: Vec<(String, EntryKind)> = entries
            .into_iter()
            .filter(|e| all || almost || !e.name.starts_with('.'))
            .map(|e| (e.name, e.kind))
            .collect();
        if all {
            names.push((".".to_owned(), EntryKind::Directory));
            names.push(("..".to_owned(), EntryKind::Directory));
        }
        names.sort_by(|a, b| a.0.cmp(&b.0));
        if reverse {
            names.reverse();
        }
        if headers {
            if !first {
                out.push('\n');
            }
            out.push_str(&format!("{dir}:\n"));
        }
        first = false;
        let mut subdirs = Vec::new();
        for (name, kind) in &names {
            out.push_str(&decorate(name, *kind));
            out.push('\n');
            if recursive && *kind == EntryKind::Directory && name != "." && name != ".." {
                subdirs.push(join(&dir, name));
            }
        }
        for (offset, subdir) in subdirs.into_iter().enumerate() {
            queue.insert(offset, subdir);
        }
    }
    prog.out(out.as_bytes()).await?;
    Ok(status)
}

// ---------------------------------------------------------------------------
// find
// ---------------------------------------------------------------------------

#[derive(Clone, Debug)]
enum Expr {
    True,
    Name(String, bool),
    Path(String, bool),
    Type(char),
    Empty,
    Print(bool),
    Not(Box<Expr>),
    And(Box<Expr>, Box<Expr>),
    Or(Box<Expr>, Box<Expr>),
    Prune,
}

struct FindParser<'a> {
    tokens: &'a [String],
    pos: usize,
    has_action: bool,
}

impl FindParser<'_> {
    fn peek(&self) -> Option<&str> {
        self.tokens.get(self.pos).map(String::as_str)
    }

    fn next(&mut self) -> Option<String> {
        let token = self.tokens.get(self.pos).cloned();
        self.pos = self.pos.saturating_add(1);
        token
    }

    fn or(&mut self) -> Result<Expr, String> {
        let mut left = self.and()?;
        while matches!(self.peek(), Some("-o" | "-or")) {
            self.next();
            let right = self.and()?;
            left = Expr::Or(Box::new(left), Box::new(right));
        }
        Ok(left)
    }

    fn and(&mut self) -> Result<Expr, String> {
        let mut left = self.not()?;
        loop {
            match self.peek() {
                None | Some("-o" | "-or" | ")") => break,
                Some("-a" | "-and") => {
                    self.next();
                }
                _ => {}
            }
            let right = self.not()?;
            left = Expr::And(Box::new(left), Box::new(right));
        }
        Ok(left)
    }

    fn not(&mut self) -> Result<Expr, String> {
        if matches!(self.peek(), Some("!" | "-not")) {
            self.next();
            return Ok(Expr::Not(Box::new(self.not()?)));
        }
        self.primary()
    }

    fn primary(&mut self) -> Result<Expr, String> {
        let Some(token) = self.next() else {
            return Err("expected an expression".to_owned());
        };
        let mut value = |name: &str| {
            self.next()
                .ok_or_else(|| format!("missing argument to `{name}'"))
        };
        Ok(match token.as_str() {
            "(" => {
                let inner = self.or()?;
                if self.next().as_deref() != Some(")") {
                    return Err("invalid expression; I was expecting to find a ')' somewhere but did not see one.".to_owned());
                }
                inner
            }
            "-name" => Expr::Name(value("-name")?, false),
            "-iname" => Expr::Name(value("-iname")?, true),
            "-path" | "-wholename" => Expr::Path(value("-path")?, false),
            "-ipath" => Expr::Path(value("-ipath")?, true),
            "-type" => {
                let kind = value("-type")?;
                match kind.as_str() {
                    "f" | "d" | "l" | "p" | "s" | "b" | "c" => {
                        Expr::Type(kind.chars().next().unwrap_or('f'))
                    }
                    _ => return Err(format!("Unknown argument to -type: {kind}")),
                }
            }
            "-empty" => Expr::Empty,
            "-print" => {
                self.has_action = true;
                Expr::Print(false)
            }
            "-print0" => {
                self.has_action = true;
                Expr::Print(true)
            }
            "-prune" => Expr::Prune,
            "-true" => Expr::True,
            "-false" => Expr::Not(Box::new(Expr::True)),
            "-maxdepth" | "-mindepth" => {
                let _ = value(&token)?;
                Expr::True
            }
            other => return Err(format!("unknown predicate `{other}'")),
        })
    }
}

struct Visit {
    shown: String,
    kind: EntryKind,
    empty: bool,
}

/// Evaluate the expression on one file: whether it is true, and what it printed.
fn evaluate(expr: &Expr, visit: &Visit, out: &mut Vec<u8>, prune: &mut bool) -> bool {
    match expr {
        Expr::True => true,
        Expr::Name(pattern, nocase) => {
            let base = if visit.shown == "/" {
                "/"
            } else {
                basename(&visit.shown)
            };
            compile(pattern).matches(
                base,
                crate::machine::pattern::MatchOptions {
                    nocase: *nocase,
                    ..Default::default()
                },
            )
        }
        Expr::Path(pattern, nocase) => compile(pattern).matches(
            &visit.shown,
            crate::machine::pattern::MatchOptions {
                nocase: *nocase,
                ..Default::default()
            },
        ),
        Expr::Type(kind) => match kind {
            'f' => visit.kind == EntryKind::File,
            'd' => visit.kind == EntryKind::Directory,
            _ => false,
        },
        Expr::Empty => visit.empty,
        Expr::Print(zero) => {
            out.extend_from_slice(visit.shown.as_bytes());
            out.push(if *zero { 0 } else { b'\n' });
            true
        }
        Expr::Prune => {
            *prune = true;
            true
        }
        Expr::Not(inner) => !evaluate(inner, visit, out, prune),
        Expr::And(a, b) => evaluate(a, visit, out, prune) && evaluate(b, visit, out, prune),
        Expr::Or(a, b) => evaluate(a, visit, out, prune) || evaluate(b, visit, out, prune),
    }
}

fn compile(pattern: &str) -> crate::machine::pattern::Pattern {
    let chars: Vec<(char, bool)> = pattern.chars().map(|c| (c, false)).collect();
    crate::machine::pattern::Pattern::compile(&chars, false)
}

pub async fn find(prog: &mut Prog<'_>, args: &[String]) -> Result<i32, Flow> {
    let split = args
        .iter()
        .position(|a| a.starts_with('-') && a.len() > 1 || a == "!" || a == "(")
        .unwrap_or(args.len());
    let mut starts: Vec<String> = args.get(..split).unwrap_or_default().to_vec();
    let mut tokens: Vec<String> = args.get(split..).unwrap_or_default().to_vec();
    if starts.is_empty() {
        starts.push(".".to_owned());
    }
    // Global options first, wherever they are.
    let mut max_depth: Option<usize> = None;
    let mut min_depth = 0usize;
    let mut index = 0usize;
    while index < tokens.len() {
        let token = tokens.get(index).cloned().unwrap_or_default();
        if token == "-maxdepth" || token == "-mindepth" {
            let value = tokens
                .get(index.saturating_add(1))
                .cloned()
                .unwrap_or_default();
            let Ok(number) = value.parse::<usize>() else {
                prog.err(&format!(
                    "Expected a positive decimal integer argument to {token}, but got ‘{value}’"
                ))
                .await?;
                return Ok(1);
            };
            if token == "-maxdepth" {
                max_depth = Some(number);
            } else {
                min_depth = number;
            }
            tokens.drain(index..index.saturating_add(2).min(tokens.len()));
            continue;
        }
        index = index.saturating_add(1);
    }
    let mut parser = FindParser {
        tokens: &tokens,
        pos: 0,
        has_action: false,
    };
    let expr = if tokens.is_empty() {
        Expr::True
    } else {
        match parser.or() {
            Ok(expr) if parser.pos >= tokens.len() => expr,
            Ok(_) => {
                prog.err(&format!(
                    "paths must precede expression: `{}'",
                    tokens.get(parser.pos).cloned().unwrap_or_default()
                ))
                .await?;
                return Ok(1);
            }
            Err(message) => {
                prog.err(&message).await?;
                return Ok(1);
            }
        }
    };
    let expr = if parser.has_action {
        expr
    } else {
        Expr::And(Box::new(expr), Box::new(Expr::Print(false)))
    };
    let mut status = 0;
    for start in starts {
        let Some((kind, size)) = prog.stat(&start).await? else {
            prog.err(&format!("‘{start}’: No such file or directory"))
                .await?;
            status = 1;
            continue;
        };
        // Depth-first, pre-order, entries in the order the host lists them.
        let mut stack: Vec<(String, EntryKind, u64, usize)> = vec![(start.clone(), kind, size, 0)];
        while let Some((shown, kind, size, depth)) = stack.pop() {
            let children =
                if kind == EntryKind::Directory && max_depth.is_none_or(|max| depth < max) {
                    list(prog, &shown).await?.ok()
                } else {
                    None
                };
            let empty = match kind {
                EntryKind::File => size == 0,
                EntryKind::Directory => match &children {
                    Some(entries) => entries.is_empty(),
                    None => match list(prog, &shown).await? {
                        Ok(entries) => entries.is_empty(),
                        Err(_) => false,
                    },
                },
            };
            let mut out = Vec::new();
            let mut prune = false;
            if depth >= min_depth {
                evaluate(
                    &expr,
                    &Visit {
                        shown: shown.clone(),
                        kind,
                        empty,
                    },
                    &mut out,
                    &mut prune,
                );
            }
            prog.out(&out).await?;
            if prune {
                continue;
            }
            if let Some(entries) = children {
                for entry in entries.into_iter().rev() {
                    let child = join(&shown, &entry.name);
                    let size = if entry.kind == EntryKind::File {
                        prog.stat(&child).await?.map_or(0, |(_, s)| s)
                    } else {
                        0
                    };
                    stack.push((child, entry.kind, size, depth.saturating_add(1)));
                }
            }
        }
    }
    Ok(status)
}

// ---------------------------------------------------------------------------
// cp and mv
// ---------------------------------------------------------------------------

async fn copy_or_move(prog: &mut Prog<'_>, args: &[String], moving: bool) -> Result<i32, Flow> {
    let (options, operands) = split_args(args);
    let mut recursive = false;
    let mut no_clobber = false;
    let mut verbose = false;
    let mut target_dir: Option<String> = None;
    for option in &options {
        match option.as_str() {
            "--recursive" => recursive = true,
            "--no-clobber" => no_clobber = true,
            "--verbose" => verbose = true,
            _ if option.starts_with("--target-directory=") => {
                target_dir = option.get(19..).map(str::to_owned)
            }
            _ => {
                for flag in option.trim_start_matches('-').chars() {
                    match flag {
                        'r' | 'R' | 'a' => recursive = true,
                        'n' => no_clobber = true,
                        'v' => verbose = true,
                        'f' | 'i' | 'p' | 'P' | 'L' | 'd' | 'u' => {}
                        other => {
                            prog.err(&format!("invalid option -- '{other}'")).await?;
                            let name = prog.name.clone();
                            prog.sh
                                .error_text(&format!("Try '{name} --help' for more information.\n"))
                                .await?;
                            return Ok(1);
                        }
                    }
                }
            }
        }
    }
    let (sources, destination) = match target_dir {
        Some(dir) => (operands.clone(), dir),
        None => {
            if operands.is_empty() {
                prog.err("missing file operand").await?;
                let name = prog.name.clone();
                prog.sh
                    .error_text(&format!("Try '{name} --help' for more information.\n"))
                    .await?;
                return Ok(1);
            }
            if operands.len() == 1 {
                let only = operands.first().cloned().unwrap_or_default();
                prog.err(&format!("missing destination file operand after '{only}'"))
                    .await?;
                let name = prog.name.clone();
                prog.sh
                    .error_text(&format!("Try '{name} --help' for more information.\n"))
                    .await?;
                return Ok(1);
            }
            let mut sources = operands.clone();
            let destination = sources.pop().unwrap_or_default();
            (sources, destination)
        }
    };
    let destination_kind = prog.stat(&destination).await?.map(|(kind, _)| kind);
    let into_dir = destination_kind == Some(EntryKind::Directory);
    if sources.len() > 1 && !into_dir {
        let message = match destination_kind {
            None => format!("target '{destination}': No such file or directory"),
            Some(_) => format!("target '{destination}' is not a directory"),
        };
        prog.err(&message).await?;
        return Ok(1);
    }
    let mut status = 0;
    for source in sources {
        let Some((kind, _)) = prog.stat(&source).await? else {
            prog.err(&format!(
                "cannot stat '{}': {}",
                source,
                describe(HostError::NotFound)
            ))
            .await?;
            status = 1;
            continue;
        };
        if kind == EntryKind::Directory && !moving && !recursive {
            prog.err(&format!("-r not specified; omitting directory '{source}'"))
                .await?;
            status = 1;
            continue;
        }
        let target = if into_dir {
            join(&destination, basename(&source))
        } else {
            destination.clone()
        };
        if no_clobber && prog.stat(&target).await?.is_some() {
            continue;
        }
        let (from, to) = (prog.abs(&source), prog.abs(&target));
        if from == to {
            prog.err(&format!("'{source}' and '{target}' are the same file"))
                .await?;
            status = 1;
            continue;
        }
        let request = if moving {
            Request::Move { from, to }
        } else {
            Request::Copy {
                from,
                to,
                recursive: kind == EntryKind::Directory,
            }
        };
        match done_or(prog, request).await? {
            Ok(()) => {
                if verbose {
                    let line = if moving {
                        format!("renamed '{source}' -> '{target}'\n")
                    } else {
                        format!("'{source}' -> '{target}'\n")
                    };
                    prog.out(line.as_bytes()).await?;
                }
            }
            Err(error) => {
                let verb = if moving {
                    "cannot move"
                } else {
                    "cannot create regular file"
                };
                let message = if moving {
                    format!("{verb} '{}' to '{}': {}", source, target, describe(error))
                } else {
                    format!("{verb} '{}': {}", target, describe(error))
                };
                prog.err(&message).await?;
                status = 1;
            }
        }
    }
    Ok(status)
}

pub async fn cp(prog: &mut Prog<'_>, args: &[String]) -> Result<i32, Flow> {
    copy_or_move(prog, args, false).await
}

pub async fn mv(prog: &mut Prog<'_>, args: &[String]) -> Result<i32, Flow> {
    copy_or_move(prog, args, true).await
}

// ---------------------------------------------------------------------------
// rm, mkdir, touch
// ---------------------------------------------------------------------------

pub async fn rm(prog: &mut Prog<'_>, args: &[String]) -> Result<i32, Flow> {
    let (options, operands) = split_args(args);
    let (mut force, mut recursive, mut verbose, mut empty_dirs) = (false, false, false, false);
    for option in &options {
        match option.as_str() {
            "--force" => force = true,
            "--recursive" => recursive = true,
            "--verbose" => verbose = true,
            "--dir" => empty_dirs = true,
            _ => {
                for flag in option.trim_start_matches('-').chars() {
                    match flag {
                        'f' => force = true,
                        'r' | 'R' => recursive = true,
                        'v' => verbose = true,
                        'd' => empty_dirs = true,
                        'i' | 'I' => {}
                        other => {
                            prog.err(&format!("invalid option -- '{other}'")).await?;
                            prog.sh
                                .error_text("Try 'rm --help' for more information.\n")
                                .await?;
                            return Ok(1);
                        }
                    }
                }
            }
        }
    }
    if operands.is_empty() {
        if force {
            return Ok(0);
        }
        prog.err("missing operand").await?;
        prog.sh
            .error_text("Try 'rm --help' for more information.\n")
            .await?;
        return Ok(1);
    }
    let mut status = 0;
    for operand in operands {
        let Some((kind, _)) = prog.stat(&operand).await? else {
            if !force {
                prog.err(&format!(
                    "cannot remove '{}': {}",
                    operand,
                    describe(HostError::NotFound)
                ))
                .await?;
                status = 1;
            }
            continue;
        };
        if kind == EntryKind::Directory && !recursive {
            let empty = matches!(list(prog, &operand).await?, Ok(entries) if entries.is_empty());
            if !(empty_dirs && empty) {
                prog.err(&format!("cannot remove '{operand}': Is a directory"))
                    .await?;
                status = 1;
                continue;
            }
        }
        let path = prog.abs(&operand);
        match done_or(prog, Request::Remove { path, recursive }).await? {
            Ok(()) => {
                if verbose {
                    let line = if kind == EntryKind::Directory {
                        format!("removed directory '{operand}'\n")
                    } else {
                        format!("removed '{operand}'\n")
                    };
                    prog.out(line.as_bytes()).await?;
                }
            }
            Err(error) => {
                prog.err(&format!("cannot remove '{}': {}", operand, describe(error)))
                    .await?;
                status = 1;
            }
        }
    }
    Ok(status)
}

pub async fn mkdir(prog: &mut Prog<'_>, args: &[String]) -> Result<i32, Flow> {
    let (options, operands) = split_args(args);
    let mut parents = false;
    let mut verbose = false;
    for option in &options {
        match option.as_str() {
            "--parents" => parents = true,
            "--verbose" => verbose = true,
            _ => {
                for flag in option.trim_start_matches('-').chars() {
                    match flag {
                        'p' => parents = true,
                        'v' => verbose = true,
                        'm' => {}
                        other => {
                            prog.err(&format!("invalid option -- '{other}'")).await?;
                            prog.sh
                                .error_text("Try 'mkdir --help' for more information.\n")
                                .await?;
                            return Ok(1);
                        }
                    }
                }
            }
        }
    }
    if operands.is_empty() {
        prog.err("missing operand").await?;
        prog.sh
            .error_text("Try 'mkdir --help' for more information.\n")
            .await?;
        return Ok(1);
    }
    let mut status = 0;
    for operand in operands {
        let path = prog.abs(&operand);
        match done_or(prog, Request::Mkdir { path, parents }).await? {
            Ok(()) => {
                if verbose {
                    prog.out(format!("mkdir: created directory '{operand}'\n").as_bytes())
                        .await?;
                }
            }
            Err(error) => {
                prog.err(&format!(
                    "cannot create directory ‘{}’: {}",
                    operand,
                    describe(error)
                ))
                .await?;
                status = 1;
            }
        }
    }
    Ok(status)
}

pub async fn touch(prog: &mut Prog<'_>, args: &[String]) -> Result<i32, Flow> {
    let (options, operands) = split_args(args);
    let no_create = options.iter().any(|o| o == "-c" || o == "--no-create");
    if operands.is_empty() {
        prog.err("missing file operand").await?;
        prog.sh
            .error_text("Try 'touch --help' for more information.\n")
            .await?;
        return Ok(1);
    }
    let mut status = 0;
    for operand in operands {
        if no_create && prog.stat(&operand).await?.is_none() {
            continue;
        }
        let path = prog.abs(&operand);
        if let Err(error) = done_or(prog, Request::Touch { path }).await? {
            prog.err(&format!("cannot touch '{}': {}", operand, describe(error)))
                .await?;
            status = 1;
        }
    }
    Ok(status)
}
