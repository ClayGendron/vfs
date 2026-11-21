//! Evaluating arithmetic: 64-bit integers that wrap, variables read as
//! expressions in their own right, and bash's messages for what fails.

use super::exec::{Flow, Index, resolve_nameref};
use super::shell::Shell;
use super::vars::{self, Value};
use crate::syntax::arith::{BinaryOp, Expr, UnaryOp, parse_arith, parse_number};

/// How deep variables may refer to expressions that refer to variables.
const RECURSION: u32 = 1024;
/// How deep one expression may nest.
const PARSE_DEPTH: u32 = 1024;

pub enum ArithFailure {
    /// Bash's message, ready to print after the line prefix.
    Error(String),
    Flow(Flow),
}

/// Evaluate arithmetic text in `sh`.
pub fn evaluate(sh: &mut Shell, text: &str) -> Result<i64, ArithFailure> {
    let mut evaluator = Evaluator { sh, depth: 0 };
    evaluator.text(text)
}

struct Evaluator<'s> {
    sh: &'s mut Shell,
    depth: u32,
}

impl Evaluator<'_> {
    fn text(&mut self, text: &str) -> Result<i64, ArithFailure> {
        self.depth = self.depth.saturating_add(1);
        if self.depth > RECURSION {
            return Err(ArithFailure::Error(format!(
                "{}: expression recursion level exceeded (error token is \"{}\")",
                text.trim(),
                text.trim()
            )));
        }
        let expr = parse_arith(text, PARSE_DEPTH).map_err(|error| {
            let token = error.token.trim().to_owned();
            let message = if error.message.contains("error token") {
                format!("{}: {}", text.trim(), error.message)
            } else {
                let message = if error.message.starts_with("syntax error") {
                    format!("arithmetic {}", error.message)
                } else {
                    error.message.clone()
                };
                format!(
                    "{}: {} (error token is \"{}\")",
                    text.trim(),
                    message,
                    token
                )
            };
            ArithFailure::Error(message)
        })?;
        let value = self.eval(&expr, text);
        self.depth = self.depth.saturating_sub(1);
        value
    }

    fn eval(&mut self, expr: &Expr, source: &str) -> Result<i64, ArithFailure> {
        Ok(match expr {
            Expr::Number(n) => *n,
            Expr::Var(name, subscript) => self.read(name, subscript.as_deref(), source)?,
            Expr::Unary(op, inner) => {
                let value = self.eval(inner, source)?;
                match op {
                    UnaryOp::Neg => value.wrapping_neg(),
                    UnaryOp::Plus => value,
                    UnaryOp::Not => i64::from(value == 0),
                    UnaryOp::BitNot => !value,
                }
            }
            Expr::Binary(op, left, right) => match op {
                BinaryOp::And => {
                    let a = self.eval(left, source)?;
                    if a == 0 {
                        0
                    } else {
                        i64::from(self.eval(right, source)? != 0)
                    }
                }
                BinaryOp::Or => {
                    let a = self.eval(left, source)?;
                    if a != 0 {
                        1
                    } else {
                        i64::from(self.eval(right, source)? != 0)
                    }
                }
                _ => {
                    let a = self.eval(left, source)?;
                    let b = self.eval(right, source)?;
                    binary(*op, a, b, source)?
                }
            },
            Expr::Assign(op, name, subscript, value) => {
                let rhs = self.eval(value, source)?;
                let result = match op {
                    None => rhs,
                    Some(op) => {
                        let current = self.read(name, subscript.as_deref(), source)?;
                        binary(*op, current, rhs, source)?
                    }
                };
                self.write(name, subscript.as_deref(), result, source)?;
                result
            }
            Expr::Step(step, post, name, subscript) => {
                let current = self.read(name, subscript.as_deref(), source)?;
                let next = current.wrapping_add(*step);
                self.write(name, subscript.as_deref(), next, source)?;
                if *post { current } else { next }
            }
            Expr::Ternary(condition, yes, no) => {
                if self.eval(condition, source)? != 0 {
                    self.eval(yes, source)?
                } else {
                    self.eval(no, source)?
                }
            }
            Expr::Comma(left, right) => {
                self.eval(left, source)?;
                self.eval(right, source)?
            }
        })
    }

    fn index(&mut self, name: &str, subscript: &str) -> Result<Index, ArithFailure> {
        let is_assoc = self.sh.vars.get(name).is_some_and(vars::Var::is_assoc);
        if is_assoc {
            let key = subscript.trim_matches(|c| c == '"' || c == '\'').to_owned();
            let key = if let Some(var) = key.strip_prefix('$') {
                self.sh.get_var(var).unwrap_or_default()
            } else {
                key
            };
            return Ok(Index::Key(key));
        }
        let text = expand_simple(self.sh, subscript);
        Ok(Index::Number(self.text(&text)?))
    }

    fn read(
        &mut self,
        name: &str,
        subscript: Option<&str>,
        source: &str,
    ) -> Result<i64, ArithFailure> {
        let name = resolve_nameref(self.sh, name);
        let text = match subscript {
            None => {
                if name == "LINENO" {
                    Some(self.sh.lineno.to_string())
                } else {
                    self.sh.get_var(&name)
                }
            }
            Some(subscript) => {
                let index = self.index(&name, subscript)?;
                match (
                    self.sh.vars.get(&name).and_then(|v| v.value.as_ref()),
                    index,
                ) {
                    (Some(Value::Indexed(map)), Index::Number(n)) => {
                        let key = if n < 0 {
                            map.keys()
                                .next_back()
                                .map_or(0, |k| k.saturating_add(1))
                                .saturating_add(n)
                        } else {
                            n
                        };
                        map.get(&key).cloned()
                    }
                    (Some(Value::Assoc(map)), Index::Key(key)) => map.get(&key).cloned(),
                    (Some(Value::Scalar(text)), Index::Number(0)) => Some(text.clone()),
                    _ => None,
                }
            }
        };
        let Some(text) = text else {
            if self.sh.options.nounset {
                return Err(ArithFailure::Error(format!("{name}: unbound variable")));
            }
            return Ok(0);
        };
        let trimmed = text.trim();
        if trimmed.is_empty() {
            return Ok(0);
        }
        if let Ok(value) = parse_number(trimmed)
            && trimmed
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b == b'#' || b == b'@' || b == b'_')
            && trimmed.bytes().next().is_some_and(|b| b.is_ascii_digit())
        {
            return Ok(value);
        }
        let _ = source;
        self.text(&text)
    }

    fn write(
        &mut self,
        name: &str,
        subscript: Option<&str>,
        value: i64,
        source: &str,
    ) -> Result<(), ArithFailure> {
        let name = resolve_nameref(self.sh, name);
        if self
            .sh
            .vars
            .get(&name)
            .is_some_and(|v| v.has(vars::READONLY))
        {
            let _ = source;
            return Err(ArithFailure::Error(format!("{name}: readonly variable")));
        }
        let text = value.to_string();
        match subscript {
            None => {
                let existing = self.sh.vars.get(&name).and_then(|v| v.value.clone());
                let new_value = match existing {
                    Some(Value::Indexed(mut map)) => {
                        map.insert(0, text);
                        Value::Indexed(map)
                    }
                    _ => Value::Scalar(text),
                };
                super::exec::set_value(self.sh, &name, new_value).map_err(ArithFailure::Flow)?;
            }
            Some(subscript) => {
                let index = self.index(&name, subscript)?;
                let existing = self.sh.vars.get(&name).and_then(|v| v.value.clone());
                let new_value = match (existing, index) {
                    (Some(Value::Assoc(mut map)), Index::Key(key)) => {
                        map.insert(key, text);
                        Value::Assoc(map)
                    }
                    (Some(Value::Indexed(mut map)), Index::Number(n)) => {
                        map.insert(n, text);
                        Value::Indexed(map)
                    }
                    (Some(Value::Scalar(old)), Index::Number(n)) => {
                        let mut map = std::collections::BTreeMap::from([(0, old)]);
                        map.insert(n, text);
                        Value::Indexed(map)
                    }
                    (_, Index::Number(n)) => {
                        Value::Indexed(std::collections::BTreeMap::from([(n, text)]))
                    }
                    (_, Index::Key(key)) => {
                        let mut map = vars::AssocMap::new();
                        map.insert(key, text);
                        Value::Assoc(map)
                    }
                };
                super::exec::set_value(self.sh, &name, new_value).map_err(ArithFailure::Flow)?;
            }
        }
        Ok(())
    }
}

/// `$name` and `${name}` inside a subscript, which bash expands before evaluating.
fn expand_simple(sh: &Shell, text: &str) -> String {
    if !text.contains('$') {
        return text.to_owned();
    }
    let mut out = String::new();
    let mut chars = text.chars().peekable();
    while let Some(ch) = chars.next() {
        if ch != '$' {
            out.push(ch);
            continue;
        }
        let braced = chars.peek() == Some(&'{');
        if braced {
            chars.next();
        }
        let mut name = String::new();
        while let Some(&c) = chars.peek() {
            if c.is_ascii_alphanumeric() || c == '_' {
                name.push(c);
                chars.next();
            } else {
                break;
            }
        }
        if braced && chars.peek() == Some(&'}') {
            chars.next();
        }
        out.push_str(&sh.get_var(&name).unwrap_or_default());
    }
    out
}

fn binary(op: BinaryOp, a: i64, b: i64, source: &str) -> Result<i64, ArithFailure> {
    Ok(match op {
        BinaryOp::Add => a.wrapping_add(b),
        BinaryOp::Sub => a.wrapping_sub(b),
        BinaryOp::Mul => a.wrapping_mul(b),
        BinaryOp::Div | BinaryOp::Rem => {
            if b == 0 {
                let token = source.rsplit(['/', '%']).next().unwrap_or_default().trim();
                return Err(ArithFailure::Error(format!(
                    "{}: division by 0 (error token is \"{}\")",
                    source.trim(),
                    token
                )));
            }
            if op == BinaryOp::Div {
                a.checked_div(b).unwrap_or(a.wrapping_neg())
            } else {
                a.checked_rem(b).unwrap_or(0)
            }
        }
        BinaryOp::Pow => {
            if b < 0 {
                return Err(ArithFailure::Error(format!(
                    "{}: exponent less than 0 (error token is \"{}\")",
                    source.trim(),
                    b
                )));
            }
            let mut result: i64 = 1;
            let mut base = a;
            let mut exponent = b;
            while exponent > 0 {
                if exponent & 1 == 1 {
                    result = result.wrapping_mul(base);
                }
                base = base.wrapping_mul(base);
                exponent >>= 1;
            }
            result
        }
        BinaryOp::Shl => a.wrapping_shl(u32::try_from(b & 63).unwrap_or(0)),
        BinaryOp::Shr => a.wrapping_shr(u32::try_from(b & 63).unwrap_or(0)),
        BinaryOp::BitAnd => a & b,
        BinaryOp::BitOr => a | b,
        BinaryOp::BitXor => a ^ b,
        BinaryOp::Lt => i64::from(a < b),
        BinaryOp::Le => i64::from(a <= b),
        BinaryOp::Gt => i64::from(a > b),
        BinaryOp::Ge => i64::from(a >= b),
        BinaryOp::Eq => i64::from(a == b),
        BinaryOp::Ne => i64::from(a != b),
        BinaryOp::And => i64::from(a != 0 && b != 0),
        BinaryOp::Or => i64::from(a != 0 || b != 0),
    })
}
