//! `printf`: the format is reused until the arguments are used up; numbers
//! are read as C reads them, a leading quote gives a character's code, and
//! a bad number prints what it could and fails the command.

/// What a `printf` call produced.
pub struct Printed {
    pub bytes: Vec<u8>,
    pub errors: Vec<String>,
    pub status: i32,
}

/// Bytes one conversion's width or precision may ask for.
pub const MAX_WIDTH: usize = 1 << 24;

pub fn printf(format: &str, args: &[String], now: i64) -> Printed {
    let mut out = Printed {
        bytes: Vec::new(),
        errors: Vec::new(),
        status: 0,
    };
    let format = format.as_bytes();
    let mut next = 0usize;
    loop {
        let consumed_before = next;
        let stop = one_pass(format, args, &mut next, &mut out, now);
        if stop || next >= args.len() || next == consumed_before {
            break;
        }
    }
    out
}

fn take<'a>(args: &'a [String], next: &mut usize) -> Option<&'a str> {
    let value = args.get(*next).map(String::as_str);
    if value.is_some() {
        *next = next.saturating_add(1);
    }
    value
}

/// One pass over the format. True when `\c` in a `%b` stops all output.
fn one_pass(format: &[u8], args: &[String], next: &mut usize, out: &mut Printed, now: i64) -> bool {
    let mut index = 0usize;
    while let Some(&byte) = format.get(index) {
        index = index.saturating_add(1);
        if byte == b'\\' {
            let (decoded, used, _) = escape(format.get(index..).unwrap_or_default(), false);
            out.bytes.extend_from_slice(&decoded);
            index = index.saturating_add(used);
            continue;
        }
        if byte != b'%' {
            out.bytes.push(byte);
            continue;
        }
        if format.get(index) == Some(&b'%') {
            out.bytes.push(b'%');
            index = index.saturating_add(1);
            continue;
        }
        // Flags, width, precision.
        let spec_start = index;
        let mut flags = String::new();
        while let Some(&f) = format.get(index) {
            if b"-+ #0".contains(&f) {
                flags.push(char::from(f));
                index = index.saturating_add(1);
            } else {
                break;
            }
        }
        let mut width: Option<i64> = None;
        if format.get(index) == Some(&b'*') {
            index = index.saturating_add(1);
            let arg = take(args, next).unwrap_or("0");
            width = Some(number(arg, out).0);
        } else {
            let start = index;
            while format.get(index).is_some_and(u8::is_ascii_digit) {
                index = index.saturating_add(1);
            }
            if index > start {
                width = std::str::from_utf8(format.get(start..index).unwrap_or_default())
                    .ok()
                    .and_then(|s| s.parse().ok());
            }
        }
        let mut precision: Option<i64> = None;
        if format.get(index) == Some(&b'.') {
            index = index.saturating_add(1);
            if format.get(index) == Some(&b'*') {
                index = index.saturating_add(1);
                let arg = take(args, next).unwrap_or("0");
                precision = Some(number(arg, out).0);
            } else {
                let start = index;
                while format.get(index).is_some_and(u8::is_ascii_digit) {
                    index = index.saturating_add(1);
                }
                precision = Some(
                    std::str::from_utf8(format.get(start..index).unwrap_or_default())
                        .ok()
                        .and_then(|s| s.parse().ok())
                        .unwrap_or(0),
                );
            }
        }
        if let Some(w) = width
            && w < 0
        {
            flags.push('-');
            width = Some(w.saturating_neg());
        }
        // Length modifiers are accepted and ignored.
        while format.get(index).is_some_and(|b| b"hlLqjzt".contains(b)) {
            index = index.saturating_add(1);
        }
        let width = width.map(|w| usize::try_from(w).unwrap_or(0).min(MAX_WIDTH));
        let precision = precision
            .and_then(|p| usize::try_from(p).ok())
            .map(|p| p.min(MAX_WIDTH));
        let Some(&conversion) = format.get(index) else {
            let spec = String::from_utf8_lossy(
                format
                    .get(spec_start.saturating_sub(1)..)
                    .unwrap_or_default(),
            )
            .into_owned();
            out.errors.push(format!(
                "`{}': missing format character",
                spec.trim_start_matches('%')
            ));
            out.status = 1;
            return true;
        };
        index = index.saturating_add(1);
        let left = flags.contains('-');
        match conversion {
            b's' => {
                let arg = take(args, next).unwrap_or("");
                let mut bytes = arg.as_bytes().to_vec();
                if let Some(p) = precision {
                    bytes.truncate(p);
                }
                pad(&mut out.bytes, &bytes, width, left, false);
            }
            b'b' => {
                let arg = take(args, next).unwrap_or("");
                let (mut bytes, _, stop) = expand_b(arg.as_bytes());
                if let Some(p) = precision {
                    bytes.truncate(p);
                }
                pad(&mut out.bytes, &bytes, width, left, false);
                if stop {
                    return true;
                }
            }
            b'q' => {
                let arg = take(args, next).unwrap_or("");
                let quoted = super::quote::backslash(arg);
                pad(&mut out.bytes, quoted.as_bytes(), width, left, false);
            }
            b'c' => {
                let arg = take(args, next).unwrap_or("");
                let bytes = match arg.as_bytes().first() {
                    Some(b) => vec![*b],
                    None => vec![0],
                };
                pad(&mut out.bytes, &bytes, width, left, false);
            }
            b'd' | b'i' | b'o' | b'u' | b'x' | b'X' => {
                let arg = take(args, next).unwrap_or("");
                let (value, unsigned) = number(arg, out);
                let text = integer_text(value, unsigned, conversion, &flags, precision);
                let zero = flags.contains('0') && !left && precision.is_none();
                pad_number(&mut out.bytes, &text, width, left, zero);
            }
            b'e' | b'E' | b'f' | b'F' | b'g' | b'G' | b'a' | b'A' => {
                let arg = take(args, next).unwrap_or("");
                let value = float(arg, out);
                let text = float_text(value, conversion, &flags, precision.unwrap_or(6));
                let zero = flags.contains('0') && !left && value.is_finite();
                pad_number(&mut out.bytes, &text, width, left, zero);
            }
            b'n' => {}
            b'(' => {
                let close = format
                    .get(index..)
                    .and_then(|rest| rest.windows(2).position(|w| w == b")T"));
                match close {
                    Some(at) => {
                        let fmt = String::from_utf8_lossy(
                            format
                                .get(index..index.saturating_add(at))
                                .unwrap_or_default(),
                        )
                        .into_owned();
                        index = index.saturating_add(at).saturating_add(2);
                        let arg = take(args, next);
                        let seconds = match arg {
                            None | Some("") => now,
                            Some(text) => {
                                let value = number(text, out).0;
                                if value == -1 || value == -2 {
                                    now
                                } else {
                                    value
                                }
                            }
                        };
                        let fmt = if fmt.is_empty() { "%X".to_owned() } else { fmt };
                        let text = strftime(&fmt, seconds);
                        pad(&mut out.bytes, text.as_bytes(), width, left, false);
                    }
                    None => {
                        out.errors.push("`(': invalid format character".to_owned());
                        out.status = 1;
                        return true;
                    }
                }
            }
            other => {
                let shown = if other == b'\\' {
                    "\\".to_owned()
                } else {
                    char::from(other).to_string()
                };
                out.errors
                    .push(format!("`{shown}': invalid format character"));
                out.status = 1;
                return true;
            }
        }
    }
    false
}

fn pad(out: &mut Vec<u8>, bytes: &[u8], width: Option<usize>, left: bool, _zero: bool) {
    let fill = width.unwrap_or(0).saturating_sub(bytes.len());
    if !left {
        out.extend(std::iter::repeat_n(b' ', fill));
    }
    out.extend_from_slice(bytes);
    if left {
        out.extend(std::iter::repeat_n(b' ', fill));
    }
}

fn pad_number(out: &mut Vec<u8>, text: &str, width: Option<usize>, left: bool, zero: bool) {
    let fill = width.unwrap_or(0).saturating_sub(text.len());
    if zero && fill > 0 {
        let (sign, rest) = match text.as_bytes().first() {
            Some(b'-' | b'+' | b' ') => text.split_at(1),
            _ => ("", text),
        };
        let (prefix, digits) = if rest.starts_with("0x") || rest.starts_with("0X") {
            rest.split_at(2)
        } else {
            ("", rest)
        };
        out.extend_from_slice(sign.as_bytes());
        out.extend_from_slice(prefix.as_bytes());
        out.extend(std::iter::repeat_n(b'0', fill));
        out.extend_from_slice(digits.as_bytes());
        return;
    }
    pad(out, text.as_bytes(), width, left, false);
}

/// A C integer argument: its value, and whether it is to be read as unsigned.
fn number(arg: &str, out: &mut Printed) -> (i64, bool) {
    let trimmed = arg.trim_start();
    if let Some(rest) = trimmed
        .strip_prefix('\'')
        .or_else(|| trimmed.strip_prefix('"'))
    {
        return (
            rest.chars().next().map_or(0, |c| i64::from(u32::from(c))),
            false,
        );
    }
    if trimmed.is_empty() {
        if !arg.is_empty() || arg.is_empty() {
            out.errors.push(format!("{arg}: invalid number"));
            out.status = 1;
        }
        return (0, false);
    }
    let (negative, body) = match trimmed.as_bytes().first() {
        Some(b'-') => (true, trimmed.get(1..).unwrap_or_default()),
        Some(b'+') => (false, trimmed.get(1..).unwrap_or_default()),
        _ => (false, trimmed),
    };
    let (radix, digits) =
        if let Some(hex) = body.strip_prefix("0x").or_else(|| body.strip_prefix("0X")) {
            (16, hex)
        } else if body.len() > 1 && body.starts_with('0') {
            (8, body.get(1..).unwrap_or_default())
        } else {
            (10, body)
        };
    let mut value: u64 = 0;
    let mut used = 0usize;
    let mut overflow = false;
    for ch in digits.chars() {
        let Some(digit) = ch.to_digit(radix) else {
            break;
        };
        match value
            .checked_mul(u64::from(radix))
            .and_then(|v| v.checked_add(u64::from(digit)))
        {
            Some(v) => value = v,
            None => overflow = true,
        }
        used = used.saturating_add(1);
    }
    let rest = digits.get(used..).unwrap_or_default();
    if used == 0
        && !(radix == 16 && digits.is_empty())
        && !(radix == 8 && digits.is_empty() && body == "0")
        || !rest.is_empty()
    {
        out.errors.push(format!("{arg}: invalid number"));
        out.status = 1;
    }
    let limit = if negative { 1u64 << 63 } else { u64::MAX };
    if overflow || value > limit {
        out.errors
            .push(format!("{arg}: Numerical result out of range"));
        out.status = 1;
        return if negative {
            (i64::MIN, false)
        } else {
            (i64::MAX, false)
        };
    }
    if negative {
        (0i64.wrapping_sub_unsigned(value), false)
    } else if value > i64::MAX as u64 {
        (value as i64, true)
    } else {
        (value as i64, false)
    }
}

fn integer_text(
    value: i64,
    unsigned: bool,
    conversion: u8,
    flags: &str,
    precision: Option<usize>,
) -> String {
    let negative = value < 0 && !unsigned && matches!(conversion, b'd' | b'i');
    let magnitude = if matches!(conversion, b'd' | b'i') && !unsigned {
        value.unsigned_abs()
    } else {
        value as u64
    };
    let mut digits = match conversion {
        b'o' => format!("{magnitude:o}"),
        b'x' => format!("{magnitude:x}"),
        b'X' => format!("{magnitude:X}"),
        _ => magnitude.to_string(),
    };
    if let Some(p) = precision {
        if p == 0 && magnitude == 0 {
            digits.clear();
        }
        if digits.len() < p {
            digits = format!("{}{}", "0".repeat(p.saturating_sub(digits.len())), digits);
        }
    }
    if flags.contains('#') && magnitude != 0 {
        match conversion {
            b'o' if !digits.starts_with('0') => digits.insert(0, '0'),
            b'x' => digits.insert_str(0, "0x"),
            b'X' => digits.insert_str(0, "0X"),
            _ => {}
        }
    }
    let sign = if negative {
        "-"
    } else if matches!(conversion, b'd' | b'i') && flags.contains('+') {
        "+"
    } else if matches!(conversion, b'd' | b'i') && flags.contains(' ') {
        " "
    } else {
        ""
    };
    format!("{sign}{digits}")
}

fn float(arg: &str, out: &mut Printed) -> f64 {
    let trimmed = arg.trim();
    if let Some(rest) = trimmed
        .strip_prefix('\'')
        .or_else(|| trimmed.strip_prefix('"'))
    {
        return rest.chars().next().map_or(0.0, |c| f64::from(u32::from(c)));
    }
    if let Some(hex) = trimmed
        .strip_prefix("0x")
        .or_else(|| trimmed.strip_prefix("0X"))
        && let Ok(v) = u64::from_str_radix(hex, 16)
    {
        return v as f64;
    }
    match trimmed.parse::<f64>() {
        Ok(value) => value,
        Err(_) => {
            // The longest numeric prefix, as strtod reads.
            let mut best = 0.0;
            let mut found = false;
            for end in (1..=trimmed.len()).rev() {
                if let Some(Ok(value)) = trimmed.get(..end).map(str::parse::<f64>) {
                    best = value;
                    found = true;
                    break;
                }
            }
            out.errors.push(format!("{arg}: invalid number"));
            out.status = 1;
            if found { best } else { 0.0 }
        }
    }
}

fn float_text(value: f64, conversion: u8, flags: &str, precision: usize) -> String {
    let upper = conversion.is_ascii_uppercase();
    let sign = if value.is_sign_negative() && !(value == 0.0 && !value.is_sign_negative()) {
        "-"
    } else if flags.contains('+') {
        "+"
    } else if flags.contains(' ') {
        " "
    } else {
        ""
    };
    let magnitude = value.abs();
    if magnitude.is_infinite() {
        return format!("{sign}{}", if upper { "INF" } else { "inf" });
    }
    if magnitude.is_nan() {
        return format!("{sign}{}", if upper { "NAN" } else { "nan" });
    }
    let body = match conversion.to_ascii_lowercase() {
        b'f' => {
            let mut text = format!("{magnitude:.precision$}");
            if flags.contains('#') && precision == 0 {
                text.push('.');
            }
            text
        }
        b'e' => exponent_text(magnitude, precision, flags.contains('#')),
        b'g' => general_text(magnitude, precision, flags.contains('#')),
        _ => format!("{magnitude:e}"),
    };
    let body = if upper { body.to_uppercase() } else { body };
    format!("{sign}{body}")
}

fn exponent_text(value: f64, precision: usize, alternate: bool) -> String {
    let text = format!("{value:.precision$e}");
    let (mantissa, exponent) = text.split_once('e').unwrap_or((&text, "0"));
    let exponent: i32 = exponent.parse().unwrap_or(0);
    let mut mantissa = mantissa.to_owned();
    if alternate && precision == 0 {
        mantissa.push('.');
    }
    let sign = if exponent < 0 { '-' } else { '+' };
    format!("{mantissa}e{sign}{:02}", exponent.unsigned_abs())
}

fn general_text(value: f64, precision: usize, alternate: bool) -> String {
    let p = if precision == 0 { 1 } else { precision };
    if value == 0.0 {
        return if alternate {
            format!("{:.*}", p.saturating_sub(1), 0.0)
        } else {
            "0".to_owned()
        };
    }
    let exact = format!("{:.*e}", p.saturating_sub(1), value);
    let exponent: i64 = exact
        .split_once('e')
        .and_then(|(_, e)| e.parse().ok())
        .unwrap_or(0);
    let p_i = i64::try_from(p).unwrap_or(6);
    let text = if exponent < -4 || exponent >= p_i {
        exponent_text(value, p.saturating_sub(1), alternate)
    } else {
        let decimals = usize::try_from(p_i.saturating_sub(1).saturating_sub(exponent)).unwrap_or(0);
        format!("{value:.decimals$}")
    };
    if alternate {
        return text;
    }
    strip_zeros(&text)
}

fn strip_zeros(text: &str) -> String {
    let (mantissa, exponent) = match text.find('e') {
        Some(at) => (
            text.get(..at).unwrap_or_default(),
            text.get(at..).unwrap_or_default(),
        ),
        None => (text, ""),
    };
    let mantissa = if mantissa.contains('.') {
        mantissa.trim_end_matches('0').trim_end_matches('.')
    } else {
        mantissa
    };
    format!("{mantissa}{exponent}")
}

/// Decode one backslash escape after the backslash: its bytes, the bytes used, and `\c`.
pub fn escape(rest: &[u8], echo_style: bool) -> (Vec<u8>, usize, bool) {
    let Some(&first) = rest.first() else {
        return (vec![b'\\'], 0, false);
    };
    let simple = |b: u8| (vec![b], 1, false);
    match first {
        b'n' => simple(b'\n'),
        b't' => simple(b'\t'),
        b'r' => simple(b'\r'),
        b'a' => simple(7),
        b'b' => simple(8),
        b'f' => simple(12),
        b'v' => simple(11),
        b'e' | b'E' => simple(27),
        b'\\' => simple(b'\\'),
        b'"' => simple(b'"'),
        b'\'' => simple(b'\''),
        b'?' => simple(b'?'),
        b'c' if echo_style => (Vec::new(), 1, true),
        b'0'..=b'7' => {
            // In `%b` and echo, an octal escape is `\0nnn`; in a format, `\nnn`.
            let (start, max) = if echo_style && first == b'0' {
                (1usize, 3usize)
            } else if echo_style {
                return (vec![b'\\', first], 1, false);
            } else {
                (0, 3)
            };
            let mut value = 0u32;
            let mut used = start;
            while used < start.saturating_add(max) {
                match rest.get(used) {
                    Some(&d @ b'0'..=b'7') => {
                        value = value
                            .saturating_mul(8)
                            .saturating_add(u32::from(d.saturating_sub(b'0')));
                        used = used.saturating_add(1);
                    }
                    _ => break,
                }
            }
            (vec![u8::try_from(value & 0xff).unwrap_or(0)], used, false)
        }
        b'x' => {
            let mut value = 0u32;
            let mut used = 1usize;
            while used < 3 {
                match rest.get(used).and_then(|b| char::from(*b).to_digit(16)) {
                    Some(d) => {
                        value = value.saturating_mul(16).saturating_add(d);
                        used = used.saturating_add(1);
                    }
                    None => break,
                }
            }
            if used == 1 {
                return (b"\\x".to_vec(), 1, false);
            }
            (vec![u8::try_from(value & 0xff).unwrap_or(0)], used, false)
        }
        b'u' | b'U' => {
            let max = if first == b'u' { 5 } else { 9 };
            let mut value = 0u32;
            let mut used = 1usize;
            while used < max {
                match rest.get(used).and_then(|b| char::from(*b).to_digit(16)) {
                    Some(d) => {
                        value = value.saturating_mul(16).saturating_add(d);
                        used = used.saturating_add(1);
                    }
                    None => break,
                }
            }
            if used == 1 {
                return (vec![b'\\', first], 1, false);
            }
            let ch = char::from_u32(value).unwrap_or('\u{fffd}');
            let mut buffer = [0u8; 4];
            (ch.encode_utf8(&mut buffer).as_bytes().to_vec(), used, false)
        }
        other => (vec![b'\\', other], 1, false),
    }
}

/// `%b` and `echo -e`: escapes decoded; true when `\c` ends the output.
pub fn expand_b(text: &[u8]) -> (Vec<u8>, usize, bool) {
    let mut out = Vec::new();
    let mut index = 0usize;
    while let Some(&byte) = text.get(index) {
        index = index.saturating_add(1);
        if byte != b'\\' {
            out.push(byte);
            continue;
        }
        let (decoded, used, stop) = escape(text.get(index..).unwrap_or_default(), true);
        if stop {
            return (out, index, true);
        }
        out.extend_from_slice(&decoded);
        index = index.saturating_add(used);
    }
    (out, index, false)
}

/// A small `strftime` in UTC.
// Calendar arithmetic on epoch seconds: every intermediate fits an i64 by far.
#[allow(clippy::arithmetic_side_effects)]
pub fn strftime(format: &str, seconds: i64) -> String {
    let days = seconds.div_euclid(86_400);
    let secs = seconds.rem_euclid(86_400);
    let (year, month, day) = civil(days);
    let hour = secs / 3600;
    let minute = (secs % 3600) / 60;
    let second = secs % 60;
    let weekday = (days.rem_euclid(7) + 4) % 7;
    let yday = days - days_from_civil(year, 1, 1);
    const DAYS: [&str; 7] = [
        "Sunday",
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
    ];
    const MONTHS: [&str; 12] = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ];
    let day_name = DAYS
        .get(usize::try_from(weekday).unwrap_or(0))
        .copied()
        .unwrap_or("Sunday");
    let month_name = MONTHS
        .get(usize::try_from(month.saturating_sub(1)).unwrap_or(0))
        .copied()
        .unwrap_or("January");
    let mut out = String::new();
    let mut chars = format.chars();
    while let Some(ch) = chars.next() {
        if ch != '%' {
            out.push(ch);
            continue;
        }
        match chars.next() {
            Some('Y') => out.push_str(&year.to_string()),
            Some('y') => out.push_str(&format!("{:02}", year.rem_euclid(100))),
            Some('C') => out.push_str(&format!("{:02}", year.div_euclid(100))),
            Some('m') => out.push_str(&format!("{month:02}")),
            Some('d') => out.push_str(&format!("{day:02}")),
            Some('e') => out.push_str(&format!("{day:2}")),
            Some('H') => out.push_str(&format!("{hour:02}")),
            Some('I') => out.push_str(&format!(
                "{:02}",
                if hour % 12 == 0 { 12 } else { hour % 12 }
            )),
            Some('M') => out.push_str(&format!("{minute:02}")),
            Some('S') => out.push_str(&format!("{second:02}")),
            Some('p') => out.push_str(if hour < 12 { "AM" } else { "PM" }),
            Some('j') => out.push_str(&format!("{:03}", yday + 1)),
            Some('a') => out.push_str(day_name.get(..3).unwrap_or(day_name)),
            Some('A') => out.push_str(day_name),
            Some('b' | 'h') => out.push_str(month_name.get(..3).unwrap_or(month_name)),
            Some('B') => out.push_str(month_name),
            Some('u') => out.push_str(&(if weekday == 0 { 7 } else { weekday }).to_string()),
            Some('w') => out.push_str(&weekday.to_string()),
            Some('s') => out.push_str(&seconds.to_string()),
            Some('F') => out.push_str(&format!("{year}-{month:02}-{day:02}")),
            Some('T' | 'X') => out.push_str(&format!("{hour:02}:{minute:02}:{second:02}")),
            Some('R') => out.push_str(&format!("{hour:02}:{minute:02}")),
            Some('D' | 'x') => {
                out.push_str(&format!("{month:02}/{day:02}/{:02}", year.rem_euclid(100)))
            }
            Some('c') => out.push_str(&format!(
                "{} {} {day:2} {hour:02}:{minute:02}:{second:02} {year}",
                day_name.get(..3).unwrap_or(day_name),
                month_name.get(..3).unwrap_or(month_name)
            )),
            Some('Z') => out.push_str("UTC"),
            Some('z') => out.push_str("+0000"),
            Some('n') => out.push('\n'),
            Some('t') => out.push('\t'),
            Some('%') => out.push('%'),
            Some(other) => {
                out.push('%');
                out.push(other);
            }
            None => out.push('%'),
        }
    }
    out
}

// Calendar arithmetic on epoch seconds: every intermediate fits an i64 by far.
#[allow(clippy::arithmetic_side_effects)]
fn civil(days: i64) -> (i64, i64, i64) {
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z.rem_euclid(146_097);
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    (if m <= 2 { y + 1 } else { y }, m, d)
}

// Calendar arithmetic on epoch seconds: every intermediate fits an i64 by far.
#[allow(clippy::arithmetic_side_effects)]
fn days_from_civil(year: i64, month: i64, day: i64) -> i64 {
    let y = if month <= 2 { year - 1 } else { year };
    let era = y.div_euclid(400);
    let yoe = y.rem_euclid(400);
    let mp = if month > 2 { month - 3 } else { month + 9 };
    let doy = (153 * mp + 2) / 5 + day - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146_097 + doe - 719_468
}
