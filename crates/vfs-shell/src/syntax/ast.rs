//! The tree a line parses to. Every node that can fail at run time carries
//! its span, so a host can name the programs, paths and globs of a line
//! before anything runs, and an error can name where it happened.

/// A byte range of the source.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Span {
    pub start: u32,
    pub end: u32,
}

/// A whole parsed line: its commands and the source they came from.
#[derive(Clone, Debug)]
pub struct Script {
    pub body: List,
    /// Byte offset of the start of each source line, for line numbers.
    pub line_starts: Vec<u32>,
    /// The here-document bodies, in the order their redirections appear.
    pub heredocs: Vec<HereDoc>,
    /// Bytes the tree holds, as the parser counted them.
    pub footprint: usize,
}

impl Script {
    /// The 1-based line of a byte offset.
    pub fn line_of(&self, offset: u32) -> u32 {
        let index = self.line_starts.partition_point(|start| *start <= offset);
        u32::try_from(index).unwrap_or(u32::MAX).max(1)
    }
}

/// Commands separated by `;`, `&` or newlines.
#[derive(Clone, Debug, Default)]
pub struct List {
    pub items: Vec<ListItem>,
}

#[derive(Clone, Debug)]
pub struct ListItem {
    pub and_or: AndOr,
    /// Ended by `&`: runs beside what follows.
    pub background: bool,
}

/// Pipelines joined by `&&` and `||`.
#[derive(Clone, Debug)]
pub struct AndOr {
    pub first: Pipeline,
    pub rest: Vec<(Connector, Pipeline)>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Connector {
    And,
    Or,
}

#[derive(Clone, Debug)]
pub struct Pipeline {
    pub negated: bool,
    /// `time` before the pipeline, with `-p` or not.
    pub timed: Option<bool>,
    pub stages: Vec<Stage>,
    pub span: Span,
}

#[derive(Clone, Debug)]
pub struct Stage {
    pub command: Command,
    /// Joined to the next stage by `|&`: standard error goes down the pipe too.
    pub pipe_stderr: bool,
}

#[derive(Clone, Debug)]
pub enum Command {
    Simple(SimpleCommand),
    Compound(Box<CompoundCommand>, Vec<Redirect>),
    Function(std::rc::Rc<FunctionDef>),
}

#[derive(Clone, Debug)]
pub struct SimpleCommand {
    pub assignments: Vec<Assignment>,
    pub words: Vec<Arg>,
    pub redirects: Vec<Redirect>,
    pub span: Span,
}

/// An argument: a word, or an assignment given to a declaration builtin.
#[derive(Clone, Debug)]
pub enum Arg {
    Word(Word),
    Assign(Assignment),
}

#[derive(Clone, Debug)]
pub struct Assignment {
    pub name: String,
    pub index: Option<Word>,
    pub append: bool,
    pub value: AssignValue,
    pub span: Span,
}

#[derive(Clone, Debug)]
pub enum AssignValue {
    Scalar(Word),
    Array(Vec<ArrayElement>),
}

#[derive(Clone, Debug)]
pub struct ArrayElement {
    pub key: Option<Word>,
    pub append: bool,
    pub value: Word,
}

#[derive(Clone, Debug)]
pub enum CompoundCommand {
    Brace(List),
    Subshell(List),
    If {
        branches: Vec<(List, List)>,
        otherwise: Option<List>,
    },
    While {
        until: bool,
        condition: List,
        body: List,
    },
    For {
        name: String,
        words: Option<Vec<Word>>,
        body: List,
        span: Span,
    },
    ArithFor {
        init: Option<Word>,
        test: Option<Word>,
        step: Option<Word>,
        body: List,
        span: Span,
    },
    Select {
        name: String,
        words: Option<Vec<Word>>,
        body: List,
        span: Span,
    },
    Case {
        word: Word,
        arms: Vec<CaseArm>,
    },
    Arith(Word, Span),
    Cond(CondExpr, Span),
}

#[derive(Clone, Debug)]
pub struct CaseArm {
    pub patterns: Vec<Word>,
    pub body: List,
    pub end: CaseEnd,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CaseEnd {
    /// `;;`
    Break,
    /// `;&`
    FallThrough,
    /// `;;&`
    Continue,
}

#[derive(Debug)]
pub struct FunctionDef {
    pub name: String,
    pub body: Command,
    pub span: Span,
    /// The definition's own source text, for `declare -f` and `type`.
    pub text: String,
}

#[derive(Clone, Debug)]
pub struct Redirect {
    pub fd: RedirFd,
    pub op: RedirOp,
    pub target: RedirTarget,
    pub span: Span,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum RedirFd {
    Default,
    Number(u32),
    /// `{name}>file`: the shell picks the descriptor and stores it in `name`.
    Variable(String),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RedirOp {
    /// `<`
    Read,
    /// `>`
    Write,
    /// `>>`
    Append,
    /// `>|`
    Clobber,
    /// `<>`
    ReadWrite,
    /// `<&`
    DupIn,
    /// `>&`
    DupOut,
    /// `&>`
    WriteBoth,
    /// `&>>`
    AppendBoth,
    /// `<<` and `<<-`
    HereDoc,
    /// `<<<`
    HereString,
}

#[derive(Clone, Debug)]
pub enum RedirTarget {
    Word(Word),
    /// An index into [`Script::heredocs`]; a body is read after its line ends.
    HereDoc(usize),
}

#[derive(Clone, Debug)]
pub struct HereDoc {
    /// The body; when the delimiter was quoted it holds one literal part.
    pub body: Word,
    pub quoted: bool,
    pub strip_tabs: bool,
}

/// A word before expansion: a sequence of parts.
#[derive(Clone, Debug, Default)]
pub struct Word {
    pub parts: Vec<WordPart>,
    pub span: Span,
}

impl Word {
    /// The word's text when it is one unquoted literal, as reserved words are.
    pub fn as_literal(&self) -> Option<&str> {
        match self.parts.as_slice() {
            [WordPart::Literal(text)] => Some(text),
            _ => None,
        }
    }

    /// The word with its quotes removed, when it holds no expansion.
    pub fn static_text(&self) -> Option<String> {
        let mut out = String::new();
        for part in &self.parts {
            if !part.push_static(&mut out) {
                return None;
            }
        }
        Some(out)
    }

    /// Whether any part of the word is quoted.
    pub fn has_quotes(&self) -> bool {
        self.parts.iter().any(|part| {
            matches!(
                part,
                WordPart::Single(_)
                    | WordPart::AnsiC(_)
                    | WordPart::Double(_)
                    | WordPart::Escaped(_)
            )
        })
    }
}

#[derive(Clone, Debug)]
pub enum WordPart {
    /// Unquoted text: it may hold glob characters, braces and a tilde.
    Literal(String),
    /// A backslash-escaped character outside quotes.
    Escaped(char),
    /// `'...'`
    Single(String),
    /// `$'...'`, already decoded.
    AnsiC(String),
    /// `"..."` and `$"..."`; its literal parts are quoted text.
    Double(Vec<WordPart>),
    Param(Box<ParamExp>),
    /// `$(...)` or a backquoted command.
    CommandSub(Box<List>, Span),
    /// `$((...))`: the expression is expanded, then evaluated.
    Arith(Box<Word>, Span),
    /// `<(...)` or `>(...)`.
    ProcessSub(bool, Box<List>, Span),
}

impl WordPart {
    fn push_static(&self, out: &mut String) -> bool {
        match self {
            WordPart::Literal(text) | WordPart::Single(text) | WordPart::AnsiC(text) => {
                out.push_str(text)
            }
            WordPart::Escaped(ch) => out.push(*ch),
            WordPart::Double(parts) => {
                for part in parts {
                    if !part.push_static(out) {
                        return false;
                    }
                }
            }
            _ => return false,
        }
        true
    }
}

#[derive(Clone, Debug)]
pub struct ParamExp {
    pub param: Param,
    /// `${!name...}`: the value names the parameter to expand.
    pub indirect: bool,
    pub op: ParamOp,
    pub span: Span,
}

#[derive(Clone, Debug)]
pub enum Param {
    Named(String),
    Positional(u32),
    /// One of `@ * # ? - $ ! 0`.
    Special(char),
    /// `name[subscript]`; `@` and `*` subscripts are kept as words too.
    Element(String, Box<Word>),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DefaultKind {
    /// `-`
    Use,
    /// `=`
    Assign,
    /// `?`
    Error,
    /// `+`
    Alternative,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ReplaceKind {
    First,
    All,
    Prefix,
    Suffix,
}

#[derive(Clone, Debug)]
pub enum ParamOp {
    Plain,
    /// `${#x}`
    Length,
    Default {
        colon: bool,
        kind: DefaultKind,
        word: Word,
    },
    RemovePrefix {
        longest: bool,
        pattern: Word,
    },
    RemoveSuffix {
        longest: bool,
        pattern: Word,
    },
    Substring {
        offset: Word,
        length: Option<Word>,
    },
    Replace {
        kind: ReplaceKind,
        pattern: Word,
        replacement: Option<Word>,
    },
    Case {
        upper: bool,
        all: bool,
        toggle: bool,
        pattern: Option<Word>,
    },
    /// `${x@Q}` and the other transforms.
    Transform(char),
    /// `${!prefix*}` or `${!prefix@}`.
    PrefixNames(bool),
    /// `${!name[@]}` or `${!name[*]}`.
    Keys(bool),
    /// Text bash parses but cannot expand; it fails when it runs.
    Invalid(String),
}

#[derive(Clone, Debug)]
pub enum CondExpr {
    Unary(String, Word),
    Binary(Word, String, Word),
    /// `=~`: the right side is a regular expression.
    Regex(Word, Word),
    Word(Word),
    Not(Box<CondExpr>),
    And(Box<CondExpr>, Box<CondExpr>),
    Or(Box<CondExpr>, Box<CondExpr>),
}
