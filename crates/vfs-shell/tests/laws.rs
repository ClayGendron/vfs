//! The laws the machine holds on its native build: one line over one world
//! asks one list of keys whatever order its replies arrive in; its output is
//! the same whatever chunks its files are read in; each budget ends a
//! counted input at exactly its count; a slice hands control back; and no
//! input, of text or of replies, makes the machine panic.
#![allow(
    clippy::unwrap_used,
    clippy::expect_used,
    clippy::panic,
    clippy::indexing_slicing
)]
#![allow(clippy::arithmetic_side_effects)]

use shell::host::{MemoryHost, Outcome};
use shell::machine::{Config, Fatal, Limits, Machine, Reply, Request, Status};
use shell::syntax::{ParseError, ParseLimits, parse};

fn world() -> MemoryHost {
    let mut host = MemoryHost::new();
    host.add_dir("/work");
    host.add_file("/work/a.txt", b"alpha\nbeta\ngamma\ndelta\n");
    host.add_file("/work/b.txt", b"one two three\nfour five\n");
    host
}

fn config(host: &MemoryHost, limits: Limits) -> Config {
    let mut config = host.config();
    config.cwd = "/work".to_owned();
    config.limits = limits;
    config
}

fn run(source: &str, limits: Limits, setup: impl Fn(&mut MemoryHost)) -> Outcome {
    let mut host = world();
    setup(&mut host);
    let config = config(&host, limits);
    host.run(source, config)
}

const LINE: &str = "for f in *.txt; do wc -l < \"$f\"; done | sort -n; cat a.txt | head -2 | tr a-z A-Z; \
    while read -r w; do echo \"[$w]\"; done < b.txt; x=$(grep -c a a.txt); echo $x > out.txt; cat out.txt";

// ---------------------------------------------------------------------------
// Keys and arrival order
// ---------------------------------------------------------------------------

#[test]
fn two_runs_of_one_line_ask_equal_key_lists() {
    let first = run(LINE, Limits::default(), |_| {});
    let second = run(LINE, Limits::default(), |_| {});
    assert!(!first.requests.is_empty());
    assert_eq!(first.requests, second.requests);
    assert_eq!(first.stdout, second.stdout);
}

#[test]
fn the_order_replies_arrive_in_changes_nothing() {
    let ordered = run(LINE, Limits::default(), |_| {});
    let reversed = run(LINE, Limits::default(), |host| host.reverse_replies = true);
    assert_eq!(ordered.stdout, reversed.stdout);
    assert_eq!(ordered.requests, reversed.requests);
}

#[test]
fn output_is_the_same_whatever_the_chunk_boundaries() {
    let line = "cat a.txt b.txt | wc -c; while read -r l; do echo \"<$l>\"; done < a.txt; head -c 7 b.txt; echo; x=$(<a.txt); echo ${#x}";
    let whole = run(line, Limits::default(), |_| {});
    for chunk in [1, 2, 3, 5, 64] {
        let chunked = run(line, Limits::default(), |host| {
            host.read_chunk = Some(chunk)
        });
        assert_eq!(whole.stdout, chunked.stdout, "chunk {chunk}");
    }
    assert_eq!(
        String::from_utf8_lossy(&whole.stdout).lines().next(),
        Some("47")
    );
}

// ---------------------------------------------------------------------------
// Budgets end a counted input at exactly its count
// ---------------------------------------------------------------------------

#[test]
fn the_source_budget_admits_its_count_and_refuses_one_more() {
    let limits = ParseLimits {
        source_bytes: 10,
        ..ParseLimits::default()
    };
    assert!(parse("echo 12345", &limits).is_ok());
    assert_eq!(
        parse("echo 123456", &limits).err(),
        Some(ParseError::Budget("source", 10))
    );
}

#[test]
fn the_token_budget_admits_its_count_and_refuses_one_more() {
    let limits = ParseLimits {
        tokens: 5,
        ..ParseLimits::default()
    };
    assert!(parse("a b c d e", &limits).is_ok());
    assert_eq!(
        parse("a b c d e f", &limits).err(),
        Some(ParseError::Budget("tokens", 5))
    );
}

#[test]
fn the_depth_budget_refuses_deep_input_before_the_stack_does() {
    let limits = ParseLimits::default();
    for (depth, ok) in [(40, true), (100_000, false)] {
        let line = format!("{}true{}", "( ".repeat(depth), " )".repeat(depth));
        let result = parse(&line, &limits);
        assert_eq!(result.is_ok(), ok, "depth {depth}");
        if !ok {
            assert_eq!(
                result.err(),
                Some(ParseError::Budget("depth", u64::from(limits.depth)))
            );
        }
    }
    let deep_word = format!("echo {}x{}", "\"$(".repeat(50_000), ")\"".repeat(50_000));
    assert!(matches!(
        parse(&deep_word, &limits),
        Err(ParseError::Budget("depth", _))
    ));
}

#[test]
fn the_pipeline_budget_admits_its_count_and_refuses_one_more() {
    let limits = ParseLimits::default();
    let stages = |n: usize| vec!["true"; n].join(" | ");
    assert!(parse(&stages(64), &limits).is_ok());
    assert_eq!(
        parse(&stages(65), &limits).err(),
        Some(ParseError::Budget("pipeline_stages", 64))
    );
}

#[test]
fn the_loop_budget_admits_its_count_and_refuses_one_more() {
    let limits = Limits {
        loop_iterations: 100,
        ..Limits::default()
    };
    let exactly = run(
        "i=0; while (( i < 100 )); do i=$((i+1)); done; echo $i",
        limits,
        |_| {},
    );
    assert_eq!(String::from_utf8_lossy(&exactly.stdout), "100\n");
    let over = run(
        "i=0; while (( i < 101 )); do i=$((i+1)); done; echo $i",
        limits,
        |_| {},
    );
    assert_eq!(over.status, 137);
    assert_eq!(
        over.ended.as_deref(),
        Some("Budget(\"loop_iterations\", 100)")
    );
}

#[test]
fn the_function_budget_admits_its_count_and_refuses_one_more() {
    let limits = Limits {
        function_depth: 50,
        ..Limits::default()
    };
    let line =
        |n: u32| format!("f() {{ if (( $1 > 1 )); then f $(( $1 - 1 )); fi; }}; f {n}; echo done");
    let exactly = run(&line(50), limits, |_| {});
    assert_eq!(String::from_utf8_lossy(&exactly.stdout), "done\n");
    let over = run(&line(51), limits, |_| {});
    assert_eq!(over.status, 137);
    assert_eq!(
        over.ended.as_deref(),
        Some("Budget(\"function_depth\", 50)")
    );
}

#[test]
fn the_memory_budget_ends_a_line_before_it_holds_more() {
    let limits = Limits {
        memory_bytes: 1 << 20,
        ..Limits::default()
    };
    let over = run("x=a; while :; do x=$x$x; done", limits, |_| {});
    assert_eq!(over.status, 137);
    assert_eq!(over.ended.as_deref(), Some("Budget(\"memory\", 1048576)"));
    let brace = run("echo {1..2000000000}", Limits::default(), |_| {});
    assert_eq!(
        brace.status, 137,
        "a brace expansion is refused before it is built"
    );
}

#[test]
fn the_output_budget_admits_its_count_and_refuses_one_more() {
    let limits = Limits {
        output_bytes: 100,
        loop_iterations: u64::MAX,
        ..Limits::default()
    };
    let exactly = run(
        "for i in 1 2 3 4 5 6 7 8 9 10; do echo 123456789; done",
        limits,
        |_| {},
    );
    assert_eq!(exactly.stdout.len(), 100);
    assert_eq!(exactly.status, 0);
    let over = run("while :; do echo 123456789; done", limits, |_| {});
    assert_eq!(over.status, 137);
    assert_eq!(
        over.stdout.len(),
        100,
        "what fits is kept, and nothing past it"
    );
    assert_eq!(over.ended.as_deref(), Some("Budget(\"output\", 100)"));
}

#[test]
fn a_width_or_precision_past_the_formatters_limit_is_written_not_a_panic() {
    let line = format!(
        "printf %.65536f 1 | wc -c; printf %.70000e 1 | wc -c; printf %.70000g 1; echo; echo {{{}1..2}} | wc -c",
        "0".repeat(70_000)
    );
    let outcome = run(&line, Limits::default(), |_| {});
    assert_eq!(outcome.ended, None);
    assert_eq!(
        String::from_utf8_lossy(&outcome.stdout),
        "65538\n70006\n1\n140004\n"
    );
}

#[test]
fn a_regex_search_that_spends_its_budget_fails_and_never_answers_no_match() {
    let line = "x=$(printf 'a%.0s' {1..5000}); [[ $x =~ ^a*$ ]]; echo $?; echo $x > big; grep -c '^a*$' big; echo $?";
    let outcome = run(line, Limits::default(), |_| {});
    assert_eq!(String::from_utf8_lossy(&outcome.stdout), "2\n2\n");
    let stderr = String::from_utf8_lossy(&outcome.stderr);
    assert!(stderr.contains("too complex"), "{stderr}");
}

// ---------------------------------------------------------------------------
// Writes
// ---------------------------------------------------------------------------

#[test]
fn each_redirection_is_one_write() {
    let line = "echo x > f; echo y >> f; echo z >> new; { echo a; echo b; } > g; set -C; echo n > fresh; set +C; : > empty; cat f g new fresh";
    let outcome = run(line, Limits::default(), |_| {});
    assert_eq!(
        String::from_utf8_lossy(&outcome.stdout),
        "x\ny\na\nb\nz\nn\n"
    );
    let writes: Vec<&String> = outcome
        .requests
        .iter()
        .filter(|r| r.contains("Write"))
        .collect();
    assert_eq!(writes.len(), 6, "{writes:#?}");
    assert!(
        writes[1].contains("Append") && writes[4].contains("CreateNew"),
        "{writes:#?}"
    );
}

#[test]
fn a_read_of_a_file_its_own_command_truncates_sees_it_empty() {
    let outcome = run(
        "echo old > f; cat f > f; wc -c < f",
        Limits::default(),
        |_| {},
    );
    assert_eq!(String::from_utf8_lossy(&outcome.stdout), "0\n");
}

// ---------------------------------------------------------------------------
// Programs the host resolves
// ---------------------------------------------------------------------------

fn shout(args: &[String], input: &[u8]) -> (Vec<u8>, Vec<u8>, i32) {
    let mut out = input.to_ascii_uppercase();
    for arg in args {
        out.extend_from_slice(arg.as_bytes());
        out.push(b'\n');
    }
    (out, b"shout: done\n".to_vec(), 3)
}

#[test]
fn a_name_the_host_resolves_runs_as_the_host_answers() {
    let line = "printf 'a\\nb\\n' | shout x y; echo $?; x=$(printf %070000d 0); echo $x | shout | wc -c; \
        curl http://example.com; echo $?; nosuch; echo $?";
    let outcome = run(line, Limits::default(), |host| {
        host.add_program("shout", shout);
        host.refuse_program("curl", 126, "network access is not available here");
    });
    assert_eq!(
        String::from_utf8_lossy(&outcome.stdout),
        "A\nB\nx\ny\n3\n70001\n126\n127\n"
    );
    let stderr = String::from_utf8_lossy(&outcome.stderr);
    assert!(stderr.contains("shout: done"), "{stderr}");
    assert!(
        stderr.contains("bash: line 1: curl: network access is not available here"),
        "{stderr}"
    );
    assert!(
        stderr.contains("bash: line 1: nosuch: command not found"),
        "{stderr}"
    );
    let feeds = outcome
        .requests
        .iter()
        .filter(|r| r.contains("Feed"))
        .count();
    assert!(
        feeds >= 3,
        "a program's input is fed a chunk at a time: {feeds} feeds"
    );
    assert_eq!(
        outcome
            .requests
            .iter()
            .filter(|r| r.contains("Start"))
            .count(),
        4
    );
}

// ---------------------------------------------------------------------------
// The slice and cancel
// ---------------------------------------------------------------------------

#[test]
fn a_slice_hands_control_back_and_cancel_ends_the_line() {
    let limits = Limits {
        slice: 1_000,
        loop_iterations: u64::MAX,
        ..Limits::default()
    };
    let mut machine = Machine::new(
        "while :; do :; done",
        Config {
            limits,
            ..Config::default()
        },
    )
    .unwrap();
    for _ in 0..5 {
        let step = machine.step(Vec::new());
        assert_eq!(step.status, Status::Running);
        assert!(step.requests.is_empty());
    }
    machine.cancel();
    let step = machine.step(Vec::new());
    assert_eq!(step.status, Status::Ended(Fatal::Cancelled, 130));
}

// ---------------------------------------------------------------------------
// Fuzz targets: seeded, a declared number of iterations, the stable compiler
// ---------------------------------------------------------------------------

/// A small seeded generator, so a failure names its seed and repeats.
struct Rng(u64);

impl Rng {
    fn next(&mut self) -> u64 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        self.0
    }

    fn below(&mut self, n: usize) -> usize {
        (self.next() % n.max(1) as u64) as usize
    }

    fn pick<'a>(&mut self, items: &[&'a str]) -> &'a str {
        items[self.below(items.len())]
    }
}

const FRAGMENTS: &[&str] = &[
    "echo", " ", "$", "${", "}", "(", ")", "((", "))", "[[", "]]", "'", "\"", "`", "\\", "\n", ";",
    "&", "|", "&&", "||", "<", ">", ">>", "<<", "<<<", "EOF", "<(", ">(", "$(", "$((", "{", ",",
    "..", "*", "?", "[", "]", "!", "#", "=", "+=", "x", "1", "-", "if", "then", "fi", "for", "in",
    "do", "done", "while", "case", "esac", ";;", "function", "a[", "@", ":-", "##", "%%", "//",
    "^^", "~", "\t", "declare", "read", "printf", "%s", "cat", "f()", "{ ", " }", "\u{e9}",
];

/// Iterations of each fuzz target in the gate.
const PARSE_ITERATIONS: u64 = 20_000;
const MACHINE_ITERATIONS: u64 = 1_500;

#[test]
fn the_parser_classifies_any_input_without_panicking() {
    let limits = ParseLimits::default();
    for seed in 1..=PARSE_ITERATIONS {
        let mut rng = Rng(seed.wrapping_mul(0x9E37_79B9_7F4A_7C15) | 1);
        let mut text = String::new();
        let pieces = rng.below(40);
        for _ in 0..pieces {
            if rng.below(8) == 0 {
                text.push(char::from((rng.below(95) + 32) as u8));
            } else {
                text.push_str(rng.pick(FRAGMENTS));
            }
        }
        let result = std::panic::catch_unwind(|| parse(&text, &limits));
        assert!(result.is_ok(), "seed {seed} panicked on {text:?}");
    }
}

const SCRIPTS: &[&str] = &[
    "echo hi",
    "x=$(cat a.txt)",
    "for i in 1 2 3; do echo $i; done",
    "while read -r l; do echo $l; done < a.txt",
    "cat a.txt | sort | uniq -c | head -3",
    "grep -n a *.txt",
    "ls; find . -name '*.txt'",
    "echo $(( RANDOM % 3 ))",
    "printf '%s\\n' \"${arr[@]}\"",
    "arr=(a b c); echo ${#arr[@]}",
    "f() { echo \"$@\"; return 3; }; f a b",
    "cp a.txt c.txt && mv c.txt d.txt; rm -f d.txt",
    "echo x > out.txt; cat out.txt >> out.txt",
    "case $x in a*) echo a;; *) echo other;; esac",
    "[[ -f a.txt ]] && echo yes",
    "set -e; false; echo no",
    "read x <<< \"$(cat b.txt)\"; echo $x",
    "echo {1..5} | wc -w",
    "cat <(echo procsub)",
    "mkdir -p d/e; touch d/e/f; ls -R d",
    "sed -n 1p a.txt",
    "cd /work && pwd",
];

/// A host that answers truly, with an error, or with junk, at random.
fn random_reply(rng: &mut Rng, host: &mut MemoryHost, request: &Request) -> Reply {
    match rng.below(6) {
        0 => Reply::Error(shell::machine::HostError::PermissionDenied),
        1 => Reply::Data {
            bytes: (0..rng.below(64)).map(|_| rng.below(256) as u8).collect(),
            eof: rng.below(2) == 0,
        },
        2 => match request {
            Request::List { .. } => Reply::Entries(Vec::new()),
            _ => Reply::Done,
        },
        _ => host.answer(request),
    }
}

#[test]
fn the_machine_ends_under_any_replies_without_panicking() {
    let limits = Limits {
        memory_bytes: 4 << 20,
        loop_iterations: 2_000,
        function_depth: 32,
        slice: 500,
        ..Limits::default()
    };
    let mut started = 0u64;
    let mut asked = 0u64;
    for seed in 1..=MACHINE_ITERATIONS {
        let mut rng = Rng(seed.wrapping_mul(0x2545_F491_4F6C_DD1D) | 1);
        let mut text = String::new();
        for index in 0..1 + rng.below(4) {
            if index > 0 {
                text.push_str(rng.pick(&["; ", "\n", " | ", " && ", " || "]));
            }
            text.push_str(rng.pick(SCRIPTS));
        }
        let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            let mut host = world();
            let config = config(&host, limits);
            let Ok(mut machine) = Machine::new(&text, config) else {
                return true;
            };
            started += 1;
            let mut replies = Vec::new();
            for _ in 0..20_000 {
                let step = machine.step(std::mem::take(&mut replies));
                for (key, request) in step.requests {
                    asked += 1;
                    let reply = random_reply(&mut rng, &mut host, &request);
                    replies.push((key, reply));
                }
                if step.status != Status::Running {
                    return true;
                }
            }
            false
        }));
        match outcome {
            Ok(ended) => assert!(ended, "seed {seed} did not end: {text:?}"),
            Err(_) => panic!("seed {seed} panicked on {text:?}"),
        }
    }
    // The target is only worth its iterations if the lines start and ask.
    assert!(
        started * 10 >= MACHINE_ITERATIONS * 9,
        "{started} of {MACHINE_ITERATIONS} lines started"
    );
    assert!(asked >= MACHINE_ITERATIONS * 2, "{asked} requests asked");
}
