//! POSIX extended regular expressions, for `[[ s =~ re ]]`. The match is
//! the leftmost one, and the longest from that start, as POSIX asks; the
//! search is a backtracking walk under a step budget, so no expression can
//! run unbounded.

use super::pattern::named_class;

/// Steps one match may take before it settles for what it has found.
const STEP_BUDGET: u64 = 2_000_000;
/// Nesting a regular expression may have.
const DEPTH: u32 = 100;
/// Frames one search may stack: each matched character of a repetition takes
/// one, so a match longer than this ends the search instead of the stack.
const SEARCH_DEPTH: u32 = 4_000;

#[derive(Clone, Debug)]
enum Re {
    Empty,
    Char(char),
    Any,
    Class(bool, Vec<Item>),
    Start,
    End,
    WordBoundary(bool),
    WordEdge(bool),
    Group(Box<Re>, usize),
    Concat(Vec<Re>),
    Alt(Vec<Re>),
    Repeat(Box<Re>, u32, Option<u32>),
}

#[derive(Clone, Debug)]
enum Item {
    Char(char),
    Range(char, char),
    Named(String),
}

pub struct Regex {
    re: Re,
    groups: usize,
    nocase: bool,
}

impl Regex {
    /// How many groups the expression has, not counting the whole match.
    pub fn groups(&self) -> usize {
        self.groups
    }
}

/// The groups of a match: each a character range of the text, if it took part.
pub type Captures = Vec<Option<(usize, usize)>>;

impl Regex {
    pub fn new(pattern: &str, nocase: bool) -> Result<Regex, String> {
        let chars: Vec<char> = pattern.chars().collect();
        let mut parser = Parser {
            chars: &chars,
            pos: 0,
            groups: 0,
            depth: 0,
        };
        let re = parser.alternation()?;
        if parser.pos < chars.len() {
            return Err("unmatched ( or \\(".to_owned());
        }
        Ok(Regex {
            re,
            groups: parser.groups,
            nocase,
        })
    }

    /// The first match: the whole match and each group, as character ranges.
    pub fn find(&self, text: &str) -> Option<(Vec<char>, Captures)> {
        let chars: Vec<char> = text.chars().collect();
        let captures = self.find_at(&chars, 0)?;
        Some((chars, captures))
    }

    /// The first match that starts at or after `from`, in `chars`: group 0 is the whole match.
    pub fn find_at(&self, chars: &[char], from: usize) -> Option<Captures> {
        let mut steps = 0u64;
        for start in from..=chars.len() {
            let mut search = Search {
                text: chars,
                nocase: self.nocase,
                steps,
                depth: 0,
                best: None,
            };
            let mut caps = vec![None; self.groups.saturating_add(1)];
            search.walk(&self.re, start, &Cont::Done, &mut caps);
            steps = search.steps;
            if let Some((end, mut caps)) = search.best {
                if let Some(first) = caps.first_mut() {
                    *first = Some((start, end));
                }
                return Some(caps);
            }
            if steps > STEP_BUDGET {
                return None;
            }
        }
        None
    }
}

struct Parser<'a> {
    chars: &'a [char],
    pos: usize,
    groups: usize,
    depth: u32,
}

impl Parser<'_> {
    fn peek(&self) -> Option<char> {
        self.chars.get(self.pos).copied()
    }

    fn bump(&mut self) {
        self.pos = self.pos.saturating_add(1);
    }

    fn alternation(&mut self) -> Result<Re, String> {
        self.depth = self.depth.saturating_add(1);
        if self.depth > DEPTH {
            return Err("regular expression too big".to_owned());
        }
        let mut alternatives = vec![self.concat()?];
        while self.peek() == Some('|') {
            self.bump();
            alternatives.push(self.concat()?);
        }
        self.depth = self.depth.saturating_sub(1);
        Ok(if alternatives.len() == 1 {
            alternatives.pop().unwrap_or(Re::Empty)
        } else {
            Re::Alt(alternatives)
        })
    }

    fn concat(&mut self) -> Result<Re, String> {
        let mut items = Vec::new();
        while let Some(ch) = self.peek() {
            if ch == '|' || ch == ')' {
                break;
            }
            let atom = self.atom()?;
            let atom = self.quantified(atom)?;
            items.push(atom);
        }
        Ok(Re::Concat(items))
    }

    fn quantified(&mut self, mut atom: Re) -> Result<Re, String> {
        loop {
            match self.peek() {
                Some('*') => {
                    self.bump();
                    atom = Re::Repeat(Box::new(atom), 0, None);
                }
                Some('+') => {
                    self.bump();
                    atom = Re::Repeat(Box::new(atom), 1, None);
                }
                Some('?') => {
                    self.bump();
                    atom = Re::Repeat(Box::new(atom), 0, Some(1));
                }
                Some('{') => {
                    let save = self.pos;
                    self.bump();
                    let min = self.number();
                    let max = if self.peek() == Some(',') {
                        self.bump();
                        if self.peek() == Some('}') {
                            None
                        } else {
                            Some(self.number().unwrap_or(0))
                        }
                    } else {
                        min
                    };
                    if self.peek() != Some('}') || min.is_none() {
                        self.pos = save;
                        return Err("invalid preceding regular expression".to_owned());
                    }
                    self.bump();
                    let min = min.unwrap_or(0);
                    if max.is_some_and(|max| max < min) || min > 255 {
                        return Err("invalid content of \\{\\}".to_owned());
                    }
                    atom = Re::Repeat(Box::new(atom), min, max);
                }
                _ => return Ok(atom),
            }
        }
    }

    fn number(&mut self) -> Option<u32> {
        let mut value: Option<u32> = None;
        while let Some(digit) = self.peek().and_then(|c| c.to_digit(10)) {
            value = Some(value.unwrap_or(0).saturating_mul(10).saturating_add(digit));
            self.bump();
        }
        value
    }

    fn atom(&mut self) -> Result<Re, String> {
        let Some(ch) = self.peek() else {
            return Ok(Re::Empty);
        };
        self.bump();
        Ok(match ch {
            '.' => Re::Any,
            '^' => Re::Start,
            '$' => Re::End,
            '(' => {
                self.groups = self.groups.saturating_add(1);
                let index = self.groups;
                let inner = self.alternation()?;
                if self.peek() != Some(')') {
                    return Err("unmatched ( or \\(".to_owned());
                }
                self.bump();
                Re::Group(Box::new(inner), index)
            }
            '[' => self.bracket()?,
            '*' | '+' | '?' if self.pos == 1 => Re::Char(ch),
            '*' | '+' | '?' | '{' => return Err("invalid preceding regular expression".to_owned()),
            '\\' => {
                let Some(next) = self.peek() else {
                    return Err("trailing backslash (\\)".to_owned());
                };
                self.bump();
                match next {
                    'w' => Re::Class(false, vec![Item::Named("word".to_owned())]),
                    'W' => Re::Class(true, vec![Item::Named("word".to_owned())]),
                    's' => Re::Class(false, vec![Item::Named("space".to_owned())]),
                    'S' => Re::Class(true, vec![Item::Named("space".to_owned())]),
                    'b' => Re::WordBoundary(true),
                    'B' => Re::WordBoundary(false),
                    '<' => Re::WordEdge(true),
                    '>' => Re::WordEdge(false),
                    other => Re::Char(other),
                }
            }
            other => Re::Char(other),
        })
    }

    fn bracket(&mut self) -> Result<Re, String> {
        let mut negated = false;
        if self.peek() == Some('^') {
            negated = true;
            self.bump();
        }
        let mut items = Vec::new();
        let mut first = true;
        loop {
            let Some(ch) = self.peek() else {
                return Err("unmatched [, [^, [:, [., or [=".to_owned());
            };
            if ch == ']' && !first {
                self.bump();
                break;
            }
            first = false;
            self.bump();
            if ch == '[' && matches!(self.peek(), Some(':' | '=' | '.')) {
                let delim = self.peek().unwrap_or(':');
                self.bump();
                let start = self.pos;
                while self.peek().is_some()
                    && !(self.peek() == Some(delim)
                        && self.chars.get(self.pos.saturating_add(1)) == Some(&']'))
                {
                    self.bump();
                }
                let name: String = self
                    .chars
                    .get(start..self.pos)
                    .unwrap_or_default()
                    .iter()
                    .collect();
                self.bump();
                self.bump();
                if delim == ':' {
                    if ![
                        "alpha", "digit", "alnum", "upper", "lower", "space", "blank", "punct",
                        "print", "graph", "cntrl", "xdigit",
                    ]
                    .contains(&name.as_str())
                    {
                        return Err("invalid character class".to_owned());
                    }
                    items.push(Item::Named(name));
                } else {
                    items.extend(name.chars().map(Item::Char));
                }
                continue;
            }
            if self.peek() == Some('-')
                && self
                    .chars
                    .get(self.pos.saturating_add(1))
                    .is_some_and(|c| *c != ']')
            {
                self.bump();
                let end = self.peek().unwrap_or(ch);
                self.bump();
                if end < ch {
                    return Err("invalid range end".to_owned());
                }
                items.push(Item::Range(ch, end));
                continue;
            }
            items.push(Item::Char(ch));
        }
        Ok(Re::Class(negated, items))
    }
}

/// What remains to match after the current node.
enum Cont<'a> {
    Done,
    Seq(&'a [Re], &'a Cont<'a>),
    GroupEnd(usize, usize, &'a Cont<'a>),
    Repeat(&'a Re, u32, Option<u32>, u32, usize, &'a Cont<'a>),
}

struct Search<'a> {
    text: &'a [char],
    nocase: bool,
    steps: u64,
    depth: u32,
    best: Option<(usize, Captures)>,
}

impl Search<'_> {
    /// Match `re` at `pos`, then what `cont` holds. True means the budget is spent.
    fn walk(&mut self, re: &Re, pos: usize, cont: &Cont<'_>, caps: &mut Captures) -> bool {
        self.steps = self.steps.saturating_add(1);
        if self.steps > STEP_BUDGET || self.depth > SEARCH_DEPTH {
            self.steps = self.steps.max(STEP_BUDGET.saturating_add(1));
            return true;
        }
        self.depth = self.depth.saturating_add(1);
        let stop = self.walk_inner(re, pos, cont, caps);
        self.depth = self.depth.saturating_sub(1);
        stop
    }

    fn walk_inner(&mut self, re: &Re, pos: usize, cont: &Cont<'_>, caps: &mut Captures) -> bool {
        match re {
            Re::Empty => self.resume(cont, pos, caps),
            Re::Char(ch) => match self.text.get(pos) {
                Some(c) if self.same(*c, *ch) => self.resume(cont, pos.saturating_add(1), caps),
                _ => false,
            },
            Re::Any => match self.text.get(pos) {
                Some(_) => self.resume(cont, pos.saturating_add(1), caps),
                None => false,
            },
            Re::Class(negated, items) => match self.text.get(pos) {
                Some(c) if self.class(items, *c) != *negated => {
                    self.resume(cont, pos.saturating_add(1), caps)
                }
                _ => false,
            },
            Re::Start => pos == 0 && self.resume(cont, pos, caps),
            Re::End => pos == self.text.len() && self.resume(cont, pos, caps),
            Re::WordBoundary(want) => self.boundary(pos) == *want && self.resume(cont, pos, caps),
            Re::WordEdge(start) => {
                let before = pos
                    .checked_sub(1)
                    .and_then(|p| self.text.get(p))
                    .is_some_and(|c| is_word(*c));
                let after = self.text.get(pos).is_some_and(|c| is_word(*c));
                let ok = if *start {
                    !before && after
                } else {
                    before && !after
                };
                ok && self.resume(cont, pos, caps)
            }
            Re::Group(inner, index) => {
                self.walk(inner, pos, &Cont::GroupEnd(*index, pos, cont), caps)
            }
            Re::Concat(items) => self.resume(&Cont::Seq(items, cont), pos, caps),
            Re::Alt(alternatives) => alternatives
                .iter()
                .any(|alternative| self.walk(alternative, pos, cont, caps)),
            Re::Repeat(inner, min, max) => self.resume(
                &Cont::Repeat(inner, *min, *max, 0, usize::MAX, cont),
                pos,
                caps,
            ),
        }
    }

    fn resume(&mut self, cont: &Cont<'_>, pos: usize, caps: &mut Captures) -> bool {
        match cont {
            Cont::Done => {
                if self.best.as_ref().is_none_or(|(end, _)| pos > *end) {
                    self.best = Some((pos, caps.clone()));
                }
                false
            }
            Cont::Seq(items, next) => match items.split_first() {
                None => self.resume(next, pos, caps),
                Some((first, rest)) => self.walk(first, pos, &Cont::Seq(rest, next), caps),
            },
            Cont::GroupEnd(index, start, next) => {
                let saved = caps.get(*index).copied().flatten();
                if let Some(slot) = caps.get_mut(*index) {
                    *slot = Some((*start, pos));
                }
                let stop = self.resume(next, pos, caps);
                if let Some(slot) = caps.get_mut(*index) {
                    *slot = saved;
                }
                stop
            }
            Cont::Repeat(inner, min, max, count, last, next) => {
                // An iteration that matched nothing ends the repetition.
                if *last == pos && count >= min {
                    return false;
                }
                if max.is_none_or(|max| *count < max) {
                    let more = Cont::Repeat(inner, *min, *max, count.saturating_add(1), pos, next);
                    if self.walk(inner, pos, &more, caps) {
                        return true;
                    }
                }
                *count >= *min && self.resume(next, pos, caps)
            }
        }
    }

    fn boundary(&self, pos: usize) -> bool {
        let before = pos
            .checked_sub(1)
            .and_then(|p| self.text.get(p))
            .is_some_and(|c| is_word(*c));
        let after = self.text.get(pos).is_some_and(|c| is_word(*c));
        before != after
    }

    fn same(&self, a: char, b: char) -> bool {
        if self.nocase {
            a.to_lowercase().eq(b.to_lowercase())
        } else {
            a == b
        }
    }

    fn class(&self, items: &[Item], ch: char) -> bool {
        items.iter().any(|item| match item {
            Item::Char(c) => self.same(*c, ch),
            Item::Range(low, high) => *low <= ch && ch <= *high,
            Item::Named(name) => named_class(name, ch),
        })
    }
}

fn is_word(ch: char) -> bool {
    ch.is_alphanumeric() || ch == '_'
}

/// A POSIX basic regular expression rewritten as an extended one, with
/// GNU's `\+`, `\?` and `\|`.
pub fn bre_to_ere(pattern: &str) -> String {
    let chars: Vec<char> = pattern.chars().collect();
    let mut out = String::new();
    let mut index = 0usize;
    // Whether the next character starts an expression, where `*` is literal.
    let mut at_start = true;
    while let Some(&ch) = chars.get(index) {
        index = index.saturating_add(1);
        match ch {
            '\\' => {
                let Some(&next) = chars.get(index) else {
                    out.push_str("\\\\");
                    break;
                };
                index = index.saturating_add(1);
                match next {
                    '(' | ')' | '{' | '}' | '|' | '+' | '?' => {
                        out.push(next);
                        at_start = matches!(next, '(' | '|');
                        continue;
                    }
                    'n' => out.push('\n'),
                    't' => out.push('\t'),
                    other => {
                        out.push('\\');
                        out.push(other);
                    }
                }
            }
            '(' | ')' | '{' | '}' | '|' | '+' | '?' => {
                out.push('\\');
                out.push(ch);
            }
            '*' if at_start => out.push_str("\\*"),
            '^' if !at_start => out.push_str("\\^"),
            '^' => {
                out.push('^');
                continue;
            }
            '$' => {
                let at_end = index >= chars.len()
                    || (chars.get(index) == Some(&'\\')
                        && matches!(chars.get(index.saturating_add(1)), Some(')' | '|')));
                if at_end {
                    out.push('$');
                } else {
                    out.push_str("\\$");
                }
            }
            '[' => {
                out.push('[');
                let mut first = true;
                while let Some(&inner) = chars.get(index) {
                    index = index.saturating_add(1);
                    out.push(inner);
                    if inner == '[' && matches!(chars.get(index), Some(':' | '.' | '=')) {
                        let delim = chars.get(index).copied().unwrap_or(':');
                        while let Some(&c) = chars.get(index) {
                            index = index.saturating_add(1);
                            out.push(c);
                            if c == delim && chars.get(index) == Some(&']') {
                                out.push(']');
                                index = index.saturating_add(1);
                                break;
                            }
                        }
                        first = false;
                        continue;
                    }
                    if inner == ']' && !first {
                        break;
                    }
                    if !(first && inner == '^') {
                        first = false;
                    }
                }
            }
            other => out.push(other),
        }
        at_start = false;
    }
    out
}
