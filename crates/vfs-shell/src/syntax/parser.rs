//! A recursive-descent parser for the bash language over the bytes of a
//! line. Every descent checks the depth budget first, so no input can
//! overflow the stack; every word and operator counts against the token
//! budget; a here-document body is read at the newline that ends its line.

use std::rc::Rc;

use super::ast::{
    AndOr, Arg, ArrayElement, AssignValue, Assignment, CaseArm, CaseEnd, Command, CompoundCommand,
    CondExpr, Connector, DefaultKind, FunctionDef, HereDoc, List, ListItem, Param, ParamExp,
    ParamOp, Pipeline, RedirFd, RedirOp, RedirTarget, Redirect, ReplaceKind, Script, SimpleCommand,
    Span, Stage, Word, WordPart,
};
use super::{ParseError, ParseLimits, Position};

type Parsed<T> = Result<T, ParseError>;

/// Command names refused before anything runs, with their reasons.
pub const REFUSED: &[(&str, &str)] = &[
    (
        "eval",
        "dynamic evaluation: a line is parsed whole before it runs",
    ),
    (
        "source",
        "dynamic evaluation: a line is parsed whole before it runs",
    ),
    (
        ".",
        "dynamic evaluation: a line is parsed whole before it runs",
    ),
    ("exec", "process replacement has no meaning inside one call"),
    ("trap", "signals have no meaning inside one call"),
    ("jobs", "job control past the call is not supported"),
    ("fg", "job control past the call is not supported"),
    ("bg", "job control past the call is not supported"),
    ("disown", "job control past the call is not supported"),
    ("suspend", "job control past the call is not supported"),
    (
        "alias",
        "aliases are not expanded in a non-interactive shell",
    ),
    (
        "unalias",
        "aliases are not expanded in a non-interactive shell",
    ),
];

/// Builtins whose `name=value` arguments are assignments.
const DECLARATIONS: &[&str] = &["declare", "typeset", "local", "export", "readonly"];

/// Bytes counted for each node the parser builds, beside its text.
const NODE_BYTES: usize = 48;

/// Parse a whole line to a tree, or name the first thing wrong with it.
pub fn parse(source: &str, limits: &ParseLimits) -> Parsed<Script> {
    if source.len() > limits.source_bytes {
        return Err(ParseError::Budget("source", limits.source_bytes as u64));
    }
    let mut parser = Parser::new(source, 0, limits, 0);
    let body = parser.parse_list()?;
    parser.skip_blanks_and_newlines()?;
    if !parser.at_end() {
        return Err(parser.unexpected());
    }
    parser.finish_heredocs()?;
    let line_starts = line_starts(source);
    Ok(Script {
        body,
        line_starts,
        heredocs: parser.heredocs.into_iter().map(|slot| slot.doc).collect(),
        footprint: parser.footprint,
    })
}

/// The byte offset of the start of every line of `source`.
pub fn line_starts(source: &str) -> Vec<u32> {
    let mut starts = vec![0];
    for (index, byte) in source.bytes().enumerate() {
        if byte == b'\n' {
            starts.push(u32::try_from(index.saturating_add(1)).unwrap_or(u32::MAX));
        }
    }
    starts
}

// ---------------------------------------------------------------------------
// The parser state
// ---------------------------------------------------------------------------

#[derive(Clone, Copy, PartialEq, Eq)]
enum WordMode {
    Normal,
    /// The right side of `=~`: parentheses and `|` belong to the word.
    Regex,
}

/// Where a run of word text stops, inside `${...}`, `$((...))` or a subscript.
#[derive(Clone, Copy, PartialEq, Eq)]
enum Inner {
    /// A parameter word: stops at any byte in `stops` at depth zero.
    Param,
    /// An arithmetic body: stops at `))` at depth zero.
    Arith,
    /// A subscript: stops at `]` at depth zero.
    Subscript,
    /// An unquoted here-document body: only `$`, backquote and backslash are special.
    HereDoc,
}

struct PendingDoc {
    delimiter: String,
    strip_tabs: bool,
    quoted: bool,
    index: usize,
}

struct DocSlot {
    doc: HereDoc,
}

struct Saved {
    pos: usize,
    depth: u32,
    pending: usize,
    heredocs: usize,
}

struct Parser<'a> {
    src: &'a str,
    bytes: &'a [u8],
    pos: usize,
    /// Added to every offset, for a parser over a piece of a larger source.
    base: u32,
    limits: &'a ParseLimits,
    depth: u32,
    tokens: u32,
    footprint: usize,
    pending: Vec<PendingDoc>,
    heredocs: Vec<DocSlot>,
    line_starts: Vec<u32>,
}

impl<'a> Parser<'a> {
    fn new(src: &'a str, base: u32, limits: &'a ParseLimits, depth: u32) -> Parser<'a> {
        Parser {
            src,
            bytes: src.as_bytes(),
            pos: 0,
            base,
            limits,
            depth,
            tokens: 0,
            footprint: 0,
            pending: Vec::new(),
            heredocs: Vec::new(),
            line_starts: line_starts(src),
        }
    }

    // -- bytes ---------------------------------------------------------------

    fn peek(&self) -> Option<u8> {
        self.bytes.get(self.pos).copied()
    }

    fn peek_at(&self, ahead: usize) -> Option<u8> {
        self.bytes.get(self.pos.saturating_add(ahead)).copied()
    }

    fn at_end(&self) -> bool {
        self.pos >= self.bytes.len()
    }

    fn bump(&mut self, count: usize) {
        self.pos = self.pos.saturating_add(count).min(self.bytes.len());
    }

    fn starts_with(&self, text: &str) -> bool {
        self.bytes
            .get(self.pos..)
            .is_some_and(|rest| rest.starts_with(text.as_bytes()))
    }

    fn eat(&mut self, text: &str) -> bool {
        if self.starts_with(text) {
            self.bump(text.len());
            true
        } else {
            false
        }
    }

    /// The character at the cursor, which may be several bytes.
    fn peek_char(&self) -> Option<char> {
        self.src
            .get(self.pos..)
            .and_then(|rest| rest.chars().next())
    }

    fn offset(&self) -> u32 {
        self.base
            .saturating_add(u32::try_from(self.pos).unwrap_or(u32::MAX))
    }

    fn span_from(&self, start: u32) -> Span {
        Span {
            start,
            end: self.offset(),
        }
    }

    fn text(&self, start: usize, end: usize) -> String {
        self.src.get(start..end).unwrap_or_default().to_owned()
    }

    // -- budgets -------------------------------------------------------------

    fn enter(&mut self) -> Parsed<()> {
        self.depth = self.depth.saturating_add(1);
        if self.depth > self.limits.depth {
            return Err(ParseError::Budget("depth", u64::from(self.limits.depth)));
        }
        Ok(())
    }

    fn leave(&mut self) {
        self.depth = self.depth.saturating_sub(1);
    }

    fn token(&mut self, bytes: usize) -> Parsed<()> {
        self.tokens = self.tokens.saturating_add(1);
        self.footprint = self
            .footprint
            .saturating_add(bytes)
            .saturating_add(NODE_BYTES);
        if self.tokens > self.limits.tokens {
            return Err(ParseError::Budget("tokens", u64::from(self.limits.tokens)));
        }
        Ok(())
    }

    // -- errors --------------------------------------------------------------

    fn position(&self) -> Position {
        let local = u32::try_from(self.pos).unwrap_or(u32::MAX);
        let index = self.line_starts.partition_point(|start| *start <= local);
        let line_start = index
            .checked_sub(1)
            .and_then(|i| self.line_starts.get(i))
            .copied()
            .unwrap_or(0);
        Position {
            line: u32::try_from(index).unwrap_or(u32::MAX).max(1),
            column: local.saturating_sub(line_start).saturating_add(1),
            offset: self.offset(),
        }
    }

    fn error(&self, message: String) -> ParseError {
        ParseError::Syntax(self.position(), message)
    }

    fn unexpected(&self) -> ParseError {
        match self.token_text() {
            None => self.error("syntax error: unexpected end of file".to_owned()),
            Some(token) if token == "\n" => {
                self.error("syntax error near unexpected token `newline'".to_owned())
            }
            Some(token) => self.error(format!("syntax error near unexpected token `{token}'")),
        }
    }

    fn eof_looking_for(&self, what: char) -> ParseError {
        self.error(format!(
            "unexpected EOF while looking for matching `{what}'"
        ))
    }

    /// The token at the cursor, as an error message names it.
    fn token_text(&self) -> Option<String> {
        let first = self.peek()?;
        for op in [
            "&&", "||", ";;&", ";;", ";&", "|&", "<<<", "<<-", "<<", ">>", "&>>", "&>", "<&", ">&",
            "<>", ">|",
        ] {
            if self.starts_with(op) {
                return Some(op.to_owned());
            }
        }
        if matches!(
            first,
            b';' | b'&' | b'|' | b'(' | b')' | b'<' | b'>' | b'\n'
        ) {
            return Some(char::from(first).to_string());
        }
        let mut end = self.pos;
        while let Some(byte) = self.bytes.get(end) {
            if is_meta(*byte) || matches!(byte, b' ' | b'\t') {
                break;
            }
            end = end.saturating_add(1);
        }
        Some(self.text(self.pos, end))
    }

    // -- blanks, comments, newlines -------------------------------------------

    /// Skip spaces, tabs, line continuations and a comment, but not a newline.
    fn skip_blanks(&mut self) {
        loop {
            match self.peek() {
                Some(b' ' | b'\t') => self.bump(1),
                Some(b'\\') if self.peek_at(1) == Some(b'\n') => self.bump(2),
                Some(b'#') => {
                    while let Some(byte) = self.peek() {
                        if byte == b'\n' {
                            break;
                        }
                        self.bump(1);
                    }
                }
                _ => return,
            }
        }
    }

    fn skip_blanks_and_newlines(&mut self) -> Parsed<()> {
        loop {
            self.skip_blanks();
            if self.peek() == Some(b'\n') {
                self.newline()?;
            } else {
                return Ok(());
            }
        }
    }

    /// Consume a newline, then read the bodies of the here-documents it ends.
    fn newline(&mut self) -> Parsed<()> {
        self.bump(1);
        if self.pending.is_empty() {
            return Ok(());
        }
        let pending = std::mem::take(&mut self.pending);
        for doc in pending {
            self.read_heredoc(&doc)?;
        }
        Ok(())
    }

    fn finish_heredocs(&mut self) -> Parsed<()> {
        let pending = std::mem::take(&mut self.pending);
        for doc in pending {
            self.read_heredoc(&doc)?;
        }
        Ok(())
    }

    fn read_heredoc(&mut self, doc: &PendingDoc) -> Parsed<()> {
        let body_start = self.offset();
        let mut body = String::new();
        while !self.at_end() {
            let line_start = self.pos;
            let mut line_end = line_start;
            while let Some(byte) = self.bytes.get(line_end) {
                if *byte == b'\n' {
                    break;
                }
                line_end = line_end.saturating_add(1);
            }
            let mut line = self.text(line_start, line_end);
            if doc.strip_tabs {
                line = line.trim_start_matches('\t').to_owned();
            }
            self.pos = line_end;
            if self.peek() == Some(b'\n') {
                self.bump(1);
            }
            if line == doc.delimiter {
                break;
            }
            body.push_str(&line);
            body.push('\n');
        }
        self.token(body.len())?;
        let word = if doc.quoted {
            Word {
                parts: vec![WordPart::Literal(body)],
                span: self.span_from(body_start),
            }
        } else {
            let mut sub = Parser::new(&body, body_start, self.limits, self.depth);
            let parts = sub.read_inner(Inner::HereDoc, b"", false)?;
            self.absorb(&sub);
            if !sub.heredocs.is_empty() {
                return Err(self.error(
                    "here-document inside a here-document body is not supported".to_owned(),
                ));
            }
            Word {
                parts,
                span: self.span_from(body_start),
            }
        };
        if let Some(slot) = self.heredocs.get_mut(doc.index) {
            slot.doc.body = word;
        }
        Ok(())
    }

    fn absorb(&mut self, sub: &Parser<'_>) {
        self.tokens = self.tokens.saturating_add(sub.tokens);
        self.footprint = self.footprint.saturating_add(sub.footprint);
    }

    // -- lists ---------------------------------------------------------------

    fn parse_list(&mut self) -> Parsed<List> {
        self.enter()?;
        let mut items = Vec::new();
        loop {
            self.skip_blanks_and_newlines()?;
            if self.at_list_end() {
                break;
            }
            let and_or = self.parse_and_or()?;
            self.skip_blanks();
            let mut background = false;
            match self.peek() {
                Some(b';') if !self.starts_with(";;") && !self.starts_with(";&") => {
                    self.bump(1);
                    self.token(1)?;
                }
                Some(b'&') if !self.starts_with("&&") && !self.starts_with("&>") => {
                    self.bump(1);
                    self.token(1)?;
                    background = true;
                }
                Some(b'\n') => self.newline()?,
                _ => {
                    items.push(ListItem { and_or, background });
                    break;
                }
            }
            items.push(ListItem { and_or, background });
        }
        self.leave();
        Ok(List { items })
    }

    /// A list that must hold at least one command, as in `if`, `while` and `{`.
    fn parse_compound_list(&mut self) -> Parsed<List> {
        let list = self.parse_list()?;
        if list.items.is_empty() {
            return Err(self.unexpected());
        }
        Ok(list)
    }

    fn at_list_end(&self) -> bool {
        match self.peek() {
            None | Some(b')') => true,
            Some(b';') => self.starts_with(";;") || self.starts_with(";&"),
            _ => ["then", "else", "elif", "fi", "do", "done", "esac", "}"]
                .iter()
                .any(|word| self.reserved(word)),
        }
    }

    /// Whether the reserved word `word` is at the cursor, followed by a delimiter.
    fn reserved(&self, word: &str) -> bool {
        if !self.starts_with(word) {
            return false;
        }
        match self.peek_at(word.len()) {
            None => true,
            Some(byte) => matches!(
                byte,
                b' ' | b'\t' | b'\n' | b';' | b'&' | b'|' | b'(' | b')' | b'<' | b'>'
            ),
        }
    }

    fn eat_reserved(&mut self, word: &str) -> Parsed<bool> {
        if self.reserved(word) {
            self.bump(word.len());
            self.token(word.len())?;
            Ok(true)
        } else {
            Ok(false)
        }
    }

    fn expect_reserved(&mut self, word: &str) -> Parsed<()> {
        self.skip_blanks_and_newlines()?;
        if self.eat_reserved(word)? {
            Ok(())
        } else {
            Err(self.unexpected())
        }
    }

    fn parse_and_or(&mut self) -> Parsed<AndOr> {
        self.enter()?;
        let first = self.parse_pipeline()?;
        let mut rest = Vec::new();
        loop {
            self.skip_blanks();
            let connector = if self.eat("&&") {
                Connector::And
            } else if self.eat("||") {
                Connector::Or
            } else {
                break;
            };
            self.token(2)?;
            self.skip_blanks_and_newlines()?;
            rest.push((connector, self.parse_pipeline()?));
        }
        self.leave();
        Ok(AndOr { first, rest })
    }

    fn parse_pipeline(&mut self) -> Parsed<Pipeline> {
        self.enter()?;
        let start = self.offset();
        let mut negated = false;
        let mut timed = None;
        loop {
            self.skip_blanks();
            if self.eat_reserved("!")? {
                negated = !negated;
            } else if self.eat_reserved("time")? {
                self.skip_blanks();
                let posix = self.reserved("-p");
                if posix {
                    self.bump(2);
                }
                timed = Some(posix);
            } else {
                break;
            }
        }
        let mut stages = Vec::new();
        loop {
            self.skip_blanks();
            if !stages.is_empty() && self.reserved("!") {
                return Err(self.unexpected());
            }
            let Some(command) = self.parse_command()? else {
                if stages.is_empty() && (negated || timed.is_some()) && self.at_pipeline_end() {
                    break;
                }
                return Err(self.unexpected());
            };
            self.skip_blanks();
            let mut stage = Stage {
                command,
                pipe_stderr: false,
            };
            if self.starts_with("|") && !self.starts_with("||") {
                stage.pipe_stderr = self.starts_with("|&");
                self.bump(if stage.pipe_stderr { 2 } else { 1 });
                self.token(1)?;
                stages.push(stage);
                if stages.len() >= self.limits.pipeline_stages as usize {
                    return Err(ParseError::Budget(
                        "pipeline_stages",
                        u64::from(self.limits.pipeline_stages),
                    ));
                }
                self.skip_blanks_and_newlines()?;
                continue;
            }
            stages.push(stage);
            break;
        }
        self.leave();
        Ok(Pipeline {
            negated,
            timed,
            stages,
            span: self.span_from(start),
        })
    }

    fn at_pipeline_end(&self) -> bool {
        match self.peek() {
            None => true,
            Some(byte) => matches!(byte, b'\n' | b';' | b'&' | b')') || self.at_list_end(),
        }
    }

    // -- commands ------------------------------------------------------------

    fn parse_command(&mut self) -> Parsed<Option<Command>> {
        self.enter()?;
        let command = self.parse_command_inner()?;
        self.leave();
        Ok(command)
    }

    fn parse_command_inner(&mut self) -> Parsed<Option<Command>> {
        self.skip_blanks();
        let start = self.offset();
        let start_pos = self.pos;
        let compound = if self.eat_reserved("if")? {
            Some(self.parse_if()?)
        } else if self.eat_reserved("while")? {
            Some(self.parse_while(false)?)
        } else if self.eat_reserved("until")? {
            Some(self.parse_while(true)?)
        } else if self.eat_reserved("for")? {
            Some(self.parse_for(start)?)
        } else if self.eat_reserved("select")? {
            Some(self.parse_select(start)?)
        } else if self.eat_reserved("case")? {
            Some(self.parse_case()?)
        } else if self.eat_reserved("{")? {
            let body = self.parse_compound_list()?;
            self.expect_reserved("}")?;
            Some(CompoundCommand::Brace(body))
        } else if self.reserved("[[") {
            self.bump(2);
            self.token(2)?;
            let expr = self.parse_cond_or()?;
            self.skip_blanks_and_newlines()?;
            if !self.eat_reserved("]]")? {
                return Err(self.unexpected());
            }
            Some(CompoundCommand::Cond(expr, self.span_from(start)))
        } else if self.starts_with("((") {
            match self.try_arith_command(start)? {
                Some(command) => Some(command),
                None => Some(self.parse_subshell()?),
            }
        } else if self.peek() == Some(b'(') {
            Some(self.parse_subshell()?)
        } else if self.eat_reserved("function")? {
            return self.parse_function_keyword(start, start_pos).map(Some);
        } else if self.reserved("coproc") {
            return Err(ParseError::Refused(
                self.position(),
                "coproc",
                "coprocesses are job control past the call",
            ));
        } else {
            None
        };
        if let Some(compound) = compound {
            let redirects = self.parse_trailing_redirects()?;
            return Ok(Some(Command::Compound(Box::new(compound), redirects)));
        }
        if self.at_command_end() || self.at_list_end() {
            return Ok(None);
        }
        if let Some(def) = self.try_function_def(start, start_pos)? {
            return Ok(Some(def));
        }
        self.parse_simple(start).map(Some)
    }

    fn at_command_end(&self) -> bool {
        match self.peek() {
            None => true,
            Some(byte) => matches!(byte, b'\n' | b';' | b'&' | b'|' | b')'),
        }
    }

    fn parse_trailing_redirects(&mut self) -> Parsed<Vec<Redirect>> {
        let mut redirects = Vec::new();
        loop {
            self.skip_blanks();
            if !self.at_redirect() {
                return Ok(redirects);
            }
            redirects.push(self.parse_redirect()?);
        }
    }

    fn parse_simple(&mut self, start: u32) -> Parsed<Command> {
        let mut assignments = Vec::new();
        let mut words: Vec<Arg> = Vec::new();
        let mut redirects = Vec::new();
        let mut declaration = false;
        loop {
            self.skip_blanks();
            if self.at_command_end() {
                break;
            }
            if self.at_redirect() {
                redirects.push(self.parse_redirect()?);
                continue;
            }
            if (words.is_empty() || declaration) && self.assignment_ahead() {
                let assignment = self.parse_assignment()?;
                if words.is_empty() {
                    assignments.push(assignment);
                } else {
                    words.push(Arg::Assign(assignment));
                }
                continue;
            }
            if self.peek() == Some(b'(') {
                return Err(self.unexpected());
            }
            let Some(word) = self.read_word(WordMode::Normal)? else {
                return Err(self.unexpected());
            };
            if words.is_empty()
                && let Some(name) = word.static_text()
            {
                if let Some((construct, reason)) =
                    REFUSED.iter().find(|(refused, _)| *refused == name)
                {
                    return Err(ParseError::Refused(
                        self.position_of(word.span.start),
                        construct,
                        reason,
                    ));
                }
                declaration = DECLARATIONS.contains(&name.as_str()) && word.as_literal().is_some();
            }
            words.push(Arg::Word(word));
        }
        if assignments.is_empty() && words.is_empty() && redirects.is_empty() {
            return Err(self.unexpected());
        }
        Ok(Command::Simple(SimpleCommand {
            assignments,
            words,
            redirects,
            span: self.span_from(start),
        }))
    }

    fn position_of(&self, offset: u32) -> Position {
        let local = offset.saturating_sub(self.base);
        let index = self.line_starts.partition_point(|start| *start <= local);
        let line_start = index
            .checked_sub(1)
            .and_then(|i| self.line_starts.get(i))
            .copied()
            .unwrap_or(0);
        Position {
            line: u32::try_from(index).unwrap_or(u32::MAX).max(1),
            column: local.saturating_sub(line_start).saturating_add(1),
            offset,
        }
    }

    // -- compound commands ---------------------------------------------------

    fn parse_if(&mut self) -> Parsed<CompoundCommand> {
        let mut branches = Vec::new();
        let mut otherwise = None;
        let condition = self.parse_compound_list()?;
        self.expect_reserved("then")?;
        let body = self.parse_compound_list()?;
        branches.push((condition, body));
        loop {
            self.skip_blanks_and_newlines()?;
            if self.eat_reserved("elif")? {
                let condition = self.parse_compound_list()?;
                self.expect_reserved("then")?;
                let body = self.parse_compound_list()?;
                branches.push((condition, body));
            } else if self.eat_reserved("else")? {
                otherwise = Some(self.parse_compound_list()?);
                self.expect_reserved("fi")?;
                break;
            } else if self.eat_reserved("fi")? {
                break;
            } else {
                return Err(self.unexpected());
            }
        }
        Ok(CompoundCommand::If {
            branches,
            otherwise,
        })
    }

    fn parse_while(&mut self, until: bool) -> Parsed<CompoundCommand> {
        let condition = self.parse_compound_list()?;
        let body = self.parse_do_group()?;
        Ok(CompoundCommand::While {
            until,
            condition,
            body,
        })
    }

    fn parse_do_group(&mut self) -> Parsed<List> {
        self.skip_blanks_and_newlines()?;
        if self.eat_reserved("{")? {
            let body = self.parse_compound_list()?;
            self.expect_reserved("}")?;
            return Ok(body);
        }
        self.expect_reserved("do")?;
        let body = self.parse_compound_list()?;
        self.expect_reserved("done")?;
        Ok(body)
    }

    fn parse_for(&mut self, start: u32) -> Parsed<CompoundCommand> {
        self.skip_blanks();
        if self.starts_with("((") {
            self.bump(2);
            self.token(2)?;
            let init = self.read_arith_clause(b';')?;
            let test = self.read_arith_clause(b';')?;
            let step = self.read_arith_clause(b')')?;
            if !self.eat(")") {
                return Err(self.unexpected());
            }
            self.skip_blanks();
            if self.peek() == Some(b';') {
                self.bump(1);
            }
            let body = self.parse_do_group()?;
            return Ok(CompoundCommand::ArithFor {
                init,
                test,
                step,
                body,
                span: self.span_from(start),
            });
        }
        let (name, words) = self.parse_for_head()?;
        let body = self.parse_do_group()?;
        Ok(CompoundCommand::For {
            name,
            words,
            body,
            span: self.span_from(start),
        })
    }

    fn parse_select(&mut self, start: u32) -> Parsed<CompoundCommand> {
        let (name, words) = self.parse_for_head()?;
        let body = self.parse_do_group()?;
        Ok(CompoundCommand::Select {
            name,
            words,
            body,
            span: self.span_from(start),
        })
    }

    fn parse_for_head(&mut self) -> Parsed<(String, Option<Vec<Word>>)> {
        self.skip_blanks();
        let Some(word) = self.read_word(WordMode::Normal)? else {
            return Err(self.unexpected());
        };
        // Bash judges the name when the loop runs, so a bad one is kept here.
        let name = word.static_text().unwrap_or_default();
        self.skip_blanks_and_newlines()?;
        let mut words = None;
        if self.eat_reserved("in")? {
            let mut list = Vec::new();
            loop {
                self.skip_blanks();
                match self.peek() {
                    Some(b';') => {
                        self.bump(1);
                        break;
                    }
                    Some(b'\n') => {
                        self.newline()?;
                        break;
                    }
                    None => break,
                    _ => {}
                }
                match self.read_word(WordMode::Normal)? {
                    Some(word) => list.push(word),
                    None => return Err(self.unexpected()),
                }
            }
            words = Some(list);
        } else if self.peek() == Some(b';') {
            self.bump(1);
        }
        Ok((name, words))
    }

    fn parse_case(&mut self) -> Parsed<CompoundCommand> {
        self.skip_blanks();
        let Some(word) = self.read_word(WordMode::Normal)? else {
            return Err(self.unexpected());
        };
        self.skip_blanks_and_newlines()?;
        if !self.eat_reserved("in")? {
            return Err(self.unexpected());
        }
        let mut arms = Vec::new();
        loop {
            self.skip_blanks_and_newlines()?;
            if self.eat_reserved("esac")? {
                break;
            }
            if self.peek() == Some(b'(') {
                self.bump(1);
            }
            let mut patterns = Vec::new();
            loop {
                self.skip_blanks();
                let Some(pattern) = self.read_word(WordMode::Normal)? else {
                    return Err(self.unexpected());
                };
                patterns.push(pattern);
                self.skip_blanks();
                if self.peek() == Some(b'|') {
                    self.bump(1);
                    continue;
                }
                if self.peek() == Some(b')') {
                    self.bump(1);
                    break;
                }
                return Err(self.unexpected());
            }
            let body = self.parse_list()?;
            self.skip_blanks_and_newlines()?;
            let end = if self.eat(";;&") {
                CaseEnd::Continue
            } else if self.eat(";;") {
                CaseEnd::Break
            } else if self.eat(";&") {
                CaseEnd::FallThrough
            } else if self.reserved("esac") {
                CaseEnd::Break
            } else {
                return Err(self.unexpected());
            };
            arms.push(CaseArm {
                patterns,
                body,
                end,
            });
        }
        Ok(CompoundCommand::Case { word, arms })
    }

    fn parse_subshell(&mut self) -> Parsed<CompoundCommand> {
        self.bump(1);
        self.token(1)?;
        let body = self.parse_compound_list()?;
        self.skip_blanks_and_newlines()?;
        if !self.eat(")") {
            return Err(self.unexpected());
        }
        Ok(CompoundCommand::Subshell(body))
    }

    /// `(( expr ))`, or nothing when the text is two nested subshells.
    fn try_arith_command(&mut self, start: u32) -> Parsed<Option<CompoundCommand>> {
        let saved = self.save();
        self.bump(2);
        match self.read_inner(Inner::Arith, b"", false) {
            Ok(parts) if self.starts_with("))") => {
                let span = self.span_from(start);
                self.bump(2);
                self.token(4)?;
                let word = Word { parts, span };
                Ok(Some(CompoundCommand::Arith(word, span)))
            }
            Err(ParseError::Budget(which, limit)) => Err(ParseError::Budget(which, limit)),
            _ => {
                self.rewind(saved);
                Ok(None)
            }
        }
    }

    /// Where the parser stands, to go back to when a reading does not fit.
    fn save(&self) -> Saved {
        Saved {
            pos: self.pos,
            depth: self.depth,
            pending: self.pending.len(),
            heredocs: self.heredocs.len(),
        }
    }

    fn rewind(&mut self, saved: Saved) {
        self.pos = saved.pos;
        self.depth = saved.depth;
        self.pending.truncate(saved.pending);
        self.heredocs.truncate(saved.heredocs);
    }

    fn read_arith_clause(&mut self, end: u8) -> Parsed<Option<Word>> {
        let start = self.offset();
        let parts = self.read_inner(Inner::Arith, &[end], false)?;
        let span = self.span_from(start);
        if self.peek() != Some(end) {
            return Err(self.unexpected());
        }
        self.bump(1);
        let word = Word { parts, span };
        let empty = word
            .static_text()
            .is_some_and(|text| text.trim().is_empty());
        Ok(if empty { None } else { Some(word) })
    }

    fn try_function_def(&mut self, start: u32, start_pos: usize) -> Parsed<Option<Command>> {
        if self.assignment_ahead() {
            return Ok(None);
        }
        let mut end = self.pos;
        while let Some(byte) = self.bytes.get(end) {
            if is_meta(*byte) || matches!(byte, b' ' | b'\t' | b'\'' | b'"' | b'\\' | b'$' | b'`') {
                break;
            }
            end = end.saturating_add(1);
        }
        if end == self.pos {
            return Ok(None);
        }
        let mut probe = end;
        while matches!(self.bytes.get(probe), Some(b' ' | b'\t')) {
            probe = probe.saturating_add(1);
        }
        if self.bytes.get(probe) != Some(&b'(') {
            return Ok(None);
        }
        probe = probe.saturating_add(1);
        while matches!(self.bytes.get(probe), Some(b' ' | b'\t')) {
            probe = probe.saturating_add(1);
        }
        if self.bytes.get(probe) != Some(&b')') {
            return Ok(None);
        }
        let name = self.text(self.pos, end);
        self.pos = probe.saturating_add(1);
        self.token(name.len())?;
        self.parse_function_body(name, start, start_pos).map(Some)
    }

    fn parse_function_keyword(&mut self, start: u32, start_pos: usize) -> Parsed<Command> {
        self.skip_blanks();
        let Some(word) = self.read_word(WordMode::Normal)? else {
            return Err(self.unexpected());
        };
        let name = word.static_text().unwrap_or_default();
        self.skip_blanks();
        if self.peek() == Some(b'(') {
            self.bump(1);
            self.skip_blanks();
            if !self.eat(")") {
                return Err(self.unexpected());
            }
        }
        self.parse_function_body(name, start, start_pos)
    }

    fn parse_function_body(
        &mut self,
        name: String,
        start: u32,
        start_pos: usize,
    ) -> Parsed<Command> {
        self.skip_blanks_and_newlines()?;
        let Some(body) = self.parse_command()? else {
            return Err(self.unexpected());
        };
        if !matches!(body, Command::Compound(..)) {
            return Err(self.unexpected());
        }
        let text = self.text(start_pos, self.pos);
        Ok(Command::Function(Rc::new(FunctionDef {
            name,
            body,
            span: self.span_from(start),
            text,
        })))
    }

    // -- conditional expressions ---------------------------------------------

    fn parse_cond_or(&mut self) -> Parsed<CondExpr> {
        self.enter()?;
        let mut left = self.parse_cond_and()?;
        loop {
            self.skip_blanks_and_newlines()?;
            if !self.eat("||") {
                break;
            }
            self.token(2)?;
            let right = self.parse_cond_and()?;
            left = CondExpr::Or(Box::new(left), Box::new(right));
        }
        self.leave();
        Ok(left)
    }

    fn parse_cond_and(&mut self) -> Parsed<CondExpr> {
        self.enter()?;
        let mut left = self.parse_cond_not()?;
        loop {
            self.skip_blanks_and_newlines()?;
            if !self.eat("&&") {
                break;
            }
            self.token(2)?;
            let right = self.parse_cond_not()?;
            left = CondExpr::And(Box::new(left), Box::new(right));
        }
        self.leave();
        Ok(left)
    }

    fn parse_cond_not(&mut self) -> Parsed<CondExpr> {
        self.enter()?;
        self.skip_blanks_and_newlines()?;
        let expr = if self.reserved("!") {
            self.bump(1);
            CondExpr::Not(Box::new(self.parse_cond_not()?))
        } else {
            self.parse_cond_primary()?
        };
        self.leave();
        Ok(expr)
    }

    fn parse_cond_primary(&mut self) -> Parsed<CondExpr> {
        self.skip_blanks_and_newlines()?;
        if self.peek() == Some(b'(') {
            self.bump(1);
            let inner = self.parse_cond_or()?;
            self.skip_blanks_and_newlines()?;
            if !self.eat(")") {
                return Err(self.unexpected());
            }
            return Ok(inner);
        }
        if self.reserved("]]") || self.at_end() {
            return Err(self.unexpected());
        }
        let first = self.read_cond_word()?;
        self.skip_blanks();
        if let Some(op) = first.as_literal().filter(|op| is_unary_test(op)) {
            let op = op.to_owned();
            if self.reserved("]]")
                || self.starts_with("&&")
                || self.starts_with("||")
                || self.peek() == Some(b')')
            {
                let token = self.token_text().unwrap_or_default();
                return Err(self.error(format!(
                    "unexpected argument `{token}' to conditional unary operator"
                )));
            }
            let operand = self.read_cond_word()?;
            return Ok(CondExpr::Unary(op, operand));
        }
        let op = if self.eat("<") {
            Some("<".to_owned())
        } else if self.eat(">") {
            Some(">".to_owned())
        } else if self.reserved("]]")
            || self.starts_with("&&")
            || self.starts_with("||")
            || self.peek() == Some(b')')
        {
            None
        } else {
            let saved = self.pos;
            let word = self.read_cond_word()?;
            match word.as_literal() {
                Some(op) if is_binary_test(op) => Some(op.to_owned()),
                _ => {
                    self.pos = saved;
                    return Err(self.unexpected_cond());
                }
            }
        };
        let Some(op) = op else {
            return Ok(CondExpr::Word(first));
        };
        self.skip_blanks();
        if op == "=~" {
            let Some(regex) = self.read_word(WordMode::Regex)? else {
                return Err(self.unexpected_cond());
            };
            return Ok(CondExpr::Regex(first, regex));
        }
        let second = self.read_cond_word()?;
        Ok(CondExpr::Binary(first, op, second))
    }

    fn unexpected_cond(&self) -> ParseError {
        match self.token_text() {
            Some(token) => self.error(format!(
                "syntax error in conditional expression: unexpected token `{token}'"
            )),
            None => self.error("unexpected EOF while looking for `]]'".to_owned()),
        }
    }

    fn read_cond_word(&mut self) -> Parsed<Word> {
        self.skip_blanks_and_newlines()?;
        match self.read_word(WordMode::Normal)? {
            Some(word) => Ok(word),
            None => Err(self.unexpected_cond()),
        }
    }

    // -- redirections --------------------------------------------------------

    fn at_redirect(&self) -> bool {
        let mut probe = self.pos;
        while matches!(self.bytes.get(probe), Some(b'0'..=b'9')) {
            probe = probe.saturating_add(1);
        }
        if probe == self.pos && self.bytes.get(probe) == Some(&b'{') {
            let mut end = probe.saturating_add(1);
            while matches!(self.bytes.get(end), Some(b) if b.is_ascii_alphanumeric() || *b == b'_')
            {
                end = end.saturating_add(1);
            }
            if end > probe.saturating_add(1) && self.bytes.get(end) == Some(&b'}') {
                probe = end.saturating_add(1);
            }
        }
        match self.bytes.get(probe) {
            Some(b'<' | b'>') => self.bytes.get(probe.saturating_add(1)) != Some(&b'('),
            Some(b'&') if probe == self.pos => {
                self.bytes.get(probe.saturating_add(1)) == Some(&b'>')
            }
            _ => false,
        }
    }

    fn parse_redirect(&mut self) -> Parsed<Redirect> {
        let start = self.offset();
        let mut fd = RedirFd::Default;
        let digits_start = self.pos;
        while matches!(self.peek(), Some(b'0'..=b'9')) {
            self.bump(1);
        }
        if self.pos > digits_start {
            let number = self
                .text(digits_start, self.pos)
                .parse::<u32>()
                .unwrap_or(u32::MAX);
            fd = RedirFd::Number(number);
        } else if self.peek() == Some(b'{') {
            let name_start = self.pos.saturating_add(1);
            let mut end = name_start;
            while matches!(self.bytes.get(end), Some(b) if b.is_ascii_alphanumeric() || *b == b'_')
            {
                end = end.saturating_add(1);
            }
            fd = RedirFd::Variable(self.text(name_start, end));
            self.pos = end.saturating_add(1);
        }
        let op = if self.eat("<<<") {
            RedirOp::HereString
        } else if self.eat("<<-") {
            return self.parse_heredoc(fd, start, true);
        } else if self.eat("<<") {
            return self.parse_heredoc(fd, start, false);
        } else if self.eat("<&") {
            RedirOp::DupIn
        } else if self.eat("<>") {
            RedirOp::ReadWrite
        } else if self.eat("<") {
            RedirOp::Read
        } else if self.eat(">>") {
            RedirOp::Append
        } else if self.eat(">&") {
            RedirOp::DupOut
        } else if self.eat(">|") {
            RedirOp::Clobber
        } else if self.eat(">") {
            RedirOp::Write
        } else if self.eat("&>>") {
            RedirOp::AppendBoth
        } else if self.eat("&>") {
            RedirOp::WriteBoth
        } else {
            return Err(self.unexpected());
        };
        self.token(2)?;
        self.skip_blanks();
        let Some(word) = self.read_word(WordMode::Normal)? else {
            return Err(self.unexpected());
        };
        Ok(Redirect {
            fd,
            op,
            target: RedirTarget::Word(word),
            span: self.span_from(start),
        })
    }

    fn parse_heredoc(&mut self, fd: RedirFd, start: u32, strip_tabs: bool) -> Parsed<Redirect> {
        self.token(2)?;
        self.skip_blanks();
        let Some(word) = self.read_word(WordMode::Normal)? else {
            return Err(self.unexpected());
        };
        let quoted = word.has_quotes();
        let delimiter = delimiter_text(&word);
        let index = self.heredocs.len();
        self.heredocs.push(DocSlot {
            doc: HereDoc {
                body: Word::default(),
                quoted,
                strip_tabs,
            },
        });
        self.pending.push(PendingDoc {
            delimiter,
            strip_tabs,
            quoted,
            index,
        });
        Ok(Redirect {
            fd,
            op: RedirOp::HereDoc,
            target: RedirTarget::HereDoc(index),
            span: self.span_from(start),
        })
    }

    // -- assignments ---------------------------------------------------------

    /// Whether `name=`, `name+=`, `name[...]=` or `name[...]+=` is at the cursor.
    fn assignment_ahead(&self) -> bool {
        let mut probe = self.pos;
        match self.bytes.get(probe) {
            Some(b) if b.is_ascii_alphabetic() || *b == b'_' => {}
            _ => return false,
        }
        while matches!(self.bytes.get(probe), Some(b) if b.is_ascii_alphanumeric() || *b == b'_') {
            probe = probe.saturating_add(1);
        }
        if self.bytes.get(probe) == Some(&b'[') {
            let Some(end) = self.matching_bracket(probe) else {
                return false;
            };
            probe = end.saturating_add(1);
        }
        if self.bytes.get(probe) == Some(&b'+') {
            probe = probe.saturating_add(1);
        }
        self.bytes.get(probe) == Some(&b'=')
    }

    /// The index of the `]` that closes the `[` at `open`, skipping quotes.
    fn matching_bracket(&self, open: usize) -> Option<usize> {
        let mut depth = 0u32;
        let mut probe = open;
        loop {
            let byte = *self.bytes.get(probe)?;
            match byte {
                b'[' => depth = depth.saturating_add(1),
                b']' => {
                    depth = depth.saturating_sub(1);
                    if depth == 0 {
                        return Some(probe);
                    }
                }
                b'\\' => probe = probe.saturating_add(1),
                b'\'' | b'"' => {
                    probe = probe.saturating_add(1);
                    while *self.bytes.get(probe)? != byte {
                        probe = probe.saturating_add(1);
                    }
                }
                b' ' | b'\t' | b'\n' | b';' | b'&' | b'|' | b'<' | b'>' => return None,
                _ => {}
            }
            probe = probe.saturating_add(1);
        }
    }

    fn parse_assignment(&mut self) -> Parsed<Assignment> {
        let start = self.offset();
        let name_start = self.pos;
        while matches!(self.peek(), Some(b) if b.is_ascii_alphanumeric() || b == b'_') {
            self.bump(1);
        }
        let name = self.text(name_start, self.pos);
        let mut index = None;
        if self.peek() == Some(b'[') {
            self.bump(1);
            let sub_start = self.offset();
            let parts = self.read_inner(Inner::Subscript, b"", false)?;
            index = Some(Word {
                parts,
                span: self.span_from(sub_start),
            });
            if !self.eat("]") {
                return Err(self.unexpected());
            }
        }
        let append = self.eat("+");
        if !self.eat("=") {
            return Err(self.unexpected());
        }
        self.token(name.len())?;
        let value = if self.peek() == Some(b'(') {
            self.bump(1);
            AssignValue::Array(self.parse_array_elements()?)
        } else {
            let value_start = self.offset();
            let word = self.read_word(WordMode::Normal)?.unwrap_or(Word {
                parts: Vec::new(),
                span: self.span_from(value_start),
            });
            AssignValue::Scalar(word)
        };
        Ok(Assignment {
            name,
            index,
            append,
            value,
            span: self.span_from(start),
        })
    }

    fn parse_array_elements(&mut self) -> Parsed<Vec<ArrayElement>> {
        let mut elements = Vec::new();
        loop {
            self.skip_blanks_and_newlines()?;
            match self.peek() {
                None => return Err(self.eof_looking_for(')')),
                Some(b')') => {
                    self.bump(1);
                    return Ok(elements);
                }
                _ => {}
            }
            if self.peek() == Some(b'[')
                && let Some(close) = self.matching_bracket(self.pos)
            {
                let after = self.bytes.get(close.saturating_add(1)).copied();
                let after_plus = self.bytes.get(close.saturating_add(2)).copied();
                if after == Some(b'=') || (after == Some(b'+') && after_plus == Some(b'=')) {
                    self.bump(1);
                    let key_start = self.offset();
                    let parts = self.read_inner(Inner::Subscript, b"", false)?;
                    let key = Word {
                        parts,
                        span: self.span_from(key_start),
                    };
                    self.bump(1);
                    let append = self.eat("+");
                    self.bump(1);
                    let value_start = self.offset();
                    let value = self.read_word(WordMode::Normal)?.unwrap_or(Word {
                        parts: Vec::new(),
                        span: self.span_from(value_start),
                    });
                    elements.push(ArrayElement {
                        key: Some(key),
                        append,
                        value,
                    });
                    continue;
                }
            }
            let Some(value) = self.read_word(WordMode::Normal)? else {
                return Err(self.unexpected());
            };
            elements.push(ArrayElement {
                key: None,
                append: false,
                value,
            });
        }
    }

    // -- words ---------------------------------------------------------------

    fn read_word(&mut self, mode: WordMode) -> Parsed<Option<Word>> {
        self.enter()?;
        let start = self.offset();
        let start_pos = self.pos;
        let mut parts = Vec::new();
        let mut literal: Vec<u8> = Vec::new();
        let mut regex_depth = 0u32;
        while let Some(byte) = self.peek() {
            match byte {
                b' ' | b'\t' | b'\n' => break,
                b';' | b'&' | b'|' | b'<' | b'>' | b'(' | b')' => {
                    if matches!(byte, b'<' | b'>') && self.peek_at(1) == Some(b'(') {
                        flush(&mut literal, &mut parts);
                        parts.push(self.read_process_sub()?);
                        continue;
                    }
                    if byte == b'(' && literal.last().is_some_and(|last| b"?*+@!".contains(last)) {
                        self.read_extglob_group(&mut literal)?;
                        continue;
                    }
                    if mode == WordMode::Regex && matches!(byte, b'(' | b')' | b'|') {
                        if byte == b'(' {
                            regex_depth = regex_depth.saturating_add(1);
                        } else if byte == b')' {
                            if regex_depth == 0 {
                                break;
                            }
                            regex_depth = regex_depth.saturating_sub(1);
                        }
                        literal.push(byte);
                        self.bump(1);
                        continue;
                    }
                    if mode == WordMode::Regex
                        && regex_depth > 0
                        && matches!(byte, b'<' | b'>' | b'&' | b';')
                    {
                        literal.push(byte);
                        self.bump(1);
                        continue;
                    }
                    break;
                }
                b'\\' => match self.peek_at(1) {
                    Some(b'\n') => self.bump(2),
                    None => {
                        literal.push(b'\\');
                        self.bump(1);
                    }
                    Some(_) => {
                        flush(&mut literal, &mut parts);
                        self.bump(1);
                        let ch = self.peek_char().unwrap_or('\\');
                        self.bump(ch.len_utf8());
                        parts.push(WordPart::Escaped(ch));
                    }
                },
                b'\'' => {
                    flush(&mut literal, &mut parts);
                    parts.push(self.read_single()?);
                }
                b'"' => {
                    flush(&mut literal, &mut parts);
                    parts.push(self.read_double()?);
                }
                b'`' => {
                    flush(&mut literal, &mut parts);
                    parts.push(self.read_backquote(false)?);
                }
                b'$' => match self.read_dollar(false)? {
                    Some(part) => {
                        flush(&mut literal, &mut parts);
                        parts.push(part);
                    }
                    None => {
                        literal.push(b'$');
                        self.bump(1);
                    }
                },
                _ => {
                    literal.push(byte);
                    self.bump(1);
                }
            }
        }
        flush(&mut literal, &mut parts);
        self.leave();
        if self.pos == start_pos {
            return Ok(None);
        }
        self.token(self.pos.saturating_sub(start_pos))?;
        Ok(Some(Word {
            parts,
            span: self.span_from(start),
        }))
    }

    fn read_extglob_group(&mut self, literal: &mut Vec<u8>) -> Parsed<()> {
        let mut depth = 0u32;
        while let Some(byte) = self.peek() {
            match byte {
                b'(' => depth = depth.saturating_add(1),
                b')' => {
                    depth = depth.saturating_sub(1);
                    if depth == 0 {
                        literal.push(byte);
                        self.bump(1);
                        return Ok(());
                    }
                }
                b'\\' => {
                    literal.push(byte);
                    self.bump(1);
                    if let Some(next) = self.peek() {
                        literal.push(next);
                        self.bump(1);
                    }
                    continue;
                }
                b'\n' => break,
                _ => {}
            }
            literal.push(byte);
            self.bump(1);
        }
        Err(self.eof_looking_for(')'))
    }

    fn read_single(&mut self) -> Parsed<WordPart> {
        self.bump(1);
        let start = self.pos;
        while let Some(byte) = self.peek() {
            if byte == b'\'' {
                let text = self.text(start, self.pos);
                self.bump(1);
                return Ok(WordPart::Single(text));
            }
            self.bump(1);
        }
        Err(self.eof_looking_for('\''))
    }

    fn read_double(&mut self) -> Parsed<WordPart> {
        self.enter()?;
        self.bump(1);
        let mut parts = Vec::new();
        let mut literal: Vec<u8> = Vec::new();
        loop {
            let Some(byte) = self.peek() else {
                return Err(self.eof_looking_for('"'));
            };
            match byte {
                b'"' => {
                    self.bump(1);
                    break;
                }
                b'\\' => match self.peek_at(1) {
                    Some(b'\n') => self.bump(2),
                    Some(next @ (b'$' | b'`' | b'"' | b'\\')) => {
                        literal.push(next);
                        self.bump(2);
                    }
                    _ => {
                        literal.push(b'\\');
                        self.bump(1);
                    }
                },
                b'`' => {
                    flush(&mut literal, &mut parts);
                    parts.push(self.read_backquote(true)?);
                }
                b'$' => match self.read_dollar(true)? {
                    Some(part) => {
                        flush(&mut literal, &mut parts);
                        parts.push(part);
                    }
                    None => {
                        literal.push(b'$');
                        self.bump(1);
                    }
                },
                _ => {
                    literal.push(byte);
                    self.bump(1);
                }
            }
        }
        flush(&mut literal, &mut parts);
        self.leave();
        Ok(WordPart::Double(parts))
    }

    fn read_backquote(&mut self, in_double: bool) -> Parsed<WordPart> {
        let start = self.offset();
        self.bump(1);
        let mut text = String::new();
        loop {
            let Some(ch) = self.peek_char() else {
                return Err(self.eof_looking_for('`'));
            };
            self.bump(ch.len_utf8());
            match ch {
                '`' => break,
                '\\' => match self.peek_char() {
                    Some(next @ ('$' | '`' | '\\')) => {
                        text.push(next);
                        self.bump(1);
                    }
                    Some('"') if in_double => {
                        text.push('"');
                        self.bump(1);
                    }
                    _ => text.push('\\'),
                },
                _ => text.push(ch),
            }
        }
        let list = self.sub_list(&text, start)?;
        Ok(WordPart::CommandSub(Box::new(list), self.span_from(start)))
    }

    fn sub_list(&mut self, text: &str, base: u32) -> Parsed<List> {
        let mut sub = Parser::new(text, base, self.limits, self.depth);
        let list = sub.parse_list()?;
        sub.skip_blanks_and_newlines()?;
        if !sub.at_end() {
            return Err(sub.unexpected());
        }
        sub.finish_heredocs()?;
        self.absorb(&sub);
        if !sub.heredocs.is_empty() {
            return Err(self.error("here-document inside backquotes is not supported".to_owned()));
        }
        Ok(list)
    }

    fn read_process_sub(&mut self) -> Parsed<WordPart> {
        let start = self.offset();
        let input = self.peek() == Some(b'<');
        self.bump(2);
        let list = self.parse_list()?;
        self.skip_blanks_and_newlines()?;
        if !self.eat(")") {
            return Err(self.eof_looking_for(')'));
        }
        Ok(WordPart::ProcessSub(
            input,
            Box::new(list),
            self.span_from(start),
        ))
    }

    /// The expansion a `$` starts, or `None` when the `$` is literal.
    fn read_dollar(&mut self, in_double: bool) -> Parsed<Option<WordPart>> {
        let start = self.offset();
        match self.peek_at(1) {
            Some(b'\'') if !in_double => {
                self.bump(2);
                Ok(Some(WordPart::AnsiC(self.read_ansi_c()?)))
            }
            Some(b'"') if !in_double => {
                self.bump(1);
                self.read_double().map(Some)
            }
            Some(b'(') if self.peek_at(2) == Some(b'(') => {
                let saved = self.save();
                self.bump(3);
                match self.read_inner(Inner::Arith, b"", false) {
                    Ok(parts) if self.starts_with("))") => {
                        self.bump(2);
                        self.token(4)?;
                        let span = self.span_from(start);
                        return Ok(Some(WordPart::Arith(Box::new(Word { parts, span }), span)));
                    }
                    Err(ParseError::Budget(which, limit)) => {
                        return Err(ParseError::Budget(which, limit));
                    }
                    _ => {}
                }
                self.rewind(saved);
                self.read_command_sub(start).map(Some)
            }
            Some(b'(') => self.read_command_sub(start).map(Some),
            Some(b'{') => {
                self.bump(2);
                self.read_braced_param(start, in_double).map(Some)
            }
            Some(byte) if byte.is_ascii_alphabetic() || byte == b'_' => {
                self.bump(1);
                let name_start = self.pos;
                while matches!(self.peek(), Some(b) if b.is_ascii_alphanumeric() || b == b'_') {
                    self.bump(1);
                }
                let name = self.text(name_start, self.pos);
                self.token(name.len())?;
                Ok(Some(param_part(Param::Named(name), self.span_from(start))))
            }
            Some(byte @ b'0'..=b'9') => {
                self.bump(2);
                let param = if byte == b'0' {
                    Param::Special('0')
                } else {
                    Param::Positional(u32::from(byte.saturating_sub(b'0')))
                };
                Ok(Some(param_part(param, self.span_from(start))))
            }
            Some(byte @ (b'@' | b'*' | b'#' | b'?' | b'-' | b'$' | b'!')) => {
                self.bump(2);
                Ok(Some(param_part(
                    Param::Special(char::from(byte)),
                    self.span_from(start),
                )))
            }
            _ => Ok(None),
        }
    }

    fn read_command_sub(&mut self, start: u32) -> Parsed<WordPart> {
        self.bump(2);
        self.enter()?;
        let list = self.parse_list()?;
        self.skip_blanks_and_newlines()?;
        if !self.eat(")") {
            if self.at_end() {
                return Err(self.eof_looking_for(')'));
            }
            return Err(self.unexpected());
        }
        self.leave();
        Ok(WordPart::CommandSub(Box::new(list), self.span_from(start)))
    }

    fn read_ansi_c(&mut self) -> Parsed<String> {
        let mut out = String::new();
        let mut bytes_out: Vec<u8> = Vec::new();
        loop {
            let Some(byte) = self.peek() else {
                return Err(self.eof_looking_for('\''));
            };
            self.bump(1);
            match byte {
                b'\'' => break,
                b'\\' => {
                    let Some(next) = self.peek() else {
                        return Err(self.eof_looking_for('\''));
                    };
                    self.bump(1);
                    match next {
                        b'n' => bytes_out.push(b'\n'),
                        b't' => bytes_out.push(b'\t'),
                        b'r' => bytes_out.push(b'\r'),
                        b'a' => bytes_out.push(7),
                        b'b' => bytes_out.push(8),
                        b'e' | b'E' => bytes_out.push(27),
                        b'f' => bytes_out.push(12),
                        b'v' => bytes_out.push(11),
                        b'\\' => bytes_out.push(b'\\'),
                        b'\'' => bytes_out.push(b'\''),
                        b'"' => bytes_out.push(b'"'),
                        b'?' => bytes_out.push(b'?'),
                        b'0'..=b'7' => {
                            let mut value = u32::from(next.saturating_sub(b'0'));
                            for _ in 0..2 {
                                match self.peek() {
                                    Some(digit @ b'0'..=b'7') => {
                                        value = value
                                            .saturating_mul(8)
                                            .saturating_add(u32::from(digit.saturating_sub(b'0')));
                                        self.bump(1);
                                    }
                                    _ => break,
                                }
                            }
                            bytes_out.push(u8::try_from(value & 0xff).unwrap_or(0));
                        }
                        b'x' => {
                            let value = self.read_hex(2);
                            match value {
                                Some(value) => {
                                    bytes_out.push(u8::try_from(value & 0xff).unwrap_or(0))
                                }
                                None => bytes_out.extend_from_slice(b"\\x"),
                            }
                        }
                        b'u' | b'U' => {
                            let width = if next == b'u' { 4 } else { 8 };
                            match self.read_hex(width).and_then(char::from_u32) {
                                Some(ch) => {
                                    let mut buffer = [0u8; 4];
                                    bytes_out
                                        .extend_from_slice(ch.encode_utf8(&mut buffer).as_bytes());
                                }
                                None => {
                                    bytes_out.push(b'\\');
                                    bytes_out.push(next);
                                }
                            }
                        }
                        b'c' => {
                            if let Some(control) = self.peek() {
                                self.bump(1);
                                bytes_out.push(control & 0x1f);
                            }
                        }
                        other => {
                            bytes_out.push(b'\\');
                            bytes_out.push(other);
                        }
                    }
                }
                other => bytes_out.push(other),
            }
        }
        out.push_str(&String::from_utf8_lossy(&bytes_out));
        self.token(out.len())?;
        Ok(out)
    }

    fn read_hex(&mut self, width: usize) -> Option<u32> {
        let mut value: u32 = 0;
        let mut count = 0usize;
        while count < width {
            let Some(digit) = self.peek().and_then(|byte| char::from(byte).to_digit(16)) else {
                break;
            };
            value = value.saturating_mul(16).saturating_add(digit);
            self.bump(1);
            count = count.saturating_add(1);
        }
        if count == 0 { None } else { Some(value) }
    }

    // -- parameter expansion -------------------------------------------------

    fn read_braced_param(&mut self, start: u32, in_double: bool) -> Parsed<WordPart> {
        self.enter()?;
        let expansion = self.read_braced_param_inner(start, in_double)?;
        self.leave();
        self.token(4)?;
        Ok(WordPart::Param(Box::new(expansion)))
    }

    fn read_braced_param_inner(&mut self, start: u32, in_double: bool) -> Parsed<ParamExp> {
        // `${#}` and `${#name}`.
        if self.peek() == Some(b'#') {
            match self.peek_at(1) {
                Some(b'}') => {
                    self.bump(2);
                    return Ok(plain(Param::Special('#'), start, self.span_from(start)));
                }
                Some(b) if b.is_ascii_alphanumeric() || b"_@*#?-$!".contains(&b) => {
                    let after_hash = self.peek_at(2);
                    let is_length = !(matches!(b, b'-' | b'?' | b'#') && after_hash != Some(b'}'));
                    if is_length {
                        self.bump(1);
                        let param = self.read_param_name()?;
                        if !self.eat("}") {
                            let op = self.invalid_param(start)?;
                            return Ok(ParamExp {
                                param,
                                indirect: false,
                                op,
                                span: self.span_from(start),
                            });
                        }
                        return Ok(ParamExp {
                            param,
                            indirect: false,
                            op: ParamOp::Length,
                            span: self.span_from(start),
                        });
                    }
                }
                _ => {}
            }
        }
        let mut indirect = false;
        if self.peek() == Some(b'!') && !matches!(self.peek_at(1), Some(b'}')) {
            indirect = true;
            self.bump(1);
        }
        let param = self.read_param_name()?;
        if indirect {
            if let Param::Named(name) = &param
                && matches!(self.peek(), Some(b'*' | b'@'))
                && self.peek_at(1) == Some(b'}')
            {
                let at = self.peek() == Some(b'@');
                self.bump(2);
                return Ok(ParamExp {
                    param: Param::Named(name.clone()),
                    indirect: false,
                    op: ParamOp::PrefixNames(at),
                    span: self.span_from(start),
                });
            }
            if let Param::Element(name, subscript) = &param
                && self.peek() == Some(b'}')
                && let Some(text) = subscript
                    .as_literal()
                    .filter(|text| *text == "@" || *text == "*")
            {
                let at = text == "@";
                self.bump(1);
                return Ok(ParamExp {
                    param: Param::Named(name.clone()),
                    indirect: false,
                    op: ParamOp::Keys(at),
                    span: self.span_from(start),
                });
            }
        }
        let op = self.read_param_op(start, in_double)?;
        Ok(ParamExp {
            param,
            indirect,
            op,
            span: self.span_from(start),
        })
    }

    fn read_param_name(&mut self) -> Parsed<Param> {
        match self.peek() {
            Some(b) if b.is_ascii_alphabetic() || b == b'_' => {
                let name_start = self.pos;
                while matches!(self.peek(), Some(b) if b.is_ascii_alphanumeric() || b == b'_') {
                    self.bump(1);
                }
                let name = self.text(name_start, self.pos);
                if self.peek() == Some(b'[') {
                    self.bump(1);
                    let sub_start = self.offset();
                    let parts = self.read_inner(Inner::Subscript, b"", false)?;
                    let subscript = Word {
                        parts,
                        span: self.span_from(sub_start),
                    };
                    if !self.eat("]") {
                        return Err(self.eof_looking_for(']'));
                    }
                    return Ok(Param::Element(name, Box::new(subscript)));
                }
                Ok(Param::Named(name))
            }
            Some(b'0') => {
                self.bump(1);
                Ok(Param::Special('0'))
            }
            Some(b'1'..=b'9') => {
                let digits_start = self.pos;
                while matches!(self.peek(), Some(b'0'..=b'9')) {
                    self.bump(1);
                }
                let number = self
                    .text(digits_start, self.pos)
                    .parse::<u32>()
                    .unwrap_or(u32::MAX);
                Ok(Param::Positional(number))
            }
            Some(b @ (b'@' | b'*' | b'#' | b'?' | b'-' | b'$' | b'!')) => {
                self.bump(1);
                Ok(Param::Special(char::from(b)))
            }
            _ => Ok(Param::Named(String::new())),
        }
    }

    fn read_param_op(&mut self, start: u32, in_double: bool) -> Parsed<ParamOp> {
        let Some(byte) = self.peek() else {
            return Err(self.eof_looking_for('}'));
        };
        let op = match byte {
            b'}' => {
                self.bump(1);
                return Ok(ParamOp::Plain);
            }
            b':' => match self.peek_at(1) {
                Some(kind @ (b'-' | b'=' | b'?' | b'+')) => {
                    self.bump(2);
                    let word = self.read_param_word(b"}", in_double, true)?;
                    ParamOp::Default {
                        colon: true,
                        kind: default_kind(kind),
                        word,
                    }
                }
                _ => {
                    self.bump(1);
                    let offset = self.read_param_word(b":}", in_double, false)?;
                    let length = if self.peek() == Some(b':') {
                        self.bump(1);
                        Some(self.read_param_word(b"}", in_double, false)?)
                    } else {
                        None
                    };
                    ParamOp::Substring { offset, length }
                }
            },
            b'-' | b'=' | b'?' | b'+' => {
                self.bump(1);
                let word = self.read_param_word(b"}", in_double, true)?;
                ParamOp::Default {
                    colon: false,
                    kind: default_kind(byte),
                    word,
                }
            }
            b'#' | b'%' => {
                self.bump(1);
                let longest = self.peek() == Some(byte);
                if longest {
                    self.bump(1);
                }
                let pattern = self.read_param_word(b"}", in_double, false)?;
                if byte == b'#' {
                    ParamOp::RemovePrefix { longest, pattern }
                } else {
                    ParamOp::RemoveSuffix { longest, pattern }
                }
            }
            b'/' => {
                self.bump(1);
                let kind = match self.peek() {
                    Some(b'/') => {
                        self.bump(1);
                        ReplaceKind::All
                    }
                    Some(b'#') => {
                        self.bump(1);
                        ReplaceKind::Prefix
                    }
                    Some(b'%') => {
                        self.bump(1);
                        ReplaceKind::Suffix
                    }
                    _ => ReplaceKind::First,
                };
                let pattern = self.read_param_word(b"/}", in_double, false)?;
                let replacement = if self.peek() == Some(b'/') {
                    self.bump(1);
                    Some(self.read_param_word(b"}", in_double, false)?)
                } else {
                    None
                };
                ParamOp::Replace {
                    kind,
                    pattern,
                    replacement,
                }
            }
            b'^' | b',' | b'~' => {
                self.bump(1);
                let all = self.peek() == Some(byte);
                if all {
                    self.bump(1);
                }
                let pattern = self.read_param_word(b"}", in_double, false)?;
                let pattern = if pattern.parts.is_empty() {
                    None
                } else {
                    Some(pattern)
                };
                ParamOp::Case {
                    upper: byte == b'^',
                    all,
                    toggle: byte == b'~',
                    pattern,
                }
            }
            b'@' => {
                self.bump(1);
                let Some(ch) = self.peek_char() else {
                    return Err(self.eof_looking_for('}'));
                };
                self.bump(ch.len_utf8());
                if self.peek() != Some(b'}') {
                    return self.invalid_param(start);
                }
                ParamOp::Transform(ch)
            }
            _ => return self.invalid_param(start),
        };
        if !self.eat("}") {
            return Err(self.eof_looking_for('}'));
        }
        Ok(op)
    }

    /// Skip to the closing brace of a substitution bash cannot expand.
    fn invalid_param(&mut self, start: u32) -> Parsed<ParamOp> {
        let begin = usize::try_from(start.saturating_sub(self.base)).unwrap_or(0);
        while let Some(byte) = self.peek() {
            self.bump(1);
            if byte == b'}' {
                return Ok(ParamOp::Invalid(self.text(begin, self.pos)));
            }
        }
        Err(self.eof_looking_for('}'))
    }

    fn read_param_word(
        &mut self,
        stops: &[u8],
        in_double: bool,
        default_word: bool,
    ) -> Parsed<Word> {
        let start = self.offset();
        let parts = self.read_inner(Inner::Param, stops, in_double && default_word)?;
        Ok(Word {
            parts,
            span: self.span_from(start),
        })
    }

    /// Text inside `${...}`, `$((...))`, a subscript or a here-document body.
    fn read_inner(
        &mut self,
        inner: Inner,
        stops: &[u8],
        literal_single: bool,
    ) -> Parsed<Vec<WordPart>> {
        self.enter()?;
        let mut parts = Vec::new();
        let mut literal: Vec<u8> = Vec::new();
        let mut depth = 0u32;
        loop {
            let Some(byte) = self.peek() else {
                if inner == Inner::HereDoc {
                    break;
                }
                let close = match inner {
                    Inner::Arith => ')',
                    Inner::Subscript => ']',
                    _ => '}',
                };
                return Err(self.eof_looking_for(close));
            };
            if depth == 0 {
                let stop = match inner {
                    Inner::Param => stops.contains(&byte),
                    Inner::Arith => {
                        (byte == b')' && self.peek_at(1) == Some(b')'))
                            || (byte != b')' && stops.contains(&byte))
                            || (byte == b')' && stops.contains(&byte))
                    }
                    Inner::Subscript => byte == b']',
                    Inner::HereDoc => false,
                };
                if stop {
                    break;
                }
            }
            match byte {
                b'\\' => {
                    let next = self.peek_at(1);
                    if next == Some(b'\n') {
                        self.bump(2);
                        continue;
                    }
                    let escapable = match inner {
                        Inner::HereDoc | Inner::Arith => matches!(next, Some(b'$' | b'`' | b'\\')),
                        _ => next.is_some(),
                    };
                    if escapable {
                        flush(&mut literal, &mut parts);
                        self.bump(1);
                        let ch = self.peek_char().unwrap_or('\\');
                        self.bump(ch.len_utf8());
                        parts.push(WordPart::Escaped(ch));
                    } else {
                        literal.push(b'\\');
                        self.bump(1);
                    }
                }
                b'\'' if matches!(inner, Inner::Param | Inner::Subscript) && !literal_single => {
                    flush(&mut literal, &mut parts);
                    parts.push(self.read_single()?);
                }
                b'"' if inner != Inner::HereDoc => {
                    flush(&mut literal, &mut parts);
                    parts.push(self.read_double()?);
                }
                b'`' => {
                    flush(&mut literal, &mut parts);
                    parts.push(self.read_backquote(false)?);
                }
                b'$' => match self.read_dollar(inner == Inner::HereDoc)? {
                    Some(part) => {
                        flush(&mut literal, &mut parts);
                        parts.push(part);
                    }
                    None => {
                        literal.push(b'$');
                        self.bump(1);
                    }
                },
                _ => {
                    match (inner, byte) {
                        (Inner::Arith, b'(') | (Inner::Subscript, b'[') | (Inner::Param, b'{') => {
                            depth = depth.saturating_add(1);
                        }
                        (Inner::Arith, b')') | (Inner::Subscript, b']') | (Inner::Param, b'}') => {
                            depth = depth.saturating_sub(1);
                        }
                        _ => {}
                    }
                    literal.push(byte);
                    self.bump(1);
                }
            }
        }
        flush(&mut literal, &mut parts);
        self.leave();
        Ok(parts)
    }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

fn is_meta(byte: u8) -> bool {
    matches!(byte, b'\n' | b';' | b'&' | b'|' | b'(' | b')' | b'<' | b'>')
}

/// Whether `text` is a shell name: a letter or underscore, then word characters.
pub fn is_name(text: &str) -> bool {
    let mut chars = text.chars();
    match chars.next() {
        Some(first) if first.is_ascii_alphabetic() || first == '_' => {}
        _ => return false,
    }
    chars.all(|ch| ch.is_ascii_alphanumeric() || ch == '_')
}

fn flush(literal: &mut Vec<u8>, parts: &mut Vec<WordPart>) {
    if literal.is_empty() {
        return;
    }
    let text = String::from_utf8_lossy(literal).into_owned();
    literal.clear();
    parts.push(WordPart::Literal(text));
}

fn param_part(param: Param, span: Span) -> WordPart {
    WordPart::Param(Box::new(ParamExp {
        param,
        indirect: false,
        op: ParamOp::Plain,
        span,
    }))
}

fn plain(param: Param, _start: u32, span: Span) -> ParamExp {
    ParamExp {
        param,
        indirect: false,
        op: ParamOp::Plain,
        span,
    }
}

fn default_kind(byte: u8) -> DefaultKind {
    match byte {
        b'=' => DefaultKind::Assign,
        b'?' => DefaultKind::Error,
        b'+' => DefaultKind::Alternative,
        _ => DefaultKind::Use,
    }
}

/// A here-document delimiter with its quotes removed.
fn delimiter_text(word: &Word) -> String {
    let mut out = String::new();
    for part in &word.parts {
        match part {
            WordPart::Literal(text) | WordPart::Single(text) | WordPart::AnsiC(text) => {
                out.push_str(text)
            }
            WordPart::Escaped(ch) => out.push(*ch),
            WordPart::Double(inner) => {
                for piece in inner {
                    if let WordPart::Literal(text) = piece {
                        out.push_str(text);
                    }
                }
            }
            WordPart::Param(expansion) => {
                out.push('$');
                if let Param::Named(name) = &expansion.param {
                    out.push_str(name);
                }
            }
            _ => {}
        }
    }
    out
}

fn is_unary_test(op: &str) -> bool {
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
            | "-o"
            | "-v"
            | "-R"
    )
}

fn is_binary_test(op: &str) -> bool {
    matches!(
        op,
        "==" | "="
            | "!="
            | "=~"
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
