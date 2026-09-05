//! Markdown references off the tree-sitter-markdown trees.
//!
//! One batch entry point: UTF-8 document bodies in, per-body references
//! out, parsed in parallel with one `MarkdownParser` per worker (the
//! block grammar with the inline grammar spliced in under every
//! `inline` node). A reference is a link destination — an inline link,
//! an image, or a reference definition — or a code span shaped like a
//! path. Each carries the referring line, folded to one bounded line.
//! Fenced code, indented code and HTML blocks hold no references by
//! construction: the tree never yields link nodes inside them. The
//! engine returns raw destination text; the host decides what is an
//! in-mount reference (schemes, anchors, fragments) and resolves it.

use rayon::prelude::*;
use tree_sitter_md::MarkdownParser;

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

/// References per body, in document order, parsed in parallel.
pub fn markdown_refs_batch(bodies: &[&[u8]]) -> Vec<Vec<MarkdownRef>> {
    bodies
        .par_iter()
        .map_init(MarkdownParser::default, |parser, body| markdown_refs(parser, body))
        .collect()
}

/// References in one body; an unparseable body (a cancelled parse) yields none.
pub fn markdown_refs(parser: &mut MarkdownParser, body: &[u8]) -> Vec<MarkdownRef> {
    let mut refs = Vec::new();
    let Some(tree) = parser.parse(body, None) else {
        return refs;
    };
    let mut cursor = tree.walk();
    loop {
        let node = cursor.node();
        let text = String::from_utf8_lossy(&body[node.byte_range()]);
        let dest = match node.kind() {
            "link_destination" => Some(strip_angles(&text).to_string()),
            "code_span" => path_shaped(&text),
            _ => None,
        };
        if let Some(dest) = dest {
            refs.push(MarkdownRef { dest, context: line_context(body, node.start_byte()) });
        }
        if cursor.goto_first_child() {
            continue;
        }
        loop {
            if cursor.goto_next_sibling() {
                break;
            }
            if !cursor.goto_parent() {
                return refs;
            }
        }
    }
}

/// The line holding byte `at`, whitespace runs collapsed, bounded.
fn line_context(body: &[u8], at: usize) -> String {
    let start = body[..at].iter().rposition(|&b| b == b'\n').map_or(0, |i| i + 1);
    let end = body[at..].iter().position(|&b| b == b'\n').map_or(body.len(), |i| at + i);
    fold_line(&String::from_utf8_lossy(&body[start..end]))
}

/// Collapse whitespace runs to one space, trim, and cap the character count.
pub fn fold_line(line: &str) -> String {
    let mut folded = String::with_capacity(line.len().min(MAX_CONTEXT_CHARS));
    let mut pending_space = false;
    for ch in line.chars() {
        if ch.is_whitespace() {
            pending_space = !folded.is_empty();
            continue;
        }
        if pending_space {
            folded.push(' ');
            pending_space = false;
        }
        folded.push(ch);
    }
    folded.chars().take(MAX_CONTEXT_CHARS).collect()
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
        markdown_refs(&mut MarkdownParser::default(), body.as_bytes()).into_iter().map(|r| r.dest).collect()
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
        let refs = markdown_refs(&mut MarkdownParser::default(), body.as_bytes());
        assert_eq!(refs[0].context, "a [x](y.md) b");
        let long = format!("[x](y.md) {}", "z".repeat(400));
        let refs = markdown_refs(&mut MarkdownParser::default(), long.as_bytes());
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
}
