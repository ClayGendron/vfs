//! Structure-aware chunk spans: tree-sitter parse, walk, and merge.
//!
//! One grammar registry (crates.io grammar crates pinned by Cargo.lock)
//! and one batch entry point: UTF-8 bodies in, per-body chunk spans out,
//! parsed in parallel with one `Parser` per worker. The engine returns
//! **byte spans with line ranges**, never text: the host slices content,
//! filters whitespace-only chunks, and re-splits oversized leaves with
//! its character splitter. A body whose grammar is unknown or whose
//! parse fails returns `None`, and the host falls back wholesale.

use rayon::prelude::*;
use tree_sitter::{Language, Node, Parser};

/// One merged chunk span: byte offsets into the body, 1-indexed line
/// range, and whether the span is an indivisible leaf over the budget
/// (the host re-splits those with its character splitter).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SpanRow {
    pub start: u32,
    pub end: u32,
    pub line_start: u32,
    pub line_end: u32,
    pub oversized: bool,
}

/// Grammar names the registry serves, sorted; the host's coverage
/// contract pins its extension map against this list.
pub const GRAMMAR_NAMES: &[&str] = &[
    "bash", "c", "cmake", "cpp", "csharp", "css", "cuda", "d", "dart", "elixir", "elm", "erlang",
    "fish", "fsharp", "gleam", "go", "graphql", "groovy", "haskell", "hcl", "html", "ini", "java",
    "javascript", "json", "julia", "kotlin", "less", "lua", "make", "markdown", "nim", "nix", "ocaml",
    "odin", "perl", "php", "powershell", "proto", "python", "r", "rst", "ruby", "rust", "scala",
    "scss", "solidity", "sql", "svelte", "swift", "terraform", "toml", "tsx", "typescript", "v",
    "vim", "xml", "yaml", "zig",
];

/// Split every `(body, grammar)` pair into merged chunk spans, in
/// parallel. Results are index-aligned with the input; `None` marks a
/// body the structure path could not serve (unknown grammar, language
/// load failure, or a body over `u32` range).
pub fn split_batch(bodies: &[(&[u8], &str)], chunk_size: usize) -> Vec<Option<Vec<SpanRow>>> {
    bodies
        .par_iter()
        .map_init(Parser::new, |parser, (body, grammar)| split_one(parser, body, grammar, chunk_size))
        .collect()
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

fn language(name: &str) -> Option<Language> {
    Some(match name {
        "bash" => tree_sitter_bash::LANGUAGE.into(),
        "c" => tree_sitter_c::LANGUAGE.into(),
        "cmake" => tree_sitter_cmake::LANGUAGE.into(),
        "cpp" => tree_sitter_cpp::LANGUAGE.into(),
        "csharp" => tree_sitter_c_sharp::LANGUAGE.into(),
        "css" => tree_sitter_css::LANGUAGE.into(),
        "cuda" => tree_sitter_cuda::LANGUAGE.into(),
        "d" => tree_sitter_d::LANGUAGE.into(),
        "dart" => tree_sitter_dart::LANGUAGE.into(),
        "elixir" => tree_sitter_elixir::LANGUAGE.into(),
        "elm" => tree_sitter_elm::LANGUAGE.into(),
        "erlang" => tree_sitter_erlang::LANGUAGE.into(),
        "fish" => tree_sitter_fish::language(),
        "fsharp" => tree_sitter_fsharp::LANGUAGE_FSHARP.into(),
        "gleam" => tree_sitter_gleam::LANGUAGE.into(),
        "go" => tree_sitter_go::LANGUAGE.into(),
        "graphql" => tree_sitter_graphql::LANGUAGE.into(),
        "groovy" => tree_sitter_groovy::LANGUAGE.into(),
        "haskell" => tree_sitter_haskell::LANGUAGE.into(),
        "hcl" | "terraform" => tree_sitter_hcl::LANGUAGE.into(),
        "html" => tree_sitter_html::LANGUAGE.into(),
        "ini" => tree_sitter_ini::LANGUAGE.into(),
        "java" => tree_sitter_java::LANGUAGE.into(),
        "javascript" => tree_sitter_javascript::LANGUAGE.into(),
        "json" => tree_sitter_json::LANGUAGE.into(),
        "julia" => tree_sitter_julia::LANGUAGE.into(),
        "kotlin" => tree_sitter_kotlin_ng::LANGUAGE.into(),
        "less" => tree_sitter_less::language(),
        "lua" => tree_sitter_lua::LANGUAGE.into(),
        "make" => tree_sitter_make::LANGUAGE.into(),
        "markdown" => tree_sitter_md::LANGUAGE.into(),
        "nim" => tree_sitter_nim::LANGUAGE.into(),
        "nix" => tree_sitter_nix::LANGUAGE.into(),
        "ocaml" => tree_sitter_ocaml::LANGUAGE_OCAML.into(),
        "odin" => tree_sitter_odin::LANGUAGE.into(),
        "perl" => tree_sitter_perl::LANGUAGE.into(),
        "php" => tree_sitter_php::LANGUAGE_PHP.into(),
        "powershell" => tree_sitter_powershell::LANGUAGE.into(),
        "proto" => tree_sitter_proto::LANGUAGE.into(),
        "python" => tree_sitter_python::LANGUAGE.into(),
        "r" => tree_sitter_r::LANGUAGE.into(),
        "rst" => tree_sitter_rst::LANGUAGE.into(),
        "ruby" => tree_sitter_ruby::LANGUAGE.into(),
        "rust" => tree_sitter_rust::LANGUAGE.into(),
        "scala" => tree_sitter_scala::LANGUAGE.into(),
        "scss" => tree_sitter_scss::language(),
        "solidity" => tree_sitter_solidity::LANGUAGE.into(),
        "sql" => tree_sitter_sequel::LANGUAGE.into(),
        "svelte" => tree_sitter_svelte_ng::LANGUAGE.into(),
        "swift" => tree_sitter_swift::LANGUAGE.into(),
        "toml" => tree_sitter_toml_ng::LANGUAGE.into(),
        "tsx" => tree_sitter_typescript::LANGUAGE_TSX.into(),
        "typescript" => tree_sitter_typescript::LANGUAGE_TYPESCRIPT.into(),
        "v" => tree_sitter_v::LANGUAGE.into(),
        "vim" => tree_sitter_vim::language(),
        "xml" => tree_sitter_xml::LANGUAGE_XML.into(),
        "yaml" => tree_sitter_yaml::LANGUAGE.into(),
        "zig" => tree_sitter_zig::LANGUAGE.into(),
        _ => return None,
    })
}

fn split_one(parser: &mut Parser, body: &[u8], grammar: &str, chunk_size: usize) -> Option<Vec<SpanRow>> {
    if body.len() > u32::MAX as usize {
        return None;
    }
    parser.set_language(&language(grammar)?).ok()?;
    let tree = parser.parse(body, None)?;
    let merged = merge_spans(&atomic_spans(tree.root_node(), chunk_size), chunk_size);

    let newlines: Vec<u32> = memchr::memchr_iter(b'\n', body).map(|i| i as u32).collect();
    let line_at = |byte: u32| newlines.partition_point(|&p| p < byte) as u32 + 1;
    Some(
        merged
            .into_iter()
            .map(|(start, end)| {
                let (start, end) = (start as u32, end as u32);
                SpanRow {
                    start,
                    end,
                    line_start: line_at(start),
                    line_end: if end > start { line_at(end - 1) } else { line_at(start) },
                    oversized: (end - start) as usize > chunk_size,
                }
            })
            .collect(),
    )
}

/// Contiguous, body-covering byte spans, each as coarse as fits budget:
/// iterative in-order descent — a node is emitted whole if it fits or
/// has no named children, otherwise its named children are walked with
/// interstitial gaps (punctuation, comments) as their own spans.
fn atomic_spans(root: Node<'_>, chunk_size: usize) -> Vec<(usize, usize)> {
    enum Item<'a> {
        Emit((usize, usize)),
        Walk(Node<'a>),
    }
    let mut spans = Vec::new();
    let mut stack = vec![Item::Walk(root)];
    while let Some(item) = stack.pop() {
        let node = match item {
            Item::Emit(span) => {
                spans.push(span);
                continue;
            }
            Item::Walk(node) => node,
        };
        let (start, end) = (node.start_byte(), node.end_byte());
        if end - start <= chunk_size || node.named_child_count() == 0 {
            spans.push((start, end));
            continue;
        }
        let mut items = Vec::new();
        let mut cursor = start;
        let mut walker = node.walk();
        for child in node.named_children(&mut walker) {
            if child.start_byte() > cursor {
                items.push(Item::Emit((cursor, child.start_byte())));
            }
            items.push(Item::Walk(child));
            cursor = child.end_byte();
        }
        if cursor < end {
            items.push(Item::Emit((cursor, end)));
        }
        items.reverse();
        stack.extend(items);
    }
    spans
}

/// Greedily merge contiguous spans while the merged byte length fits budget.
fn merge_spans(spans: &[(usize, usize)], chunk_size: usize) -> Vec<(usize, usize)> {
    let mut out = Vec::new();
    let mut current: Option<(usize, usize)> = None;
    for &(start, end) in spans {
        current = match current {
            None => Some((start, end)),
            Some((cur_start, _)) if end - cur_start <= chunk_size => Some((cur_start, end)),
            Some(done) => {
                out.push(done);
                Some((start, end))
            }
        };
    }
    out.extend(current);
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    const PY: &str = "def f(x):\n    return x + 1\n\n\ndef g(y):\n    return y * 2\n";

    fn rows(body: &str, grammar: &str, chunk_size: usize) -> Vec<SpanRow> {
        split_batch(&[(body.as_bytes(), grammar)], chunk_size)[0].clone().expect("splits")
    }

    #[test]
    fn every_registered_grammar_loads() {
        for name in GRAMMAR_NAMES {
            assert!(language(name).is_some(), "{name} failed to load");
        }
    }

    #[test]
    fn unknown_grammar_is_none() {
        assert_eq!(split_batch(&[(b"x", "no-such-grammar")], 2048), vec![None]);
    }

    #[test]
    fn spans_are_contiguous_and_cover_the_body() {
        let rows = rows(PY, "python", 16);
        assert_eq!(rows.first().expect("nonempty").start, 0);
        assert_eq!(rows.last().expect("nonempty").end as usize, PY.len());
        for pair in rows.windows(2) {
            assert_eq!(pair[0].end, pair[1].start);
        }
    }

    #[test]
    fn a_fitting_body_is_one_span() {
        let rows = rows(PY, "python", 4096);
        assert_eq!(rows.len(), 1);
        assert!(!rows[0].oversized);
        assert_eq!((rows[0].line_start, rows[0].line_end), (1, 6));
    }

    #[test]
    fn line_ranges_are_one_indexed_and_tight() {
        // Budget 32 splits the two defs apart; each function spans its own lines.
        let rows = rows(PY, "python", 32);
        assert!(rows.len() >= 2);
        assert_eq!(rows[0].line_start, 1);
        assert_eq!(rows.last().expect("nonempty").line_end, 6);
    }

    #[test]
    fn an_indivisible_leaf_over_budget_is_marked_oversized() {
        let body = format!("x = \"{}\"\n", "a".repeat(64));
        let rows = rows(&body, "python", 16);
        assert!(rows.iter().any(|row| row.oversized));
    }

    #[test]
    fn batch_results_align_with_inputs() {
        let out = split_batch(&[(PY.as_bytes(), "python"), (b"body", "no-such"), (PY.as_bytes(), "python")], 2048);
        assert!(out[0].is_some() && out[1].is_none() && out[2].is_some());
        assert_eq!(out[0], out[2]);
    }
}
