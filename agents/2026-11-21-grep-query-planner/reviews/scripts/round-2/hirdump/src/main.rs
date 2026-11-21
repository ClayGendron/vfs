//! Print the regex-syntax 0.8.11 HIR the vfs-core matcher parses, under the matcher's own builder flags.
use regex_syntax::ParserBuilder;

fn main() {
    let cases: &[(&str, bool)] = &[
        ("kmalloc", false), ("kmalloc", true), ("(?i)kmalloc", false), ("(?i:K)", false), ("[Kk]malloc", false),
        ("Kmalloc|kmalloc", false), ("[k]x", false), ("(?i)_1", false), ("(?i)s", false), ("(?i)ſ", false),
        ("(?i)İ", false), ("abc|abd", false), ("foo\\bbar", false), ("(abc){0}x", false), ("(ab){2,3}", false),
        ("[[:alpha:]]_count", false), ("x[a[bc]]y", false), ("\\<i_count", false), ("\\b{start}i_count", false),
        ("i_count\\>", false), ("[a-c&&b]x", false), ("[ac~~c]x", false),
    ];
    for (pattern, ci) in cases {
        let parsed = ParserBuilder::new().case_insensitive(*ci).multi_line(true).dot_matches_new_line(false).build().parse(pattern);
        match parsed {
            Ok(hir) => println!("{pattern:24} ci={ci:5} -> {:?}", hir.kind()),
            Err(e) => println!("{pattern:24} ci={ci:5} -> ERROR {}", e.to_string().lines().last().unwrap_or("")),
        }
    }
}
