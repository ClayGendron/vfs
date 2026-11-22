//! GNU `sed`, as a pure function over input already read: [`inputs`] names
//! the files a run will read, the caller reads them, and [`run`] runs the
//! script over their bytes and says what to print and what to write.
//!
//! ```text
//! sed -n '/TODO/{s/TODO: //;p}' notes.txt
//! ```

use std::collections::{BTreeMap, BTreeSet};

use crate::machine::regex::{Captures, Regex, bre_to_ere};

/// The files a run was given: each name maps to its bytes or the error text a read gave.
type Files = BTreeMap<String, Result<Vec<u8>, String>>;

/// Columns the `l` command wraps at when neither it nor `-l` names a width.
const LIST_WIDTH: usize = 70;
/// Commands a run may execute without reading a line: a script that loops forever stops here.
const STEP_BUDGET: u64 = 50_000_000;
/// Bytes the pattern and hold spaces may hold between them beyond a multiple of the input,
/// so a script that doubles them without end stops while any script bounded by its input runs.
const SPACE_FLOOR: usize = 64 << 20;
/// How many times its input a script's spaces may hold, over the floor.
const SPACE_PER_INPUT: usize = 8;
/// GNU's complaint about text after a command that takes none.
const EXTRA_CHARACTERS: &str = "extra characters after command";
/// The status of a read error, which ends the run as GNU's does.
const READ_ERROR: i32 = 4;
/// The long options, for GNU's unambiguous-prefix matching.
const LONG_OPTIONS: &[&str] = &[
    "binary",
    "debug",
    "expression",
    "file",
    "follow-symlinks",
    "help",
    "in-place",
    "line-length",
    "null-data",
    "posix",
    "quiet",
    "regexp-extended",
    "sandbox",
    "separate",
    "silent",
    "unbuffered",
    "version",
    "zero-terminated",
];
const USAGE: &str = "Usage: sed [OPTION]... {script-only-if-no-other-script} [input-file]...

  -n, --quiet, --silent
                 suppress automatic printing of pattern space
      --debug
                 annotate program execution
  -e script, --expression=script
                 add the script to the commands to be executed
  -f script-file, --file=script-file
                 add the contents of script-file to the commands to be executed
  --follow-symlinks
                 follow symlinks when processing in place
  -i[SUFFIX], --in-place[=SUFFIX]
                 edit files in place (makes backup if SUFFIX supplied)
  -l N, --line-length=N
                 specify the desired line-wrap length for the `l' command
  --posix
                 disable all GNU extensions.
  -E, -r, --regexp-extended
                 use extended regular expressions in the script
                 (for portability use POSIX -E).
  -s, --separate
                 consider files as separate rather than as a single,
                 continuous long stream.
      --sandbox
                 operate in sandbox mode (disable e/r/w commands).
  -u, --unbuffered
                 load minimal amounts of data from the input files and flush
                 the output buffers more often
  -z, --null-data
                 separate lines by NUL characters
      --help     display this help and exit
      --version  output version information and exit

If no -e, --expression, -f, or --file option is given, then the first
non-option argument is taken as the sed script to interpret.  All
remaining arguments are names of input files; if no input files are
specified, then the standard input is read.

GNU sed home page: <https://www.gnu.org/software/sed/>.
General help using GNU software: <https://www.gnu.org/gethelp/>.
";
/// The line `--help` adds after the usage text.
const BUGS: &str = "E-mail bug reports to: <bug-sed@gnu.org>.\n";
const VERSION: &str = "sed (GNU sed) 4.9
Copyright (C) 2022 Free Software Foundation, Inc.
License GPLv3+: GNU GPL version 3 or later <https://gnu.org/licenses/gpl.html>.
This is free software: you are free to change and redistribute it.
There is NO WARRANTY, to the extent permitted by law.

Written by Jay Fenlason, Tom Lord, Ken Pizzini,
Paolo Bonzini, Jim Meyering, and Assaf Gordon.

This sed program was built without SELinux support.

GNU sed home page: <https://www.gnu.org/software/sed/>.
General help using GNU software: <https://www.gnu.org/gethelp/>.
E-mail bug reports to: <bug-sed@gnu.org>.
";

/// What a `sed` run produced.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct SedOutput {
    pub stdout: Vec<u8>,
    pub stderr: Vec<u8>,
    pub status: i32,
    /// Files to write whole, in order: each `-i` result after its backup, then the `w` targets,
    /// by the path as given.
    pub writes: Vec<SedWrite>,
}

/// One file `sed` writes whole.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SedWrite {
    pub path: String,
    pub data: Vec<u8>,
    pub kind: WriteKind,
}

/// What a write is for, so a refused backup can stop the edit it guards.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum WriteKind {
    /// The backup `-i` makes of `source` before it replaces it.
    Backup { source: String },
    /// The edited body `-i` writes over its source.
    InPlace,
    /// A `w` or `W` target.
    Script,
}

// ---------------------------------------------------------------------------
// The entry points
// ---------------------------------------------------------------------------

/// The files `sed` will read for `args` (operands, `-` for standard input,
/// the targets of `r` and `R`, and `-f` script files), or the output of a
/// usage or script error. The `r` and `R` targets inside a `-f` script are
/// not known before the script is read, so they are not named.
pub fn inputs(args: &[String]) -> Result<Vec<String>, SedOutput> {
    let options = Options::parse(args)?;
    let mut names = options.operand_names();
    let scripts: Vec<String> = options
        .sources
        .iter()
        .filter_map(|source| match source {
            Source::File(name) => Some(name.clone()),
            Source::Expr(_) => None,
        })
        .collect();
    if scripts.is_empty() {
        let program = compile(&options, &Files::new(), &[])?;
        names.extend(program.reads);
    }
    names.extend(scripts);
    let mut seen = BTreeSet::new();
    names.retain(|name| seen.insert(name.clone()));
    Ok(names)
}

/// Run `sed` over files already read: each name from [`inputs`] maps to its
/// bytes or the error text a read of it gave.
pub fn run(
    args: &[String],
    stdin: &[u8],
    files: &BTreeMap<String, Result<Vec<u8>, String>>,
) -> SedOutput {
    let options = match Options::parse(args) {
        Ok(options) => options,
        Err(output) => return output,
    };
    let program = match compile(&options, files, stdin) {
        Ok(program) => program,
        Err(output) => return output,
    };
    Machine::new(&options, &program, files).process(stdin)
}

// ---------------------------------------------------------------------------
// Options
// ---------------------------------------------------------------------------

/// One piece of the script, in the order the options gave it.
#[derive(Clone, Debug)]
enum Source {
    Expr(String),
    File(String),
}

#[derive(Clone, Debug, Default)]
struct Options {
    quiet: bool,
    extended: bool,
    separate: bool,
    null_data: bool,
    /// The backup suffix of `-i`, empty for none.
    in_place: Option<String>,
    line_width: usize,
    sources: Vec<Source>,
    operands: Vec<String>,
    /// `--sandbox`: the script may not name a file or a command.
    sandbox: bool,
}

impl Options {
    /// Parse the arguments the way GNU's getopt does: options may follow operands until `--`.
    fn parse(args: &[String]) -> Result<Options, SedOutput> {
        let mut options = Options {
            line_width: LIST_WIDTH,
            ..Options::default()
        };
        let mut rest = args.iter();
        let mut operands_only = false;
        while let Some(arg) = rest.next() {
            if operands_only || arg == "-" || !arg.starts_with('-') {
                options.operands.push(arg.clone());
                continue;
            }
            if arg == "--" {
                operands_only = true;
                continue;
            }
            if let Some(long) = arg.strip_prefix("--") {
                options.long(long, &mut rest)?;
                continue;
            }
            let flags: Vec<char> = arg.chars().skip(1).collect();
            for (at, flag) in flags.iter().enumerate() {
                let tail: String = flags.iter().skip(at.saturating_add(1)).collect();
                match flag {
                    'n' => options.quiet = true,
                    'E' | 'r' => options.extended = true,
                    's' => options.separate = true,
                    'z' => options.null_data = true,
                    'u' | 'b' => {}
                    'i' => {
                        options.in_place = Some(tail);
                        break;
                    }
                    'e' | 'f' | 'l' => {
                        let value = if tail.is_empty() {
                            rest.next().cloned().ok_or_else(|| {
                                usage_error(&format!("option requires an argument -- '{flag}'"))
                            })?
                        } else {
                            tail
                        };
                        options.take(*flag, value)?;
                        break;
                    }
                    other => return Err(usage_error(&format!("invalid option -- '{other}'"))),
                }
            }
        }
        if options.sources.is_empty() {
            if options.operands.is_empty() {
                return Err(SedOutput {
                    stderr: USAGE.as_bytes().to_vec(),
                    status: 1,
                    ..SedOutput::default()
                });
            }
            let script = options.operands.remove(0);
            options.sources.push(Source::Expr(script));
        }
        if options.in_place.is_some() {
            options.separate = true;
            if options.operands.is_empty() {
                return Err(failure("no input files", 4));
            }
        }
        Ok(options)
    }

    fn long(
        &mut self,
        text: &str,
        rest: &mut std::slice::Iter<'_, String>,
    ) -> Result<(), SedOutput> {
        let (name, value) = match text.split_once('=') {
            Some((name, value)) => (name, Some(value.to_owned())),
            None => (text, None),
        };
        let candidates: Vec<&str> = LONG_OPTIONS
            .iter()
            .copied()
            .filter(|option| option.starts_with(name))
            .collect();
        let full = match candidates.as_slice() {
            _ if LONG_OPTIONS.contains(&name) => name,
            [one] => one,
            [] => return Err(usage_error(&format!("unrecognized option '--{name}'"))),
            _ => return Err(usage_error(&format!("option '--{name}' is ambiguous"))),
        };
        match full {
            "quiet" | "silent" => self.quiet = true,
            "regexp-extended" => self.extended = true,
            "separate" => self.separate = true,
            "null-data" | "zero-terminated" => self.null_data = true,
            "in-place" => self.in_place = Some(value.unwrap_or_default()),
            "sandbox" => self.sandbox = true,
            "expression" | "file" | "line-length" => {
                let value = match value {
                    Some(value) => value,
                    None => rest.next().cloned().ok_or_else(|| {
                        usage_error(&format!("option '--{full}' requires an argument"))
                    })?,
                };
                let flag = match full {
                    "expression" => 'e',
                    "file" => 'f',
                    _ => 'l',
                };
                self.take(flag, value)?;
            }
            "help" => {
                return Err(SedOutput {
                    stdout: format!("{USAGE}{BUGS}").into_bytes(),
                    ..SedOutput::default()
                });
            }
            "version" => {
                return Err(SedOutput {
                    stdout: VERSION.as_bytes().to_vec(),
                    ..SedOutput::default()
                });
            }
            _ => {}
        }
        Ok(())
    }

    /// Take the argument of `-e`, `-f` or `-l`.
    fn take(&mut self, flag: char, value: String) -> Result<(), SedOutput> {
        match flag {
            'e' => self.sources.push(Source::Expr(value)),
            'f' => self.sources.push(Source::File(value)),
            _ => {
                self.line_width = value
                    .parse()
                    .map_err(|_| failure(&format!("invalid line length: {value}"), 1))?;
            }
        }
        Ok(())
    }

    /// The input files, `-` for standard input when there are none.
    fn operand_names(&self) -> Vec<String> {
        if self.operands.is_empty() {
            vec!["-".to_owned()]
        } else {
            self.operands.clone()
        }
    }

    fn delimiter(&self) -> char {
        if self.null_data { '\0' } else { '\n' }
    }
}

// ---------------------------------------------------------------------------
// The compiled script
// ---------------------------------------------------------------------------

struct Program {
    cmds: Vec<Cmd>,
    regexes: Vec<Regex>,
    /// Targets of `r` and `R`.
    reads: Vec<String>,
    /// Targets of `w`, `W` and the `s` command's `w` flag, each opened once.
    writes: Vec<String>,
    /// Whether the script starts with `#n`.
    quiet: bool,
}

struct Cmd {
    first: Option<Addr>,
    second: Option<Addr>,
    negate: bool,
    kind: Kind,
}

/// An address; `Plus` and `Multiple` end a range only, `Step` starts one only.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Addr {
    Line(usize),
    Step(usize, usize),
    Last,
    /// A regex by index, `None` being the last one used.
    Match(Option<usize>),
    Plus(usize),
    Multiple(usize),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Jump {
    Always,
    IfReplaced,
    UnlessReplaced,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Sink {
    Stdout,
    Stderr,
    File(usize),
}

enum Kind {
    /// `{`, holding the index of its `}`.
    Block(usize),
    EndBlock,
    Nop,
    Label,
    Jump(Jump, String, usize),
    LineNumber,
    Append(String),
    Insert(String),
    Change(String),
    Delete,
    DeleteFirst,
    FileName,
    Get,
    GetAppend,
    Hold,
    HoldAppend,
    Exchange,
    List(Option<usize>),
    Next,
    NextAppend,
    Print,
    PrintFirst,
    Quit(i32),
    QuitSilent(i32),
    ReadFile(String),
    ReadLine(String),
    Substitute(Box<Subst>),
    Translate(Vec<(char, char)>),
    Write(Sink),
    WriteFirst(Sink),
    Zap,
}

struct Subst {
    regex: Option<usize>,
    replacement: Vec<Part>,
    global: bool,
    occurrence: usize,
    print: bool,
    write: Option<Sink>,
}

/// A piece of an `s` replacement.
#[derive(Clone, Debug, PartialEq, Eq)]
enum Part {
    Text(String),
    Group(usize),
    Case(CaseOp),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum CaseOp {
    Lower,
    Upper,
    LowerNext,
    UpperNext,
    End,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Case {
    Lower,
    Upper,
}

/// Where a stretch of the joined script came from, for error messages.
enum Origin {
    Expr(usize),
    File(String),
}

struct Chunk {
    start: usize,
    len: usize,
    origin: Origin,
}

struct Parser<'a> {
    text: &'a [char],
    pos: usize,
    chunks: &'a [Chunk],
    extended: bool,
    sandbox: bool,
    program: Program,
    /// The indices of the `{` commands not yet closed.
    open: Vec<usize>,
    /// Each `:` label and the index of its command.
    labels: Vec<(String, usize)>,
}

impl Parser<'_> {
    fn program(mut self) -> Result<Program, SedOutput> {
        if self.text.first() == Some(&'#') && self.text.get(1) == Some(&'n') {
            self.program.quiet = true;
        }
        loop {
            while self.peek().is_some_and(|c| c == ';' || c.is_whitespace()) {
                self.bump();
            }
            match self.peek() {
                None => break,
                Some('#') => self.skip_line(),
                Some(_) => self.command().map_err(|message| failure(&message, 1))?,
            }
        }
        if !self.open.is_empty() {
            return Err(failure(&self.error_at(0, "unmatched `{'"), 1));
        }
        self.resolve().map_err(|message| failure(&message, 4))?;
        Ok(self.program)
    }

    fn command(&mut self) -> Result<(), String> {
        let first = self.address(false)?;
        let mut second = None;
        if first.is_some() {
            self.skip_blanks();
            if self.peek() == Some(',') {
                self.bump();
                self.skip_blanks();
                second = self.address(true)?;
                if second.is_none() {
                    let read = self.pos.saturating_add(1);
                    return Err(self.error_at(read, "unexpected `,'"));
                }
            }
        }
        self.skip_blanks();
        let zero = matches!(first, Some(Addr::Line(0) | Addr::Step(0, 0)));
        if zero && !matches!(second, Some(Addr::Match(_))) {
            // GNU has read the character after the address when it refuses.
            let read = self.pos.saturating_add(1);
            return Err(self.error_at(read, "invalid usage of line address 0"));
        }
        let mut negate = false;
        if self.peek() == Some('!') {
            self.bump();
            negate = true;
            self.skip_blanks();
            if self.peek() == Some('!') {
                self.bump();
                return Err(self.error("multiple `!'s"));
            }
        }
        let addressed = first.is_some();
        let kind = match self.next() {
            None | Some('\n' | ';') => return Err(self.error("missing command")),
            Some('{') => {
                self.open.push(self.program.cmds.len());
                Kind::Block(usize::MAX)
            }
            Some('}') => {
                if addressed {
                    return Err(self.error("} doesn't want any addresses"));
                }
                let Some(open) = self.open.pop() else {
                    return Err(self.error("unexpected `}'"));
                };
                let here = self.program.cmds.len();
                if let Some(cmd) = self.program.cmds.get_mut(open) {
                    cmd.kind = Kind::Block(here);
                }
                self.end_of_command(EXTRA_CHARACTERS)?;
                Kind::EndBlock
            }
            Some('#') => return Err(self.error("comments don't accept any addresses")),
            Some(':') => {
                if addressed {
                    return Err(self.error(": doesn't want any addresses"));
                }
                let label = self.label();
                if label.is_empty() {
                    return Err(self.error("\":\" lacks a label"));
                }
                self.end_of_command(EXTRA_CHARACTERS)?;
                self.labels.push((label, self.program.cmds.len()));
                Kind::Label
            }
            Some(letter @ ('a' | 'i' | 'c')) => {
                let text = self.text_argument()?;
                match letter {
                    'a' => Kind::Append(text),
                    'i' => Kind::Insert(text),
                    _ => Kind::Change(text),
                }
            }
            Some(letter @ ('b' | 't' | 'T')) => {
                let label = self.label();
                self.end_of_command(EXTRA_CHARACTERS)?;
                let when = match letter {
                    'b' => Jump::Always,
                    't' => Jump::IfReplaced,
                    _ => Jump::UnlessReplaced,
                };
                Kind::Jump(when, label, usize::MAX)
            }
            Some(letter @ ('l' | 'q' | 'Q')) => {
                if letter != 'l' && second.is_some() {
                    return Err(self.error("command only uses one address"));
                }
                self.skip_blanks();
                let number = self.number();
                self.end_of_command(EXTRA_CHARACTERS)?;
                let code = number.and_then(|n| i32::try_from(n).ok()).unwrap_or(0);
                match letter {
                    'l' => Kind::List(number),
                    'q' => Kind::Quit(code),
                    _ => Kind::QuitSilent(code),
                }
            }
            Some(letter @ ('r' | 'R' | 'w' | 'W')) => {
                self.unsandboxed()?;
                let name = self.filename()?;
                match letter {
                    'r' | 'R' => {
                        if !self.program.reads.contains(&name) {
                            self.program.reads.push(name.clone());
                        }
                        if letter == 'r' {
                            Kind::ReadFile(name)
                        } else {
                            Kind::ReadLine(name)
                        }
                    }
                    'w' => Kind::Write(self.sink(name)),
                    _ => Kind::WriteFirst(self.sink(name)),
                }
            }
            Some('s') => self.substitute()?,
            Some('y') => self.transliterate()?,
            Some('v') => {
                self.label();
                self.end_of_command(EXTRA_CHARACTERS)?;
                Kind::Nop
            }
            Some('e') => {
                self.unsandboxed()?;
                return Err(self.error("the `e' command is not supported"));
            }
            Some(letter) => {
                let kind = match letter {
                    '=' => Kind::LineNumber,
                    'd' => Kind::Delete,
                    'D' => Kind::DeleteFirst,
                    'F' => Kind::FileName,
                    'g' => Kind::Get,
                    'G' => Kind::GetAppend,
                    'h' => Kind::Hold,
                    'H' => Kind::HoldAppend,
                    'x' => Kind::Exchange,
                    'n' => Kind::Next,
                    'N' => Kind::NextAppend,
                    'p' => Kind::Print,
                    'P' => Kind::PrintFirst,
                    'z' => Kind::Zap,
                    other => return Err(self.error(&format!("unknown command: `{other}'"))),
                };
                self.end_of_command(EXTRA_CHARACTERS)?;
                kind
            }
        };
        self.program.cmds.push(Cmd {
            first,
            second,
            negate,
            kind,
        });
        Ok(())
    }

    fn address(&mut self, second: bool) -> Result<Option<Addr>, String> {
        let Some(ch) = self.peek() else {
            return Ok(None);
        };
        let addr = match ch {
            '0'..='9' => {
                let number = self.number().unwrap_or(0);
                if !second && self.peek() == Some('~') {
                    self.bump();
                    Addr::Step(number, self.number().unwrap_or(0))
                } else {
                    Addr::Line(number)
                }
            }
            '+' | '~' if second => {
                self.bump();
                let Some(number) = self.number() else {
                    return Err(self.error("expected newer version of sed"));
                };
                if ch == '+' {
                    Addr::Plus(number)
                } else {
                    Addr::Multiple(number)
                }
            }
            '$' => {
                self.bump();
                Addr::Last
            }
            '/' | '\\' => {
                self.bump();
                let delim = if ch == '\\' {
                    match self.next() {
                        Some(delim) if delim != '\n' && delim != '\\' => delim,
                        _ => return Err(self.error("unterminated address regex")),
                    }
                } else {
                    '/'
                };
                let Some(pattern) = self.delimited(delim, true) else {
                    return Err(self.error("unterminated address regex"));
                };
                let mut nocase = false;
                loop {
                    match self.peek() {
                        Some('I') => {
                            self.bump();
                            nocase = true;
                        }
                        Some('M') => {
                            self.bump();
                            return Err(self.error("the `M' modifier is not supported"));
                        }
                        _ => break,
                    }
                }
                Addr::Match(self.regex(&pattern, nocase)?)
            }
            _ => return Ok(None),
        };
        Ok(Some(addr))
    }

    /// Compile a regex, `None` for the empty one that reuses the last.
    fn regex(&mut self, pattern: &str, nocase: bool) -> Result<Option<usize>, String> {
        if pattern.is_empty() {
            return Ok(None);
        }
        let ere = translate_regex(pattern, self.extended).map_err(|e| self.error(&e))?;
        let regex = Regex::new(&ere, nocase).map_err(|e| self.error(&capitalize(&e)))?;
        self.program.regexes.push(regex);
        Ok(Some(self.program.regexes.len().saturating_sub(1)))
    }

    fn substitute(&mut self) -> Result<Kind, String> {
        const UNTERMINATED: &str = "unterminated `s' command";
        let delim = match self.next() {
            Some(delim) if delim != '\n' && delim != '\\' => delim,
            _ => return Err(self.error(UNTERMINATED)),
        };
        let Some(pattern) = self.delimited(delim, true) else {
            return Err(self.error(UNTERMINATED));
        };
        let Some(replacement) = self.delimited(delim, false) else {
            return Err(self.error(UNTERMINATED));
        };
        let replacement = parse_replacement(&replacement);
        let mut subst = Subst {
            regex: None,
            replacement,
            global: false,
            occurrence: 1,
            print: false,
            write: None,
        };
        let mut nocase = false;
        let mut numbered = false;
        loop {
            match self.peek() {
                Some('g') => {
                    self.bump();
                    if subst.global {
                        return Err(self.error("multiple `g' options to `s' command"));
                    }
                    subst.global = true;
                }
                Some('p') => {
                    self.bump();
                    if subst.print {
                        return Err(self.error("multiple `p' options to `s' command"));
                    }
                    subst.print = true;
                }
                Some('i' | 'I') => {
                    self.bump();
                    nocase = true;
                }
                Some('m' | 'M') => {
                    self.bump();
                    return Err(self.error("the `M' modifier is not supported"));
                }
                Some('e') => {
                    self.bump();
                    self.unsandboxed()?;
                    return Err(self.error("the `e' option to `s' is not supported"));
                }
                Some('0'..='9') => {
                    if numbered {
                        self.bump();
                        return Err(self.error("multiple number options to `s' command"));
                    }
                    let number = self.number().unwrap_or(0);
                    if number == 0 {
                        return Err(self.error("number option to `s' command may not be zero"));
                    }
                    subst.occurrence = number;
                    numbered = true;
                }
                Some('w') => {
                    self.bump();
                    self.unsandboxed()?;
                    let name = self.filename()?;
                    subst.write = Some(self.sink(name));
                    break;
                }
                _ => {
                    self.end_of_command("unknown option to `s'")?;
                    break;
                }
            }
        }
        subst.regex = self.regex(&pattern, nocase)?;
        if let Some(index) = subst.regex {
            let groups = self.program.regexes.get(index).map_or(0, Regex::groups);
            let wanted = subst.replacement.iter().find_map(|part| match part {
                Part::Group(group) if *group > groups => Some(*group),
                _ => None,
            });
            if let Some(group) = wanted {
                return Err(
                    self.error(&format!("invalid reference \\{group} on `s' command's RHS"))
                );
            }
        }
        Ok(Kind::Substitute(Box::new(subst)))
    }

    fn transliterate(&mut self) -> Result<Kind, String> {
        const UNTERMINATED: &str = "unterminated `y' command";
        let delim = match self.next() {
            Some(delim) if delim != '\n' && delim != '\\' => delim,
            _ => return Err(self.error(UNTERMINATED)),
        };
        let Some(from) = self.delimited(delim, false) else {
            return Err(self.error(UNTERMINATED));
        };
        let Some(to) = self.delimited(delim, false) else {
            return Err(self.error(UNTERMINATED));
        };
        let from = unescape_y(&from);
        let to = unescape_y(&to);
        if from.len() != to.len() {
            return Err(self.error("strings for `y' command are different lengths"));
        }
        self.end_of_command(EXTRA_CHARACTERS)?;
        Ok(Kind::Translate(from.into_iter().zip(to).collect()))
    }

    /// The text of `a`, `i` or `c`: the GNU one-liner `a text` or the classic `a\` and a newline.
    fn text_argument(&mut self) -> Result<String, String> {
        const EXPECTED: &str = "expected \\ after `a', `c' or `i'";
        self.skip_blanks();
        let mut raw: Vec<char> = Vec::new();
        match self.next() {
            None | Some('\n') => return Err(self.error(EXPECTED)),
            Some('\\') => match self.next() {
                None => return Ok(String::new()),
                Some('\n') => {}
                Some(ch) => raw.push(ch),
            },
            Some(ch) => raw.push(ch),
        }
        loop {
            match self.next() {
                None | Some('\n') => break,
                Some('\\') => match self.next() {
                    None => break,
                    Some(ch) => {
                        raw.push('\\');
                        raw.push(ch);
                    }
                },
                Some(ch) => raw.push(ch),
            }
        }
        let mut text = unescape_text(&raw);
        text.push('\n');
        Ok(text)
    }

    /// Read up to an unescaped `delim`, as GNU's `match_slash` does; `None` when unterminated.
    fn delimited(&mut self, delim: char, regex: bool) -> Option<String> {
        let mut out = String::new();
        loop {
            let ch = self.next()?;
            if ch == '\n' {
                return None;
            }
            if ch == delim {
                return Some(out);
            }
            if ch != '\\' {
                out.push(ch);
                continue;
            }
            let escaped = self.next()?;
            if escaped == 'n' && regex {
                out.push('\n');
            } else if escaped == '\n' || (escaped == delim && (regex || escaped != '&')) {
                out.push(escaped);
            } else {
                out.push('\\');
                out.push(escaped);
            }
        }
    }

    fn label(&mut self) -> String {
        self.skip_blanks();
        let mut out = String::new();
        while let Some(ch) = self.peek() {
            if ch == ';' || ch == '}' || ch.is_whitespace() {
                break;
            }
            out.push(ch);
            self.bump();
        }
        out
    }

    fn filename(&mut self) -> Result<String, String> {
        self.skip_blanks();
        let mut out = String::new();
        while let Some(ch) = self.peek() {
            if ch == '\n' {
                break;
            }
            out.push(ch);
            self.bump();
        }
        if out.is_empty() {
            return Err(self.error("missing filename in r/R/w/W commands"));
        }
        Ok(out)
    }

    fn sink(&mut self, name: String) -> Sink {
        match name.as_str() {
            "/dev/stdout" => Sink::Stdout,
            "/dev/stderr" => Sink::Stderr,
            _ => {
                let index = match self.program.writes.iter().position(|w| *w == name) {
                    Some(index) => index,
                    None => {
                        self.program.writes.push(name);
                        self.program.writes.len().saturating_sub(1)
                    }
                };
                Sink::File(index)
            }
        }
    }

    /// What may follow a command: blanks, then the end, a newline, `;`, `#` or `}`.
    fn end_of_command(&mut self, message: &str) -> Result<(), String> {
        self.skip_blanks();
        match self.peek() {
            None | Some('#' | '}') => Ok(()),
            Some('\n' | ';') => {
                self.bump();
                Ok(())
            }
            Some(_) => {
                self.bump();
                Err(self.error(message))
            }
        }
    }

    /// Point every jump at its label, or past the end for a bare one.
    fn resolve(&mut self) -> Result<(), String> {
        let end = self.program.cmds.len();
        let labels = std::mem::take(&mut self.labels);
        for cmd in &mut self.program.cmds {
            if let Kind::Jump(_, label, target) = &mut cmd.kind {
                *target = if label.is_empty() {
                    end
                } else {
                    labels
                        .iter()
                        .find(|(name, _)| name == label)
                        .map(|(_, index)| *index)
                        .ok_or_else(|| format!("can't find label for jump to `{label}'"))?
                };
            }
        }
        Ok(())
    }

    fn peek(&self) -> Option<char> {
        self.text.get(self.pos).copied()
    }

    fn bump(&mut self) {
        self.pos = self.pos.saturating_add(1);
    }

    fn next(&mut self) -> Option<char> {
        let ch = self.peek();
        if ch.is_some() {
            self.bump();
        }
        ch
    }

    fn skip_blanks(&mut self) {
        while matches!(self.peek(), Some(' ' | '\t')) {
            self.bump();
        }
    }

    fn skip_line(&mut self) {
        while let Some(ch) = self.next() {
            if ch == '\n' {
                break;
            }
        }
    }

    fn number(&mut self) -> Option<usize> {
        let mut value: Option<usize> = None;
        while let Some(digit) = self.peek().and_then(|c| c.to_digit(10)) {
            let digit = usize::try_from(digit).unwrap_or(0);
            value = Some(value.unwrap_or(0).saturating_mul(10).saturating_add(digit));
            self.bump();
        }
        value
    }

    fn error(&self, message: &str) -> String {
        self.error_at(self.pos, message)
    }

    /// Under `--sandbox`, the refusal of a command that names a file or runs one.
    fn unsandboxed(&self) -> Result<(), String> {
        if self.sandbox {
            return Err(self.error("e/r/w commands disabled in sandbox mode"));
        }
        Ok(())
    }

    /// GNU's location prefix: the expression and the characters read of it, or a script file's line.
    fn error_at(&self, pos: usize, message: &str) -> String {
        let last = pos.saturating_sub(1);
        let chunk = self
            .chunks
            .iter()
            .rev()
            .find(|chunk| chunk.start <= last)
            .or(self.chunks.first());
        let Some(chunk) = chunk else {
            return message.to_owned();
        };
        match &chunk.origin {
            Origin::Expr(number) => {
                let local = pos.saturating_sub(chunk.start).min(chunk.len);
                format!("-e expression #{number}, char {local}: {message}")
            }
            Origin::File(name) => {
                let line = self
                    .text
                    .get(chunk.start..last.max(chunk.start))
                    .map_or(0, |read| read.iter().filter(|c| **c == '\n').count())
                    .saturating_add(1);
                format!("file {name} line {line}: {message}")
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Execution
// ---------------------------------------------------------------------------

/// An input line: its text without the delimiter, and whether it had one.
#[derive(Clone, Debug, Default)]
struct Line {
    text: String,
    chomped: bool,
    unit: usize,
}

/// What one run of the script reads, in order: lines, and the inputs that could not be read.
enum Item {
    Line(Line),
    Unreadable(String, i32),
    Taken,
}

/// The items of a run; an unreadable input is reported when the run reaches it, as GNU opens files.
struct Stream {
    items: Vec<Item>,
    next: usize,
    complaints: Vec<(String, i32)>,
    /// Set by a read error, which ends all input.
    stopped: bool,
}

impl Stream {
    fn new(items: Vec<Item>) -> Stream {
        Stream {
            items,
            next: 0,
            complaints: Vec::new(),
            stopped: false,
        }
    }

    fn take(&mut self) -> Option<Line> {
        if self.at_end() {
            return None;
        }
        let item = self.items.get_mut(self.next)?;
        self.next = self.next.saturating_add(1);
        match std::mem::replace(item, Item::Taken) {
            Item::Line(line) => Some(line),
            Item::Unreadable(..) | Item::Taken => None,
        }
    }

    /// Whether no line is left, reporting the unreadable inputs passed on the way.
    fn at_end(&mut self) -> bool {
        while !self.stopped {
            let Some(item) = self.items.get_mut(self.next) else {
                return true;
            };
            if matches!(item, Item::Line(_)) {
                return false;
            }
            if let Item::Unreadable(message, status) = std::mem::replace(item, Item::Taken) {
                self.stopped = status == READ_ERROR;
                self.complaints.push((message, status));
            }
            self.next = self.next.saturating_add(1);
        }
        true
    }
}

/// One output, and whether its last line still owes a delimiter.
#[derive(Clone, Debug, Default)]
struct Out {
    bytes: Vec<u8>,
    missing: bool,
}

impl Out {
    fn text(&mut self, text: &str, delim: char) {
        if self.missing {
            push_char(&mut self.bytes, delim);
            self.missing = false;
        }
        self.bytes.extend_from_slice(text.as_bytes());
    }

    fn line(&mut self, text: &str, chomped: bool, delim: char) {
        self.text(text, delim);
        if chomped {
            push_char(&mut self.bytes, delim);
        } else {
            self.missing = true;
        }
    }
}

#[derive(Default)]
struct Outputs {
    stdout: Out,
    stderr: Out,
    in_place: Option<Out>,
    files: Vec<Out>,
}

impl Outputs {
    fn current(&mut self) -> &mut Out {
        match &mut self.in_place {
            Some(out) => out,
            None => &mut self.stdout,
        }
    }

    fn sink(&mut self, sink: Sink) -> Option<&mut Out> {
        match sink {
            Sink::Stdout => Some(&mut self.stdout),
            Sink::Stderr => Some(&mut self.stderr),
            Sink::File(index) => self.files.get_mut(index),
        }
    }
}

/// How a pass of the script over the pattern space ended.
enum End {
    /// The end of the script: print, then read the next line.
    Cycle,
    /// `d`: read the next line without printing.
    Delete,
    /// `D` with a newline left: run again without reading.
    Restart,
    /// `q`: print, then stop.
    Quit(i32),
    /// `Q`: stop.
    Exit(i32),
}

/// A run that cannot go on: what to say, and the status to end with.
struct Fault {
    message: String,
    status: i32,
}

impl Fault {
    fn panic(message: &str) -> Fault {
        Fault {
            message: message.to_owned(),
            status: 4,
        }
    }

    fn spent() -> Fault {
        Fault {
            message: "the regular expression is too complex to match the pattern space".to_owned(),
            status: 4,
        }
    }

    fn no_regex() -> Fault {
        Fault {
            message: "-e expression #1, char 0: no previous regular expression".to_owned(),
            status: 1,
        }
    }
}

#[derive(Clone, Copy, Debug, Default)]
struct Range {
    active: bool,
    end: usize,
}

enum Queued {
    Text(String),
    File(String),
}

struct Unit {
    name: String,
    original: Vec<u8>,
    lines: Vec<Line>,
}

/// An input operand: its lines, or what to say about it and the status that leaves.
enum Entry {
    Data(Unit),
    Unreadable(String, i32),
}

struct Machine<'a> {
    options: &'a Options,
    program: &'a Program,
    files: &'a Files,
    delim: char,
    quiet: bool,
    space: String,
    chomped: bool,
    hold: String,
    line: usize,
    unit: usize,
    names: Vec<String>,
    replaced: bool,
    last_regex: Option<usize>,
    ranges: Vec<Range>,
    queue: Vec<Queued>,
    outputs: Outputs,
    /// For `R`: each file's lines and how many have been read.
    cursors: BTreeMap<String, (Vec<Line>, usize)>,
    steps: u64,
    space_limit: usize,
    /// The worst status an unreadable input left.
    bad: i32,
}

impl<'a> Machine<'a> {
    fn new(options: &'a Options, program: &'a Program, files: &'a Files) -> Machine<'a> {
        Machine {
            options,
            program,
            files,
            delim: options.delimiter(),
            quiet: options.quiet || program.quiet,
            space: String::new(),
            chomped: true,
            hold: String::new(),
            line: 0,
            unit: 0,
            names: Vec::new(),
            replaced: false,
            last_regex: None,
            ranges: fresh_ranges(program),
            queue: Vec::new(),
            outputs: Outputs {
                files: vec![Out::default(); program.writes.len()],
                ..Outputs::default()
            },
            cursors: BTreeMap::new(),
            steps: 0,
            space_limit: SPACE_FLOOR,
            bad: 0,
        }
    }

    fn process(mut self, stdin: &[u8]) -> SedOutput {
        let entries = self.entries(stdin);
        let input: usize = entries
            .iter()
            .map(|entry| match entry {
                Entry::Data(unit) => unit.original.len(),
                Entry::Unreadable(..) => 0,
            })
            .fold(0, usize::saturating_add);
        self.space_limit = SPACE_FLOOR.saturating_add(input.saturating_mul(SPACE_PER_INPUT));
        let mut writes = Vec::new();
        let mut outcome: Result<Option<i32>, Fault> = Ok(None);
        if self.options.separate {
            for entry in entries {
                let unit = match entry {
                    Entry::Data(unit) => unit,
                    Entry::Unreadable(message, status) => {
                        self.complain(&message);
                        self.bad = self.bad.max(status);
                        if status == READ_ERROR {
                            break;
                        }
                        continue;
                    }
                };
                self.line = 0;
                self.ranges = fresh_ranges(self.program);
                if self.options.in_place.is_some() {
                    self.outputs.in_place = Some(Out::default());
                }
                let items = unit.lines.into_iter().map(Item::Line).collect();
                outcome = self.stream(Stream::new(items));
                // A file is published only when its edit ended well, by its end or a quit.
                if let (Some(out), Ok(_)) = (self.outputs.in_place.take(), &outcome) {
                    let suffix = self.options.in_place.as_deref().unwrap_or_default();
                    if !suffix.is_empty() {
                        writes.push(SedWrite {
                            path: backup_name(&unit.name, suffix),
                            data: unit.original,
                            kind: WriteKind::Backup {
                                source: unit.name.clone(),
                            },
                        });
                    }
                    writes.push(SedWrite {
                        path: unit.name,
                        data: out.bytes,
                        kind: WriteKind::InPlace,
                    });
                }
                if !matches!(outcome, Ok(None)) {
                    break;
                }
            }
        } else {
            let mut items = Vec::new();
            for entry in entries {
                match entry {
                    Entry::Data(unit) => items.extend(unit.lines.into_iter().map(Item::Line)),
                    Entry::Unreadable(message, status) => {
                        items.push(Item::Unreadable(message, status));
                    }
                }
            }
            outcome = self.stream(Stream::new(items));
        }
        let status = match outcome {
            Err(fault) => {
                self.complain(&fault.message);
                fault.status
            }
            Ok(_) if self.bad != 0 => self.bad,
            Ok(code) => code.unwrap_or(0),
        };
        for (name, out) in self.program.writes.iter().zip(self.outputs.files) {
            writes.push(SedWrite {
                path: name.clone(),
                data: out.bytes,
                kind: WriteKind::Script,
            });
        }
        SedOutput {
            stdout: self.outputs.stdout.bytes,
            stderr: self.outputs.stderr.bytes,
            status,
            writes,
        }
    }

    /// Each operand's lines, or what GNU says when it cannot read it.
    fn entries(&mut self, stdin: &[u8]) -> Vec<Entry> {
        let in_place = self.options.in_place.is_some();
        let mut entries = Vec::new();
        let mut stdin = Some(stdin);
        for name in self.options.operand_names() {
            let content = if name == "-" && !in_place {
                // Standard input is read once; a second `-` finds it at its end.
                Ok(stdin.take().unwrap_or_default().to_vec())
            } else {
                self.files
                    .get(&name)
                    .cloned()
                    .unwrap_or_else(|| Err("No such file or directory".to_owned()))
            };
            entries.push(match content {
                Ok(bytes) => {
                    let index = self.names.len();
                    self.names.push(name.clone());
                    Entry::Data(Unit {
                        lines: split_lines(&bytes, self.delim, index),
                        name,
                        original: bytes,
                    })
                }
                Err(error) if error == "Is a directory" && in_place => Entry::Unreadable(
                    format!("couldn't edit {name}: not a regular file"),
                    READ_ERROR,
                ),
                Err(error) if error == "Is a directory" => {
                    Entry::Unreadable(format!("read error on {name}: {error}"), READ_ERROR)
                }
                Err(error) => Entry::Unreadable(format!("can't read {name}: {error}"), 2),
            });
        }
        entries
    }

    /// Run the script over every line of `input`; `Some` is the status a quit gave.
    fn stream(&mut self, mut input: Stream) -> Result<Option<i32>, Fault> {
        let outcome = self.cycles(&mut input);
        for (message, status) in std::mem::take(&mut input.complaints) {
            self.complain(&message);
            self.bad = self.bad.max(status);
        }
        outcome
    }

    fn cycles(&mut self, input: &mut Stream) -> Result<Option<i32>, Fault> {
        while let Some(line) = input.take() {
            self.load(line);
            loop {
                match self.execute(input)? {
                    End::Cycle => {
                        self.autoprint();
                        self.flush();
                        break;
                    }
                    End::Delete => {
                        self.flush();
                        break;
                    }
                    End::Restart => self.flush(),
                    End::Quit(code) => {
                        self.autoprint();
                        self.flush();
                        return Ok(Some(code));
                    }
                    End::Exit(code) => return Ok(Some(code)),
                }
            }
        }
        Ok(None)
    }

    fn load(&mut self, line: Line) {
        self.space = line.text;
        self.chomped = line.chomped;
        self.unit = line.unit;
        self.line = self.line.saturating_add(1);
        self.replaced = false;
        self.steps = 0;
    }

    fn execute(&mut self, input: &mut Stream) -> Result<End, Fault> {
        let program = self.program;
        let delim = self.delim;
        let mut pc = 0usize;
        while let Some(cmd) = program.cmds.get(pc) {
            self.steps = self.steps.saturating_add(1);
            if self.steps > STEP_BUDGET {
                return Err(Fault::panic("the script ran past its step budget"));
            }
            let next = pc.saturating_add(1);
            if !self.selected(pc, cmd, input)? {
                pc = match cmd.kind {
                    Kind::Block(end) => end.saturating_add(1),
                    _ => next,
                };
                continue;
            }
            match &cmd.kind {
                Kind::Block(_) | Kind::EndBlock | Kind::Label | Kind::Nop => {}
                Kind::Jump(when, _, target) => {
                    let jump = match when {
                        Jump::Always => true,
                        Jump::IfReplaced => std::mem::replace(&mut self.replaced, false),
                        Jump::UnlessReplaced => !std::mem::replace(&mut self.replaced, false),
                    };
                    if jump {
                        pc = *target;
                        continue;
                    }
                }
                Kind::LineNumber => {
                    let text = format!("{}{delim}", self.line);
                    self.outputs.current().text(&text, delim);
                }
                Kind::Append(text) => self.queue.push(Queued::Text(text.clone())),
                Kind::Insert(text) => self.outputs.current().text(text, delim),
                Kind::Change(text) => {
                    if !self.ranges.get(pc).is_some_and(|range| range.active) {
                        self.outputs.current().text(text, delim);
                    }
                    return Ok(End::Delete);
                }
                Kind::Delete => return Ok(End::Delete),
                Kind::DeleteFirst => {
                    return Ok(match self.space.split_once(delim) {
                        Some((_, rest)) => {
                            self.space = rest.to_owned();
                            End::Restart
                        }
                        None => End::Delete,
                    });
                }
                Kind::FileName => {
                    let name = self.names.get(self.unit).map_or("-", String::as_str);
                    let text = format!("{name}{delim}");
                    self.outputs.current().text(&text, delim);
                }
                Kind::Get => self.space.clone_from(&self.hold),
                Kind::GetAppend => {
                    self.space.push(delim);
                    self.space.push_str(&self.hold);
                }
                Kind::Hold => self.hold.clone_from(&self.space),
                Kind::HoldAppend => {
                    self.hold.push(delim);
                    self.hold.push_str(&self.space);
                }
                Kind::Exchange => std::mem::swap(&mut self.space, &mut self.hold),
                Kind::List(width) => {
                    let width = width.unwrap_or(self.options.line_width);
                    let text = list(&self.space, width, delim);
                    self.outputs.current().text(&text, delim);
                }
                Kind::Next => {
                    if input.at_end() {
                        return Ok(End::Cycle);
                    }
                    self.autoprint();
                    self.flush();
                    if let Some(line) = input.take() {
                        self.load(line);
                    }
                }
                Kind::NextAppend => {
                    if input.at_end() {
                        return Ok(End::Cycle);
                    }
                    self.flush();
                    if let Some(line) = input.take() {
                        let mut space = std::mem::take(&mut self.space);
                        space.push(delim);
                        space.push_str(&line.text);
                        self.load(Line {
                            text: space,
                            ..line
                        });
                    }
                }
                Kind::Print => self
                    .outputs
                    .current()
                    .line(&self.space, self.chomped, delim),
                Kind::PrintFirst => {
                    let first = self.space.split(delim).next().unwrap_or_default();
                    self.outputs.current().line(first, true, delim);
                }
                Kind::Quit(code) => return Ok(End::Quit(*code)),
                Kind::QuitSilent(code) => return Ok(End::Exit(*code)),
                Kind::ReadFile(name) => self.queue.push(Queued::File(name.clone())),
                Kind::ReadLine(name) => {
                    if let Some(text) = self.read_line(name) {
                        self.queue.push(Queued::Text(text));
                    }
                }
                Kind::Substitute(subst) => self.substitute(subst)?,
                Kind::Translate(map) => {
                    self.space = self
                        .space
                        .chars()
                        .map(|ch| {
                            map.iter()
                                .find(|(from, _)| *from == ch)
                                .map_or(ch, |(_, to)| *to)
                        })
                        .collect();
                }
                Kind::Write(sink) => {
                    if let Some(out) = self.outputs.sink(*sink) {
                        out.line(&self.space, self.chomped, delim);
                    }
                }
                Kind::WriteFirst(sink) => {
                    let first = self.space.split(delim).next().unwrap_or_default();
                    if let Some(out) = self.outputs.sink(*sink) {
                        out.line(first, true, delim);
                    }
                }
                Kind::Zap => self.space.clear(),
            }
            if self.space.len().saturating_add(self.hold.len()) > self.space_limit {
                return Err(Fault::panic(
                    "the pattern and hold spaces outgrew their limit",
                ));
            }
            pc = next;
        }
        Ok(End::Cycle)
    }

    /// Whether `cmd` applies to the current line, stepping its range.
    fn selected(&mut self, pc: usize, cmd: &Cmd, input: &mut Stream) -> Result<bool, Fault> {
        let matched = match (cmd.first, cmd.second) {
            (None, _) => true,
            (Some(first), None) => self.matches(first, input)?,
            (Some(first), Some(second)) => self.in_range(pc, first, second, input)?,
        };
        Ok(matched != cmd.negate)
    }

    fn matches(&mut self, addr: Addr, input: &mut Stream) -> Result<bool, Fault> {
        Ok(match addr {
            Addr::Line(number) => self.line == number,
            Addr::Step(first, 0) => self.line == first,
            Addr::Step(first, step) => {
                self.line
                    .checked_sub(first)
                    .and_then(|distance| distance.checked_rem(step))
                    == Some(0)
            }
            Addr::Last => input.at_end(),
            Addr::Match(regex) => self.search(regex)?,
            Addr::Plus(_) | Addr::Multiple(_) => false,
        })
    }

    fn in_range(
        &mut self,
        pc: usize,
        first: Addr,
        second: Addr,
        input: &mut Stream,
    ) -> Result<bool, Fault> {
        let state = self.ranges.get(pc).copied().unwrap_or_default();
        if state.active {
            let (keep, matched) = match second {
                Addr::Line(end) => (self.line < end, self.line <= end),
                Addr::Plus(_) | Addr::Multiple(_) => {
                    (self.line < state.end, self.line <= state.end)
                }
                Addr::Last => (!input.at_end(), true),
                Addr::Match(regex) => (!self.search(regex)?, true),
                Addr::Step(..) => (false, true),
            };
            self.set_range(pc, keep, state.end);
            return Ok(matched);
        }
        if !self.matches(first, input)? {
            return Ok(false);
        }
        let end = match second {
            Addr::Line(end) if self.line >= end => return Ok(true),
            Addr::Line(end) => end,
            Addr::Plus(0) | Addr::Multiple(0) => return Ok(true),
            Addr::Plus(count) => self.line.saturating_add(count),
            Addr::Multiple(step) => match self.line.checked_rem(step) {
                None => return Ok(true),
                Some(rem) => self.line.saturating_sub(rem).saturating_add(step),
            },
            Addr::Last | Addr::Match(_) | Addr::Step(..) => 0,
        };
        self.set_range(pc, true, end);
        Ok(true)
    }

    fn set_range(&mut self, pc: usize, active: bool, end: usize) {
        if let Some(range) = self.ranges.get_mut(pc) {
            *range = Range { active, end };
        }
    }

    /// The regex at `index`, or the last one used for `None`; it becomes the last one used.
    fn regex(&mut self, index: Option<usize>) -> Result<&'a Regex, Fault> {
        let program = self.program;
        let index = index.or(self.last_regex).ok_or_else(Fault::no_regex)?;
        self.last_regex = Some(index);
        program.regexes.get(index).ok_or_else(Fault::no_regex)
    }

    fn search(&mut self, index: Option<usize>) -> Result<bool, Fault> {
        let regex = self.regex(index)?;
        let chars: Vec<char> = self.space.chars().collect();
        Ok(regex
            .find_at(&chars, 0)
            .map_err(|_| Fault::spent())?
            .is_some())
    }

    fn substitute(&mut self, subst: &Subst) -> Result<(), Fault> {
        let regex = self.regex(subst.regex)?;
        let chars: Vec<char> = self.space.chars().collect();
        let mut out = String::new();
        let mut copied = 0usize;
        let mut from = 0usize;
        let mut count = 0usize;
        let mut previous_end: Option<usize> = None;
        let mut any = false;
        while from <= chars.len() {
            let Some(caps) = regex.find_at(&chars, from).map_err(|_| Fault::spent())? else {
                break;
            };
            let Some(Some((start, end))) = caps.first().copied() else {
                break;
            };
            // An empty match just after the previous match is no match, as in GNU.
            if start == end && previous_end == Some(start) {
                from = start.saturating_add(1);
                continue;
            }
            count = count.saturating_add(1);
            if count >= subst.occurrence {
                out.extend(chars.get(copied..start).unwrap_or_default());
                expand(&subst.replacement, &chars, &caps, &mut out);
                copied = end;
                any = true;
                if !subst.global {
                    break;
                }
            }
            previous_end = Some(end);
            from = if start == end {
                end.saturating_add(1)
            } else {
                end
            };
        }
        if !any {
            return Ok(());
        }
        out.extend(chars.get(copied..).unwrap_or_default());
        self.space = out;
        self.replaced = true;
        let delim = self.delim;
        if subst.print {
            self.outputs
                .current()
                .line(&self.space, self.chomped, delim);
        }
        if let Some(out) = subst.write.and_then(|sink| self.outputs.sink(sink)) {
            out.line(&self.space, self.chomped, delim);
        }
        Ok(())
    }

    /// The next line of `name` for `R`, with its delimiter if it had one.
    fn read_line(&mut self, name: &str) -> Option<String> {
        let Some(Ok(bytes)) = self.files.get(name) else {
            return None;
        };
        let delim = self.delim;
        let (lines, cursor) = self
            .cursors
            .entry(name.to_owned())
            .or_insert_with(|| (split_lines(bytes, delim, 0), 0));
        let line = lines.get(*cursor)?;
        *cursor = cursor.saturating_add(1);
        let mut text = line.text.clone();
        if line.chomped {
            text.push(delim);
        }
        Some(text)
    }

    fn autoprint(&mut self) {
        if !self.quiet {
            self.outputs
                .current()
                .line(&self.space, self.chomped, self.delim);
        }
    }

    /// Write what `a`, `r` and `R` queued during the cycle.
    fn flush(&mut self) {
        for queued in std::mem::take(&mut self.queue) {
            match queued {
                Queued::Text(text) => self.outputs.current().text(&text, self.delim),
                Queued::File(name) => {
                    if let Some(Ok(bytes)) = self.files.get(&name) {
                        self.outputs.current().bytes.extend_from_slice(bytes);
                    }
                }
            }
        }
    }

    fn complain(&mut self, message: &str) {
        let text = format!("sed: {message}\n");
        self.outputs.stderr.bytes.extend_from_slice(text.as_bytes());
    }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/// Each command's range state at the start of an input: only `0,/re/` starts open.
fn fresh_ranges(program: &Program) -> Vec<Range> {
    program
        .cmds
        .iter()
        .map(|cmd| Range {
            active: cmd.first == Some(Addr::Line(0)),
            end: 0,
        })
        .collect()
}

fn failure(message: &str, status: i32) -> SedOutput {
    SedOutput {
        stderr: format!("sed: {message}\n").into_bytes(),
        status,
        ..SedOutput::default()
    }
}

fn usage_error(message: &str) -> SedOutput {
    SedOutput {
        stderr: format!("sed: {message}\n{USAGE}").into_bytes(),
        status: 1,
        ..SedOutput::default()
    }
}

/// Join the script pieces and compile them.
fn compile(options: &Options, files: &Files, stdin: &[u8]) -> Result<Program, SedOutput> {
    let mut text: Vec<char> = Vec::new();
    let mut chunks = Vec::new();
    let mut expressions = 0usize;
    for source in &options.sources {
        let (body, origin) = match source {
            Source::Expr(body) => {
                expressions = expressions.saturating_add(1);
                (body.clone(), Origin::Expr(expressions))
            }
            Source::File(name) => {
                let bytes = if name == "-" {
                    Ok(stdin.to_vec())
                } else {
                    files
                        .get(name)
                        .cloned()
                        .unwrap_or_else(|| Err("No such file or directory".to_owned()))
                };
                match bytes {
                    Ok(bytes) => (
                        String::from_utf8_lossy(&bytes).into_owned(),
                        Origin::File(name.clone()),
                    ),
                    Err(error) => {
                        return Err(failure(&format!("couldn't open file {name}: {error}"), 4));
                    }
                }
            }
        };
        let mut body: Vec<char> = body.chars().collect();
        if matches!(origin, Origin::File(_)) && body.last() == Some(&'\n') {
            body.pop();
        }
        chunks.push(Chunk {
            start: text.len(),
            len: body.len(),
            origin,
        });
        text.extend(body);
        text.push('\n');
    }
    text.pop();
    let parser = Parser {
        text: &text,
        pos: 0,
        chunks: &chunks,
        extended: options.extended,
        sandbox: options.sandbox,
        program: Program {
            cmds: Vec::new(),
            regexes: Vec::new(),
            reads: Vec::new(),
            writes: Vec::new(),
            quiet: false,
        },
        open: Vec::new(),
        labels: Vec::new(),
    };
    parser.program()
}

/// A regex as the script wrote it, turned into the engine's extended syntax.
fn translate_regex(pattern: &str, extended: bool) -> Result<String, String> {
    let chars: Vec<char> = pattern.chars().collect();
    let mut out = String::new();
    let mut at = 0usize;
    while let Some(&ch) = chars.get(at) {
        at = at.saturating_add(1);
        match ch {
            '\\' => {
                let Some(&next) = chars.get(at) else {
                    out.push('\\');
                    break;
                };
                at = at.saturating_add(1);
                if next.is_ascii_digit() && next != '0' {
                    return Err("back-references in a regex are not supported".to_owned());
                }
                match decode_escape(&chars, &mut at, next) {
                    Some(literal) => out.push(literal),
                    None => {
                        out.push('\\');
                        out.push(next);
                    }
                }
                if next == '{' && !extended && chars.get(at) == Some(&',') {
                    out.push('0');
                }
            }
            '[' => {
                out.push('[');
                at = copy_bracket(&chars, at, &mut out);
            }
            '{' if extended && chars.get(at) == Some(&',') => out.push_str("{0"),
            other => out.push(other),
        }
    }
    Ok(if extended { out } else { bre_to_ere(&out) })
}

/// Copy a bracket expression from just after its `[`, turning `\n` and `\t` into their characters.
fn copy_bracket(chars: &[char], start: usize, out: &mut String) -> usize {
    let mut at = start;
    if chars.get(at) == Some(&'^') {
        out.push('^');
        at = at.saturating_add(1);
    }
    if chars.get(at) == Some(&']') {
        out.push(']');
        at = at.saturating_add(1);
    }
    while let Some(&ch) = chars.get(at) {
        at = at.saturating_add(1);
        match ch {
            ']' => {
                out.push(']');
                return at;
            }
            '[' if matches!(chars.get(at), Some(':' | '.' | '=')) => {
                let delim = chars.get(at).copied().unwrap_or(':');
                out.push('[');
                out.push(delim);
                at = at.saturating_add(1);
                while let Some(&inner) = chars.get(at) {
                    at = at.saturating_add(1);
                    out.push(inner);
                    if inner == delim && chars.get(at) == Some(&']') {
                        out.push(']');
                        at = at.saturating_add(1);
                        break;
                    }
                }
            }
            '\\' => match chars.get(at) {
                Some('n') => {
                    out.push('\n');
                    at = at.saturating_add(1);
                }
                Some('t') => {
                    out.push('\t');
                    at = at.saturating_add(1);
                }
                _ => out.push('\\'),
            },
            other => out.push(other),
        }
    }
    at
}

/// The character GNU's escapes `\a \f \n \r \t \v \cX \dNNN \oNNN \xHH` stand for; `at` is just after the letter.
fn decode_escape(chars: &[char], at: &mut usize, letter: char) -> Option<char> {
    match letter {
        'a' => Some('\u{7}'),
        'f' => Some('\u{c}'),
        'n' => Some('\n'),
        'r' => Some('\r'),
        't' => Some('\t'),
        'v' => Some('\u{b}'),
        'c' => {
            let next = chars.get(*at).copied().filter(char::is_ascii)?;
            *at = at.saturating_add(1);
            let code = u32::from(next.to_ascii_uppercase()) ^ 0x40;
            char::from_u32(code)
        }
        'd' => radix(chars, at, 10, 3),
        'o' => radix(chars, at, 8, 3),
        'x' => radix(chars, at, 16, 2),
        _ => None,
    }
}

fn radix(chars: &[char], at: &mut usize, base: u32, most: usize) -> Option<char> {
    let mut value = 0u32;
    let mut digits = 0usize;
    while digits < most {
        let Some(digit) = chars.get(*at).and_then(|c| c.to_digit(base)) else {
            break;
        };
        value = value.saturating_mul(base).saturating_add(digit);
        *at = at.saturating_add(1);
        digits = digits.saturating_add(1);
    }
    if digits == 0 {
        None
    } else {
        char::from_u32(value)
    }
}

/// An `s` replacement as `match_slash` left it, split into text, groups and case changes.
fn parse_replacement(raw: &str) -> Vec<Part> {
    let chars: Vec<char> = raw.chars().collect();
    let mut parts = Vec::new();
    let mut text = String::new();
    let mut at = 0usize;
    let flush = |text: &mut String, parts: &mut Vec<Part>| {
        if !text.is_empty() {
            parts.push(Part::Text(std::mem::take(text)));
        }
    };
    while let Some(&ch) = chars.get(at) {
        at = at.saturating_add(1);
        if ch == '&' {
            flush(&mut text, &mut parts);
            parts.push(Part::Group(0));
            continue;
        }
        if ch != '\\' {
            text.push(ch);
            continue;
        }
        let Some(&next) = chars.get(at) else {
            text.push('\\');
            break;
        };
        at = at.saturating_add(1);
        if let Some(digit) = next.to_digit(10) {
            flush(&mut text, &mut parts);
            parts.push(Part::Group(usize::try_from(digit).unwrap_or(0)));
            continue;
        }
        let case = match next {
            'L' => Some(CaseOp::Lower),
            'U' => Some(CaseOp::Upper),
            'l' => Some(CaseOp::LowerNext),
            'u' => Some(CaseOp::UpperNext),
            'E' => Some(CaseOp::End),
            _ => None,
        };
        if let Some(op) = case {
            flush(&mut text, &mut parts);
            parts.push(Part::Case(op));
            continue;
        }
        text.push(decode_escape(&chars, &mut at, next).unwrap_or(next));
    }
    flush(&mut text, &mut parts);
    parts
}

/// Append the replacement for one match, applying GNU's case conversions.
fn expand(parts: &[Part], chars: &[char], caps: &Captures, out: &mut String) {
    let mut mode: Option<Case> = None;
    let mut once: Option<Case> = None;
    for part in parts {
        match part {
            Part::Text(text) => push_cased(out, text.chars(), mode, &mut once),
            Part::Group(group) => {
                if let Some(Some((start, end))) = caps.get(*group) {
                    let piece = chars.get(*start..*end).unwrap_or_default();
                    push_cased(out, piece.iter().copied(), mode, &mut once);
                }
            }
            Part::Case(op) => match op {
                CaseOp::Lower => {
                    mode = Some(Case::Lower);
                    once = None;
                }
                CaseOp::Upper => {
                    mode = Some(Case::Upper);
                    once = None;
                }
                CaseOp::LowerNext => once = Some(Case::Lower),
                CaseOp::UpperNext => once = Some(Case::Upper),
                CaseOp::End => {
                    mode = None;
                    once = None;
                }
            },
        }
    }
}

fn push_cased(
    out: &mut String,
    chars: impl Iterator<Item = char>,
    mode: Option<Case>,
    once: &mut Option<Case>,
) {
    for ch in chars {
        match once.take().or(mode) {
            Some(Case::Upper) => out.extend(ch.to_uppercase()),
            Some(Case::Lower) => out.extend(ch.to_lowercase()),
            None => out.push(ch),
        }
    }
}

/// The text of `a`, `i` or `c` with its escapes resolved: a backslash before any other character drops.
fn unescape_text(raw: &[char]) -> String {
    let mut out = String::new();
    let mut at = 0usize;
    while let Some(&ch) = raw.get(at) {
        at = at.saturating_add(1);
        if ch != '\\' {
            out.push(ch);
            continue;
        }
        let Some(&next) = raw.get(at) else {
            break;
        };
        at = at.saturating_add(1);
        out.push(decode_escape(raw, &mut at, next).unwrap_or(next));
    }
    out
}

/// One side of a `y` command, with `\\`, `\n` and the other escapes resolved.
fn unescape_y(raw: &str) -> Vec<char> {
    let chars: Vec<char> = raw.chars().collect();
    let mut out = Vec::new();
    let mut at = 0usize;
    while let Some(&ch) = chars.get(at) {
        at = at.saturating_add(1);
        if ch != '\\' {
            out.push(ch);
            continue;
        }
        let Some(&next) = chars.get(at) else {
            out.push('\\');
            break;
        };
        at = at.saturating_add(1);
        match next {
            '\\' => out.push('\\'),
            _ => match decode_escape(&chars, &mut at, next) {
                Some(decoded) => out.push(decoded),
                None => {
                    out.push('\\');
                    out.push(next);
                }
            },
        }
    }
    out
}

fn split_lines(bytes: &[u8], delim: char, unit: usize) -> Vec<Line> {
    let text = String::from_utf8_lossy(bytes);
    let mut lines = Vec::new();
    let mut rest: &str = &text;
    while !rest.is_empty() {
        match rest.split_once(delim) {
            Some((line, after)) => {
                lines.push(Line {
                    text: line.to_owned(),
                    chomped: true,
                    unit,
                });
                rest = after;
            }
            None => {
                lines.push(Line {
                    text: rest.to_owned(),
                    chomped: false,
                    unit,
                });
                break;
            }
        }
    }
    lines
}

/// The `l` command's view of the pattern space: escapes for the unprintable, wrapped at `width`.
fn list(text: &str, width: usize, delim: char) -> String {
    let mut out = String::new();
    let mut column = 0usize;
    for byte in text.bytes() {
        let piece = match byte {
            b'\\' => "\\\\".to_owned(),
            0x07 => "\\a".to_owned(),
            0x08 => "\\b".to_owned(),
            0x0c => "\\f".to_owned(),
            b'\n' => "\\n".to_owned(),
            b'\r' => "\\r".to_owned(),
            b'\t' => "\\t".to_owned(),
            0x0b => "\\v".to_owned(),
            0x20..=0x7e => char::from(byte).to_string(),
            _ => format!("\\{byte:03o}"),
        };
        if width > 0 && column.saturating_add(piece.len()) > width.saturating_sub(1) {
            out.push_str("\\\n");
            column = 0;
        }
        column = column.saturating_add(piece.len());
        out.push_str(&piece);
    }
    out.push('$');
    out.push(delim);
    out
}

/// Where `-i` with `suffix` keeps the original: a `*` in the suffix stands for the file's name.
fn backup_name(name: &str, suffix: &str) -> String {
    if !suffix.contains('*') {
        return format!("{name}{suffix}");
    }
    let (dir, base) = match name.rsplit_once('/') {
        Some((dir, base)) => (format!("{dir}/"), base),
        None => (String::new(), name),
    };
    let replaced = suffix.replace('*', base);
    if replaced.contains('/') {
        replaced
    } else {
        format!("{dir}{replaced}")
    }
}

fn capitalize(message: &str) -> String {
    let mut chars = message.chars();
    match chars.next() {
        Some(first) => first.to_uppercase().chain(chars).collect(),
        None => String::new(),
    }
}

fn push_char(bytes: &mut Vec<u8>, ch: char) {
    let mut buffer = [0u8; 4];
    bytes.extend_from_slice(ch.encode_utf8(&mut buffer).as_bytes());
}

#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod tests {
    use super::*;

    const PEOPLE: &str = "name,age,city\nada,36,london\nalan,41,manchester\ngrace,85,new york\nlinus,28,helsinki\nmargaret,33,boston\n";
    const NUMBERS: &str = "42\n7\n19\n7\n100\n3\n42\n8\n15\n7\n";
    const LOG: &str = "INFO start\nERROR id=2 failed\nINFO id=3\nERROR id=4\n";

    fn args(list: &[&str]) -> Vec<String> {
        list.iter().map(|arg| (*arg).to_owned()).collect()
    }

    fn sed_with(list: &[&str], stdin: &str, files: &[(&str, &str)]) -> SedOutput {
        let files: Files = files
            .iter()
            .map(|(name, text)| ((*name).to_owned(), Ok(text.as_bytes().to_vec())))
            .collect();
        run(&args(list), stdin.as_bytes(), &files)
    }

    fn sed(list: &[&str], stdin: &str) -> String {
        let output = sed_with(list, stdin, &[]);
        assert_eq!(
            output.stderr,
            b"",
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
        String::from_utf8(output.stdout).unwrap()
    }

    fn error(list: &[&str]) -> (String, i32) {
        let output = sed_with(list, "", &[]);
        (String::from_utf8(output.stderr).unwrap(), output.status)
    }

    fn written(output: &SedOutput) -> Vec<(&str, &str)> {
        output
            .writes
            .iter()
            .map(|write| {
                (
                    write.path.as_str(),
                    std::str::from_utf8(&write.data).unwrap(),
                )
            })
            .collect()
    }

    #[test]
    fn inputs_names_operands_stdin_and_read_targets() {
        assert_eq!(inputs(&args(&["p"])).unwrap(), ["-"]);
        assert_eq!(
            inputs(&args(&["-n", "1r extra\n2R more", "a", "-", "b"])).unwrap(),
            ["a", "-", "b", "extra", "more"]
        );
        assert_eq!(
            inputs(&args(&["-f", "script.sed", "in.txt"])).unwrap(),
            ["in.txt", "script.sed"]
        );
        let refused = inputs(&args(&["s/a/b"])).unwrap_err();
        assert_eq!(
            refused.stderr,
            b"sed: -e expression #1, char 5: unterminated `s' command\n"
        );
        assert_eq!(refused.status, 1);
    }

    #[test]
    fn script_errors_name_the_expression_and_character() {
        assert_eq!(
            error(&["k"]),
            (
                "sed: -e expression #1, char 1: unknown command: `k'\n".to_owned(),
                1
            )
        );
        assert_eq!(
            error(&["-e", "p", "-e", "s/x/y/q"]).0,
            "sed: -e expression #2, char 7: unknown option to `s'\n"
        );
        assert_eq!(
            error(&["/x/{p"]).0,
            "sed: -e expression #1, char 0: unmatched `{'\n"
        );
        assert_eq!(
            error(&["p}"]).0,
            "sed: -e expression #1, char 2: unexpected `}'\n"
        );
        assert_eq!(
            error(&["y/ab/c/"]).0,
            "sed: -e expression #1, char 7: strings for `y' command are different lengths\n"
        );
        assert_eq!(
            error(&["s/a/\\1/"]).0,
            "sed: -e expression #1, char 7: invalid reference \\1 on `s' command's RHS\n"
        );
        assert_eq!(
            error(&["0p"]).0,
            "sed: -e expression #1, char 2: invalid usage of line address 0\n"
        );
        assert_eq!(
            error(&["b nowhere"]).0,
            "sed: can't find label for jump to `nowhere'\n"
        );
        assert_eq!(error(&["s/\\(a\\)\\1/x/"]).1, 1);
        assert_eq!(error(&["-k", "p"]).1, 1);
        assert_eq!(error(&[]).1, 1);
    }

    #[test]
    fn substitution_flags_and_occurrences() {
        assert_eq!(sed(&["s/-/+/2"], "a-b-c-d\n"), "a-b+c-d\n");
        assert_eq!(sed(&["s/-/+/2g"], "a-b-c-d\n"), "a-b+c+d\n");
        assert_eq!(sed(&["s/alpha/x/gI"], "Alpha ALPHA alpha\n"), "x x x\n");
        assert_eq!(sed(&["-n", "s/b/B/p"], "abc\nxyz\n"), "aBc\n");
        assert_eq!(
            sed(&["s/[a-z]*/<&>/g"], "hello world\n"),
            "<hello> <world>\n"
        );
        assert_eq!(sed(&["s/b*/X/g"], "abc\n"), "XaXcX\n");
        assert_eq!(sed(&["s/[0-9]/\\&&/"], "cost 5\n"), "cost &5\n");
        assert_eq!(sed(&["s|/usr|/opt|"], "/usr/bin\n"), "/opt/bin\n");
        assert_eq!(sed(&["s/,/\\n/g"], "a,b\n"), "a\nb\n");
        assert_eq!(sed(&["s/ /\\t/"], "a b\n"), "a\tb\n");
        assert_eq!(sed(&["s/\\t/<TAB>/"], "a\tb\n"), "a<TAB>b\n");
        assert_eq!(
            sed(
                &["s/^[[:space:]]*//;s/[[:space:]]*$//"],
                "  padded  \n\tx \n"
            ),
            "padded\nx\n"
        );
    }

    #[test]
    fn groups_and_case_conversion() {
        assert_eq!(
            sed(&["s/\\(.*\\) \\(.*\\)/\\2, \\1/"], "john smith\n"),
            "smith, john\n"
        );
        assert_eq!(sed(&["-E", "s/(a+)(b)/\\2\\1/"], "aab\n"), "baa\n");
        assert_eq!(sed(&["s/\\w\\+/\\u&/g"], "hello world\n"), "Hello World\n");
        assert_eq!(sed(&["s/.*/\\U&/"], "hello\n"), "HELLO\n");
        assert_eq!(
            sed(&["-E", "s/(\\w+) (\\w+)/\\L\\1\\E \\2/"], "HELLO World\n"),
            "hello World\n"
        );
        assert_eq!(sed(&["s/.*/\\L\\u&/"], "hELLO\n"), "Hello\n");
        assert_eq!(sed(&["s/.*/\\u\\L&/"], "hELLO\n"), "hello\n");
        assert_eq!(sed(&["s/.*/\\l\\U&/"], "hello\n"), "HELLO\n");
        assert_eq!(
            sed(&["s/\\(x*\\)\\(.*\\)/\\u\\1\\2/"], "hello\n"),
            "Hello\n"
        );
        assert_eq!(sed(&["s/a+/X/g"], "a+b aab\n"), "Xb aab\n");
        assert_eq!(sed(&["s/a\\+/X/g"], "a+b aab\n"), "X+b Xb\n");
    }

    #[test]
    fn empty_regex_reuses_the_last_one() {
        assert_eq!(sed(&["/foo/s//baz/g"], "foo bar foo\n"), "baz bar baz\n");
    }

    #[test]
    fn addresses_ranges_and_steps() {
        assert_eq!(sed(&["-n", "1~2p"], NUMBERS), "42\n19\n100\n42\n15\n");
        assert_eq!(sed(&["-n", "0~3p"], NUMBERS), "19\n3\n15\n");
        assert_eq!(sed(&["-n", "0,/x/p"], "x\nx\ny\n"), "x\n");
        assert_eq!(sed(&["-n", "1,/x/p"], "x\nx\ny\n"), "x\nx\n");
        assert_eq!(sed(&["-n", "2,+1p"], NUMBERS), "7\n19\n");
        assert_eq!(sed(&["-n", "5,~4p"], NUMBERS), "100\n3\n42\n8\n");
        assert_eq!(
            sed(&["-n", "/ERROR/,/ERROR/p"], LOG),
            "ERROR id=2 failed\nINFO id=3\nERROR id=4\n"
        );
        assert_eq!(sed(&["-n", "3,1p"], NUMBERS), "19\n");
        assert_eq!(sed(&["-n", "/info/Ip"], LOG), "INFO start\nINFO id=3\n");
        assert_eq!(sed(&["-n", "\\,id=3,p"], LOG), "INFO id=3\n");
        assert_eq!(
            sed(&["-n", "/INFO/!p"], LOG),
            "ERROR id=2 failed\nERROR id=4\n"
        );
        assert_eq!(sed(&["-n", "$p"], NUMBERS), "7\n");
        assert_eq!(sed(&["2,4d"], "1\n2\n3\n4\n5\n"), "1\n5\n");
    }

    #[test]
    fn blocks_labels_and_branches() {
        assert_eq!(
            sed(&["-n", "/ERROR/{s/ERROR //;p}"], LOG),
            "id=2 failed\nid=4\n"
        );
        assert_eq!(sed(&[":a;N;$!ba;s/\\n/,/g"], "1\n2\n3\n"), "1,2,3\n");
        assert_eq!(sed(&["s/x/y/;t;s/$/!/"], "x\nz\n"), "y\nz!\n");
        assert_eq!(sed(&["s/x/y/;T;s/$/!/"], "x\nz\n"), "y!\nz\n");
        assert_eq!(sed(&["-n", "2{p;p}"], "1\n2\n3\n"), "2\n2\n");
        assert_eq!(sed(&["$!{N};P;D"], "1\n2\n3\n"), "1\n2\n3\n");
    }

    #[test]
    fn hold_space_and_multiline_commands() {
        assert_eq!(sed(&["-n", "1!G;h;$p"], "a\nb\nc\n"), "c\nb\na\n");
        assert_eq!(sed(&["N;s/\\n/+/"], "1\n2\n3\n4\n"), "1+2\n3+4\n");
        assert_eq!(sed(&["N;s/\\n/+/"], "1\n2\n3\n"), "1+2\n3\n");
        assert_eq!(sed(&["n;d"], "1\n2\n3\n"), "1\n3\n");
        assert_eq!(sed(&["$!N;P;D"], "1\n2\n3\n"), "1\n2\n3\n");
        assert_eq!(sed(&["x;G"], "a\nb\n"), "\na\na\nb\n");
        assert_eq!(sed(&["H;$!d;x"], "a\nb\n"), "\na\nb\n");
        assert_eq!(sed(&["z;s/^$/empty/"], "a\n"), "empty\n");
    }

    #[test]
    fn text_commands() {
        assert_eq!(sed(&["1i\\top"], "a\nb\n"), "top\na\nb\n");
        assert_eq!(sed(&["1a after one"], "a\nb\n"), "a\nafter one\nb\n");
        assert_eq!(sed(&["2c replaced"], "a\nb\n"), "a\nreplaced\n");
        assert_eq!(sed(&["1,2c gone"], "a\nb\nc\n"), "gone\nc\n");
        assert_eq!(sed(&["a\\\n  two\\\nlines"], "x\n"), "x\n  two\nlines\n");
        assert_eq!(sed(&["-e", "a\\", "-e", "next"], "x\n"), "x\nnext\n");
        assert_eq!(sed(&["$a end"], "x"), "x\nend\n");
        assert_eq!(sed(&["1i\\  lead"], "x\n"), "  lead\nx\n");
    }

    #[test]
    fn printing_commands() {
        assert_eq!(sed(&["-n", "/ERROR/="], LOG), "2\n4\n");
        assert_eq!(sed(&["1p"], "a\nb\n"), "a\na\nb\n");
        assert_eq!(sed(&["-n", "N;P"], "a\nb\n"), "a\n");
        assert_eq!(
            sed(&["-n", "l"], "a\tb\\\u{1}é\n"),
            "a\\tb\\\\\\001\\303\\251$\n"
        );
        let long = "x".repeat(100);
        assert_eq!(
            sed(&["-n", "l"], &format!("{long}\n")),
            format!("{}\\\n{}$\n", "x".repeat(69), "x".repeat(31))
        );
        assert_eq!(
            sed(&["-n", "l 0"], &format!("{long}\n")),
            format!("{long}$\n")
        );
        assert_eq!(sed(&["-n", "l 5"], "abcdefgh\n"), "abcd\\\nefgh$\n");
        assert_eq!(sed(&["y/abc/xyz/"], "aabbcc\n"), "xxyyzz\n");
        assert_eq!(sed(&["N;y/a\\nb/A B/"], "a\nb\n"), "A B\n");
    }

    #[test]
    fn quitting() {
        assert_eq!(sed(&["2q"], "1\n2\n3\n"), "1\n2\n");
        assert_eq!(sed(&["2Q"], "1\n2\n3\n"), "1\n");
        let output = sed_with(&["q5"], "1\n2\n", &[]);
        assert_eq!((output.stdout, output.status), (b"1\n".to_vec(), 5));
        assert_eq!(sed_with(&["Q 3"], "1\n", &[]).status, 3);
        assert_eq!(sed(&["1{a after\nq}"], "1\n2\n"), "1\nafter\n");
    }

    #[test]
    fn missing_trailing_newline_is_kept() {
        assert_eq!(sed(&["s/no/NO/"], "no newline"), "NO newline");
        assert_eq!(sed(&["p"], "a"), "a\na");
        let output = sed_with(&["", "one", "two"], "", &[("one", "a"), ("two", "b\n")]);
        assert_eq!(output.stdout, b"a\nb\n");
    }

    #[test]
    fn null_data_separates_on_nul() {
        assert_eq!(sed(&["-z", "s/\\n/,/g"], "a\nb\n"), "a,b,");
        assert_eq!(sed(&["-z", "s/^/>/"], "a\0b\0"), ">a\0>b\0");
    }

    #[test]
    fn files_streams_and_errors() {
        let files = [("a", "1\n2\n"), ("b", "3\n")];
        assert_eq!(sed_with(&["-n", "$=", "a", "b"], "", &files).stdout, b"3\n");
        assert_eq!(
            sed_with(&["-s", "-n", "$=", "a", "b"], "", &files).stdout,
            b"2\n1\n"
        );
        assert_eq!(
            sed_with(&["-s", "1F", "a", "b"], "", &files).stdout,
            b"a\n1\n2\nb\n3\n"
        );
        assert_eq!(
            sed_with(&["s/z/w/", "a", "-"], "z\n", &files).stdout,
            b"1\n2\nw\n"
        );
        let missing = sed_with(&["s/1/one/", "a", "gone"], "", &files);
        assert_eq!(missing.stdout, b"one\n2\n");
        assert_eq!(
            missing.stderr,
            b"sed: can't read gone: No such file or directory\n"
        );
        assert_eq!(missing.status, 2);
        let mut broken = Files::new();
        broken.insert("x".to_owned(), Err("Permission denied".to_owned()));
        let output = run(&args(&["p", "x"]), b"", &broken);
        assert_eq!(output.stderr, b"sed: can't read x: Permission denied\n");
        assert_eq!(output.status, 2);
    }

    #[test]
    fn in_place_edits_each_file_separately() {
        let output = sed_with(&["-i", "1d;/boston/d", "p.csv"], "", &[("p.csv", PEOPLE)]);
        assert_eq!(output.stdout, b"");
        assert_eq!(
            written(&output),
            [(
                "p.csv",
                "ada,36,london\nalan,41,manchester\ngrace,85,new york\nlinus,28,helsinki\n"
            )]
        );
        let output = sed_with(
            &["-i", "1d", "one.md", "two.md"],
            "",
            &[
                ("one.md", "# alpha\nfirst\n"),
                ("two.md", "# beta\nsecond\n"),
            ],
        );
        assert_eq!(
            written(&output),
            [("one.md", "first\n"), ("two.md", "second\n")]
        );
        let output = sed_with(
            &["-i.bak", "s/alpha/ALPHA/g", "copy.md"],
            "",
            &[("copy.md", "# alpha\n")],
        );
        assert_eq!(
            written(&output),
            [("copy.md.bak", "# alpha\n"), ("copy.md", "# ALPHA\n")]
        );
        let output = sed_with(
            &["--in-place=old_*", "s/a/b/", "dir/f"],
            "",
            &[("dir/f", "a\n")],
        );
        assert_eq!(written(&output), [("dir/old_f", "a\n"), ("dir/f", "b\n")]);
    }

    #[test]
    fn write_commands_fill_their_files() {
        let output = sed_with(&["-n", "s/ERROR/E/w errors.txt"], LOG, &[]);
        assert_eq!(output.stdout, b"");
        assert_eq!(
            written(&output),
            [("errors.txt", "E id=2 failed\nE id=4\n")]
        );
        let output = sed_with(&["-n", "/INFO/w info\n/never/w empty"], LOG, &[]);
        assert_eq!(
            written(&output),
            [("info", "INFO start\nINFO id=3\n"), ("empty", "")]
        );
        let output = sed_with(&["N;W first"], "a\nb\n", &[]);
        assert_eq!(written(&output), [("first", "a\n")]);
        assert_eq!(sed(&["-n", "w /dev/stdout"], "a\n"), "a\n");
    }

    #[test]
    fn read_commands_queue_file_text() {
        let files = [("extra", "X\n"), ("lines", "L1\nL2\n")];
        assert_eq!(
            sed_with(&["1r extra"], "a\nb\n", &files).stdout,
            b"a\nX\nb\n"
        );
        assert_eq!(
            sed_with(&["R lines"], "a\nb\nc\n", &files).stdout,
            b"a\nL1\nb\nL2\nc\n"
        );
        assert_eq!(sed_with(&["r nothing"], "a\n", &files).stdout, b"a\n");
    }

    #[test]
    fn options_and_script_sources() {
        assert_eq!(sed(&["-e", "s/a/b/", "-e", "s/b/c/"], "abc\n"), "cbc\n");
        assert_eq!(
            sed(&["--expression=s/a/b/", "--quiet", "-e", "p"], "a\n"),
            "b\n"
        );
        assert_eq!(sed(&["-nE", "s/(x)/[\\1]/p"], "x\ny\n"), "[x]\n");
        assert_eq!(sed(&["#n\np"], "a\n"), "a\n");
        assert_eq!(sed(&["p", "-n"], "a\n"), "a\n");
        assert_eq!(sed(&["--regexp-extended", "s/a{2}/X/"], "aaa\n"), "Xa\n");
        let output = sed_with(
            &["-f", "script.sed", "in"],
            "",
            &[
                ("script.sed", "s/alpha/A/\n/second/d\n"),
                ("in", "alpha\nsecond\n"),
            ],
        );
        assert_eq!(output.stdout, b"A\n");
        let output = sed_with(&["-f", "bad.sed"], "", &[("bad.sed", "p\nk\n")]);
        assert_eq!(
            output.stderr,
            b"sed: file bad.sed line 2: unknown command: `k'\n"
        );
        assert_eq!(sed_with(&["--version"], "", &[]).stdout, VERSION.as_bytes());
    }

    #[test]
    fn behaviour_checked_against_gnu_sed() {
        assert_eq!(sed(&["-n", "2,~2p"], "a\nb\nc\nd\ne\n"), "b\nc\nd\n");
        assert_eq!(sed(&["-n", "2,~0p"], "a\nb\nc\n"), "b\n");
        assert_eq!(sed(&["-n", "1,0p"], "a\nb\n"), "a\n");
        assert_eq!(sed(&["s/a\\{,2\\}/X/"], "aaa\n"), "Xa\n");
        assert_eq!(sed(&["-E", "s/a{,2}/X/"], "aaa\n"), "Xa\n");
        assert_eq!(sed(&["s/a\\x2a/X/"], "aa*\n"), "X*\n");
        assert_eq!(sed(&["#nfoo"], "a\n"), "");
        assert_eq!(sed(&["-e", "p", "-e", "#n"], "a\n"), "a\na\n");
        assert_eq!(sed(&["$a\\"], "a\n"), "a\n");
        assert_eq!(sed(&["a\\\n"], "a\n"), "a\n\n");
        assert_eq!(sed(&["c\\"], "a\n"), "");
        assert_eq!(sed(&["-n", "/x/{:a;N;ba}"], "a\n"), "");
        assert_eq!(sed(&["-z", "="], "a\0b\0"), concat!("1\0a\0", "2\0b\0"));
        assert_eq!(sed(&["-n", "l 1"], "ab\n"), "\\\na\\\nb$\n");
        assert_eq!(sed(&["s/a/b/ ; p"], "ab\n"), "bb\nbb\n");
        assert_eq!(sed(&["2!c X"], "1\n2\n3\n"), "X\n2\nX\n");
        assert_eq!(sed(&["s/x*/-/g"], "abc\n"), "-a-b-c-\n");
        assert_eq!(sed(&["s/b*/X/2"], "abc\n"), "aXc\n");
        assert_eq!(sed(&["s/x/y/;N;t;s/$/!/"], "1x\n2\n3\n"), "1y\n2!\n3\n");
        assert_eq!(
            error(&["1,p"]).0,
            "sed: -e expression #1, char 3: unexpected `,'\n"
        );
        assert_eq!(error(&["0~0p"]).1, 1);
        assert_eq!(error(&["b nowhere"]).1, 4);
        assert_eq!(error(&["-f", "gone.sed"]).1, 4);
        assert_eq!(error(&["-i", "p"]).1, 4);
        let output = sed_with(&["2s/x/y/;s//z/"], "a\n", &[]);
        assert_eq!(
            output.stderr,
            b"sed: -e expression #1, char 0: no previous regular expression\n"
        );
        assert_eq!(output.status, 1);
    }

    #[test]
    fn unreadable_inputs_are_reported_when_reached() {
        let files = [("two", "b\n")];
        let output = sed_with(&["q", "-", "missing"], "a\n", &files);
        assert_eq!(
            (output.stdout, output.stderr, output.status),
            (b"a\n".to_vec(), Vec::new(), 0)
        );
        let output = sed_with(&["q5", "missing", "-"], "a\n", &files);
        assert_eq!(output.stdout, b"a\n");
        assert_eq!(output.status, 2);
        let output = sed_with(&["-n", "$p", "two", "missing"], "", &files);
        assert_eq!(output.stdout, b"b\n");
        assert_eq!(output.status, 2);
        let mut with_dir: Files = Files::new();
        with_dir.insert("two".to_owned(), Ok(b"b\n".to_vec()));
        with_dir.insert("d".to_owned(), Err("Is a directory".to_owned()));
        let output = run(&args(&["p", "two", "d", "two"]), b"", &with_dir);
        assert_eq!(output.stdout, b"b\nb\n");
        assert_eq!(output.stderr, b"sed: read error on d: Is a directory\n");
        assert_eq!(output.status, 4);
        let output = sed_with(&["-i", "p", "-"], "z\n", &[]);
        assert_eq!(
            output.stderr,
            b"sed: can't read -: No such file or directory\n"
        );
        assert_eq!(output.status, 2);
    }

    #[test]
    fn separate_files_restart_ranges() {
        let files = [("three", "1\n2\n3\n")];
        assert_eq!(
            sed_with(&["-s", "-n", "2,4p", "three", "three"], "", &files).stdout,
            b"2\n3\n2\n3\n"
        );
        assert_eq!(
            sed_with(&["-s", "-n", "0,/1/p", "three", "three"], "", &files).stdout,
            b"1\n1\n"
        );
        assert_eq!(
            sed_with(&["-n", "0,/1/p", "three", "three"], "", &files).stdout,
            b"1\n"
        );
        assert_eq!(
            sed_with(&["-s", "N;s/\\n/+/", "three", "three"], "", &files).stdout,
            b"1+2\n3\n1+2\n3\n"
        );
    }

    #[test]
    fn a_runaway_script_stops() {
        let output = sed_with(&[":a;ba"], "x\n", &[]);
        assert_eq!(output.status, 4);
        assert!(!output.stderr.is_empty());
    }
}
