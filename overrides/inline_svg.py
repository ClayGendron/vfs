"""Place a page's SVG diagrams inline, so each one takes the page's colours and typefaces.

An SVG shown through an image tag is a separate document. It cannot read the
page's tokens, and Safari does not tell it which theme the reader is in, so a
diagram drawn for both themes shows its light ink on a dark page. MkDocs calls
``on_page_content`` with each page's HTML, and every image whose source is an
SVG file of the docs folder is replaced by that file's own markup::

    <img alt="..." src="../images/architecture.svg">  ->  <svg id="vfs-architecture" ...>

A diagram written for this scopes each of its style rules to its own id, so
its styles reach nothing else on the page.
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mkdocs.config.defaults import MkDocsConfig
    from mkdocs.structure.files import Files
    from mkdocs.structure.pages import Page

SVG_IMAGE = re.compile(r'<img\b[^>]*\bsrc="(?P<src>[^":]+\.svg)"[^>]*>')
XML_PROLOG = re.compile(r"^\s*<\?xml[^>]*\?>\s*")

# ---------------------------------------------------------------------------
# The hook MkDocs calls
# ---------------------------------------------------------------------------


def on_page_content(html: str, *, page: Page, config: MkDocsConfig, files: Files) -> str:
    """Return the page's HTML with each local SVG image replaced by the file's markup."""
    page_folder = posixpath.dirname(page.file.dest_uri)

    def inline(match: re.Match[str]) -> str:
        source = _source_of(posixpath.normpath(posixpath.join(page_folder, match["src"])), files)
        # An image that is not a file of the docs folder stays an image.
        return match[0] if source is None else XML_PROLOG.sub("", source.read_text(encoding="utf-8")).strip()

    return SVG_IMAGE.sub(inline, html)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _source_of(dest_uri: str, files: Files) -> Path | None:
    """The source path of the docs file published at ``dest_uri``, or None when there is none."""
    for file in files:
        if file.dest_uri == dest_uri and file.abs_src_path is not None:
            return Path(file.abs_src_path)
    return None
