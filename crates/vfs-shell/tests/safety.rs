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
