//! Markdown references off the tree-sitter-markdown trees.
//!
//! One batch entry point: UTF-8 document bodies in, per-body references
//! out, parsed in parallel with one `RefParser` per worker. The crate
//! splices the two grammars itself: the block grammar parses the body,
//! and the inline grammar parses each `inline` or `pipe_table_cell` node
//! over the node's range minus its block continuation markers, one inline
//! tree at a time, walked and dropped before the next. A reference is a
//! link destination — an inline link, an image, or a reference
//! definition — or a code span shaped like a path. Each carries the
//! referring line, folded to one bounded line.
//! Fenced code, indented code and HTML blocks hold no references by
//! construction: the tree never yields link nodes inside them. The
//! engine returns raw destination text; the host decides what is an
//! in-mount reference (schemes, anchors, fragments) and resolves it.
//!
//! The walk is linear in the body: the block tree and each inline tree
//! are walked with their own cursors, whose steps cost constant time;
//! only reference nodes are decoded; and each reference finds its line by
//! bisection over the body's newline offsets, a line holding many
//! references folded once.

use memchr::memchr_iter;
use rayon::prelude::*;
use tree_sitter::{Node, Parser, Range, Tree};

/// The folded referring line is bounded to this many characters.
pub const MAX_CONTEXT_CHARS: usize = 256;

/// The longest extension a bare file name may carry to count as a path.
const MAX_EXTENSION_CHARS: usize = 8;

/// One reference: the destination text as written and the line holding it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MarkdownRef {
    pub dest: String,
    pub context: String,
}

/// The two Markdown grammars, one parser each; build one per worker.
pub struct RefParser {
    block: Parser,
    inline: Parser,
}

impl Default for RefParser {
    /// Both grammars load or the build is defective, so a failed load panics.
    fn default() -> Self {
        let mut block = Parser::new();
        block.set_language(&tree_sitter_md::LANGUAGE.into()).expect("the Markdown block grammar loads");
        let mut inline = Parser::new();
        inline.set_language(&tree_sitter_md::INLINE_LANGUAGE.into()).expect("the Markdown inline grammar loads");
        RefParser { block, inline }
    }
}

/// References per body, in document order, parsed in parallel.
pub fn markdown_refs_batch(bodies: &[&[u8]]) -> Vec<Vec<MarkdownRef>> {
    bodies
        .par_iter()
        .map_init(RefParser::default, |parser, body| markdown_refs(parser, body))
        .collect()
}

/// References in one body; an unparseable body (a cancelled parse) yields none.
pub fn markdown_refs(parser: &mut RefParser, body: &[u8]) -> Vec<MarkdownRef> {
    walk(parser, body).0
}

/// Collapse whitespace runs to one space, trim, and cap the character count.
pub fn fold_line(line: &str) -> String {
    let mut folded = String::with_capacity(line.len().min(MAX_CONTEXT_CHARS));
    let mut kept = 0usize;
    let mut pending_space = false;
    for ch in line.chars() {
        if ch.is_whitespace() {
            pending_space = kept > 0;
            continue;
        }
        if pending_space {
            if kept == MAX_CONTEXT_CHARS {
                break;
            }
            folded.push(' ');
            kept += 1;
            pending_space = false;
        }
        if kept == MAX_CONTEXT_CHARS {
            break;
        }
        folded.push(ch);
        kept += 1;
    }
    folded
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/// What one walk cost: lines folded, and bytes handed to the decoder.
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
struct WalkCost {
    folds: usize,
    decoded_bytes: usize,
}

/// The references of one body with the walk's cost.
///
/// The block tree is walked with a `TreeCursor`; at an inline node, its
/// inline tree is parsed, walked in place of the node's block children,
/// and dropped. A failed inline parse skips that node. No step calls
/// `Node::parent`, which walks down from the root.
fn walk(parser: &mut RefParser, body: &[u8]) -> (Vec<MarkdownRef>, WalkCost) {
    let mut refs = Vec::new();
    let mut cost = WalkCost::default();
    let Some(tree) = parser.block.parse(body, None) else {
        return (refs, cost);
    };
    let mut lines = LineContexts::new(body);
    let mut cursor = tree.walk();
    loop {
        let node = cursor.node();
        visit(node, body, &mut lines, &mut refs, &mut cost);
        let descended = if matches!(node.kind(), "inline" | "pipe_table_cell") {
            if let Some(inline) = parse_inline(&mut parser.inline, node, body) {
                walk_inline(&inline, body, &mut lines, &mut refs, &mut cost);
            }
            false
        } else {
            cursor.goto_first_child()
        };
        if descended {
            continue;
        }
        loop {
            if cursor.goto_next_sibling() {
                break;
            }
            if !cursor.goto_parent() {
                return (refs, cost);
            }
        }
    }
}

/// The inline grammar's tree of one inline node, over its inline ranges.
fn parse_inline(inline: &mut Parser, node: Node<'_>, body: &[u8]) -> Option<Tree> {
    inline.set_included_ranges(&inline_ranges(node)).ok()?;
    inline.parse(body, None)
}

/// An inline node's range minus the range of every named child, in order.
///
/// The named children are block syntax inside the paragraph (continuation
/// markers, an `ERROR` node in a malformed body), never inline text; an
/// empty piece between adjacent children is kept.
fn inline_ranges(node: Node<'_>) -> Vec<Range> {
    let mut ranges = Vec::new();
    let mut range = node.range();
    let mut cursor = node.walk();
    for child in node.named_children(&mut cursor) {
        ranges.push(Range {
            start_byte: range.start_byte,
            start_point: range.start_point,
            end_byte: child.start_byte(),
            end_point: child.start_position(),
        });
        range.start_byte = child.end_byte();
        range.start_point = child.end_position();
    }
    ranges.push(range);
    ranges
}

/// One inline tree's nodes below its root, in document order.
fn walk_inline(tree: &Tree, body: &[u8], lines: &mut LineContexts<'_>, refs: &mut Vec<MarkdownRef>, cost: &mut WalkCost) {
    let mut cursor = tree.walk();
    if !cursor.goto_first_child() {
        return;
    }
    // Our own depth: TreeCursor::depth and Node::parent both cost the node's depth.
    let mut depth = 1usize;
    loop {
        visit(cursor.node(), body, lines, refs, cost);
        if cursor.goto_first_child() {
            depth += 1;
            continue;
        }
        loop {
            if cursor.goto_next_sibling() {
                break;
            }
            cursor.goto_parent();
            depth -= 1;
            if depth == 0 {
                return;
            }
        }
    }
}

/// Record *node* when it is a reference; only reference nodes are decoded.
fn visit(node: Node<'_>, body: &[u8], lines: &mut LineContexts<'_>, refs: &mut Vec<MarkdownRef>, cost: &mut WalkCost) {
    let kind = node.kind();
    if kind != "link_destination" && kind != "code_span" {
        return;
    }
    let range = node.byte_range();
    cost.decoded_bytes += range.len();
    let text = String::from_utf8_lossy(&body[range]);
    let dest = if kind == "link_destination" {
        Some(strip_angles(&text).to_string())
    } else {
        path_shaped(&text)
    };
    if let Some(dest) = dest {
        refs.push(MarkdownRef { dest, context: lines.context_at(node.start_byte(), cost) });
    }
}

/// A body's newline offsets, found once, and the last line folded.
struct LineContexts<'a> {
    body: &'a [u8],
    newlines: Vec<usize>,
    last: Option<(usize, String)>,
}

impl<'a> LineContexts<'a> {
    fn new(body: &'a [u8]) -> Self {
        Self { body, newlines: memchr_iter(b'\n', body).collect(), last: None }
    }

    /// The folded line holding byte `at`, found by bisection, folded once per line.
    fn context_at(&mut self, at: usize, cost: &mut WalkCost) -> String {
        let index = self.newlines.partition_point(|&newline| newline < at);
        let start = if index == 0 { 0 } else { self.newlines[index - 1] + 1 };
        if let Some((cached, folded)) = &self.last
            && *cached == start
        {
            return folded.clone();
        }
        let end = self.newlines.get(index).copied().unwrap_or(self.body.len());
        cost.folds += 1;
        cost.decoded_bytes += end - start;
        let folded = fold_line(&String::from_utf8_lossy(&self.body[start..end]));
        self.last = Some((start, folded.clone()));
        folded
    }
}

/// A destination written as `<...>` without its brackets.
fn strip_angles(dest: &str) -> &str {
    dest.strip_prefix('<').and_then(|inner| inner.strip_suffix('>')).unwrap_or(dest)
}

/// The path a code span names, if it is shaped like one.
///
/// The span's backtick runs come off and one surrounding space each
/// side is stripped as CommonMark reads it. What remains counts as a
/// path when it has no whitespace, only path characters, and either a
/// `/` or a short file extension.
fn path_shaped(span: &str) -> Option<String> {
    let inner = span.trim_matches('`');
    let inner = match inner.strip_prefix(' ').and_then(|s| s.strip_suffix(' ')) {
        Some(stripped) if !stripped.trim().is_empty() => stripped,
        _ => inner,
    };
    let text = inner.trim();
    if text.is_empty() || !text.chars().all(is_path_char) {
        return None;
    }
    if !(text.contains('/') || has_extension(text)) {
        return None;
    }
    Some(text.to_string())
}

fn is_path_char(ch: char) -> bool {
    ch.is_alphanumeric() || "_.-/@+~%".contains(ch)
}

/// `name.ext` with a 1–8 alphanumeric extension and a non-empty stem.
fn has_extension(name: &str) -> bool {
    match name.rsplit_once('.') {
        Some((stem, ext)) => {
            !stem.is_empty() && (1..=MAX_EXTENSION_CHARS).contains(&ext.len()) && ext.chars().all(|c| c.is_ascii_alphanumeric())
        }
        None => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn dests(body: &str) -> Vec<String> {
        markdown_refs(&mut RefParser::default(), body.as_bytes()).into_iter().map(|r| r.dest).collect()
    }

    #[test]
    fn links_images_and_definitions_yield_their_destinations() {
        let body = "See [spec](../specs/spec.md \"t\") and ![i](img.png) and [y](#a).\n\n[ref]: d.md\n[lab]: <e f.md> 'title'\n";
        assert_eq!(dests(body), ["../specs/spec.md", "img.png", "#a", "d.md", "e f.md"]);
    }

    #[test]
    fn code_spans_count_only_when_path_shaped() {
        let body = "`base.py` `storage/backends` `` `x.md` `` `not a path` `word` `a.toolongext` `.md` `vfs.storage`\n";
        // The double-backtick span holds literal backticks, so it is code, not a path.
        assert_eq!(dests(body), ["base.py", "storage/backends", "vfs.storage"]);
    }

    #[test]
    fn code_holds_no_references() {
        let body = "```\n[in fence](a.md)\n`b.md`\n```\n\n    [indented](c.md)\n\n`[code](d.md)` ok\n\n<a href=\"e.md\">raw</a>\n";
        assert_eq!(dests(body), Vec::<String>::new());
    }

    #[test]
    fn reference_style_links_carry_no_destination_of_their_own() {
        let body = "[full][ref] and [ref] and [collapsed][]\n\n[ref]: target.md\n";
        assert_eq!(dests(body), ["target.md"]);
    }

    #[test]
    fn context_is_the_folded_referring_line() {
        let body = "\n\n  a   [x](y.md)\t\tb  \n";
        let refs = markdown_refs(&mut RefParser::default(), body.as_bytes());
        assert_eq!(refs[0].context, "a [x](y.md) b");
        let long = format!("[x](y.md) {}", "z".repeat(400));
        let refs = markdown_refs(&mut RefParser::default(), long.as_bytes());
        assert_eq!(refs[0].context.chars().count(), MAX_CONTEXT_CHARS);
    }

    #[test]
    fn tables_lists_and_quotes_are_prose() {
        let body = "| a | b |\n|---|---|\n| [t](h.md) | `i.md` |\n\n- item [j](k.md)\n> quote [l](m.md)\n";
        assert_eq!(dests(body), ["h.md", "i.md", "k.md", "m.md"]);
    }

    #[test]
    fn batches_align_with_their_bodies() {
        let out = markdown_refs_batch(&[b"[a](a.md)".as_slice(), b"plain".as_slice(), b"`b.md`".as_slice()]);
        assert_eq!(out.iter().map(Vec::len).collect::<Vec<_>>(), [1, 0, 1]);
    }

    #[test]
    fn both_markdown_grammars_load() {
        let mut parser = RefParser::default();
        assert!(parser.block.parse("x", None).is_some());
        assert!(parser.inline.parse("x", None).is_some());
    }

    /// Every named child is cut out, the first included; the 0.5.3 binding kept the first.
    #[test]
    fn continuation_markers_are_left_out_of_the_inline_ranges() {
        let mut parser = RefParser::default();
        let tree = parser.block.parse("> a\n> b\n> c\n", None).expect("parses");
        let mut cursor = tree.walk();
        let inline = loop {
            if cursor.node().kind() == "inline" {
                break cursor.node();
            }
            assert!(cursor.goto_first_child() || cursor.goto_next_sibling(), "an inline node");
        };
        let spans: Vec<(usize, usize)> = inline_ranges(inline).iter().map(|r| (r.start_byte, r.end_byte)).collect();
        assert_eq!(spans, [(2, 4), (6, 8), (10, 11)]);
    }

    #[test]
    fn a_body_nested_past_the_scanner_cap_yields_its_reference() {
        assert_eq!(dests(&format!("{}[l](a.md)\n", "> ".repeat(2000))), ["a.md"]);
    }

    #[test]
    fn nested_list_markers_past_the_cap_parse() {
        let refs = markdown_refs(&mut RefParser::default(), format!("{}x\n", "- ".repeat(2000)).as_bytes());
        assert!(refs.is_empty());
    }

    fn costed(body: &str) -> (Vec<MarkdownRef>, WalkCost) {
        walk(&mut RefParser::default(), body.as_bytes())
    }

    #[test]
    fn one_line_of_many_references_folds_once() {
        for count in [2_000, 4_000] {
            let body = "[x](a.md) ".repeat(count);
            let (refs, cost) = costed(&body);
            assert_eq!(refs.len(), count);
            let folded = fold_line(&body);
            assert!(refs.iter().all(|r| r.dest == "a.md" && r.context == folded));
            assert_eq!(cost.folds, 1);
        }
    }

    #[test]
    fn nested_blocks_decode_only_reference_nodes() {
        let body = format!("{}[x](a.md)\n", "> ".repeat(200));
        let (refs, cost) = costed(&body);
        assert_eq!(refs.len(), 1);
        assert!(cost.decoded_bytes <= 2 * body.len(), "{} decoded of {}", cost.decoded_bytes, body.len());
    }

    #[test]
    fn nested_images_yield_every_destination() {
        let body = format!("{}x{}", "![".repeat(4_000), "](a.md)".repeat(4_000));
        let (refs, cost) = costed(&body);
        assert_eq!(refs.len(), 4_000);
        assert!(refs.iter().all(|r| r.dest == "a.md"));
        assert!(cost.decoded_bytes <= 2 * body.len(), "{} decoded of {}", cost.decoded_bytes, body.len());
    }

    #[test]
    fn references_on_separate_lines_fold_each_line() {
        let (refs, cost) = costed("one [a](a.md)\ntwo [b](b.md)\nthree [c](c.md)\n");
        let contexts: Vec<&str> = refs.iter().map(|r| r.context.as_str()).collect();
        assert_eq!(contexts, ["one [a](a.md)", "two [b](b.md)", "three [c](c.md)"]);
        assert_eq!(cost.folds, 3);
    }

    /// Today's fold: collapse, trim, then keep the first MAX_CONTEXT_CHARS characters.
    fn fold_then_take(line: &str) -> String {
        let collapsed: Vec<&str> = line.split_whitespace().collect();
        collapsed.join(" ").chars().take(MAX_CONTEXT_CHARS).collect()
    }

    #[test]
    fn fold_line_keeps_the_first_256_characters() {
        let alphabet = [' ', '\t', 'a', 'Z', 'é', '漢', '\u{3000}'];
        let mut state: u64 = 20_261_107;
        for _ in 0..200 {
            state = state.wrapping_mul(6_364_136_223_846_793_005).wrapping_add(1_442_695_040_888_963_407);
            let length = (state >> 33) as usize % 1_001;
            let line: String = (0..length)
                .map(|_| {
                    state = state.wrapping_mul(6_364_136_223_846_793_005).wrapping_add(1_442_695_040_888_963_407);
                    alphabet[(state >> 33) as usize % alphabet.len()]
                })
                .collect();
            assert_eq!(fold_line(&line), fold_then_take(&line), "{line:?}");
        }
    }
}
