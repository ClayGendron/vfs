//! Arithmetic text to a tree. Bash parses arithmetic when it runs, after
//! the text has been expanded, so this parser is called by the machine on
//! expanded text, under the same depth budget as the line.

/// An arithmetic expression.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Expr {
    Number(i64),
    /// A variable, with an optional subscript text: `x` or `a[i+1]`.
    Var(String, Option<String>),
    Unary(UnaryOp, Box<Expr>),
    Binary(BinaryOp, Box<Expr>, Box<Expr>),
    /// `a = b`, `a += b`, ... with `None` for plain `=`.
    Assign(Option<BinaryOp>, String, Option<String>, Box<Expr>),
    /// `++x`, `--x`, `x++`, `x--`: the step, and whether the old value is the result.
    Step(i64, bool, String, Option<String>),
    Ternary(Box<Expr>, Box<Expr>, Box<Expr>),
    Comma(Box<Expr>, Box<Expr>),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum UnaryOp {
    Neg,
    Plus,
    Not,
    BitNot,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BinaryOp {
    Add,
    Sub,
    Mul,
    Div,
    Rem,
    Pow,
    Shl,
    Shr,
    BitAnd,
    BitOr,
    BitXor,
    And,
    Or,
    Lt,
    Le,
    Gt,
    Ge,
    Eq,
    Ne,
}

/// Why arithmetic text does not parse: bash's message and the text it names.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ArithError {
    pub message: String,
    /// The rest of the expression from where the error was found.
    pub token: String,
}

/// Parse expanded arithmetic text. Empty text is zero.
pub fn parse_arith(text: &str, max_depth: u32) -> Result<Expr, ArithError> {
    let mut parser = ArithParser {
        bytes: text.as_bytes(),
        text,
        pos: 0,
        depth: 0,
        max_depth,
    };
    parser.skip_space();
    if parser.at_end() {
        return Ok(Expr::Number(0));
    }
    let expr = parser.comma()?;
    parser.skip_space();
    if !parser.at_end() {
        return Err(parser.error("syntax error in expression"));
    }
    Ok(expr)
}

/// Parse an integer constant the way bash reads one: `0x1f`, `017`, `2#101`.
pub fn parse_number(text: &str) -> Result<i64, String> {
    let bytes = text.as_bytes();
    if bytes.is_empty() {
        return Ok(0);
    }
    if let Some(hash) = text.find('#') {
        let base_text = text.get(..hash).unwrap_or_default();
        let digits = text.get(hash.saturating_add(1)..).unwrap_or_default();
        let base: u32 = base_text.parse().map_err(|_| "invalid number".to_owned())?;
        if !(2..=64).contains(&base) || digits.is_empty() {
            return Err("invalid arithmetic base".to_owned());
        }
        return digits_value(digits, base).ok_or_else(|| "value too great for base".to_owned());
    }
    if let Some(hex) = text.strip_prefix("0x").or_else(|| text.strip_prefix("0X")) {
        if hex.is_empty() {
            return Ok(0);
        }
        return digits_value(hex, 16).ok_or_else(|| "value too great for base".to_owned());
    }
    if text.len() > 1 && text.starts_with('0') {
        return digits_value(text.get(1..).unwrap_or_default(), 8)
            .ok_or_else(|| "value too great for base".to_owned());
    }
    digits_value(text, 10).ok_or_else(|| "value too great for base".to_owned())
}

/// The value of `digits` in `base`, wrapping like a 64-bit integer.
fn digits_value(digits: &str, base: u32) -> Option<i64> {
    let mut value: i64 = 0;
    for ch in digits.chars() {
        let digit = digit_value(ch, base)?;
        if digit >= base {
            return None;
        }
        value = value
            .wrapping_mul(i64::from(base))
            .wrapping_add(i64::from(digit));
    }
    Some(value)
}

fn digit_value(ch: char, base: u32) -> Option<u32> {
    match ch {
        '0'..='9' => Some(u32::from(ch).wrapping_sub(u32::from('0'))),
        'a'..='z' => Some(u32::from(ch).wrapping_sub(u32::from('a')).wrapping_add(10)),
        'A'..='Z' => {
            let offset = u32::from(ch).wrapping_sub(u32::from('A'));
            if base <= 36 {
                Some(offset.wrapping_add(10))
            } else {
                Some(offset.wrapping_add(36))
            }
        }
        '@' => Some(62),
        '_' => Some(63),
        _ => None,
    }
}

struct ArithParser<'a> {
    bytes: &'a [u8],
    text: &'a str,
    pos: usize,
    depth: u32,
    max_depth: u32,
}

impl ArithParser<'_> {
    fn at_end(&self) -> bool {
        self.pos >= self.bytes.len()
    }

    fn peek(&self) -> Option<u8> {
        self.bytes.get(self.pos).copied()
    }

    fn peek_at(&self, ahead: usize) -> Option<u8> {
        self.bytes.get(self.pos.saturating_add(ahead)).copied()
    }

    fn bump(&mut self, count: usize) {
        self.pos = self.pos.saturating_add(count).min(self.bytes.len());
    }

    fn skip_space(&mut self) {
        while matches!(self.peek(), Some(b' ' | b'\t' | b'\n' | b'\r')) {
            self.bump(1);
        }
    }

    fn rest(&self) -> String {
        self.text.get(self.pos..).unwrap_or_default().to_owned()
    }

    fn error(&self, message: &str) -> ArithError {
        ArithError {
            message: message.to_owned(),
            token: self.rest(),
        }
    }

    fn starts_with(&self, op: &str) -> bool {
        self.bytes
            .get(self.pos..)
            .is_some_and(|rest| rest.starts_with(op.as_bytes()))
    }

    /// Consume `op` unless it is the start of a longer operator in `longer`.
    fn eat_op(&mut self, op: &str, longer: &[&str]) -> bool {
        self.skip_space();
        if !self.starts_with(op) || longer.iter().any(|long| self.starts_with(long)) {
            return false;
        }
        self.bump(op.len());
        true
    }

    fn enter(&mut self) -> Result<(), ArithError> {
        self.depth = self.depth.saturating_add(1);
        if self.depth > self.max_depth {
            return Err(self.error("expression recursion level exceeded"));
        }
        Ok(())
    }

    fn leave(&mut self) {
        self.depth = self.depth.saturating_sub(1);
    }

    fn comma(&mut self) -> Result<Expr, ArithError> {
        self.enter()?;
        let mut left = self.assignment()?;
        let mut links = 0u32;
        while self.eat_op(",", &[]) {
            self.enter()?;
            links = links.saturating_add(1);
            let right = self.assignment()?;
            left = Expr::Comma(Box::new(left), Box::new(right));
        }
        self.depth = self.depth.saturating_sub(links);
        self.leave();
        Ok(left)
    }

    fn assignment(&mut self) -> Result<Expr, ArithError> {
        self.enter()?;
        let saved = self.pos;
        self.skip_space();
        if let Some((name, subscript)) = self.lvalue()? {
            self.skip_space();
            const OPS: &[(&str, Option<BinaryOp>)] = &[
                ("<<=", Some(BinaryOp::Shl)),
                (">>=", Some(BinaryOp::Shr)),
                ("+=", Some(BinaryOp::Add)),
                ("-=", Some(BinaryOp::Sub)),
                ("*=", Some(BinaryOp::Mul)),
                ("/=", Some(BinaryOp::Div)),
                ("%=", Some(BinaryOp::Rem)),
                ("&=", Some(BinaryOp::BitAnd)),
                ("|=", Some(BinaryOp::BitOr)),
                ("^=", Some(BinaryOp::BitXor)),
                ("=", None),
            ];
            for (op, kind) in OPS {
                if self.starts_with(op) && !(*op == "=" && self.starts_with("==")) {
                    self.bump(op.len());
                    let value = self.assignment()?;
                    self.leave();
                    return Ok(Expr::Assign(*kind, name, subscript, Box::new(value)));
                }
            }
        }
        self.pos = saved;
        let expr = self.ternary()?;
        self.leave();
        Ok(expr)
    }

    /// A variable name with an optional subscript, at the cursor.
    fn lvalue(&mut self) -> Result<Option<(String, Option<String>)>, ArithError> {
        let start = self.pos;
        match self.peek() {
            Some(b) if b.is_ascii_alphabetic() || b == b'_' => {}
            _ => return Ok(None),
        }
        while matches!(self.peek(), Some(b) if b.is_ascii_alphanumeric() || b == b'_') {
            self.bump(1);
        }
        let name = self
            .text
            .get(start..self.pos)
            .unwrap_or_default()
            .to_owned();
        if self.peek() != Some(b'[') {
            return Ok(Some((name, None)));
        }
        self.bump(1);
        let sub_start = self.pos;
        let mut depth = 1u32;
        while let Some(byte) = self.peek() {
            if byte == b'[' {
                depth = depth.saturating_add(1);
            } else if byte == b']' {
                depth = depth.saturating_sub(1);
                if depth == 0 {
                    break;
                }
            }
            self.bump(1);
        }
        if self.peek() != Some(b']') {
            return Err(self.error("missing `]'"));
        }
        let subscript = self
            .text
            .get(sub_start..self.pos)
            .unwrap_or_default()
            .to_owned();
        self.bump(1);
        Ok(Some((name, Some(subscript))))
    }

    fn ternary(&mut self) -> Result<Expr, ArithError> {
        self.enter()?;
        let condition = self.binary(0)?;
        if self.eat_op("?", &[]) {
            let yes = self.comma_no_assign_top()?;
            if !self.eat_op(":", &[]) {
                return Err(self.error("`:' expected for conditional expression"));
            }
            let no = self.assignment_or_ternary()?;
            self.leave();
            return Ok(Expr::Ternary(
                Box::new(condition),
                Box::new(yes),
                Box::new(no),
            ));
        }
        self.leave();
        Ok(condition)
    }

    fn comma_no_assign_top(&mut self) -> Result<Expr, ArithError> {
        self.comma()
    }

    fn assignment_or_ternary(&mut self) -> Result<Expr, ArithError> {
        self.assignment()
    }

    fn binary(&mut self, level: usize) -> Result<Expr, ArithError> {
        const LEVELS: &[&[(&str, BinaryOp, &[&str])]] = &[
            &[("||", BinaryOp::Or, &[])],
            &[("&&", BinaryOp::And, &[])],
            &[("|", BinaryOp::BitOr, &["||", "|="])],
            &[("^", BinaryOp::BitXor, &["^="])],
            &[("&", BinaryOp::BitAnd, &["&&", "&="])],
            &[("==", BinaryOp::Eq, &[]), ("!=", BinaryOp::Ne, &[])],
            &[
                ("<=", BinaryOp::Le, &[]),
                (">=", BinaryOp::Ge, &[]),
                ("<", BinaryOp::Lt, &["<<", "<="]),
                (">", BinaryOp::Gt, &[">>", ">="]),
            ],
            &[
                ("<<", BinaryOp::Shl, &["<<="]),
                (">>", BinaryOp::Shr, &[">>="]),
            ],
            &[
                ("+", BinaryOp::Add, &["+=", "++"]),
                ("-", BinaryOp::Sub, &["-=", "--"]),
            ],
            &[
                ("*", BinaryOp::Mul, &["*=", "**"]),
                ("/", BinaryOp::Div, &["/="]),
                ("%", BinaryOp::Rem, &["%="]),
            ],
        ];
        let Some(ops) = LEVELS.get(level) else {
            return self.power();
        };
        self.enter()?;
        let mut left = self.binary(level.saturating_add(1))?;
        // Each link of a chain deepens the tree its evaluation recurses into, so it counts as depth.
        let mut links = 0u32;
        'outer: loop {
            for (op, kind, longer) in *ops {
                // After an operand that is no variable, `--` and `++` are an operator and a sign.
                let signed = matches!(*op, "+" | "-") && !matches!(left, Expr::Var(..));
                if self.eat_op(op, longer) || (signed && self.eat_op(op, &[&format!("{op}=")])) {
                    self.enter()?;
                    links = links.saturating_add(1);
                    let right = self.binary(level.saturating_add(1))?;
                    left = Expr::Binary(*kind, Box::new(left), Box::new(right));
                    continue 'outer;
                }
            }
            break;
        }
        self.depth = self.depth.saturating_sub(links);
        self.leave();
        Ok(left)
    }

    fn power(&mut self) -> Result<Expr, ArithError> {
        self.enter()?;
        let base = self.unary()?;
        if self.eat_op("**", &["**="]) {
            let exponent = self.power()?;
            self.leave();
            return Ok(Expr::Binary(
                BinaryOp::Pow,
                Box::new(base),
                Box::new(exponent),
            ));
        }
        self.leave();
        Ok(base)
    }

    fn unary(&mut self) -> Result<Expr, ArithError> {
        self.enter()?;
        self.skip_space();
        let expr = if self.starts_with("++") || self.starts_with("--") {
            let step = if self.starts_with("++") { 1 } else { -1 };
            let saved = self.pos;
            self.bump(2);
            self.skip_space();
            match self.lvalue()? {
                Some((name, subscript)) => Expr::Step(step, false, name, subscript),
                None => {
                    // `--5` is two signs, not a decrement.
                    self.pos = saved.saturating_add(1);
                    let op = if step > 0 {
                        UnaryOp::Plus
                    } else {
                        UnaryOp::Neg
                    };
                    Expr::Unary(op, Box::new(self.unary()?))
                }
            }
        } else if self.eat_op("-", &[]) {
            Expr::Unary(UnaryOp::Neg, Box::new(self.unary()?))
        } else if self.eat_op("+", &[]) {
            Expr::Unary(UnaryOp::Plus, Box::new(self.unary()?))
        } else if self.eat_op("!", &["!="]) {
            Expr::Unary(UnaryOp::Not, Box::new(self.unary()?))
        } else if self.eat_op("~", &[]) {
            Expr::Unary(UnaryOp::BitNot, Box::new(self.unary()?))
        } else {
            self.postfix()?
        };
        self.leave();
        Ok(expr)
    }

    fn postfix(&mut self) -> Result<Expr, ArithError> {
        self.skip_space();
        let start = self.pos;
        if let Some((name, subscript)) = self.lvalue()? {
            self.skip_space();
            if self.starts_with("++") || self.starts_with("--") {
                let step = if self.starts_with("++") { 1 } else { -1 };
                self.bump(2);
                return Ok(Expr::Step(step, true, name, subscript));
            }
            return Ok(Expr::Var(name, subscript));
        }
        self.pos = start;
        self.primary()
    }

    fn primary(&mut self) -> Result<Expr, ArithError> {
        self.skip_space();
        match self.peek() {
            Some(b'(') => {
                self.bump(1);
                let inner = self.comma()?;
                self.skip_space();
                if self.peek() != Some(b')') {
                    return Err(self.error("missing `)'"));
                }
                self.bump(1);
                Ok(inner)
            }
            Some(b'0'..=b'9') => {
                let start = self.pos;
                while matches!(self.peek(), Some(b) if b.is_ascii_alphanumeric() || b == b'#' || b == b'@' || b == b'_')
                {
                    self.bump(1);
                }
                let text = self.text.get(start..self.pos).unwrap_or_default();
                match parse_number(text) {
                    Ok(value) => Ok(Expr::Number(value)),
                    Err(message) => Err(ArithError {
                        message: format!("{message} (error token is \"{text}\")"),
                        token: text.to_owned(),
                    }),
                }
            }
            None => Err(self.error("syntax error: operand expected")),
            Some(_) => {
                let _ = self.peek_at(0);
                Err(self.error("syntax error: operand expected"))
            }
        }
    }
}
