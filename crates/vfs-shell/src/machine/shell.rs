//! The state of one shell: its variables, functions, options, descriptors
//! and its place in the walk. A subshell is a fork of it: a copy that
//! shares nothing it can change, with a new place in the walk.

use std::cell::RefCell;
use std::collections::BTreeMap;
use std::rc::Rc;

use super::files::{FileReader, FileWriter, ReadBuffer};
use super::io::{HubRef, ReadEnd, Stream, WriteEnd, Written};
use super::vars::{Value, Var, Vars};
use super::{Fatal, ProgramKind, RequestKey};
use crate::syntax::ast::FunctionDef;

/// A descriptor of the shell: where reads come from or writes go.
#[derive(Clone)]
pub enum Fd {
    /// The line's own output streams.
    Terminal(Stream),
    Null,
    PipeIn(ReadEnd),
    PipeOut(WriteEnd),
    /// Bytes held whole: a here-document, a here-string, the line's input.
    Buffer(Rc<RefCell<ReadBuffer>>),
    FileIn(Rc<RefCell<FileReader>>),
    FileOut(Rc<RefCell<FileWriter>>),
}

#[derive(Clone, Debug, Default)]
pub struct Options {
    pub errexit: bool,
    pub nounset: bool,
    pub xtrace: bool,
    pub noglob: bool,
    pub noclobber: bool,
    pub pipefail: bool,
    pub allexport: bool,
    pub verbose: bool,
    pub posix: bool,
    pub noexec: bool,
    pub braceexpand: bool,
    pub hashall: bool,
    pub errtrace: bool,
    pub functrace: bool,
    pub physical: bool,
    pub keyword: bool,
    pub monitor: bool,
    pub notify: bool,
    pub onecmd: bool,
    pub privileged: bool,
    pub ignoreeof: bool,
    pub interactive_comments: bool,
    pub history: bool,
    pub emacs: bool,
    pub vi: bool,
    /// `shopt` options by name, holding those that are on.
    pub shopt: BTreeMap<&'static str, bool>,
}

/// Every `shopt` name bash knows, with whether it is on in a `bash -c` line.
pub const SHOPT_DEFAULTS: &[(&str, bool)] = &[
    ("array_expand_once", false),
    ("assoc_expand_once", false),
    ("autocd", false),
    ("bash_source_fullpath", false),
    ("cdable_vars", false),
    ("cdspell", false),
    ("checkhash", false),
    ("checkjobs", false),
    ("checkwinsize", false),
    ("cmdhist", true),
    ("compat31", false),
    ("compat32", false),
    ("compat40", false),
    ("compat41", false),
    ("compat42", false),
    ("compat43", false),
    ("compat44", false),
    ("complete_fullquote", true),
    ("direxpand", false),
    ("dirspell", false),
    ("dotglob", false),
    ("execfail", false),
    ("expand_aliases", false),
    ("extdebug", false),
    ("extglob", false),
    ("extquote", true),
    ("failglob", false),
    ("force_fignore", true),
    ("globasciiranges", true),
    ("globskipdots", true),
    ("globstar", false),
    ("gnu_errfmt", false),
    ("histappend", false),
    ("histreedit", false),
    ("histverify", false),
    ("hostcomplete", true),
    ("huponexit", false),
    ("inherit_errexit", false),
    ("interactive_comments", true),
    ("lastpipe", false),
    ("lithist", false),
    ("localvar_inherit", false),
    ("localvar_unset", false),
    ("login_shell", false),
    ("mailwarn", false),
    ("no_empty_cmd_completion", false),
    ("nocaseglob", false),
    ("nocasematch", false),
    ("noexpand_translation", false),
    ("nullglob", false),
    ("patsub_replacement", true),
    ("progcomp", true),
    ("progcomp_alias", false),
    ("promptvars", true),
    ("restricted_shell", false),
    ("shift_verbose", false),
    ("sourcepath", true),
    ("varredir_close", false),
    ("xpg_echo", false),
];

impl Options {
    pub fn new() -> Options {
        let mut options = Options {
            braceexpand: true,
            hashall: true,
            interactive_comments: true,
            ..Options::default()
        };
        for (name, on) in SHOPT_DEFAULTS {
            options.shopt.insert(name, *on);
        }
        options
    }

    pub fn shopt(&self, name: &str) -> bool {
        self.shopt.get(name).copied().unwrap_or(false)
    }

    /// The `set -o` names, in bash's order, with a handle on each.
    pub fn set_names() -> &'static [&'static str] {
        &[
            "allexport",
            "braceexpand",
            "emacs",
            "errexit",
            "errtrace",
            "functrace",
            "hashall",
            "histexpand",
            "history",
            "ignoreeof",
            "interactive-comments",
            "keyword",
            "monitor",
            "noclobber",
            "noexec",
            "noglob",
            "nolog",
            "notify",
            "nounset",
            "onecmd",
            "physical",
            "pipefail",
            "posix",
            "privileged",
            "verbose",
            "vi",
            "xtrace",
        ]
    }

    pub fn set_option(&mut self, name: &str) -> Option<&mut bool> {
        Some(match name {
            "allexport" => &mut self.allexport,
            "braceexpand" => &mut self.braceexpand,
            "emacs" => &mut self.emacs,
            "errexit" => &mut self.errexit,
            "errtrace" => &mut self.errtrace,
            "functrace" => &mut self.functrace,
            "hashall" => &mut self.hashall,
            "history" => &mut self.history,
            "ignoreeof" => &mut self.ignoreeof,
            "interactive-comments" => &mut self.interactive_comments,
            "keyword" => &mut self.keyword,
            "monitor" => &mut self.monitor,
            "noclobber" => &mut self.noclobber,
            "noexec" => &mut self.noexec,
            "noglob" => &mut self.noglob,
            "notify" => &mut self.notify,
            "nounset" => &mut self.nounset,
            "onecmd" => &mut self.onecmd,
            "physical" => &mut self.physical,
            "pipefail" => &mut self.pipefail,
            "posix" => &mut self.posix,
            "privileged" => &mut self.privileged,
            "verbose" => &mut self.verbose,
            "vi" => &mut self.vi,
            "xtrace" => &mut self.xtrace,
            _ => return None,
        })
    }

    pub fn get_set_option(&self, name: &str) -> Option<bool> {
        let mut copy = self.clone();
        copy.set_option(name).map(|flag| *flag)
    }

    /// The short flag letter of a `set -o` name.
    pub fn letter_name(letter: char) -> Option<&'static str> {
        Some(match letter {
            'a' => "allexport",
            'B' => "braceexpand",
            'e' => "errexit",
            'E' => "errtrace",
            'T' => "functrace",
            'h' => "hashall",
            'k' => "keyword",
            'm' => "monitor",
            'C' => "noclobber",
            'n' => "noexec",
            'f' => "noglob",
            'b' => "notify",
            'u' => "nounset",
            't' => "onecmd",
            'P' => "physical",
            'p' => "privileged",
            'v' => "verbose",
            'x' => "xtrace",
            'H' => "histexpand",
            _ => return None,
        })
    }

    /// `$-`: the letters of the flags that are on, in bash's order.
    pub fn flags(&self) -> String {
        let mut out = String::new();
        for (letter, on) in [
            ('a', self.allexport),
            ('e', self.errexit),
            ('f', self.noglob),
            ('h', self.hashall),
            ('k', self.keyword),
            ('m', self.monitor),
            ('n', self.noexec),
            ('p', self.privileged),
            ('t', self.onecmd),
            ('u', self.nounset),
            ('v', self.verbose),
            ('x', self.xtrace),
            ('B', self.braceexpand),
            ('C', self.noclobber),
            ('E', self.errtrace),
            ('P', self.physical),
            ('T', self.functrace),
        ] {
            if on {
                out.push(letter);
            }
        }
        out.push('c');
        out
    }
}

/// A job run with `&`: its number in the line's job table.
#[derive(Clone, Debug)]
pub struct JobRef {
    pub id: usize,
    pub pid: u32,
}

#[derive(Clone)]
pub struct Shell {
    pub vars: Vars,
    pub functions: BTreeMap<String, Rc<FunctionDef>>,
    pub positional: Vec<String>,
    pub arg0: String,
    pub options: Options,
    pub fds: BTreeMap<u32, Fd>,
    pub cwd: String,
    pub last_status: i32,
    pub pipestatus: Vec<i32>,
    pub lineno: u32,
    /// This shell's place in the walk, and its counters there.
    pub task: Vec<u32>,
    pub next_child: u32,
    pub next_request: u32,
    pub function_depth: u32,
    /// Compound commands and substitutions open inside one another, counted against `nesting`.
    pub nesting: u32,
    /// While a simple command's redirections open: whether its files may wait for one write each.
    pub defer_writes: bool,
    /// A job run with `&`, whose status bash reports without its pipeline's `!`.
    pub in_background: bool,
    /// The status a loop takes from the `break` that left it, when it is not 0: `break 0` is 1.
    pub break_status: Option<i32>,
    pub loop_depth: u32,
    /// Inside an `if` or `while` condition, a `!`, or the left of `&&` and `||`.
    pub in_condition: bool,
    pub subshell: u32,
    /// The function call stack: name, and the line it was called from.
    pub frames: Vec<(String, u32)>,
    pub jobs: Vec<JobRef>,
    pub last_job_pid: Option<u32>,
    pub pid: u32,
    /// The shell's own pid as `$BASHPID`, which a subshell changes.
    pub bash_pid: u32,
    pub getopts_char: usize,
    /// The `OPTIND` that `getopts_char` belongs to.
    pub getopts_optind: usize,
    pub programs: Rc<BTreeMap<String, ProgramKind>>,
    pub hub: HubRef,
    pub dir_stack: Vec<String>,
    /// Descriptors a redirection saved, to restore when its command ends.
    pub next_fd: u32,
    pub source: Rc<str>,
    pub hashed: BTreeMap<String, String>,
    pub in_funsub: bool,
    /// Expanding the word of an unquoted `${x:-word}`: its literal text splits too.
    pub literal_splits: bool,
    /// Expanding a word that will be one string: unquoted `$*` joins on `IFS` there.
    pub single_word: bool,
    /// Each `>(list)` of the current command: its descriptor, what was written, and the list.
    pub pending_outputs: Vec<(u32, ReadEnd, crate::syntax::ast::List)>,
}

impl Shell {
    pub fn key(&mut self) -> RequestKey {
        let key = RequestKey {
            task: self.task.clone(),
            ordinal: self.next_request,
        };
        self.next_request = self.next_request.saturating_add(1);
        key
    }

    /// A copy of this shell for a subshell, at a new place in the walk.
    pub fn fork(&mut self) -> Shell {
        let mut child = self.clone();
        child.task.push(self.next_child);
        self.next_child = self.next_child.saturating_add(1);
        child.next_child = 0;
        child.next_request = 0;
        child.subshell = child.subshell.saturating_add(1);
        child.single_word = false;
        child.literal_splits = false;
        child.jobs = Vec::new();
        child.bash_pid = self
            .bash_pid
            .wrapping_add(self.next_child)
            .wrapping_add(100);
        child
    }

    // -- variables -----------------------------------------------------------

    /// The scalar value of a variable, or element 0 of an array.
    pub fn get_var(&self, name: &str) -> Option<String> {
        let var = self.vars.get(name)?;
        match var.value.as_ref()? {
            Value::Scalar(text) => Some(text.clone()),
            Value::Indexed(map) => map.get(&0).cloned(),
            Value::Assoc(map) => map.get("0").cloned(),
        }
    }

    pub fn ifs(&self) -> Option<String> {
        self.get_var("IFS").or_else(|| {
            if self.vars.get("IFS").is_some() {
                None
            } else {
                Some(" \t\n".to_owned())
            }
        })
    }

    /// Set a plain variable, ignoring its attributes. For the shell's own variables.
    pub fn set_plain(&mut self, name: &str, value: &str) {
        let var = self.vars.entry(name);
        var.value = Some(Value::Scalar(value.to_owned()));
    }

    pub fn has_var(&self, name: &str) -> bool {
        self.vars.get(name).is_some_and(|var| var.value.is_some())
    }

    pub fn new_var(text: String) -> Var {
        Var::scalar(text)
    }

    // -- output --------------------------------------------------------------

    /// Write to a descriptor of this shell. A closed or broken one reports why.
    pub async fn write_fd(&mut self, fd: u32, bytes: &[u8]) -> Result<WriteOutcome, Fatal> {
        let Some(target) = self.fds.get(&fd).cloned() else {
            return Ok(WriteOutcome::BadFd);
        };
        match target {
            Fd::Terminal(stream) => {
                self.hub.borrow_mut().emit(stream, bytes)?;
                Ok(WriteOutcome::Done)
            }
            Fd::Null => Ok(WriteOutcome::Done),
            Fd::PipeOut(end) => match end.write(bytes).await? {
                Written::All => Ok(WriteOutcome::Done),
                Written::Broken => Ok(WriteOutcome::Broken),
            },
            Fd::FileOut(writer) => {
                let flush = {
                    let mut writer = writer.borrow_mut();
                    writer.push(&self.hub, bytes)?
                };
                if flush {
                    let key = self.key();
                    FileWriter::flush(&writer, &self.hub, key).await?;
                }
                Ok(WriteOutcome::Done)
            }
            Fd::PipeIn(_) | Fd::Buffer(_) | Fd::FileIn(_) => Ok(WriteOutcome::BadFd),
        }
    }

    /// Write to standard error, which never stops the shell.
    pub async fn error_text(&mut self, text: &str) -> Result<(), Fatal> {
        self.write_fd(2, text.as_bytes()).await.map(|_| ())
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum WriteOutcome {
    Done,
    /// The reading end is gone: the writer dies as if by SIGPIPE.
    Broken,
    BadFd,
}
