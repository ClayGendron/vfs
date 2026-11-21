//! Shell patterns: `*`, `?`, bracket expressions and, with `extglob`, the
//! five pattern lists. A pattern is compiled from characters that each
//! carry whether they were quoted, since a quoted `*` is only a star.
//! Matching memoizes each (pattern node, text position) pair, so a pattern
//! costs at most its size times the text's.

use std::collections::BTreeMap;

/// A pattern character and whether it was quoted.
pub type PatChar = (char, bool);

#[derive(Clone, Debug, PartialEq, Eq)]
enum Node {
    Char(char),
    Any,
    Star,
    Class(Class),
    /// An extglob list: its operator and its alternatives.
    List(char, Vec<Vec<Node>>),
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct Class {
    negated: bool,
    items: Vec<ClassItem>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
enum ClassItem {
    Char(char),
    Range(char, char),
    Named(String),
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Pattern {
    nodes: Vec<Node>,
}

/// How a match is judged.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct MatchOptions {
    pub nocase: bool,
    /// A leading `.` and every `/` must be matched by a literal, as in a path.
    pub path: bool,
    pub dotglob: bool,
}

/// Whether the characters hold an unquoted pattern character.
pub fn has_glob(chars: &[PatChar], extglob: bool) -> bool {
    let mut iter = chars.iter().peekable();
    while let Some((ch, quoted)) = iter.next() {
        if *quoted {
            continue;
        }
        match ch {
            '*' | '?' => return true,
            '[' => {
                if bracket_end(
                    chars,
                    chars.len().saturating_sub(iter.len()).saturating_sub(1),
                )
                .is_some()
                {
                    return true;
                }
            }
            '+' | '@' | '!'
                if extglob
                    && iter
                        .peek()
                        .is_some_and(|(next, quoted)| *next == '(' && !quoted) =>
            {
                return true;
            }
            _ => {}
        }
    }
    false
}

/// The index of the `]` closing the bracket expression opened at `open`.
fn bracket_end(chars: &[PatChar], open: usize) -> Option<usize> {
    let mut index = open.saturating_add(1);
    if matches!(chars.get(index), Some(('!' | '^', false))) {
        index = index.saturating_add(1);
    }
    if matches!(chars.get(index), Some((']', _))) {
        index = index.saturating_add(1);
    }
    while let Some((ch, quoted)) = chars.get(index) {
        if *ch == '['
            && !quoted
            && matches!(
                chars.get(index.saturating_add(1)),
                Some((':' | '=' | '.', false))
            )
        {
            let delim = chars.get(index.saturating_add(1)).map_or(':', |c| c.0);
            let mut probe = index.saturating_add(2);
            let mut closed = None;
            while let Some((c, _)) = chars.get(probe) {
                if *c == delim && matches!(chars.get(probe.saturating_add(1)), Some((']', _))) {
                    closed = Some(probe.saturating_add(1));
                    break;
                }
                probe = probe.saturating_add(1);
            }
            if let Some(end) = closed {
                index = end.saturating_add(1);
                continue;
            }
        }
        if *ch == ']' && !quoted {
            return Some(index);
        }
        if *ch == '/' {
            return None;
        }
        index = index.saturating_add(1);
    }
    None
}

impl Pattern {
    pub fn compile(chars: &[PatChar], extglob: bool) -> Pattern {
        let mut pos = 0;
        let nodes = compile_seq(chars, &mut pos, extglob, false);
        Pattern { nodes }
    }

    pub fn matches(&self, text: &str, options: MatchOptions) -> bool {
        let chars: Vec<char> = text.chars().collect();
        let mut matcher = Matcher {
            text: &chars,
            options,
            frames: 0,
            memo: BTreeMap::new(),
        };
        matcher.seq(&self.nodes, 0, 0, chars.len(), 0)
    }

    /// Whether the pattern matches the characters `text[start..end]`.
    pub fn matches_chars(&self, text: &[char], options: MatchOptions) -> bool {
        let mut matcher = Matcher {
            text,
            options,
            frames: 0,
            memo: BTreeMap::new(),
        };
        matcher.seq(&self.nodes, 0, 0, text.len(), 0)
    }
}

fn compile_seq(chars: &[PatChar], pos: &mut usize, extglob: bool, in_list: bool) -> Vec<Node> {
    let mut nodes = Vec::new();
    while let Some(&(ch, quoted)) = chars.get(*pos) {
        if quoted {
            nodes.push(Node::Char(ch));
            *pos = pos.saturating_add(1);
            continue;
        }
        if in_list && (ch == '|' || ch == ')') {
            break;
        }
        let next_open = matches!(chars.get(pos.saturating_add(1)), Some(('(', false)));
        if extglob && next_open && matches!(ch, '?' | '*' | '+' | '@' | '!') {
            let save = *pos;
            *pos = pos.saturating_add(2);
            let mut alternatives = Vec::new();
            let mut closed = false;
            loop {
                let alt = compile_seq(chars, pos, extglob, true);
                alternatives.push(alt);
                match chars.get(*pos) {
                    Some(('|', false)) => *pos = pos.saturating_add(1),
                    Some((')', false)) => {
                        *pos = pos.saturating_add(1);
                        closed = true;
                        break;
                    }
                    _ => break,
                }
            }
            if closed {
                nodes.push(Node::List(ch, alternatives));
                continue;
            }
            *pos = save;
        }
        match ch {
            '*' => {
                if nodes.last() != Some(&Node::Star) {
                    nodes.push(Node::Star);
                }
                *pos = pos.saturating_add(1);
            }
            '?' => {
                nodes.push(Node::Any);
                *pos = pos.saturating_add(1);
            }
            '[' => match bracket_end(chars, *pos) {
                Some(end) => {
                    nodes.push(Node::Class(compile_class(
                        chars.get(pos.saturating_add(1)..end).unwrap_or_default(),
                    )));
                    *pos = end.saturating_add(1);
                }
                None => {
                    nodes.push(Node::Char('['));
                    *pos = pos.saturating_add(1);
                }
            },
            '\\' => {
                // An unquoted backslash in a pattern quotes the next character.
                *pos = pos.saturating_add(1);
                match chars.get(*pos) {
                    Some(&(next, _)) => {
                        nodes.push(Node::Char(next));
                        *pos = pos.saturating_add(1);
                    }
                    None => nodes.push(Node::Char('\\')),
                }
            }
            _ => {
                nodes.push(Node::Char(ch));
                *pos = pos.saturating_add(1);
            }
        }
    }
    nodes
}

fn compile_class(body: &[PatChar]) -> Class {
    let mut index = 0;
    let mut negated = false;
    if matches!(body.first(), Some(('!' | '^', false))) {
        negated = true;
        index = 1;
    }
    let mut items = Vec::new();
    let mut first = true;
    while let Some(&(ch, quoted)) = body.get(index) {
        if ch == '['
            && !quoted
            && matches!(
                body.get(index.saturating_add(1)),
                Some((':' | '=' | '.', false))
            )
        {
            let delim = body.get(index.saturating_add(1)).map_or(':', |c| c.0);
            let start = index.saturating_add(2);
            let mut probe = start;
            while let Some((c, _)) = body.get(probe) {
                if *c == delim && matches!(body.get(probe.saturating_add(1)), Some((']', _))) {
                    break;
                }
                probe = probe.saturating_add(1);
            }
            let name: String = body
                .get(start..probe)
                .unwrap_or_default()
                .iter()
                .map(|(c, _)| *c)
                .collect();
            match delim {
                ':' => items.push(ClassItem::Named(name)),
                _ => {
                    for c in name.chars() {
                        items.push(ClassItem::Char(c));
                    }
                }
            }
            index = probe.saturating_add(2);
            first = false;
            continue;
        }
        let mut current = ch;
        if ch == '\\'
            && !quoted
            && let Some(&(next, _)) = body.get(index.saturating_add(1))
        {
            current = next;
            index = index.saturating_add(1);
        }
        let dash = body.get(index.saturating_add(1));
        let after = body.get(index.saturating_add(2));
        if !first || ch != ']' || quoted {
            // fall through: a `]` first is a literal member
        }
        if matches!(dash, Some(('-', false)))
            && let Some(&(end, _)) = after
        {
            items.push(ClassItem::Range(current, end));
            index = index.saturating_add(3);
            first = false;
            continue;
        }
        items.push(ClassItem::Char(current));
        index = index.saturating_add(1);
        first = false;
    }
    Class { negated, items }
}

/// Frames one match may stack. A pattern recurses only at a star or a list,
/// so this bounds the stars in a pattern, never the length of the text.
const MATCH_DEPTH: u32 = 2_000;

struct Matcher<'a> {
    text: &'a [char],
    options: MatchOptions,
    frames: u32,
    /// Whether node `n` of sequence `seq` matches from `pos` to `end`.
    memo: BTreeMap<(usize, usize, usize, usize), bool>,
}

impl Matcher<'_> {
    /// Whether `nodes` match `text[pos..end]` exactly. `id` names the sequence for the memo.
    fn seq(&mut self, nodes: &[Node], id: usize, pos: usize, end: usize, depth: u32) -> bool {
        self.at(nodes, id, 0, pos, end, depth)
    }

    fn at(
        &mut self,
        nodes: &[Node],
        id: usize,
        index: usize,
        pos: usize,
        end: usize,
        depth: u32,
    ) -> bool {
        if depth > 64 || self.frames > MATCH_DEPTH {
            return false;
        }
        // Single-character nodes are matched in a loop, so text length never deepens the stack.
        let mut index = index;
        let mut pos = pos;
        while let Some(node) = nodes.get(index) {
            let ok = match node {
                Node::Char(ch) => {
                    pos < end && self.text.get(pos).is_some_and(|c| self.same(*c, *ch))
                }
                Node::Any => pos < end && self.text.get(pos).is_some_and(|c| self.wild_ok(*c, pos)),
                Node::Class(class) => {
                    pos < end
                        && self.text.get(pos).is_some_and(|c| {
                            self.class_matches(class, *c) && !(self.options.path && *c == '/')
                        })
                        && !(self.options.path
                            && self.leading(pos)
                            && self.text.get(pos) == Some(&'.')
                            && !self.options.dotglob)
                }
                _ => break,
            };
            if !ok {
                return false;
            }
            index = index.saturating_add(1);
            pos = pos.saturating_add(1);
        }
        let Some(node) = nodes.get(index) else {
            return pos == end;
        };
        self.frames = self.frames.saturating_add(1);
        let result = self.at_wild(nodes, id, index, node, pos, end, depth);
        self.frames = self.frames.saturating_sub(1);
        result
    }

    #[allow(clippy::too_many_arguments)]
    fn at_wild(
        &mut self,
        nodes: &[Node],
        id: usize,
        index: usize,
        node: &Node,
        pos: usize,
        end: usize,
        depth: u32,
    ) -> bool {
        // A sequence is named by its address, which is unique while the pattern lives.
        let key = (nodes.as_ptr() as usize, index, pos, end);
        if let Some(known) = self.memo.get(&key) {
            return *known;
        }
        let next = index.saturating_add(1);
        let result = match node {
            Node::Char(ch) => {
                pos < end && self.text.get(pos).is_some_and(|c| self.same(*c, *ch)) && {
                    if self.options.path && *ch == '.' && self.leading(pos) && !self.options.dotglob
                    {
                        // A literal dot matches a leading dot.
                    }
                    self.at(nodes, id, next, pos.saturating_add(1), end, depth)
                }
            }
            Node::Any => {
                pos < end
                    && self.text.get(pos).is_some_and(|c| self.wild_ok(*c, pos))
                    && self.at(nodes, id, next, pos.saturating_add(1), end, depth)
            }
            Node::Class(class) => {
                pos < end
                    && self.text.get(pos).is_some_and(|c| {
                        self.class_matches(class, *c) && !(self.options.path && *c == '/')
                    })
                    && !(self.options.path
                        && self.leading(pos)
                        && self.text.get(pos) == Some(&'.')
                        && !self.options.dotglob)
                    && self.at(nodes, id, next, pos.saturating_add(1), end, depth)
            }
            Node::Star => {
                let mut found = false;
                let mut probe = pos;
                loop {
                    if self.at(nodes, id, next, probe, end, depth) {
                        found = true;
                        break;
                    }
                    if probe >= end {
                        break;
                    }
                    match self.text.get(probe) {
                        Some(c) if self.wild_ok(*c, probe) => probe = probe.saturating_add(1),
                        _ => break,
                    }
                }
                found
            }
            Node::List(op, alternatives) => {
                self.list(nodes, id, index, *op, alternatives, pos, end, depth)
            }
        };
        self.memo.insert(key, result);
        result
    }

    #[allow(clippy::too_many_arguments)]
    fn list(
        &mut self,
        nodes: &[Node],
        id: usize,
        index: usize,
        op: char,
        alternatives: &[Vec<Node>],
        pos: usize,
        end: usize,
        depth: u32,
    ) -> bool {
        let next = index.saturating_add(1);
        let depth = depth.saturating_add(1);
        let base = id
            .saturating_mul(131)
            .saturating_add(index.saturating_add(1).saturating_mul(7919));
        let one = |this: &mut Self, from: usize, to: usize| -> bool {
            alternatives.iter().enumerate().any(|(alt_index, alt)| {
                let alt_id = base.saturating_add(alt_index.saturating_add(1));
                this.seq(alt, alt_id, from, to, depth)
            })
        };
        match op {
            '@' | '?' => {
                if op == '?' && self.at(nodes, id, next, pos, end, depth) {
                    return true;
                }
                (pos..=end).any(|k| one(self, pos, k) && self.at(nodes, id, next, k, end, depth))
            }
            '*' | '+' => {
                // Positions reachable after one or more repetitions.
                let mut reach = vec![false; end.saturating_sub(pos).saturating_add(1)];
                let mut frontier = vec![pos];
                while let Some(from) = frontier.pop() {
                    for k in from..=end {
                        if k == from {
                            if !one(self, from, k) {
                                continue;
                            }
                        } else if !one(self, from, k) {
                            continue;
                        }
                        if let Some(seen) = reach.get_mut(k.saturating_sub(pos))
                            && !*seen
                        {
                            *seen = true;
                            if k != from {
                                frontier.push(k);
                            }
                        }
                    }
                }
                if op == '*'
                    && let Some(first) = reach.first_mut()
                {
                    *first = true;
                }
                (pos..=end).any(|k| {
                    reach.get(k.saturating_sub(pos)).copied().unwrap_or(false)
                        && self.at(nodes, id, next, k, end, depth)
                })
            }
            '!' => (pos..=end).any(|k| {
                !one(self, pos, k)
                    && !(self.options.path
                        && self.leading(pos)
                        && self.text.get(pos) == Some(&'.')
                        && !self.options.dotglob
                        && k > pos)
                    && self.at(nodes, id, next, k, end, depth)
            }),
            _ => false,
        }
    }

    fn leading(&self, pos: usize) -> bool {
        pos == 0
            || (self.options.path
                && pos.checked_sub(1).and_then(|p| self.text.get(p)) == Some(&'/'))
    }

    /// Whether `*` or `?` may match `ch` at `pos`.
    fn wild_ok(&self, ch: char, pos: usize) -> bool {
        if self.options.path {
            if ch == '/' {
                return false;
            }
            if ch == '.' && self.leading(pos) && !self.options.dotglob {
                return false;
            }
        }
        true
    }

    fn same(&self, a: char, b: char) -> bool {
        if self.options.nocase {
            a.to_lowercase().eq(b.to_lowercase())
        } else {
            a == b
        }
    }

    fn class_matches(&self, class: &Class, ch: char) -> bool {
        let found = class.items.iter().any(|item| match item {
            ClassItem::Char(c) => self.same(*c, ch),
            ClassItem::Range(low, high) => {
                (*low <= ch && ch <= *high)
                    || (self.options.nocase && {
                        let lower = ch.to_lowercase().next().unwrap_or(ch);
                        let upper = ch.to_uppercase().next().unwrap_or(ch);
                        (*low <= lower && lower <= *high) || (*low <= upper && upper <= *high)
                    })
            }
            ClassItem::Named(name) => named_class(name, ch),
        });
        found != class.negated
    }
}

/// Whether `ch` belongs to the POSIX character class `name`.
pub fn named_class(name: &str, ch: char) -> bool {
    match name {
        "alpha" => ch.is_alphabetic(),
        "digit" => ch.is_ascii_digit(),
        "alnum" => ch.is_alphanumeric(),
        "upper" => ch.is_uppercase(),
        "lower" => ch.is_lowercase(),
        "space" => matches!(ch, ' ' | '\t' | '\n' | '\r' | '\u{b}' | '\u{c}'),
        "blank" => matches!(ch, ' ' | '\t'),
        "punct" => ch.is_ascii_punctuation(),
        "print" => !ch.is_control(),
        "graph" => !ch.is_control() && !ch.is_whitespace(),
        "cntrl" => ch.is_control(),
        "xdigit" => ch.is_ascii_hexdigit(),
        "word" => ch.is_alphanumeric() || ch == '_',
        _ => false,
    }
}
