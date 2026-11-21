//! Word expansion in bash's order: braces, then tilde, parameters,
//! arithmetic and command substitution from left to right, then field
//! splitting, then pathnames, then quote removal. Text keeps where it came
//! from until the end: quoted text is never split or globbed, literal text
//! is globbed but never split, and the result of an expansion is both.

use std::borrow::Cow;
use std::future::Future;
use std::pin::Pin;

use super::arith::{self, ArithFailure};
use super::exec::{Ctx, Flow, capture};
use super::pattern::{MatchOptions, PatChar, Pattern, has_glob};
use super::quote;
use super::shell::Shell;
use super::vars::{self, Value};
use super::{Entry, EntryKind, Reply, Request, io};
use crate::syntax::ast::{DefaultKind, Param, ParamExp, ParamOp, ReplaceKind, Word, WordPart};
use crate::syntax::is_name;

/// Words a brace expansion may make from one word.
const BRACE_WORDS: usize = 1 << 20;
/// Entries one pathname expansion may visit.
const GLOB_VISITS: usize = 1 << 20;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Kind {
    /// From quotes or a backslash: never split, never a pattern.
    Quoted,
    /// Unquoted source text: a pattern, never split.
    Literal,
    /// The result of an unquoted expansion: split, and a pattern.
    Expanded,
}

#[derive(Clone, Debug)]
struct Piece {
    text: String,
    kind: Kind,
}

/// A field before splitting: its pieces, and whether a quote kept it even if empty.
#[derive(Clone, Debug, Default)]
struct Field {
    pieces: Vec<Piece>,
    keep: bool,
}

/// How a word is expanded.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Mode {
    /// Split and globbed: a command's arguments.
    Fields,
    /// One string, neither split nor globbed: assignments, `case` words, here-strings.
    Single,
    /// An assignment's value: also expands `~` after `:`.
    Assignment,
}

type Boxed<'b, T> = Pin<Box<dyn Future<Output = Result<T, Flow>> + 'b>>;

// ---------------------------------------------------------------------------
// Entry points
// ---------------------------------------------------------------------------

/// A word's fields, split and globbed.
pub async fn expand_fields(
    ctx: &Ctx<'_>,
    sh: &mut Shell,
    word: &Word,
) -> Result<Vec<String>, Flow> {
    let mut out = Vec::new();
    for parts in brace_expand(sh, word)? {
        let fields = expand_parts(ctx, sh, &parts, false, true).await?;
        for chars in split_fields(sh, fields) {
            if sh.options.noglob
                || !has_glob(&chars, sh.options.shopt("extglob"))
                || backslash_in_expansion(&chars)
            {
                out.push(chars.iter().map(|(c, _)| *c).collect());
                continue;
            }
            match glob(ctx, sh, &chars).await? {
                Some(paths) => out.extend(paths),
                None => {
                    if sh.options.shopt("failglob") {
                        let text: String = chars.iter().map(|(c, _)| *c).collect();
                        sh.error_text(&format!("bash: line {}: no match: {}\n", sh.lineno, text))
                            .await?;
                        return Err(Flow::CommandFailed(1));
                    }
                    if !sh.options.shopt("nullglob") {
                        out.push(chars.iter().map(|(c, _)| *c).collect());
                    }
                }
            }
        }
    }
    Ok(out)
}

/// Every word's fields, in order.
pub async fn expand_words(
    ctx: &Ctx<'_>,
    sh: &mut Shell,
    words: &[Word],
) -> Result<Vec<String>, Flow> {
    let mut out = Vec::new();
    for word in words {
        out.extend(expand_fields(ctx, sh, word).await?);
    }
    Ok(out)
}

/// A word as one string, with no splitting and no globbing.
pub async fn expand_single(
    ctx: &Ctx<'_>,
    sh: &mut Shell,
    word: &Word,
    mode: Mode,
) -> Result<String, Flow> {
    let saved = std::mem::replace(&mut sh.single_word, true);
    let fields = expand_parts(ctx, sh, &word.parts, false, mode != Mode::Fields).await;
    sh.single_word = saved;
    let mut fields = fields?;
    if mode == Mode::Assignment {
        assignment_tildes(sh, &mut fields);
    }
    Ok(join_fields(sh, &fields))
}

/// A word as a pattern: its characters and whether each was quoted.
pub async fn expand_pattern(
    ctx: &Ctx<'_>,
    sh: &mut Shell,
    word: &Word,
) -> Result<Vec<PatChar>, Flow> {
    let fields = expand_parts(ctx, sh, &word.parts, false, true).await?;
    let mut chars = Vec::new();
    for (index, field) in fields.iter().enumerate() {
        if index > 0 {
            chars.push((' ', true));
        }
        for piece in &field.pieces {
            let quoted = piece.kind == Kind::Quoted;
            chars.extend(piece.text.chars().map(|c| (c, quoted)));
        }
    }
    Ok(chars)
}

/// A pattern word compiled, honouring `extglob`.
pub async fn compile_pattern(ctx: &Ctx<'_>, sh: &mut Shell, word: &Word) -> Result<Pattern, Flow> {
    let chars = expand_pattern(ctx, sh, word).await?;
    Ok(Pattern::compile(&chars, sh.options.shopt("extglob")))
}

/// Fields of a word that becomes one string: they join with spaces, as `"$@"` does there.
fn join_fields(_sh: &Shell, fields: &[Field]) -> String {
    let texts: Vec<String> = fields
        .iter()
        .map(|f| f.pieces.iter().map(|p| p.text.as_str()).collect())
        .collect();
    texts.join(" ")
}

fn backslash_in_expansion(chars: &[PatChar]) -> bool {
    let _ = chars;
    false
}

// ---------------------------------------------------------------------------
// Brace expansion
// ---------------------------------------------------------------------------

#[derive(Clone)]
enum Token<'a> {
    Char(char),
    Part(&'a WordPart),
}

/// The words a brace expansion makes, as part lists.
fn brace_expand<'w>(sh: &Shell, word: &'w Word) -> Result<Vec<Cow<'w, [WordPart]>>, Flow> {
    let has_brace = word
        .parts
        .iter()
        .any(|part| matches!(part, WordPart::Literal(text) if text.contains('{')));
    if !sh.options.braceexpand || !has_brace {
        return Ok(vec![Cow::Borrowed(word.parts.as_slice())]);
    }
    let mut tokens = Vec::new();
    for part in &word.parts {
        match part {
            WordPart::Literal(text) => tokens.extend(text.chars().map(Token::Char)),
            other => tokens.push(Token::Part(other)),
        }
    }
    let mut words = Vec::new();
    expand_braces(&tokens, &mut words, 0)?;
    if words.len() == 1 {
        return Ok(vec![Cow::Borrowed(word.parts.as_slice())]);
    }
    Ok(words
        .into_iter()
        .map(|tokens| {
            let mut parts = Vec::new();
            let mut literal = String::new();
            for token in tokens {
                match token {
                    Token::Char(c) => literal.push(c),
                    Token::Part(part) => {
                        if !literal.is_empty() {
                            parts.push(WordPart::Literal(std::mem::take(&mut literal)));
                        }
                        parts.push(part.clone());
                    }
                }
            }
            if !literal.is_empty() {
                parts.push(WordPart::Literal(literal));
            }
            Cow::Owned(parts)
        })
        .collect())
}

fn expand_braces<'a>(
    tokens: &[Token<'a>],
    out: &mut Vec<Vec<Token<'a>>>,
    depth: u32,
) -> Result<(), Flow> {
    if depth > 64 {
        out.push(tokens.to_vec());
        return Ok(());
    }
    // Find the first `{` with a matching `}` holding a top-level comma or a sequence.
    let mut start = 0;
    while start < tokens.len() {
        if !matches!(tokens.get(start), Some(Token::Char('{'))) || is_dollar_brace(tokens, start) {
            start = start.saturating_add(1);
            continue;
        }
        let mut level = 0u32;
        let mut commas = Vec::new();
        let mut close = None;
        for (index, token) in tokens.iter().enumerate().skip(start) {
            match token {
                Token::Char('{') => level = level.saturating_add(1),
                Token::Char('}') => {
                    level = level.saturating_sub(1);
                    if level == 0 {
                        close = Some(index);
                        break;
                    }
                }
                Token::Char(',') if level == 1 => commas.push(index),
                _ => {}
            }
        }
        let Some(close) = close else {
            start = start.saturating_add(1);
            continue;
        };
        let prefix = tokens.get(..start).unwrap_or_default();
        let suffix = tokens.get(close.saturating_add(1)..).unwrap_or_default();
        let inner = tokens
            .get(start.saturating_add(1)..close)
            .unwrap_or_default();
        let alternatives: Vec<Vec<Token<'a>>> = if commas.is_empty() {
            match sequence(inner)? {
                Some(items) => items
                    .into_iter()
                    .map(|text| text.chars().map(Token::Char).collect())
                    .collect(),
                None => {
                    start = start.saturating_add(1);
                    continue;
                }
            }
        } else {
            let mut pieces = Vec::new();
            let mut from = start.saturating_add(1);
            for comma in commas.iter().copied().chain(std::iter::once(close)) {
                pieces.push(tokens.get(from..comma).unwrap_or_default().to_vec());
                from = comma.saturating_add(1);
            }
            pieces
        };
        for alternative in alternatives {
            let mut combined = prefix.to_vec();
            combined.extend(alternative);
            combined.extend_from_slice(suffix);
            // The rest of the word, alternative included, may hold more braces.
            let before = out.len();
            expand_braces(&combined, out, depth.saturating_add(1))?;
            if out.len() > BRACE_WORDS || before > BRACE_WORDS {
                return Err(Flow::Fatal(super::Fatal::Budget(
                    "brace_words",
                    BRACE_WORDS as u64,
                )));
            }
        }
        return Ok(());
    }
    out.push(tokens.to_vec());
    Ok(())
}

fn is_dollar_brace(tokens: &[Token<'_>], index: usize) -> bool {
    index > 0 && matches!(tokens.get(index.saturating_sub(1)), Some(Token::Char('$')))
}

/// The items of `{a..b}` or `{a..b..step}`, or `None` when the text is no sequence.
fn sequence(inner: &[Token<'_>]) -> Result<Option<Vec<String>>, Flow> {
    let count = sequence_count(inner);
    if count.is_some_and(|count| count > BRACE_WORDS as u64) {
        return Err(Flow::Fatal(super::Fatal::Budget(
            "brace_words",
            BRACE_WORDS as u64,
        )));
    }
    Ok(sequence_items(inner))
}

/// How many items a sequence would make, counted before any is built.
fn sequence_count(inner: &[Token<'_>]) -> Option<u64> {
    let text: String = inner
        .iter()
        .map(|token| match token {
            Token::Char(c) => Some(*c),
            Token::Part(_) => None,
        })
        .collect::<Option<String>>()?;
    let pieces: Vec<&str> = text.split("..").collect();
    let (from, to, step) = match pieces.as_slice() {
        [from, to] => (*from, *to, "1"),
        [from, to, step] => (*from, *to, *step),
        _ => return None,
    };
    let a: i64 = from.parse().ok()?;
    let b: i64 = to.parse().ok()?;
    let step: i64 = step.parse().ok()?;
    let step = step.unsigned_abs().max(1);
    a.abs_diff(b).checked_div(step)
}

fn sequence_items(inner: &[Token<'_>]) -> Option<Vec<String>> {
    let text: String = inner
        .iter()
        .map(|token| match token {
            Token::Char(c) => Some(*c),
            Token::Part(_) => None,
        })
        .collect::<Option<String>>()?;
    let pieces: Vec<&str> = text.split("..").collect();
    let (from, to, step) = match pieces.as_slice() {
        [from, to] => (*from, *to, None),
        [from, to, step] => (*from, *to, Some(*step)),
        _ => return None,
    };
    let step: i64 = match step {
        Some(step) => step.parse().ok()?,
        None => 1,
    };
    let step = if step == 0 { 1 } else { step.checked_abs()? };
    if let (Ok(a), Ok(b)) = (from.parse::<i64>(), to.parse::<i64>()) {
        let width = |s: &str| {
            let digits = s.trim_start_matches('-');
            if digits.len() > 1 && digits.starts_with('0') {
                s.len()
            } else {
                0
            }
        };
        let pad = width(from).max(width(to));
        let mut items = Vec::new();
        let mut value = a;
        loop {
            items.push(if pad > 0 {
                pad_number(value, pad)
            } else {
                value.to_string()
            });
            if value == b {
                break;
            }
            let next = if a <= b {
                value.checked_add(step)?
            } else {
                value.checked_sub(step)?
            };
            if (a <= b && next > b) || (a > b && next < b) {
                break;
            }
            value = next;
        }
        return Some(items);
    }
    let (Some(a), Some(b)) = (single_char(from), single_char(to)) else {
        return None;
    };
    let (a, b) = (u32::from(a), u32::from(b));
    let step = u32::try_from(step).ok()?;
    let mut items = Vec::new();
    let mut value = a;
    loop {
        if let Some(ch) = char::from_u32(value) {
            items.push(if ch == '\\' {
                String::new()
            } else {
                ch.to_string()
            });
        }
        if value == b {
            break;
        }
        let next = if a <= b {
            value.checked_add(step)?
        } else {
            value.checked_sub(step)?
        };
        if (a <= b && next > b) || (a > b && next < b) {
            break;
        }
        value = next;
    }
    Some(items)
}

fn single_char(text: &str) -> Option<char> {
    let mut chars = text.chars();
    let first = chars.next()?;
    (chars.next().is_none() && first.is_ascii_alphabetic()).then_some(first)
}

/// `value` zero-padded to `width` characters, the sign inside the width. Written here, since the
/// formatter refuses a width past 65,535.
fn pad_number(value: i64, width: usize) -> String {
    let digits = value.unsigned_abs().to_string();
    let sign = if value < 0 { "-" } else { "" };
    let zeros = width
        .saturating_sub(sign.len())
        .saturating_sub(digits.len());
    format!("{sign}{}{digits}", "0".repeat(zeros))
}

// ---------------------------------------------------------------------------
// Parts to fields
// ---------------------------------------------------------------------------

struct Builder {
    fields: Vec<Field>,
}

impl Builder {
    fn new() -> Builder {
        Builder {
            fields: vec![Field::default()],
        }
    }

    fn push(&mut self, text: String, kind: Kind) {
        if let Some(field) = self.fields.last_mut() {
            if kind == Kind::Quoted {
                field.keep = true;
            }
            if !text.is_empty() {
                field.pieces.push(Piece { text, kind });
            }
        }
    }

    /// Start a new field: the boundary between two elements of `"$@"`.
    fn split(&mut self) {
        self.fields.push(Field::default());
    }
}

/// Expand parts. `quoted` is whether they sit inside double quotes.
fn expand_parts<'p, 'b>(
    ctx: &'b Ctx<'_>,
    sh: &'b mut Shell,
    parts: &'p [WordPart],
    quoted: bool,
    tilde: bool,
) -> Boxed<'b, Vec<Field>>
where
    'p: 'b,
{
    Box::pin(async move {
        let mut out = Builder::new();
        for (index, part) in parts.iter().enumerate() {
            match part {
                WordPart::Literal(text)
                    if sh.literal_splits && !quoted && !(index == 0 && text.starts_with('~')) =>
                {
                    out.push(text.clone(), Kind::Expanded);
                }
                WordPart::Literal(text) => {
                    if quoted {
                        out.push(text.clone(), Kind::Quoted);
                    } else if index == 0 && tilde && text.starts_with('~') {
                        let (expanded, rest) = tilde_prefix(sh, text, parts.get(1));
                        match expanded {
                            Some(home) => {
                                out.push(home, Kind::Quoted);
                                out.push(rest, Kind::Literal);
                            }
                            None => out.push(text.clone(), Kind::Literal),
                        }
                    } else if index == 0 && tilde && !quoted && assignment_like(text) {
                        let (head, value) = text.split_once('=').unwrap_or((text, ""));
                        out.push(format!("{head}="), Kind::Literal);
                        if value.starts_with('~') {
                            let (expanded, rest) = tilde_prefix(sh, value, parts.get(1));
                            match expanded {
                                Some(home) => {
                                    out.push(home, Kind::Quoted);
                                    out.push(rest, Kind::Literal);
                                }
                                None => out.push(value.to_owned(), Kind::Literal),
                            }
                        } else {
                            out.push(value.to_owned(), Kind::Literal);
                        }
                    } else {
                        out.push(text.clone(), Kind::Literal);
                    }
                }
                WordPart::Escaped(ch) => out.push(ch.to_string(), Kind::Quoted),
                WordPart::Single(text) | WordPart::AnsiC(text) => {
                    out.push(text.clone(), Kind::Quoted)
                }
                WordPart::Double(inner) => {
                    let saved = std::mem::replace(&mut sh.literal_splits, false);
                    let fields = expand_parts(ctx, sh, inner, true, false).await;
                    sh.literal_splits = saved;
                    let fields = fields?;
                    merge(&mut out, fields);
                    if let Some(field) = out.fields.last_mut() {
                        field.keep = field.keep || !inner_has_at(inner);
                    }
                }
                WordPart::Param(expansion) => {
                    let fields = expand_param(ctx, sh, expansion, quoted).await?;
                    merge(&mut out, fields);
                }
                WordPart::CommandSub(list, _) => {
                    let text = capture(ctx, sh, list).await?;
                    out.push(text, if quoted { Kind::Quoted } else { Kind::Expanded });
                }
                WordPart::Arith(word, _) => {
                    let text = expand_single(ctx, sh, word, Mode::Single).await?;
                    let value = eval_arith(ctx, sh, &text).await?;
                    out.push(
                        value.to_string(),
                        if quoted { Kind::Quoted } else { Kind::Expanded },
                    );
                }
                WordPart::ProcessSub(input, list, _) => {
                    let path = super::exec::process_sub(ctx, sh, *input, list).await?;
                    out.push(path, if quoted { Kind::Quoted } else { Kind::Expanded });
                }
            }
        }
        Ok(out.fields)
    })
}

fn inner_has_at(parts: &[WordPart]) -> bool {
    parts.iter().any(|part| match part {
        WordPart::Param(expansion) => is_at_list(expansion),
        _ => false,
    })
}

fn is_at_list(expansion: &ParamExp) -> bool {
    if !matches!(
        expansion.op,
        ParamOp::Plain
            | ParamOp::RemovePrefix { .. }
            | ParamOp::RemoveSuffix { .. }
            | ParamOp::Replace { .. }
            | ParamOp::Case { .. }
            | ParamOp::Substring { .. }
            | ParamOp::Transform(_)
            | ParamOp::Keys(true)
            | ParamOp::PrefixNames(true)
    ) {
        return false;
    }
    match &expansion.param {
        Param::Special('@') => true,
        Param::Element(_, sub) => sub.as_literal() == Some("@"),
        Param::Named(_) => matches!(
            expansion.op,
            ParamOp::Keys(true) | ParamOp::PrefixNames(true)
        ),
        _ => false,
    }
}

/// Append `fields` to `out`: the first joins the open field, the rest start new ones.
fn merge(out: &mut Builder, fields: Vec<Field>) {
    let mut first = true;
    for field in fields {
        if !first {
            out.split();
        }
        first = false;
        if let Some(open) = out.fields.last_mut() {
            open.keep = open.keep || field.keep;
            open.pieces.extend(field.pieces);
        }
    }
}

fn assignment_like(text: &str) -> bool {
    match text.split_once('=') {
        Some((name, _)) => is_name(name),
        None => false,
    }
}

/// `~`, `~/x`, `~+`, `~-` at the start of `text`: the expansion and the rest.
fn tilde_prefix(sh: &Shell, text: &str, next: Option<&WordPart>) -> (Option<String>, String) {
    let body = text.get(1..).unwrap_or_default();
    let (name, rest) = match body.find(['/', ':']) {
        Some(at) => (
            body.get(..at).unwrap_or_default(),
            body.get(at..).unwrap_or_default(),
        ),
        None => {
            // `~` followed by a quoted or expanded part is not a tilde prefix.
            if next.is_some() && !body.is_empty() {
                return (None, text.to_owned());
            }
            if next.is_some_and(|part| !matches!(part, WordPart::Literal(_))) && body.is_empty() {
                // `~"x"`: the prefix ends at the quote, so it is the bare tilde.
            }
            (body, "")
        }
    };
    let expanded = match name {
        "" => sh.get_var("HOME"),
        "+" => sh.get_var("PWD"),
        "-" => sh.get_var("OLDPWD"),
        user if Some(user.to_owned()) == sh.get_var("USER") => sh.get_var("HOME"),
        "root" => Some("/root".to_owned()),
        _ => None,
    };
    (expanded, rest.to_owned())
}

/// In an assignment, `~` after each unquoted `:` expands too.
fn assignment_tildes(sh: &Shell, fields: &mut [Field]) {
    for field in fields {
        let mut out = Vec::new();
        for (index, piece) in field.pieces.iter().enumerate() {
            if piece.kind != Kind::Literal {
                out.push(piece.clone());
                continue;
            }
            let mut text = String::new();
            let segments: Vec<&str> = piece.text.split(':').collect();
            for (n, segment) in segments.iter().enumerate() {
                if n > 0 {
                    text.push(':');
                }
                let first_of_value = index == 0 && n == 0;
                if (n > 0 || first_of_value) && segment.starts_with('~') {
                    let (expanded, rest) = tilde_prefix(sh, segment, None);
                    match expanded {
                        Some(home) => {
                            text.push_str(&home);
                            text.push_str(&rest);
                        }
                        None => text.push_str(segment),
                    }
                } else {
                    text.push_str(segment);
                }
            }
            out.push(Piece {
                text,
                kind: Kind::Literal,
            });
        }
        field.pieces = out;
    }
}

// ---------------------------------------------------------------------------
// Field splitting
// ---------------------------------------------------------------------------

fn split_fields(sh: &Shell, fields: Vec<Field>) -> Vec<Vec<PatChar>> {
    let ifs = sh.ifs().unwrap_or_default();
    let ifs_unset = sh.vars.get("IFS").is_none();
    let ifs = if ifs_unset { " \t\n".to_owned() } else { ifs };
    let mut out = Vec::new();
    for field in fields {
        let mut current: Vec<PatChar> = Vec::new();
        let mut nonempty = field.keep;
        let mut after_space = false;
        for piece in &field.pieces {
            let quoted = piece.kind == Kind::Quoted;
            if piece.kind != Kind::Expanded || ifs.is_empty() {
                current.extend(piece.text.chars().map(|c| (c, quoted)));
                nonempty = true;
                after_space = false;
                continue;
            }
            for ch in piece.text.chars() {
                if !ifs.contains(ch) {
                    current.push((ch, false));
                    nonempty = true;
                    after_space = false;
                    continue;
                }
                if is_ifs_space(ch) {
                    if nonempty {
                        out.push(std::mem::take(&mut current));
                        nonempty = false;
                        after_space = true;
                    }
                } else if after_space && current.is_empty() && !nonempty {
                    after_space = false;
                } else {
                    out.push(std::mem::take(&mut current));
                    nonempty = false;
                    after_space = false;
                }
            }
        }
        if nonempty {
            out.push(current);
        }
    }
    out
}

fn is_ifs_space(ch: char) -> bool {
    matches!(ch, ' ' | '\t' | '\n')
}

/// Split `text` as `read` does: into at most `max` fields, the last taking the rest.
pub fn split_read(text: &str, ifs: &str, max: usize) -> Vec<String> {
    let chars: Vec<char> = text.chars().collect();
    let mut fields = Vec::new();
    let mut index = 0usize;
    let len = chars.len();
    let is_ifs = |c: char| ifs.contains(c);
    let is_space = |c: char| ifs.contains(c) && is_ifs_space(c);
    while index < len && chars.get(index).is_some_and(|c| is_space(*c)) {
        index = index.saturating_add(1);
    }
    while index < len {
        if max > 0 && fields.len().saturating_add(1) == max {
            let mut rest: String = chars.get(index..).unwrap_or_default().iter().collect();
            // Trailing IFS whitespace goes; one trailing non-space delimiter goes too.
            let trimmed: String = rest.trim_end_matches(|c: char| is_space(c)).to_owned();
            rest = trimmed;
            let mut tail: Vec<char> = rest.chars().collect();
            if let Some(last) = tail.last().copied()
                && is_ifs(last)
                && !is_space(last)
            {
                let before = tail.len().checked_sub(2).and_then(|i| tail.get(i)).copied();
                if before.is_none_or(|b| !is_ifs(b) || is_space(b)) {
                    tail.pop();
                    while tail.last().is_some_and(|c| is_space(*c)) {
                        tail.pop();
                    }
                }
            }
            fields.push(tail.into_iter().collect());
            return fields;
        }
        let mut field = String::new();
        while index < len {
            let Some(&ch) = chars.get(index) else { break };
            if is_ifs(ch) {
                break;
            }
            field.push(ch);
            index = index.saturating_add(1);
        }
        fields.push(field);
        // Skip one delimiter: spaces around at most one non-space IFS character.
        while index < len && chars.get(index).is_some_and(|c| is_space(*c)) {
            index = index.saturating_add(1);
        }
        if index < len
            && chars
                .get(index)
                .is_some_and(|c| is_ifs(*c) && !is_space(*c))
        {
            index = index.saturating_add(1);
            while index < len && chars.get(index).is_some_and(|c| is_space(*c)) {
                index = index.saturating_add(1);
            }
        }
    }
    fields
}

// ---------------------------------------------------------------------------
// Parameter expansion
// ---------------------------------------------------------------------------

/// A parameter's value before its operator applies.
#[derive(Clone, Debug)]
enum Got {
    Unset,
    Scalar(String),
    /// Elements of `$@`, `$*`, `a[@]` or `a[*]`: the elements, and whether it was `@`.
    List(Vec<String>, bool),
}

impl Got {
    fn is_unset(&self) -> bool {
        match self {
            Got::Unset => true,
            Got::List(items, _) => items.is_empty(),
            Got::Scalar(_) => false,
        }
    }

    fn is_null(&self, sh: &Shell) -> bool {
        match self {
            Got::Unset => true,
            Got::Scalar(text) => text.is_empty(),
            Got::List(items, _) => join_star(sh, items).is_empty(),
        }
    }
}

fn join_star(sh: &Shell, items: &[String]) -> String {
    let separator = match sh.ifs() {
        None => " ".to_owned(),
        Some(ifs) => ifs.chars().next().map(String::from).unwrap_or_default(),
    };
    let separator = if sh.vars.get("IFS").is_none() {
        " ".to_owned()
    } else {
        separator
    };
    items.join(&separator)
}

fn expand_param<'p, 'b>(
    ctx: &'b Ctx<'_>,
    sh: &'b mut Shell,
    expansion: &'p ParamExp,
    quoted: bool,
) -> Boxed<'b, Vec<Field>>
where
    'p: 'b,
{
    Box::pin(async move {
        let kind = if quoted { Kind::Quoted } else { Kind::Expanded };
        let name = param_name(&expansion.param);
        match &expansion.op {
            ParamOp::Invalid(text) => {
                sh.error_text(&format!(
                    "bash: line {}: {}: bad substitution\n",
                    sh.lineno, text
                ))
                .await?;
                return Err(Flow::CommandFailed(1));
            }
            ParamOp::PrefixNames(at) => {
                let prefix = match &expansion.param {
                    Param::Named(name) => name.clone(),
                    _ => String::new(),
                };
                let names: Vec<String> = sh
                    .vars
                    .names()
                    .into_iter()
                    .filter(|n| {
                        n.starts_with(&prefix) && sh.vars.get(n).is_some_and(|v| v.value.is_some())
                    })
                    .collect();
                return Ok(list_fields(sh, names, *at, quoted));
            }
            ParamOp::Keys(at) => {
                let keys = match &expansion.param {
                    Param::Named(name) => array_keys(sh, name),
                    _ => Vec::new(),
                };
                return Ok(list_fields(sh, keys, *at, quoted));
            }
            _ => {}
        }
        if matches!(&expansion.param, Param::Named(name) if name.is_empty()) {
            sh.error_text(&format!(
                "bash: line {}: ${{}}: bad substitution\n",
                sh.lineno
            ))
            .await?;
            return Err(Flow::CommandFailed(1));
        }
        // `${!ref}` where `ref` is a nameref names its target.
        if expansion.indirect
            && matches!(expansion.op, ParamOp::Plain)
            && let Param::Named(name) = &expansion.param
            && let Some(var) = sh.vars.get(name).filter(|v| v.has(vars::NAMEREF))
        {
            let target = match &var.value {
                Some(Value::Scalar(text)) => text.clone(),
                _ => String::new(),
            };
            return Ok(vec![one(target, kind)]);
        }
        let mut got = lookup(ctx, sh, &expansion.param).await?;
        if expansion.indirect {
            let target = match &got {
                Got::Scalar(text) => text.clone(),
                Got::List(items, _) => join_star(sh, items),
                Got::Unset => {
                    if sh.options.nounset {
                        return unbound(sh, &name).await;
                    }
                    sh.error_text(&format!(
                        "bash: line {}: {}: invalid indirect expansion\n",
                        sh.lineno, name
                    ))
                    .await?;
                    return Err(Flow::Discard(1));
                }
            };
            if target.is_empty() && got.is_unset() {
                got = Got::Unset;
            } else {
                let Some(param) = parse_param_ref(&target) else {
                    sh.error_text(&format!(
                        "bash: line {}: {}: invalid variable name\n",
                        sh.lineno, target
                    ))
                    .await?;
                    return Err(Flow::Discard(1));
                };
                got = lookup_owned(ctx, sh, &param).await?;
            }
        }
        if sh.options.nounset && got.is_unset() && !matches!(expansion.op, ParamOp::Default { .. })
        {
            let list_ok = matches!(&expansion.param, Param::Special('@' | '*'))
                || matches!(&expansion.param, Param::Element(_, sub) if matches!(sub.as_literal(), Some("@" | "*")));
            if !list_ok || matches!(&got, Got::Unset) && !list_ok {
                return unbound(sh, &name).await;
            }
        }
        match &expansion.op {
            ParamOp::Plain => Ok(got_fields(sh, got, quoted)),
            ParamOp::Length => {
                let length = match &expansion.param {
                    Param::Special('@' | '*') => sh.positional.len(),
                    Param::Element(_, sub) if matches!(sub.as_literal(), Some("@" | "*")) => {
                        match &got {
                            Got::List(items, _) => items.len(),
                            _ => 0,
                        }
                    }
                    _ => match &got {
                        Got::Scalar(text) => text.chars().count(),
                        Got::List(items, _) => items.len(),
                        Got::Unset => 0,
                    },
                };
                Ok(vec![one(length.to_string(), kind)])
            }
            ParamOp::Default {
                colon,
                kind: which,
                word,
            } => {
                let absent = if *colon {
                    got.is_null(sh)
                } else {
                    got.is_unset()
                };
                match which {
                    DefaultKind::Use => {
                        if absent {
                            default_word(ctx, sh, word, quoted).await
                        } else {
                            Ok(got_fields(sh, got, quoted))
                        }
                    }
                    DefaultKind::Alternative => {
                        if absent {
                            Ok(if quoted {
                                vec![Field {
                                    pieces: Vec::new(),
                                    keep: true,
                                }]
                            } else {
                                Vec::new()
                            })
                        } else {
                            default_word(ctx, sh, word, quoted).await
                        }
                    }
                    DefaultKind::Assign => {
                        if !absent {
                            return Ok(got_fields(sh, got, quoted));
                        }
                        let value = expand_single(ctx, sh, word, Mode::Single).await?;
                        match &expansion.param {
                            Param::Named(var) => {
                                super::exec::assign_scalar(sh, var, value.clone(), false).await?;
                            }
                            Param::Element(var, sub) => {
                                let index = super::exec::subscript(ctx, sh, var, sub).await?;
                                super::exec::assign_element(sh, var, index, value.clone(), false)
                                    .await?;
                            }
                            _ => {
                                sh.error_text(&format!(
                                    "bash: line {}: ${}: cannot assign in this way\n",
                                    sh.lineno, name
                                ))
                                .await?;
                                return Err(Flow::Discard(1));
                            }
                        }
                        Ok(vec![one(value, kind)])
                    }
                    DefaultKind::Error => {
                        if !absent {
                            return Ok(got_fields(sh, got, quoted));
                        }
                        let message = expand_single(ctx, sh, word, Mode::Single).await?;
                        let message = if message.is_empty() {
                            if *colon {
                                "parameter null or not set".to_owned()
                            } else {
                                "parameter not set".to_owned()
                            }
                        } else {
                            message
                        };
                        sh.error_text(&format!(
                            "bash: line {}: {}: {}\n",
                            sh.lineno, name, message
                        ))
                        .await?;
                        Err(Flow::ExpansionExit)
                    }
                }
            }
            ParamOp::RemovePrefix { longest, pattern }
            | ParamOp::RemoveSuffix { longest, pattern } => {
                let prefix = matches!(expansion.op, ParamOp::RemovePrefix { .. });
                let compiled = compile_pattern(ctx, sh, pattern).await?;
                let options = MatchOptions::default();
                Ok(map_got(sh, got, quoted, |text| {
                    remove_match(text, &compiled, prefix, *longest, options)
                }))
            }
            ParamOp::Substring { offset, length } => {
                let offset_text = expand_single(ctx, sh, offset, Mode::Single).await?;
                let offset_value = eval_arith(ctx, sh, &offset_text).await?;
                let length_value = match length {
                    Some(word) => {
                        let text = expand_single(ctx, sh, word, Mode::Single).await?;
                        Some(eval_arith(ctx, sh, &text).await?)
                    }
                    None => None,
                };
                substring(
                    ctx,
                    sh,
                    &expansion.param,
                    got,
                    offset_value,
                    length_value,
                    quoted,
                )
                .await
            }
            ParamOp::Replace {
                kind: which,
                pattern,
                replacement,
            } => {
                let compiled = compile_pattern(ctx, sh, pattern).await?;
                let replacement = match replacement {
                    Some(word) => expand_pattern(ctx, sh, word).await?,
                    None => Vec::new(),
                };
                let ampersand = sh.options.shopt("patsub_replacement");
                let empty_pattern = pattern.parts.is_empty();
                Ok(map_got(sh, got, quoted, |text| {
                    if empty_pattern && matches!(which, ReplaceKind::First | ReplaceKind::All) {
                        return text.to_owned();
                    }
                    replace(text, &compiled, *which, &replacement, ampersand)
                }))
            }
            ParamOp::Case {
                upper,
                all,
                toggle,
                pattern,
            } => {
                let compiled = match pattern {
                    Some(word) => Some(compile_pattern(ctx, sh, word).await?),
                    None => None,
                };
                Ok(map_got(sh, got, quoted, |text| {
                    change_case(text, *upper, *all, *toggle, compiled.as_ref())
                }))
            }
            ParamOp::Transform(op) => transform(ctx, sh, &expansion.param, got, *op, quoted).await,
            ParamOp::PrefixNames(_) | ParamOp::Keys(_) | ParamOp::Invalid(_) => Ok(Vec::new()),
        }
    })
}

/// The word of `${x:-word}` or `${x:+word}`: unquoted, its literal text splits as an expansion's does.
async fn default_word(
    ctx: &Ctx<'_>,
    sh: &mut Shell,
    word: &Word,
    quoted: bool,
) -> Result<Vec<Field>, Flow> {
    let saved = std::mem::replace(&mut sh.literal_splits, !quoted && !sh.single_word);
    let fields = expand_parts(ctx, sh, &word.parts, quoted, !quoted).await;
    sh.literal_splits = saved;
    fields
}

async fn unbound<T>(sh: &mut Shell, name: &str) -> Result<T, Flow> {
    sh.error_text(&format!(
        "bash: line {}: {}: unbound variable\n",
        sh.lineno, name
    ))
    .await?;
    Err(Flow::ExpansionExit)
}

fn one(text: String, kind: Kind) -> Field {
    Field {
        keep: kind == Kind::Quoted,
        pieces: vec![Piece { text, kind }],
    }
}

fn list_fields(sh: &Shell, items: Vec<String>, at: bool, quoted: bool) -> Vec<Field> {
    got_fields(sh, Got::List(items, at), quoted)
}

fn got_fields(sh: &Shell, got: Got, quoted: bool) -> Vec<Field> {
    let kind = if quoted { Kind::Quoted } else { Kind::Expanded };
    match got {
        Got::Unset => vec![Field {
            pieces: Vec::new(),
            keep: false,
        }],
        Got::Scalar(text) => vec![one(text, kind)],
        Got::List(items, at) => {
            if (quoted || sh.single_word) && !at {
                return vec![one(join_star(sh, &items), kind)];
            }
            if items.is_empty() {
                return vec![Field {
                    pieces: Vec::new(),
                    keep: false,
                }];
            }
            items.into_iter().map(|item| one(item, kind)).collect()
        }
    }
}

fn map_got(sh: &Shell, got: Got, quoted: bool, f: impl Fn(&str) -> String) -> Vec<Field> {
    let mapped = match got {
        Got::Unset => Got::Unset,
        Got::Scalar(text) => Got::Scalar(f(&text)),
        Got::List(items, at) => Got::List(items.iter().map(|item| f(item)).collect(), at),
    };
    got_fields(sh, mapped, quoted)
}

fn param_name(param: &Param) -> String {
    match param {
        Param::Named(name) => name.clone(),
        Param::Positional(n) => n.to_string(),
        Param::Special(c) => c.to_string(),
        Param::Element(name, sub) => format!("{}[{}]", name, sub.static_text().unwrap_or_default()),
    }
}

/// Parse an indirect reference: `name`, `name[sub]`, a number or a special.
fn parse_param_ref(text: &str) -> Option<Param> {
    if is_name(text) {
        return Some(Param::Named(text.to_owned()));
    }
    if let Ok(number) = text.parse::<u32>() {
        return Some(if number == 0 {
            Param::Special('0')
        } else {
            Param::Positional(number)
        });
    }
    if let [c] = text.chars().collect::<Vec<char>>().as_slice()
        && "@*#?-$!".contains(*c)
    {
        return Some(Param::Special(*c));
    }
    let open = text.find('[')?;
    let name = text.get(..open)?;
    let sub = text.get(open.saturating_add(1)..)?.strip_suffix(']')?;
    if !is_name(name) {
        return None;
    }
    let word = Word {
        parts: vec![WordPart::Literal(sub.to_owned())],
        span: Default::default(),
    };
    Some(Param::Element(name.to_owned(), Box::new(word)))
}

async fn lookup_owned(ctx: &Ctx<'_>, sh: &mut Shell, param: &Param) -> Result<Got, Flow> {
    match param {
        Param::Element(name, sub) => {
            let name = name.clone();
            let text = sub.static_text().unwrap_or_default();
            if text == "@" || text == "*" {
                return Ok(Got::List(array_values(sh, &name), text == "@"));
            }
            element_by_text(ctx, sh, &name, &text).await
        }
        other => lookup_simple(sh, other),
    }
}

async fn lookup(ctx: &Ctx<'_>, sh: &mut Shell, param: &Param) -> Result<Got, Flow> {
    match param {
        Param::Element(name, sub) => {
            let name = super::exec::resolve_nameref(sh, name);
            if let Some(text) = sub.as_literal()
                && (text == "@" || text == "*")
            {
                if !sh.vars.get(&name).is_some_and(|v| v.value.is_some()) {
                    return Ok(Got::List(Vec::new(), text == "@"));
                }
                return Ok(Got::List(array_values(sh, &name), text == "@"));
            }
            let index = super::exec::subscript(ctx, sh, &name, sub).await?;
            Ok(element(sh, &name, &index))
        }
        other => lookup_simple(sh, other),
    }
}

async fn element_by_text(
    ctx: &Ctx<'_>,
    sh: &mut Shell,
    name: &str,
    text: &str,
) -> Result<Got, Flow> {
    let is_assoc = sh.vars.get(name).is_some_and(vars::Var::is_assoc);
    let index = if is_assoc {
        super::exec::Index::Key(text.to_owned())
    } else {
        super::exec::Index::Number(eval_arith(ctx, sh, text).await?)
    };
    Ok(element(sh, name, &index))
}

fn element(sh: &Shell, name: &str, index: &super::exec::Index) -> Got {
    let Some(var) = sh.vars.get(name) else {
        return Got::Unset;
    };
    match (&var.value, index) {
        (Some(Value::Indexed(map)), super::exec::Index::Number(n)) => {
            let key = if *n < 0 {
                let last = map.keys().next_back().copied().unwrap_or(-1);
                last.saturating_add(1).saturating_add(*n)
            } else {
                *n
            };
            map.get(&key).map_or(Got::Unset, |v| Got::Scalar(v.clone()))
        }
        (Some(Value::Assoc(map)), super::exec::Index::Key(key)) => {
            map.get(key).map_or(Got::Unset, |v| Got::Scalar(v.clone()))
        }
        (Some(Value::Assoc(map)), super::exec::Index::Number(n)) => map
            .get(&n.to_string())
            .map_or(Got::Unset, |v| Got::Scalar(v.clone())),
        (Some(Value::Scalar(text)), super::exec::Index::Number(0 | -1)) => {
            Got::Scalar(text.clone())
        }
        _ => Got::Unset,
    }
}

pub fn array_values(sh: &Shell, name: &str) -> Vec<String> {
    match sh.vars.get(name).and_then(|var| var.value.as_ref()) {
        Some(Value::Indexed(map)) => map.values().cloned().collect(),
        Some(Value::Assoc(map)) => map.iter().map(|(_, v)| v.clone()).collect(),
        Some(Value::Scalar(text)) => vec![text.clone()],
        None => Vec::new(),
    }
}

pub fn array_keys(sh: &Shell, name: &str) -> Vec<String> {
    match sh.vars.get(name).and_then(|var| var.value.as_ref()) {
        Some(Value::Indexed(map)) => map.keys().map(i64::to_string).collect(),
        Some(Value::Assoc(map)) => map.iter().map(|(k, _)| k.clone()).collect(),
        Some(Value::Scalar(_)) => vec!["0".to_owned()],
        None => Vec::new(),
    }
}

fn lookup_simple(sh: &Shell, param: &Param) -> Result<Got, Flow> {
    Ok(match param {
        Param::Named(name) => {
            let name = super::exec::resolve_nameref(sh, name);
            match special_var(sh, &name) {
                Some(value) => Got::Scalar(value),
                None => sh.get_var(&name).map_or(Got::Unset, Got::Scalar),
            }
        }
        Param::Positional(n) => {
            let index = usize::try_from(*n).unwrap_or(usize::MAX).saturating_sub(1);
            sh.positional
                .get(index)
                .map_or(Got::Unset, |v| Got::Scalar(v.clone()))
        }
        Param::Special(c) => match c {
            '@' => Got::List(sh.positional.clone(), true),
            '*' => Got::List(sh.positional.clone(), false),
            '#' => Got::Scalar(sh.positional.len().to_string()),
            '?' => Got::Scalar(sh.last_status.to_string()),
            '-' => Got::Scalar(sh.options.flags()),
            '$' => Got::Scalar(sh.pid.to_string()),
            '!' => sh
                .last_job_pid
                .map_or(Got::Unset, |pid| Got::Scalar(pid.to_string())),
            '0' => Got::Scalar(sh.arg0.clone()),
            _ => Got::Unset,
        },
        Param::Element(..) => Got::Unset,
    })
}

/// The shell's own dynamic variables.
fn special_var(sh: &Shell, name: &str) -> Option<String> {
    match name {
        "LINENO" => Some(sh.lineno.to_string()),
        "BASHPID" => Some(sh.bash_pid.to_string()),
        "FUNCNAME" => {
            if sh.frames.is_empty() {
                return None;
            }
            sh.frames.last().map(|(name, _)| name.clone())
        }
        "BASH_SUBSHELL" => Some(sh.subshell.to_string()),
        "SHELLOPTS" => Some(shellopts(sh)),
        "BASHOPTS" => Some(bashopts(sh)),
        _ => None,
    }
}

pub fn shellopts(sh: &Shell) -> String {
    super::shell::Options::set_names()
        .iter()
        .filter(|name| sh.options.get_set_option(name).unwrap_or(false))
        .copied()
        .collect::<Vec<&str>>()
        .join(":")
}

pub fn bashopts(sh: &Shell) -> String {
    sh.options
        .shopt
        .iter()
        .filter(|(_, on)| **on)
        .map(|(name, _)| *name)
        .collect::<Vec<&str>>()
        .join(":")
}

// -- operators ---------------------------------------------------------------

fn remove_match(
    text: &str,
    pattern: &Pattern,
    prefix: bool,
    longest: bool,
    options: MatchOptions,
) -> String {
    let chars: Vec<char> = text.chars().collect();
    let len = chars.len();
    let lengths: Vec<usize> = if longest {
        (0..=len).rev().collect()
    } else {
        (0..=len).collect()
    };
    for cut in lengths {
        let (piece, rest) = if prefix {
            (
                chars.get(..cut).unwrap_or_default(),
                chars.get(cut..).unwrap_or_default(),
            )
        } else {
            let from = len.saturating_sub(cut);
            (
                chars.get(from..).unwrap_or_default(),
                chars.get(..from).unwrap_or_default(),
            )
        };
        if pattern.matches_chars(piece, options) {
            return rest.iter().collect();
        }
    }
    text.to_owned()
}

fn replace(
    text: &str,
    pattern: &Pattern,
    which: ReplaceKind,
    replacement: &[PatChar],
    ampersand: bool,
) -> String {
    let chars: Vec<char> = text.chars().collect();
    let len = chars.len();
    let options = MatchOptions::default();
    let render = |matched: &[char]| -> String {
        let mut out = String::new();
        let mut index = 0;
        while let Some(&(ch, quoted)) = replacement.get(index) {
            if ch == '\\' && !quoted {
                if let Some(&(next, _)) = replacement.get(index.saturating_add(1))
                    && (next == '&' || next == '\\')
                {
                    out.push(next);
                    index = index.saturating_add(2);
                    continue;
                }
                out.push('\\');
            } else if ch == '&' && !quoted && ampersand {
                out.extend(matched.iter());
            } else {
                out.push(ch);
            }
            index = index.saturating_add(1);
        }
        out
    };
    match which {
        ReplaceKind::Prefix => {
            for cut in (0..=len).rev() {
                let piece = chars.get(..cut).unwrap_or_default();
                if pattern.matches_chars(piece, options) {
                    let mut out = render(piece);
                    out.extend(chars.get(cut..).unwrap_or_default());
                    return out;
                }
            }
            text.to_owned()
        }
        ReplaceKind::Suffix => {
            for from in 0..=len {
                let piece = chars.get(from..).unwrap_or_default();
                if pattern.matches_chars(piece, options) {
                    let mut out: String = chars.get(..from).unwrap_or_default().iter().collect();
                    out.push_str(&render(piece));
                    return out;
                }
            }
            text.to_owned()
        }
        ReplaceKind::First | ReplaceKind::All => {
            let mut out = String::new();
            let mut start = 0;
            let mut replaced = false;
            while start <= len {
                if replaced && which == ReplaceKind::First {
                    break;
                }
                let mut found = None;
                for end in (start..=len).rev() {
                    let piece = chars.get(start..end).unwrap_or_default();
                    if pattern.matches_chars(piece, options) {
                        found = Some(end);
                        break;
                    }
                }
                match found {
                    Some(end) if end > start => {
                        out.push_str(&render(chars.get(start..end).unwrap_or_default()));
                        start = end;
                        replaced = true;
                    }
                    Some(end) => {
                        // An empty match replaces nothing and moves on.
                        let _ = end;
                        if let Some(ch) = chars.get(start) {
                            out.push(*ch);
                        }
                        start = start.saturating_add(1);
                    }
                    None => {
                        if let Some(ch) = chars.get(start) {
                            out.push(*ch);
                        }
                        start = start.saturating_add(1);
                    }
                }
            }
            if start < len {
                out.extend(chars.get(start..).unwrap_or_default());
            }
            out
        }
    }
}

fn change_case(
    text: &str,
    upper: bool,
    all: bool,
    toggle: bool,
    pattern: Option<&Pattern>,
) -> String {
    let mut out = String::new();
    for (index, ch) in text.chars().enumerate() {
        let eligible = (all || index == 0)
            && pattern.is_none_or(|p| p.matches(&ch.to_string(), MatchOptions::default()));
        if !eligible {
            out.push(ch);
            continue;
        }
        if toggle {
            if ch.is_uppercase() {
                out.extend(ch.to_lowercase());
            } else {
                out.extend(ch.to_uppercase());
            }
        } else if upper {
            out.extend(ch.to_uppercase());
        } else {
            out.extend(ch.to_lowercase());
        }
    }
    out
}

async fn substring(
    _ctx: &Ctx<'_>,
    sh: &mut Shell,
    param: &Param,
    got: Got,
    offset: i64,
    length: Option<i64>,
    quoted: bool,
) -> Result<Vec<Field>, Flow> {
    match got {
        Got::Unset => Ok(got_fields(sh, Got::Unset, quoted)),
        Got::Scalar(text) => {
            let chars: Vec<char> = text.chars().collect();
            let len = i64::try_from(chars.len()).unwrap_or(i64::MAX);
            let start = if offset < 0 {
                len.saturating_add(offset)
            } else {
                offset
            };
            if start < 0 || start > len {
                return Ok(got_fields(sh, Got::Scalar(String::new()), quoted));
            }
            let end = match length {
                None => len,
                Some(n) if n < 0 => {
                    let end = len.saturating_add(n);
                    if end < start {
                        sh.error_text(&format!(
                            "bash: line {}: {}: substring expression < 0\n",
                            sh.lineno, n
                        ))
                        .await?;
                        return Err(Flow::Discard(1));
                    }
                    end
                }
                Some(n) => start.saturating_add(n).min(len),
            };
            let from = usize::try_from(start).unwrap_or(0);
            let to = usize::try_from(end).unwrap_or(0);
            let piece: String = chars
                .get(from..to.max(from))
                .unwrap_or_default()
                .iter()
                .collect();
            Ok(got_fields(sh, Got::Scalar(piece), quoted))
        }
        Got::List(items, at) => {
            let positional = matches!(param, Param::Special('@' | '*'));
            // For `$@`, index 0 is `$0`; for arrays, offsets count indices.
            let entries: Vec<(i64, String)> = if positional {
                std::iter::once((0, sh.arg0.clone()))
                    .chain(
                        items
                            .into_iter()
                            .enumerate()
                            .map(|(i, v)| (i64::try_from(i).unwrap_or(0).saturating_add(1), v)),
                    )
                    .collect()
            } else if let Param::Element(name, _) = param {
                match sh.vars.get(name).and_then(|v| v.value.as_ref()) {
                    Some(Value::Indexed(map)) => map.iter().map(|(k, v)| (*k, v.clone())).collect(),
                    _ => items
                        .into_iter()
                        .enumerate()
                        .map(|(i, v)| (i64::try_from(i).unwrap_or(0), v))
                        .collect(),
                }
            } else {
                items
                    .into_iter()
                    .enumerate()
                    .map(|(i, v)| (i64::try_from(i).unwrap_or(0), v))
                    .collect()
            };
            let top = entries.last().map_or(0, |(k, _)| k.saturating_add(1));
            let start = if offset < 0 {
                top.saturating_add(offset)
            } else {
                offset
            };
            if offset < 0 && start < 0 {
                return Ok(got_fields(sh, Got::List(Vec::new(), at), quoted));
            }
            if let Some(n) = length
                && n < 0
            {
                sh.error_text(&format!(
                    "bash: line {}: {}: substring expression < 0\n",
                    sh.lineno, n
                ))
                .await?;
                return Err(Flow::Discard(1));
            }
            let mut selected: Vec<String> = entries
                .into_iter()
                .filter(|(k, _)| *k >= start)
                .map(|(_, v)| v)
                .collect();
            if let Some(n) = length {
                selected.truncate(usize::try_from(n).unwrap_or(0));
            }
            Ok(got_fields(sh, Got::List(selected, at), quoted))
        }
    }
}

async fn transform(
    ctx: &Ctx<'_>,
    sh: &mut Shell,
    param: &Param,
    got: Got,
    op: char,
    quoted: bool,
) -> Result<Vec<Field>, Flow> {
    let _ = ctx;
    let name = match param {
        Param::Named(name) | Param::Element(name, _) => name.clone(),
        _ => String::new(),
    };
    match op {
        'Q' => Ok(map_got(sh, got, quoted, quote::single)),
        'E' => Ok(map_got(sh, got, quoted, quote::ansi_decode)),
        'P' => Ok(map_got(sh, got, quoted, str::to_owned)),
        'U' => Ok(map_got(sh, got, quoted, |text| text.to_uppercase())),
        'u' => Ok(map_got(sh, got, quoted, |text| {
            change_case(text, true, false, false, None)
        })),
        'L' => Ok(map_got(sh, got, quoted, |text| text.to_lowercase())),
        'a' => {
            let attrs = sh
                .vars
                .get(&name)
                .map(quote::attr_letters)
                .unwrap_or_default();
            let items = match &got {
                Got::List(items, at) => {
                    Got::List(items.iter().map(|_| attrs.clone()).collect(), *at)
                }
                _ => Got::Scalar(attrs),
            };
            Ok(got_fields(sh, items, quoted))
        }
        'A' => {
            if got.is_unset() {
                return Ok(got_fields(sh, Got::Unset, quoted));
            }
            let whole = matches!(param, Param::Element(_, sub) if matches!(sub.as_literal(), Some("@" | "*")));
            if whole && let Some(var) = sh.vars.get(&name) {
                let text = quote::declaration(&name, var);
                return Ok(vec![one(
                    text,
                    if quoted { Kind::Quoted } else { Kind::Expanded },
                )]);
            }
            let text = match sh.vars.get(&name) {
                Some(var) if !name.is_empty() => {
                    let flags = quote::attr_letters(var);
                    let value = match &got {
                        Got::Scalar(text) => text.clone(),
                        Got::List(items, _) => items.first().cloned().unwrap_or_default(),
                        Got::Unset => String::new(),
                    };
                    if flags.is_empty() {
                        format!("{}={}", name, quote::single(&value))
                    } else {
                        format!("declare -{} {}={}", flags, name, quote::single(&value))
                    }
                }
                _ => match &got {
                    Got::Scalar(text) => quote::single(text),
                    _ => String::new(),
                },
            };
            Ok(vec![one(
                text,
                if quoted { Kind::Quoted } else { Kind::Expanded },
            )])
        }
        'K' | 'k' => {
            let pairs: Vec<(String, String)> =
                match sh.vars.get(&name).and_then(|v| v.value.as_ref()) {
                    Some(Value::Indexed(map)) => map
                        .iter()
                        .map(|(k, v)| (k.to_string(), v.clone()))
                        .collect(),
                    Some(Value::Assoc(map)) => {
                        map.iter().map(|(k, v)| (k.clone(), v.clone())).collect()
                    }
                    _ => {
                        return Ok(map_got(sh, got, quoted, quote::single));
                    }
                };
            let whole = matches!(param, Param::Element(_, sub) if matches!(sub.as_literal(), Some("@" | "*")));
            if !whole {
                return Ok(map_got(sh, got, quoted, quote::single));
            }
            let assoc = sh.vars.get(&name).is_some_and(vars::Var::is_assoc);
            let quote_key = |k: &str| {
                if assoc {
                    quote::assoc_key(k)
                } else {
                    k.to_owned()
                }
            };
            if op == 'K' {
                let mut words = Vec::new();
                for (k, v) in &pairs {
                    words.push(format!("{} {}", quote_key(k), quote::double(v)));
                }
                let mut text = words.join(" ");
                if assoc {
                    text.push(' ');
                }
                Ok(vec![one(
                    text,
                    if quoted { Kind::Quoted } else { Kind::Expanded },
                )])
            } else {
                let mut items = Vec::new();
                for (k, v) in pairs {
                    items.push(k);
                    items.push(v);
                }
                Ok(got_fields(sh, Got::List(items, true), quoted))
            }
        }
        _ => {
            if got.is_unset() {
                return Ok(Vec::new());
            }
            sh.error_text(&format!(
                "bash: line {}: ${{{}@{}}}: bad substitution\n",
                sh.lineno,
                param_name(param),
                op
            ))
            .await?;
            Err(Flow::ExpansionExit)
        }
    }
}

// ---------------------------------------------------------------------------
// Arithmetic
// ---------------------------------------------------------------------------

/// Evaluate arithmetic text; an error ends the rest of the line, as bash does.
pub async fn eval_arith(ctx: &Ctx<'_>, sh: &mut Shell, text: &str) -> Result<i64, Flow> {
    let _ = ctx;
    match arith::evaluate(sh, text) {
        Ok(value) => Ok(value),
        Err(ArithFailure::Error(message)) => {
            sh.error_text(&format!("bash: line {}: {}\n", sh.lineno, message))
                .await?;
            Err(Flow::Discard(1))
        }
        Err(ArithFailure::Flow(flow)) => Err(flow),
    }
}

// ---------------------------------------------------------------------------
// Pathname expansion
// ---------------------------------------------------------------------------

async fn glob(
    ctx: &Ctx<'_>,
    sh: &mut Shell,
    chars: &[PatChar],
) -> Result<Option<Vec<String>>, Flow> {
    let _ = ctx;
    let text: String = chars.iter().map(|(c, _)| *c).collect();
    let absolute = text.starts_with('/');
    // Split into components on unquoted and quoted slashes alike.
    let mut components: Vec<Vec<PatChar>> = vec![Vec::new()];
    for &(ch, quoted) in chars {
        if ch == '/' {
            components.push(Vec::new());
        } else if let Some(last) = components.last_mut() {
            last.push((ch, quoted));
        }
    }
    let extglob = sh.options.shopt("extglob");
    let options = MatchOptions {
        nocase: sh.options.shopt("nocaseglob"),
        path: true,
        dotglob: sh.options.shopt("dotglob") || sh.has_var("GLOBIGNORE"),
    };
    let globstar = sh.options.shopt("globstar");
    // Each candidate is (display path, absolute path, whether it must be a directory).
    let base_abs = if absolute {
        "/".to_owned()
    } else {
        sh.cwd.clone()
    };
    let mut candidates: Vec<(String, String)> = vec![(
        if absolute {
            "/".to_owned()
        } else {
            String::new()
        },
        base_abs,
    )];
    let mut visits = 0usize;
    let last_index = components.len().saturating_sub(1);
    for (index, component) in components.iter().enumerate() {
        if index == 0 && absolute {
            continue;
        }
        let is_last = index == last_index;
        if component.is_empty() {
            // A trailing slash: keep only directories.
            if is_last {
                let mut kept = Vec::new();
                for (shown, abs) in candidates {
                    if is_dir(sh, &abs).await? {
                        kept.push((format!("{shown}/"), abs));
                    }
                }
                candidates = kept;
            }
            continue;
        }
        let literal = !has_glob(component, extglob);
        let mut next = Vec::new();
        if literal {
            let name: String = component.iter().map(|(c, _)| *c).collect();
            for (shown, abs) in candidates {
                let shown = join_display(&shown, &name);
                let abs = join_abs(&abs, &name);
                if is_last {
                    if exists(sh, &abs).await? {
                        next.push((shown, abs));
                    }
                } else {
                    next.push((shown, abs));
                }
            }
            candidates = next;
            continue;
        }
        let star_star =
            globstar && component.len() == 2 && component.iter().all(|(c, q)| *c == '*' && !q);
        let pattern = Pattern::compile(component, extglob);
        let dot_pattern = component.first().is_some_and(|(c, _)| *c == '.');
        for (shown, abs) in candidates {
            if star_star {
                // `**` matches this directory and every directory below it, and files too when last.
                let mut stack = vec![(shown.clone(), abs.clone())];
                if !is_last {
                    next.push((shown.clone(), abs.clone()));
                }
                while let Some((dir_shown, dir_abs)) = stack.pop() {
                    let entries = list_dir(sh, &dir_abs).await?;
                    visits = visits.saturating_add(entries.len());
                    if visits > GLOB_VISITS {
                        return Err(Flow::Fatal(super::Fatal::Budget(
                            "glob_visits",
                            GLOB_VISITS as u64,
                        )));
                    }
                    let mut subdirs = Vec::new();
                    for entry in entries {
                        if entry.name.starts_with('.') && !options.dotglob {
                            continue;
                        }
                        let child_shown = join_display(&dir_shown, &entry.name);
                        let child_abs = join_abs(&dir_abs, &entry.name);
                        if entry.kind == EntryKind::Directory {
                            subdirs.push((child_shown.clone(), child_abs.clone()));
                            next.push((child_shown, child_abs));
                        } else if is_last {
                            next.push((child_shown, child_abs));
                        }
                    }
                    for subdir in subdirs.into_iter().rev() {
                        stack.push(subdir);
                    }
                }
                continue;
            }
            let entries = list_dir(sh, &abs).await?;
            visits = visits.saturating_add(entries.len());
            if visits > GLOB_VISITS {
                return Err(Flow::Fatal(super::Fatal::Budget(
                    "glob_visits",
                    GLOB_VISITS as u64,
                )));
            }
            let mut names: Vec<Entry> = entries;
            if dot_pattern || options.dotglob {
                let skip_dots =
                    sh.options.shopt("globskipdots") && !dot_pattern_explicit(component);
                if (!skip_dots || dot_pattern) && !sh.options.shopt("globskipdots") {
                    names.push(Entry {
                        name: ".".to_owned(),
                        kind: EntryKind::Directory,
                    });
                    names.push(Entry {
                        name: "..".to_owned(),
                        kind: EntryKind::Directory,
                    });
                }
            }
            for entry in names {
                if !is_last && entry.kind != EntryKind::Directory {
                    continue;
                }
                let matches = if entry.name.starts_with('.') && !options.dotglob && !dot_pattern {
                    false
                } else {
                    pattern.matches(&entry.name, options)
                };
                if matches {
                    next.push((
                        join_display(&shown, &entry.name),
                        join_abs(&abs, &entry.name),
                    ));
                }
            }
        }
        candidates = next;
    }
    let mut results: Vec<String> = candidates.into_iter().map(|(shown, _)| shown).collect();
    if let Some(ignore) = sh.get_var("GLOBIGNORE") {
        let patterns: Vec<Pattern> = ignore
            .split(':')
            .filter(|p| !p.is_empty())
            .map(|p| Pattern::compile(&p.chars().map(|c| (c, false)).collect::<Vec<_>>(), extglob))
            .collect();
        results.retain(|path| {
            let base = path.rsplit('/').next().unwrap_or(path);
            base != "."
                && base != ".."
                && !patterns
                    .iter()
                    .any(|p| p.matches(path, MatchOptions::default()))
        });
    }
    if results.is_empty() {
        return Ok(None);
    }
    results.sort_by(|a, b| glob_order(a, b));
    results.dedup();
    Ok(Some(results))
}

fn dot_pattern_explicit(component: &[PatChar]) -> bool {
    component.first().is_some_and(|(c, _)| *c == '.')
}

/// Bash sorts glob results by the locale's collation; under C.UTF-8 that is code point order.
fn glob_order(a: &str, b: &str) -> std::cmp::Ordering {
    a.cmp(b)
}

fn join_display(base: &str, name: &str) -> String {
    if base.is_empty() {
        name.to_owned()
    } else if base.ends_with('/') {
        format!("{base}{name}")
    } else {
        format!("{base}/{name}")
    }
}

pub fn join_abs(base: &str, name: &str) -> String {
    if base.ends_with('/') {
        format!("{base}{name}")
    } else {
        format!("{base}/{name}")
    }
}

async fn list_dir(sh: &mut Shell, path: &str) -> Result<Vec<Entry>, Flow> {
    let key = sh.key();
    let reply = io::host_call(
        &sh.hub,
        key,
        Request::List {
            path: path.to_owned(),
        },
    )
    .await?;
    Ok(match reply {
        Reply::Entries(entries) => entries,
        _ => Vec::new(),
    })
}

async fn is_dir(sh: &mut Shell, path: &str) -> Result<bool, Flow> {
    let key = sh.key();
    let reply = io::host_call(
        &sh.hub,
        key,
        Request::Stat {
            path: path.to_owned(),
        },
    )
    .await?;
    Ok(matches!(
        reply,
        Reply::Stat {
            kind: EntryKind::Directory,
            ..
        }
    ))
}

async fn exists(sh: &mut Shell, path: &str) -> Result<bool, Flow> {
    let key = sh.key();
    let reply = io::host_call(
        &sh.hub,
        key,
        Request::Stat {
            path: path.to_owned(),
        },
    )
    .await?;
    Ok(matches!(reply, Reply::Stat { .. }))
}
