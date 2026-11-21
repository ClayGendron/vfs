//! The ways bash quotes a value back as shell text: `${x@Q}`, `printf %q`,
//! `set -x` traces and `declare -p`.

use super::vars::{self, Value, Var};

/// Whether `text` needs `$'...'` because it holds a control character.
fn has_control(text: &str) -> bool {
    text.chars().any(|c| c.is_control())
}

/// `$'...'` quoting of a value with control characters.
pub fn ansi(text: &str) -> String {
    let mut out = String::from("$'");
    for ch in text.chars() {
        match ch {
            '\n' => out.push_str("\\n"),
            '\t' => out.push_str("\\t"),
            '\r' => out.push_str("\\r"),
            '\u{7}' => out.push_str("\\a"),
            '\u{8}' => out.push_str("\\b"),
            '\u{1b}' => out.push_str("\\E"),
            '\u{c}' => out.push_str("\\f"),
            '\u{b}' => out.push_str("\\v"),
            '\'' => out.push_str("\\'"),
            '\\' => out.push_str("\\\\"),
            c if c.is_control() => out.push_str(&format!("\\{:03o}", u32::from(c))),
            c => out.push(c),
        }
    }
    out.push('\'');
    out
}

/// `${x@Q}`: single quotes, or `$'...'` when the value holds a control character.
pub fn single(text: &str) -> String {
    if has_control(text) {
        return ansi(text);
    }
    let mut out = String::from("'");
    for ch in text.chars() {
        if ch == '\'' {
            out.push_str("'\\''");
        } else {
            out.push(ch);
        }
    }
    out.push('\'');
    out
}

/// `printf %q`: backslashes before each special character.
pub fn backslash(text: &str) -> String {
    if text.is_empty() {
        return "''".to_owned();
    }
    if has_control(text) {
        return ansi(text);
    }
    let mut out = String::new();
    for (index, ch) in text.chars().enumerate() {
        let special = matches!(
            ch,
            ' ' | '\t'
                | '!'
                | '"'
                | '#'
                | '$'
                | '&'
                | '\''
                | '('
                | ')'
                | '*'
                | ';'
                | '<'
                | '>'
                | '?'
                | '['
                | '\\'
                | ']'
                | '^'
                | '`'
                | '{'
                | '|'
                | '}'
        ) || (ch == '~' && index == 0)
            || (ch == '=' && false)
            || (ch == ',' && false);
        if special {
            out.push('\\');
        }
        out.push(ch);
    }
    out
}

/// A word as `set -x` shows it: plain when safe, else single-quoted.
pub fn trace(text: &str) -> String {
    if text.is_empty() {
        return "''".to_owned();
    }
    if has_control(text) {
        return ansi(text);
    }
    let safe = text.chars().all(|c| {
        c.is_alphanumeric()
            || matches!(
                c,
                '_' | '-' | '.' | '/' | ',' | ':' | '=' | '+' | '@' | '%' | '^'
            )
    }) && !text.starts_with('=');
    let reserved = matches!(text, "!" | "[[" | "]]" | "{" | "}");
    if safe && !reserved && text != "[" && text != "]" {
        return text.to_owned();
    }
    if text == "]" || text == "[" {
        return format!("'{text}'");
    }
    single(text)
}

/// A value inside double quotes, as `declare -p` prints it.
pub fn double(text: &str) -> String {
    if has_control(text)
        && text
            .chars()
            .any(|c| c.is_control() && c != '\n' && c != '\t')
    {
        return ansi(text);
    }
    let mut out = String::from("\"");
    for ch in text.chars() {
        if matches!(ch, '"' | '\\' | '$' | '`') {
            out.push('\\');
        }
        out.push(ch);
    }
    out.push('"');
    out
}

/// The attribute letters of a variable, in bash's order.
pub fn attr_letters(var: &Var) -> String {
    let mut out = String::new();
    let is_assoc = var.is_assoc();
    if var.is_array() && !is_assoc {
        out.push('a');
    }
    if is_assoc {
        out.push('A');
    }
    for (flag, letter) in [
        (vars::INTEGER, 'i'),
        (vars::NAMEREF, 'n'),
        (vars::READONLY, 'r'),
        (vars::TRACE, 't'),
        (vars::EXPORT, 'x'),
        (vars::CAPITALIZE, 'c'),
        (vars::LOWER, 'l'),
        (vars::UPPER, 'u'),
    ] {
        if var.has(flag) {
            out.push(letter);
        }
    }
    out
}

/// `declare -p name`.
pub fn declaration(name: &str, var: &Var) -> String {
    let letters = attr_letters(var);
    let flags = if letters.is_empty() {
        "--".to_owned()
    } else {
        format!("-{letters}")
    };
    match &var.value {
        None => format!("declare {flags} {name}"),
        Some(Value::Scalar(text)) => format!("declare {flags} {name}={}", double(text)),
        Some(Value::Indexed(map)) => {
            let items: Vec<String> = map
                .iter()
                .map(|(k, v)| format!("[{k}]={}", double(v)))
                .collect();
            format!("declare {flags} {name}=({})", items.join(" "))
        }
        Some(Value::Assoc(map)) => {
            let mut text = String::new();
            for (k, v) in map.iter() {
                text.push_str(&format!("[{}]={} ", assoc_key(k), double(v)));
            }
            format!("declare {flags} {name}=({text})")
        }
    }
}

fn assoc_key(key: &str) -> String {
    let plain = !key.is_empty()
        && key.chars().all(|c| {
            c.is_alphanumeric() || matches!(c, '_' | '-' | '.' | '/' | ',' | ':' | '+' | '@' | '%')
        });
    if plain { key.to_owned() } else { double(key) }
}

/// Decode backslash escapes as `$'...'` does: `${x@E}`.
pub fn ansi_decode(text: &str) -> String {
    let mut out: Vec<u8> = Vec::new();
    let bytes = text.as_bytes();
    let mut index = 0usize;
    while let Some(&byte) = bytes.get(index) {
        index = index.saturating_add(1);
        if byte != b'\\' {
            out.push(byte);
            continue;
        }
        let Some(&next) = bytes.get(index) else {
            out.push(b'\\');
            break;
        };
        index = index.saturating_add(1);
        match next {
            b'n' => out.push(b'\n'),
            b't' => out.push(b'\t'),
            b'r' => out.push(b'\r'),
            b'a' => out.push(7),
            b'b' => out.push(8),
            b'e' | b'E' => out.push(27),
            b'f' => out.push(12),
            b'v' => out.push(11),
            b'\\' => out.push(b'\\'),
            b'\'' => out.push(b'\''),
            b'"' => out.push(b'"'),
            b'0'..=b'7' => {
                let mut value = u32::from(next.saturating_sub(b'0'));
                for _ in 0..2 {
                    match bytes.get(index) {
                        Some(&d @ b'0'..=b'7') => {
                            value = value
                                .saturating_mul(8)
                                .saturating_add(u32::from(d.saturating_sub(b'0')));
                            index = index.saturating_add(1);
                        }
                        _ => break,
                    }
                }
                out.push(u8::try_from(value & 0xff).unwrap_or(0));
            }
            b'x' => {
                let mut value = 0u32;
                let mut count = 0usize;
                while count < 2 {
                    match bytes.get(index).and_then(|b| char::from(*b).to_digit(16)) {
                        Some(d) => {
                            value = value.saturating_mul(16).saturating_add(d);
                            index = index.saturating_add(1);
                            count = count.saturating_add(1);
                        }
                        None => break,
                    }
                }
                if count == 0 {
                    out.extend_from_slice(b"\\x");
                } else {
                    out.push(u8::try_from(value & 0xff).unwrap_or(0));
                }
            }
            other => {
                out.push(b'\\');
                out.push(other);
            }
        }
    }
    String::from_utf8_lossy(&out).into_owned()
}
