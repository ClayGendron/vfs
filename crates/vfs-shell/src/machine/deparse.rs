//! A function printed as `declare -f` and `type` print it: bash's own layout,
//! with each word as it was written.

use crate::syntax::ast::{
    AndOr, Arg, AssignValue, Assignment, CaseEnd, Command, CompoundCommand, CondExpr, Connector,
    FunctionDef, List, Pipeline, RedirTarget, Redirect, Span, Word,
};

const INDENT: &str = "    ";

pub fn function(def: &FunctionDef, source: &str) -> String {
    let mut out = format!("{} () \n", def.name);
    let printer = Printer { source };
    out.push_str(&printer.command(&def.body, 0, true));
    out
}

struct Printer<'s> {
    source: &'s str,
}

impl Printer<'_> {
    fn text(&self, span: Span) -> String {
        let start = usize::try_from(span.start).unwrap_or(0);
        let end = usize::try_from(span.end).unwrap_or(0);
        self.source.get(start..end).unwrap_or_default().to_owned()
    }

    fn word(&self, word: &Word) -> String {
        let text = self.text(word.span);
        if text.is_empty() {
            word.static_text().unwrap_or_default()
        } else {
            text
        }
    }

    fn list(&self, list: &List, depth: usize) -> String {
        let pad = INDENT.repeat(depth);
        let mut lines = Vec::new();
        let count = list.items.len();
        for (index, item) in list.items.iter().enumerate() {
            let mut line = format!("{pad}{}", self.and_or(&item.and_or, depth));
            if item.background {
                line.push_str(" &");
            } else if index.saturating_add(1) < count {
                line.push(';');
            }
            lines.push(line);
        }
        lines.join("\n")
    }

    fn and_or(&self, and_or: &AndOr, depth: usize) -> String {
        let mut out = self.pipeline(&and_or.first, depth);
        for (connector, pipeline) in &and_or.rest {
            out.push_str(match connector {
                Connector::And => " && ",
                Connector::Or => " || ",
            });
            out.push_str(&self.pipeline(pipeline, depth));
        }
        out
    }

    fn pipeline(&self, pipeline: &Pipeline, depth: usize) -> String {
        let mut out = String::new();
        if pipeline.negated {
            out.push_str("! ");
        }
        let stages: Vec<String> = pipeline
            .stages
            .iter()
            .map(|stage| self.command(&stage.command, depth, false))
            .collect();
        out.push_str(&stages.join(" | "));
        out
    }

    fn redirects(&self, redirects: &[Redirect]) -> String {
        let mut out = String::new();
        for redirect in redirects {
            out.push(' ');
            match &redirect.target {
                RedirTarget::Word(_) => out.push_str(&self.text(redirect.span)),
                RedirTarget::HereDoc(_) => out.push_str(&self.text(redirect.span)),
            }
        }
        out
    }

    fn assignment(&self, assignment: &Assignment) -> String {
        let text = self.text(assignment.span);
        if !text.is_empty() {
            return text;
        }
        let value = match &assignment.value {
            AssignValue::Scalar(word) => self.word(word),
            AssignValue::Array(_) => "()".to_owned(),
        };
        format!("{}={}", assignment.name, value)
    }

    fn command(&self, command: &Command, depth: usize, top: bool) -> String {
        let pad = INDENT.repeat(depth);
        match command {
            Command::Simple(simple) => {
                let mut parts: Vec<String> = simple
                    .assignments
                    .iter()
                    .map(|a| self.assignment(a))
                    .collect();
                for arg in &simple.words {
                    parts.push(match arg {
                        Arg::Word(word) => self.word(word),
                        Arg::Assign(assignment) => self.assignment(assignment),
                    });
                }
                let mut out = parts.join(" ");
                out.push_str(&self.redirects(&simple.redirects));
                out
            }
            Command::Function(def) => {
                let mut out = format!("{} () \n", def.name);
                out.push_str(&self.command(&def.body, depth, true));
                out
            }
            Command::Compound(compound, redirects) => {
                let mut out = self.compound(compound, depth, top);
                out.push_str(&self.redirects(redirects));
                let _ = &pad;
                out
            }
        }
    }

    fn compound(&self, compound: &CompoundCommand, depth: usize, top: bool) -> String {
        let pad = INDENT.repeat(depth);
        let inner = depth.saturating_add(1);
        match compound {
            CompoundCommand::Brace(list) => {
                if top {
                    format!("{{ \n{}\n{pad}}}", self.list(list, inner))
                } else {
                    format!("{{ \n{}\n{pad}}}", self.list(list, inner))
                }
            }
            CompoundCommand::Subshell(list) => format!("( {} )", self.inline(list)),
            CompoundCommand::If {
                branches,
                otherwise,
            } => {
                let mut out = String::new();
                for (index, (condition, body)) in branches.iter().enumerate() {
                    let keyword = if index == 0 { "if" } else { "elif" };
                    if index > 0 {
                        out.push('\n');
                        out.push_str(&pad);
                    }
                    out.push_str(&format!(
                        "{keyword} {}; then\n{}",
                        self.inline(condition),
                        self.list_terminated(body, inner)
                    ));
                }
                if let Some(body) = otherwise {
                    out.push_str(&format!(
                        "\n{pad}else\n{}",
                        self.list_terminated(body, inner)
                    ));
                }
                out.push_str(&format!("\n{pad}fi"));
                out
            }
            CompoundCommand::While {
                until,
                condition,
                body,
            } => format!(
                "{} {}; do\n{}\n{pad}done",
                if *until { "until" } else { "while" },
                self.inline(condition),
                self.list_terminated(body, inner)
            ),
            CompoundCommand::For {
                name, words, body, ..
            } => {
                let list = match words {
                    Some(words) => format!(
                        " in {}",
                        words
                            .iter()
                            .map(|w| self.word(w))
                            .collect::<Vec<_>>()
                            .join(" ")
                    ),
                    None => " in \"$@\"".to_owned(),
                };
                format!(
                    "for {name}{list};\n{pad}do\n{}\n{pad}done",
                    self.list_terminated(body, inner)
                )
            }
            CompoundCommand::Select {
                name, words, body, ..
            } => {
                let list = match words {
                    Some(words) => format!(
                        " in {}",
                        words
                            .iter()
                            .map(|w| self.word(w))
                            .collect::<Vec<_>>()
                            .join(" ")
                    ),
                    None => " in \"$@\"".to_owned(),
                };
                format!(
                    "select {name}{list};\n{pad}do\n{}\n{pad}done",
                    self.list_terminated(body, inner)
                )
            }
            CompoundCommand::ArithFor {
                init,
                test,
                step,
                body,
                ..
            } => {
                let part = |w: &Option<Word>| {
                    w.as_ref()
                        .map(|w| self.word(w).trim().to_owned())
                        .unwrap_or_default()
                };
                format!(
                    "for (({}; {}; {}))\n{pad}do\n{}\n{pad}done",
                    part(init),
                    part(test),
                    part(step),
                    self.list_terminated(body, inner)
                )
            }
            CompoundCommand::Case { word, arms } => {
                let mut out = format!("case {} in ", self.word(word));
                let arm_pad = INDENT.repeat(inner);
                for arm in arms {
                    let patterns: Vec<String> = arm.patterns.iter().map(|p| self.word(p)).collect();
                    out.push_str(&format!("\n{arm_pad}{})\n", patterns.join(" | ")));
                    if !arm.body.items.is_empty() {
                        out.push_str(&self.list(&arm.body, inner.saturating_add(1)));
                        out.push('\n');
                    }
                    out.push_str(&arm_pad);
                    out.push_str(match arm.end {
                        CaseEnd::Break => ";;",
                        CaseEnd::FallThrough => ";&",
                        CaseEnd::Continue => ";;&",
                    });
                }
                out.push_str(&format!("\n{pad}esac"));
                out
            }
            CompoundCommand::Arith(word, _) => format!("(({}))", self.word(word)),
            CompoundCommand::Cond(expr, _) => format!("[[ {} ]]", self.cond(expr)),
        }
    }

    fn list_terminated(&self, list: &List, depth: usize) -> String {
        let mut text = self.list(list, depth);
        if !text.ends_with('&') {
            text.push(';');
        }
        text
    }

    fn inline(&self, list: &List) -> String {
        let items: Vec<String> = list
            .items
            .iter()
            .map(|item| {
                let mut text = self.and_or(&item.and_or, 0);
                if item.background {
                    text.push_str(" &");
                }
                text
            })
            .collect();
        items.join("; ")
    }

    fn cond(&self, expr: &CondExpr) -> String {
        match expr {
            CondExpr::Unary(op, word) => format!("{op} {}", self.word(word)),
            CondExpr::Binary(a, op, b) => format!("{} {op} {}", self.word(a), self.word(b)),
            CondExpr::Regex(a, b) => format!("{} =~ {}", self.word(a), self.word(b)),
            CondExpr::Word(word) => self.word(word),
            CondExpr::Not(inner) => format!("! {}", self.cond(inner)),
            CondExpr::And(a, b) => format!("{} && {}", self.cond(a), self.cond(b)),
            CondExpr::Or(a, b) => format!("{} || {}", self.cond(a), self.cond(b)),
        }
    }
}
