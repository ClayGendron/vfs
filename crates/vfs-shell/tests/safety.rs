//! The commands that change files do only what their operands and answers select: `rm` refuses
//! an empty, `.` or `..` operand before it resolves one, and its `-i` and `-I` ask on standard
//! error and act only on an answer that begins with `y`, as GNU rm 9.4 does.
#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use shell::host::{MemoryHost, Outcome};

fn world() -> MemoryHost {
    let mut host = MemoryHost::new();
    host.add_dir("/top/sub/deep/inner");
    host.add_file("/top/keep.txt", b"keep\n");
    host.add_file("/top/sub/a.txt", b"alpha\n");
    host.add_file("/top/sub/b.txt", b"");
    host.add_file("/top/sub/c.txt", b"gamma\n");
    host.add_file("/top/sub/e.txt", b"eta\n");
    host.add_file("/top/sub/deep/x.txt", b"x\n");
    host.add_file("/top/sub/deep/inner/y.txt", b"y\n");
    host
}

/// Run `source` in `/top/sub` with `stdin`, returning what ran and what is left.
fn run(source: &str, stdin: &[u8]) -> (Outcome, MemoryHost) {
    let mut host = world();
    let mut config = host.config();
    config.cwd = "/top/sub".to_owned();
    config.stdin = stdin.to_vec();
    let outcome = host.run(source, config);
    (outcome, host)
}

fn stderr(outcome: &Outcome) -> String {
    String::from_utf8_lossy(&outcome.stderr).into_owned()
}

fn removes(outcome: &Outcome) -> Vec<&String> {
    outcome
        .requests
        .iter()
        .filter(|request| request.contains("Remove"))
        .collect()
}

const ALL: [&str; 7] = [
    "/top/keep.txt",
    "/top/sub/a.txt",
    "/top/sub/b.txt",
    "/top/sub/c.txt",
    "/top/sub/e.txt",
    "/top/sub/deep/x.txt",
    "/top/sub/deep/inner/y.txt",
];

fn left(host: &MemoryHost) -> Vec<&'static str> {
    ALL.into_iter().filter(|path| host.exists(path)).collect()
}

// ---------------------------------------------------------------------------
// Operands that name the working directory or its parent
// ---------------------------------------------------------------------------

#[test]
fn an_empty_operand_is_a_missing_file_and_never_the_working_directory() {
    let (outcome, host) = run("X=; rm -rf \"$X\"; echo st=$?", b"");
    assert_eq!(outcome.stdout, b"st=0\n");
    assert_eq!(stderr(&outcome), "");
    assert!(removes(&outcome).is_empty());
    assert_eq!(left(&host), ALL);

    let (outcome, host) = run("rm -r ''; echo st=$?", b"");
    assert_eq!(outcome.stdout, b"st=1\n");
    assert_eq!(
        stderr(&outcome),
        "rm: cannot remove '': No such file or directory\n"
    );
    assert!(removes(&outcome).is_empty());
    assert_eq!(left(&host), ALL);
}

#[test]
fn a_last_component_of_dot_or_dot_dot_is_refused_even_under_force() {
    for (operand, shown) in [
        (".", "."),
        ("..", ".."),
        ("./", "./"),
        ("deep/.", "deep/."),
        ("deep/..", "deep/.."),
        ("deep/./", "deep/./"),
        ("deep/..//", "deep/../"),
    ] {
        let (outcome, host) = run(&format!("rm -rf '{operand}'; echo st=$?"), b"");
        assert_eq!(outcome.stdout, b"st=1\n", "{operand}");
        assert_eq!(
            stderr(&outcome),
            format!("rm: refusing to remove '.' or '..' directory: skipping '{shown}'\n"),
            "{operand}"
        );
        assert!(removes(&outcome).is_empty(), "{operand}");
        assert_eq!(left(&host), ALL, "{operand}");
    }
}

#[test]
fn a_valid_operand_after_a_refused_one_is_still_removed() {
    let (outcome, host) = run("rm -rf . a.txt; echo st=$?", b"");
    assert_eq!(outcome.stdout, b"st=1\n");
    assert!(!host.exists("/top/sub/a.txt"));
    assert!(host.exists("/top/sub/c.txt"));
}

// ---------------------------------------------------------------------------
// -i asks for each file, and acts only on yes
// ---------------------------------------------------------------------------

#[test]
fn rm_i_removes_only_on_an_answer_that_begins_with_y() {
    for (answer, removed) in [
        (&b"y\n"[..], true),
        (b"Yes\n", true),
        (b"n\n", false),
        (b"", false),
        (b"  y\n", false),
    ] {
        let (outcome, host) = run("rm -i a.txt; echo st=$?", answer);
        assert_eq!(outcome.stdout, b"st=0\n");
        assert_eq!(stderr(&outcome), "rm: remove regular file 'a.txt'? ");
        assert_eq!(!host.exists("/top/sub/a.txt"), removed, "{answer:?}");
        assert_eq!(removes(&outcome).len(), usize::from(removed));
    }
}

#[test]
fn rm_i_reads_one_answer_for_each_operand_and_names_an_empty_file() {
    let (outcome, host) = run("rm -i a.txt b.txt c.txt; echo st=$?", b"n\ny\ny\n");
    assert_eq!(outcome.stdout, b"st=0\n");
    assert_eq!(
        stderr(&outcome),
        "rm: remove regular file 'a.txt'? rm: remove regular empty file 'b.txt'? rm: remove regular file 'c.txt'? "
    );
    assert!(host.exists("/top/sub/a.txt"));
    assert!(!host.exists("/top/sub/b.txt"));
    assert!(!host.exists("/top/sub/c.txt"));
}

#[test]
fn rm_ri_descends_on_yes_and_keeps_a_directory_whose_child_it_kept() {
    let all_yes = b"y\ny\ny\ny\ny\ny\ny\n";
    let (outcome, host) = run("rm -ri deep; echo st=$?", all_yes);
    assert_eq!(outcome.stdout, b"st=0\n");
    assert_eq!(
        stderr(&outcome),
        "rm: descend into directory 'deep'? rm: descend into directory 'deep/inner'? \
         rm: remove regular file 'deep/inner/y.txt'? rm: remove directory 'deep/inner'? \
         rm: remove regular file 'deep/x.txt'? rm: remove directory 'deep'? "
    );
    assert!(!host.exists("/top/sub/deep"));

    let (outcome, host) = run("rm -ri deep; echo st=$?", b"n\n");
    assert_eq!(outcome.stdout, b"st=0\n");
    assert_eq!(stderr(&outcome), "rm: descend into directory 'deep'? ");
    assert!(removes(&outcome).is_empty());
    assert_eq!(left(&host), ALL);

    // y.txt kept, inner removal then refused, so deep is not asked about.
    let (outcome, host) = run("rm -ri deep; echo st=$?", b"y\ny\nn\ny\n");
    assert_eq!(outcome.stdout, b"st=1\n");
    assert_eq!(
        stderr(&outcome),
        "rm: descend into directory 'deep'? rm: descend into directory 'deep/inner'? \
         rm: remove regular file 'deep/inner/y.txt'? rm: remove directory 'deep/inner'? \
         rm: cannot remove 'deep/inner': Directory not empty\n\
         rm: remove regular file 'deep/x.txt'? "
    );
    assert!(host.exists("/top/sub/deep/inner/y.txt"));
    assert!(host.exists("/top/sub/deep/x.txt"));
    assert!(
        removes(&outcome)
            .iter()
            .all(|r| r.contains("recursive: false"))
    );
}

// ---------------------------------------------------------------------------
// -I asks once, for recursion or more than three operands
// ---------------------------------------------------------------------------

#[test]
fn rm_capital_i_asks_once_for_four_operands_or_any_recursion() {
    let (outcome, host) = run("rm -I a.txt b.txt c.txt; echo st=$?", b"n\n");
    assert_eq!(stderr(&outcome), "");
    assert!(!host.exists("/top/sub/a.txt"));
    assert_eq!(outcome.stdout, b"st=0\n");

    let four = "rm -I a.txt b.txt c.txt e.txt; echo st=$?";
    let (outcome, host) = run(four, b"n\n");
    assert_eq!(stderr(&outcome), "rm: remove 4 arguments? ");
    assert!(removes(&outcome).is_empty());
    assert_eq!(left(&host), ALL);
    let (outcome, host) = run(four, b"y\n");
    assert_eq!(stderr(&outcome), "rm: remove 4 arguments? ");
    assert!(!host.exists("/top/sub/e.txt"));
    assert_eq!(outcome.stdout, b"st=0\n");

    let (outcome, host) = run("rm -rI deep; echo st=$?", b"");
    assert_eq!(stderr(&outcome), "rm: remove 1 argument recursively? ");
    assert_eq!(left(&host), ALL);
    let (outcome, host) = run("rm -rI deep a.txt; echo st=$?", b"y\n");
    assert_eq!(stderr(&outcome), "rm: remove 2 arguments recursively? ");
    assert!(!host.exists("/top/sub/deep"));
    assert!(!host.exists("/top/sub/a.txt"));
}

#[test]
fn the_last_of_f_i_and_capital_i_wins() {
    let (outcome, host) = run("rm -if a.txt", b"n\n");
    assert_eq!(stderr(&outcome), "");
    assert!(!host.exists("/top/sub/a.txt"));

    let (outcome, host) = run("rm -fi a.txt", b"n\n");
    assert_eq!(stderr(&outcome), "rm: remove regular file 'a.txt'? ");
    assert!(host.exists("/top/sub/a.txt"));

    let (outcome, _) = run("rm -iI a.txt b.txt c.txt e.txt", b"n\n");
    assert_eq!(stderr(&outcome), "rm: remove 4 arguments? ");

    let (outcome, host) = run("rm --interactive=never a.txt", b"n\n");
    assert_eq!(stderr(&outcome), "");
    assert!(!host.exists("/top/sub/a.txt"));

    let (outcome, host) = run("rm --interactive a.txt", b"n\n");
    assert_eq!(stderr(&outcome), "rm: remove regular file 'a.txt'? ");
    assert!(host.exists("/top/sub/a.txt"));
}

#[test]
fn rm_i_on_a_missing_operand_asks_nothing() {
    let (outcome, _) = run("rm -i nope; echo st=$?", b"y\n");
    assert_eq!(outcome.stdout, b"st=1\n");
    assert_eq!(
        stderr(&outcome),
        "rm: cannot remove 'nope': No such file or directory\n"
    );
}

// ---------------------------------------------------------------------------
// sed --sandbox refuses e, r and w before it reads or writes anything
// ---------------------------------------------------------------------------

fn writes(outcome: &Outcome) -> Vec<&String> {
    outcome
        .requests
        .iter()
        .filter(|request| request.contains("Write"))
        .collect()
}

#[test]
fn sed_sandbox_refuses_r_w_and_e_where_gnu_sed_points() {
    for (script, char) in [
        ("w out", 1),
        ("1r keep.txt", 2),
        ("s/a/X/w out", 7),
        ("$!N;2e ls", 6),
        ("p;W out", 3),
        ("R keep.txt", 1),
        ("s/a/b/e", 7),
    ] {
        let (outcome, host) = run(&format!("sed --sandbox '{script}' a.txt; echo st=$?"), b"");
        assert_eq!(outcome.stdout, b"st=1\n", "{script}");
        assert_eq!(
            stderr(&outcome),
            format!(
                "sed: -e expression #1, char {char}: e/r/w commands disabled in sandbox mode\n"
            ),
            "{script}"
        );
        assert!(writes(&outcome).is_empty(), "{script}");
        assert!(!host.exists("/top/sub/out"), "{script}");
    }
}

#[test]
fn sed_sandbox_reaches_a_script_file_and_a_later_expression() {
    let (outcome, _) = run(
        "printf '1r keep.txt\\n' > s.sed; sed --sandbox -f s.sed a.txt; echo st=$?",
        b"",
    );
    assert_eq!(outcome.stdout, b"st=1\n");
    assert_eq!(
        stderr(&outcome),
        "sed: file s.sed line 1: e/r/w commands disabled in sandbox mode\n"
    );
    let (outcome, _) = run("sed --sandbox -e p -e 'w q' a.txt; echo st=$?", b"");
    assert_eq!(
        stderr(&outcome),
        "sed: -e expression #2, char 1: e/r/w commands disabled in sandbox mode\n"
    );
    let (outcome, _) = run("sed --sandbox 's/a/X/' a.txt", b"");
    assert_eq!(outcome.stdout, b"Xlpha\n");
}

// ---------------------------------------------------------------------------
// sed -i publishes a file only when its edit ends well, and its backup first
// ---------------------------------------------------------------------------

#[test]
fn sed_i_leaves_a_file_whose_edit_failed_as_it_was() {
    let line = "printf 'a\\nb\\nc\\n' > f.txt; sed -i '2s//x/' f.txt; echo st=$?; cat f.txt";
    let (outcome, host) = run(line, b"");
    assert_eq!(outcome.stdout, b"st=1\na\nb\nc\n");
    assert_eq!(
        stderr(&outcome),
        "sed: -e expression #1, char 0: no previous regular expression\n"
    );
    assert_eq!(host.file("/top/sub/f.txt"), Some(&b"a\nb\nc\n"[..]));

    let line = "printf 'a\\nb\\n' > g.txt; printf 'a\\nb\\nc\\n' > f.txt; sed -i '3s//x/' g.txt f.txt; echo st=$?";
    let (outcome, host) = run(line, b"");
    assert_eq!(outcome.stdout, b"st=1\n");
    assert_eq!(host.file("/top/sub/f.txt"), Some(&b"a\nb\nc\n"[..]));
    assert_eq!(host.file("/top/sub/g.txt"), Some(&b"a\nb\n"[..]));
}

#[test]
fn sed_i_stops_at_a_backup_it_cannot_write_and_leaves_its_source() {
    let line = "mkdir a.txt.bak; sed -i.bak 's/a/X/' a.txt c.txt; echo st=$?";
    let (outcome, host) = run(line, b"");
    assert_eq!(outcome.stdout, b"st=4\n");
    assert_eq!(
        stderr(&outcome),
        "sed: cannot rename a.txt: Is a directory\n"
    );
    assert_eq!(host.file("/top/sub/a.txt"), Some(&b"alpha\n"[..]));
    assert_eq!(host.file("/top/sub/c.txt"), Some(&b"gamma\n"[..]));
    assert!(!host.exists("/top/sub/c.txt.bak"));

    // A file edited before the refused backup stays edited, with its own backup.
    let line = "mkdir c.txt.bak; sed -i.bak 's/a/X/' a.txt c.txt; echo st=$?";
    let (outcome, host) = run(line, b"");
    assert_eq!(outcome.stdout, b"st=4\n");
    assert_eq!(host.file("/top/sub/a.txt"), Some(&b"Xlpha\n"[..]));
    assert_eq!(host.file("/top/sub/a.txt.bak"), Some(&b"alpha\n"[..]));
    assert_eq!(host.file("/top/sub/c.txt"), Some(&b"gamma\n"[..]));
}

#[test]
fn sed_i_publishes_a_file_a_quit_ended_and_opens_no_later_one() {
    let line = "printf 'a\\nb\\nc\\n' > f.txt; sed -i 's/a/X/;2q5' f.txt c.txt; echo st=$?";
    let (outcome, host) = run(line, b"");
    assert_eq!(outcome.stdout, b"st=5\n");
    assert_eq!(host.file("/top/sub/f.txt"), Some(&b"X\nb\n"[..]));
    assert_eq!(host.file("/top/sub/c.txt"), Some(&b"gamma\n"[..]));
}

// ---------------------------------------------------------------------------
// A writer the host refused stays refused
// ---------------------------------------------------------------------------

fn run_refusing(source: &str, refused: usize) -> (Outcome, MemoryHost) {
    let mut host = world();
    host.add_file("/top/big", &vec![b'z'; 9 << 20]);
    host.refuse_write = Some(("/top/sub/out".to_owned(), refused));
    let mut config = host.config();
    config.cwd = "/top/sub".to_owned();
    let outcome = host.run(source, config);
    (outcome, host)
}

fn writes_to_out(outcome: &Outcome) -> usize {
    outcome
        .requests
        .iter()
        .filter(|request| request.contains("Write") && request.contains("\"/top/sub/out\""))
        .count()
}

#[test]
fn a_writer_refused_at_its_first_write_never_writes_again() {
    let (outcome, host) = run_refusing("cat < /top/big > out; echo st=$?", 0);
    assert_eq!(outcome.stdout, b"st=1\n");
    assert!(stderr(&outcome).contains("out: Permission denied"));
    assert_eq!(writes_to_out(&outcome), 1);
    assert!(!host.exists("/top/sub/out"));
}

#[test]
fn a_writer_refused_after_an_accepted_write_sends_no_later_chunk() {
    let (outcome, host) = run_refusing(
        "{ echo head; cat /top/big; echo tail; } > out; echo st=$?",
        1,
    );
    assert_eq!(outcome.stdout, b"st=1\n");
    assert!(stderr(&outcome).contains("out: Permission denied"));
    assert_eq!(writes_to_out(&outcome), 2);
    assert_eq!(host.file("/top/sub/out"), Some(&b""[..]));
}

#[test]
fn a_write_refused_when_the_line_ends_fails_the_line() {
    let (outcome, host) = run_refusing(": {fd}>out; echo hi >&$fd; echo st=$?", 1);
    assert_eq!(outcome.stdout, b"st=0\n");
    assert_eq!(outcome.status, 1);
    assert!(stderr(&outcome).contains("out: Permission denied"));
    assert_eq!(host.file("/top/sub/out"), Some(&b""[..]));
}
