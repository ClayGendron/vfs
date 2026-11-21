//! Conditional expressions: `[[ ... ]]`, which expands each operand only
//! when it is reached, and `test` and `[`, which judge their arguments by
//! how many there are, as POSIX describes.

use std::collections::BTreeMap;

use super::EntryKind;
use super::exec::{Ctx, Flow, absolute, set_value};
use super::expand::{Mode, compile_pattern, eval_arith, expand_pattern, expand_single};
use super::io;
use super::pattern::MatchOptions;
use super::regex::Regex;
use super::shell::Shell;
use super::vars::Value;
use super::{Reply, Request};
use crate::syntax::ast::CondExpr;

/// What a file test knows about a path.
#[derive(Clone, Copy)]
struct FileFacts {
    kind: Option<EntryKind>,
    size: u64,
}

async fn stat(sh: &mut Shell, path: &str) -> Result<FileFacts, Flow> {
    if path.is_empty() {
        return Ok(FileFacts {
            kind: None,
            size: 0,
        });
    }
    if matches!(
        path,
        "/dev/null" | "/dev/stdin" | "/dev/stdout" | "/dev/stderr"
    ) || path.starts_with("/dev/fd/")
    {
        return Ok(FileFacts {
            kind: Some(EntryKind::File),
            size: 0,
        });
    }
    let absolute = absolute(sh, path);
    super::exec::sync_path(sh, &absolute).await?;
    let key = sh.key();
    let reply = io::host_call(&sh.hub, key, Request::Stat { path: absolute }).await?;
    Ok(match reply {
        Reply::Stat { kind, size } => FileFacts {
            kind: Some(kind),
            size,
        },
        _ => FileFacts {
            kind: None,
            size: 0,
        },
    })
}

async fn unary(sh: &mut Shell, op: &str, operand: &str) -> Result<bool, Flow> {
    Ok(match op {
        "-z" => operand.is_empty(),
        "-n" => !operand.is_empty(),
        "-v" => var_is_set(sh, operand),
        "-R" => sh
            .vars
            .get(operand)
            .is_some_and(|v| v.has(super::vars::NAMEREF)),
        "-o" => sh.options.get_set_option(operand).unwrap_or(false),
        "-t" => false,
        "-e" | "-a" => stat(sh, operand).await?.kind.is_some(),
        "-f" => stat(sh, operand).await?.kind == Some(EntryKind::File),
        "-d" => stat(sh, operand).await?.kind == Some(EntryKind::Directory),
        "-s" => {
            let facts = stat(sh, operand).await?;
            facts.kind.is_some() && (facts.size > 0 || facts.kind == Some(EntryKind::Directory))
        }
        "-r" | "-w" | "-O" | "-G" => stat(sh, operand).await?.kind.is_some(),
        "-x" => stat(sh, operand).await?.kind == Some(EntryKind::Directory),
        "-h" | "-L" | "-p" | "-S" | "-b" | "-c" | "-g" | "-u" | "-k" | "-N" => false,
        _ => false,
    })
}

fn var_is_set(sh: &Shell, operand: &str) -> bool {
    if let Some(open) = operand.find('[') {
        let name = operand.get(..open).unwrap_or_default();
        let sub = operand
            .get(open.saturating_add(1)..)
            .and_then(|s| s.strip_suffix(']'))
            .unwrap_or_default();
        return match sh.vars.get(name).and_then(|v| v.value.as_ref()) {
            Some(Value::Indexed(map)) => {
                if sub == "@" || sub == "*" {
                    !map.is_empty()
                } else {
                    sub.parse::<i64>()
                        .ok()
                        .is_some_and(|n| map.contains_key(&n))
                }
            }
            Some(Value::Assoc(map)) => {
                if sub == "@" || sub == "*" {
                    !map.is_empty()
                } else {
                    map.get(sub).is_some()
                }
            }
            Some(Value::Scalar(_)) => sub == "0" || sub == "@" || sub == "*",
            None => false,
        };
    }
    if let Ok(n) = operand.parse::<usize>() {
        return n == 0 || n <= sh.positional.len();
    }
    match sh.vars.get(operand).and_then(|v| v.value.as_ref()) {
        Some(Value::Indexed(map)) => map.contains_key(&0),
        Some(Value::Assoc(map)) => map.get("0").is_some(),
        Some(Value::Scalar(_)) => true,
        None => false,
    }
}

// ---------------------------------------------------------------------------
// `[[ ... ]]`
// ---------------------------------------------------------------------------

pub fn eval_cond<'b>(
    ctx: &'b Ctx<'_>,
    sh: &'b mut Shell,
    expr: &'b CondExpr,
) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<i32, Flow>> + 'b>> {
    Box::pin(async move {
        let result = match expr {
            CondExpr::Word(word) => {
                let text = expand_single(ctx, sh, word, Mode::Single).await?;
                i32::from(text.is_empty())
            }
            CondExpr::Not(inner) => {
                let status = eval_cond(ctx, sh, inner).await?;
                if status == 2 {
                    2
                } else {
                    i32::from(status == 0)
                }
            }
            CondExpr::And(left, right) => {
                let status = eval_cond(ctx, sh, left).await?;
                if status != 0 {
                    status
                } else {
                    eval_cond(ctx, sh, right).await?
                }
            }
            CondExpr::Or(left, right) => {
                let status = eval_cond(ctx, sh, left).await?;
                if status == 0 {
                    0
                } else {
                    eval_cond(ctx, sh, right).await?
                }
            }
            CondExpr::Unary(op, word) => {
                let operand = expand_single(ctx, sh, word, Mode::Single).await?;
                i32::from(!unary(sh, op, &operand).await?)
            }
            CondExpr::Binary(left, op, right) => {
                let a = expand_single(ctx, sh, left, Mode::Single).await?;
                match op.as_str() {
                    "==" | "=" | "!=" => {
                        let pattern = compile_pattern(ctx, sh, right).await?;
                        let options = MatchOptions {
                            nocase: sh.options.shopt("nocasematch"),
                            ..Default::default()
                        };
                        let matched = pattern.matches(&a, options);
                        i32::from(matched == (op == "!="))
                    }
                    "<" | ">" => {
                        let b = expand_single(ctx, sh, right, Mode::Single).await?;
                        let ok = if op == "<" { a < b } else { a > b };
                        i32::from(!ok)
                    }
                    "-eq" | "-ne" | "-lt" | "-le" | "-gt" | "-ge" => {
                        let x = eval_arith(ctx, sh, &a).await?;
                        let b = expand_single(ctx, sh, right, Mode::Single).await?;
                        let y = eval_arith(ctx, sh, &b).await?;
                        i32::from(!compare(op, x, y))
                    }
                    "-ef" => {
                        let b = expand_single(ctx, sh, right, Mode::Single).await?;
                        let same = stat(sh, &a).await?.kind.is_some()
                            && absolute(sh, &a) == absolute(sh, &b);
                        i32::from(!same)
                    }
                    "-nt" | "-ot" => {
                        let b = expand_single(ctx, sh, right, Mode::Single).await?;
                        let left_exists = stat(sh, &a).await?.kind.is_some();
                        let right_exists = stat(sh, &b).await?.kind.is_some();
                        let ok = if op == "-nt" {
                            left_exists && !right_exists
                        } else {
                            right_exists && !left_exists
                        };
                        i32::from(!ok)
                    }
                    _ => 2,
                }
            }
            CondExpr::Regex(left, right) => {
                let subject = expand_single(ctx, sh, left, Mode::Single).await?;
                let chars = expand_pattern(ctx, sh, right).await?;
                let mut source = String::new();
                for (ch, quoted) in chars {
                    if quoted && "\\.[]()*+?{}|^$".contains(ch) {
                        source.push('\\');
                    }
                    source.push(ch);
                }
                match Regex::new(&source, sh.options.shopt("nocasematch")) {
                    Err(message) => {
                        sh.error_text(&format!(
                            "bash: line {}: [[: invalid regular expression `{}': {}\n",
                            sh.lineno, source, message
                        ))
                        .await?;
                        2
                    }
                    Ok(regex) => match regex.find(&subject) {
                        Err(_) => {
                            sh.error_text(&format!(
                                "bash: line {}: [[: regular expression too complex to match `{}'\n",
                                sh.lineno, source
                            ))
                            .await?;
                            2
                        }
                        Ok(Some((text, captures))) => {
                            let mut map = BTreeMap::new();
                            for (index, capture) in captures.iter().enumerate() {
                                let value: String = match capture {
                                    Some((start, end)) => {
                                        text.get(*start..*end).unwrap_or_default().iter().collect()
                                    }
                                    None => String::new(),
                                };
                                map.insert(i64::try_from(index).unwrap_or(0), value);
                            }
                            set_value(sh, "BASH_REMATCH", Value::Indexed(map))?;
                            0
                        }
                        Ok(None) => {
                            set_value(sh, "BASH_REMATCH", Value::Indexed(BTreeMap::new()))?;
                            1
                        }
                    },
                }
            }
        };
        Ok(result)
    })
}

fn compare(op: &str, x: i64, y: i64) -> bool {
    match op {
        "-eq" => x == y,
        "-ne" => x != y,
        "-lt" => x < y,
        "-le" => x <= y,
        "-gt" => x > y,
        _ => x >= y,
    }
}

// ---------------------------------------------------------------------------
// `test` and `[`
// ---------------------------------------------------------------------------

/// Run `test` over its arguments (without the closing `]`).
pub async fn test_builtin(sh: &mut Shell, name: &str, args: &[String]) -> Result<i32, Flow> {
    let mut judge = Test {
        sh,
        name,
        error: None,
    };
    let result = judge.expression(args).await;
    match judge.error.take() {
        Some(message) => {
            let line = judge.sh.lineno;
            judge
                .sh
                .error_text(&format!("bash: line {line}: {name}: {message}\n"))
                .await?;
            Ok(2)
        }
        None => Ok(i32::from(!result?)),
    }
}

struct Test<'s> {
    sh: &'s mut Shell,
    name: &'s str,
    error: Option<String>,
}

fn is_unary(op: &str) -> bool {
    matches!(
        op,
        "-a" | "-b"
            | "-c"
            | "-d"
            | "-e"
            | "-f"
            | "-g"
            | "-h"
            | "-k"
            | "-p"
            | "-r"
            | "-s"
            | "-t"
            | "-u"
            | "-w"
            | "-x"
            | "-G"
            | "-L"
            | "-N"
            | "-O"
            | "-S"
            | "-z"
            | "-n"
            | "-v"
            | "-o"
            | "-R"
    )
}

fn is_binary(op: &str) -> bool {
    matches!(
        op,
        "=" | "=="
            | "!="
            | "<"
            | ">"
            | "-eq"
            | "-ne"
            | "-lt"
            | "-le"
            | "-gt"
            | "-ge"
            | "-ef"
            | "-nt"
            | "-ot"
    )
}

impl Test<'_> {
    fn fail(&mut self, message: String) -> bool {
        if self.error.is_none() {
            self.error = Some(message);
        }
        false
    }

    fn expression<'x>(
        &'x mut self,
        args: &'x [String],
    ) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<bool, Flow>> + 'x>> {
        Box::pin(async move {
            let _ = self.name;
            match args {
                [] => Ok(false),
                [one] => Ok(!one.is_empty()),
                [bang, rest @ ..] if bang == "!" && args.len() <= 4 => {
                    Ok(!self.expression(rest).await? && self.error.is_none())
                }
                [op, operand] => {
                    if is_unary(op) {
                        Ok(unary(self.sh, op, operand).await?)
                    } else {
                        Ok(self.fail(format!("{op}: unary operator expected")))
                    }
                }
                [open, inner, close] if open == "(" && close == ")" => Ok(!inner.is_empty()),
                [a, op, b] if is_binary(op) => self.binary(a, op, b).await,
                [a, op, b] if op == "-a" || op == "-o" => {
                    let x = !a.is_empty();
                    let y = !b.is_empty();
                    Ok(if op == "-a" { x && y } else { x || y })
                }
                [_, op, _] => Ok(self.fail(format!("{op}: binary operator expected"))),
                [open, a, b, close] if open == "(" && close == ")" => {
                    self.expression(args.get(1..3).unwrap_or_default()).await
                }
                _ => {
                    let mut pos = 0usize;
                    let value = self.or(args, &mut pos).await?;
                    if pos < args.len() && self.error.is_none() {
                        let token = args.get(pos).cloned().unwrap_or_default();
                        return Ok(self.fail(format!("{token}: binary operator expected")));
                    }
                    Ok(value)
                }
            }
        })
    }

    async fn binary(&mut self, a: &str, op: &str, b: &str) -> Result<bool, Flow> {
        Ok(match op {
            "=" | "==" => a == b,
            "!=" => a != b,
            "<" => a < b,
            ">" => a > b,
            "-ef" => {
                stat(self.sh, a).await?.kind.is_some()
                    && absolute(self.sh, a) == absolute(self.sh, b)
            }
            "-nt" => {
                stat(self.sh, a).await?.kind.is_some() && stat(self.sh, b).await?.kind.is_none()
            }
            "-ot" => {
                stat(self.sh, b).await?.kind.is_some() && stat(self.sh, a).await?.kind.is_none()
            }
            _ => {
                let Some(x) = self.integer(a) else {
                    return Ok(false);
                };
                let Some(y) = self.integer(b) else {
                    return Ok(false);
                };
                compare(op, x, y)
            }
        })
    }

    fn integer(&mut self, text: &str) -> Option<i64> {
        let trimmed = text.trim();
        let digits = trimmed.strip_prefix(['-', '+']).unwrap_or(trimmed);
        if digits.is_empty() || !digits.bytes().all(|b| b.is_ascii_digit()) {
            self.fail(format!("{text}: integer expected"));
            return None;
        }
        match trimmed.parse::<i64>() {
            Ok(value) => Some(value),
            Err(_) => {
                self.fail(format!("{text}: integer expected"));
                None
            }
        }
    }

    fn or<'x>(
        &'x mut self,
        args: &'x [String],
        pos: &'x mut usize,
    ) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<bool, Flow>> + 'x>> {
        Box::pin(async move {
            let mut value = self.and(args, pos).await?;
            while args.get(*pos).is_some_and(|a| a == "-o") {
                *pos = pos.saturating_add(1);
                let right = self.and(args, pos).await?;
                value = value || right;
            }
            Ok(value)
        })
    }

    async fn and(&mut self, args: &[String], pos: &mut usize) -> Result<bool, Flow> {
        let mut value = self.not(args, pos).await?;
        while args.get(*pos).is_some_and(|a| a == "-a") {
            *pos = pos.saturating_add(1);
            let right = self.not(args, pos).await?;
            value = value && right;
        }
        Ok(value)
    }

    fn not<'x>(
        &'x mut self,
        args: &'x [String],
        pos: &'x mut usize,
    ) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<bool, Flow>> + 'x>> {
        Box::pin(async move {
            if args.get(*pos).is_some_and(|a| a == "!") {
                *pos = pos.saturating_add(1);
                return Ok(!self.not(args, pos).await?);
            }
            self.primary(args, pos).await
        })
    }

    async fn primary(&mut self, args: &[String], pos: &mut usize) -> Result<bool, Flow> {
        let Some(first) = args.get(*pos).cloned() else {
            return Ok(self.fail("argument expected".to_owned()));
        };
        if first == "(" {
            *pos = pos.saturating_add(1);
            let value = self.or(args, pos).await?;
            if args.get(*pos).is_some_and(|a| a == ")") {
                *pos = pos.saturating_add(1);
            } else {
                return Ok(self.fail("`)' expected".to_owned()));
            }
            return Ok(value);
        }
        if let (Some(op), Some(b)) = (
            args.get(pos.saturating_add(1)).cloned(),
            args.get(pos.saturating_add(2)).cloned(),
        ) && is_binary(&op)
        {
            *pos = pos.saturating_add(3);
            return self.binary(&first, &op, &b).await;
        }
        if is_unary(&first)
            && let Some(operand) = args.get(pos.saturating_add(1)).cloned()
        {
            *pos = pos.saturating_add(2);
            return unary(self.sh, &first, &operand).await;
        }
        *pos = pos.saturating_add(1);
        Ok(!first.is_empty())
    }
}
