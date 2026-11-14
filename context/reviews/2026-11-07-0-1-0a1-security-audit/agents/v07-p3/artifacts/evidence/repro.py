"""Measure docx footnote-reference inline amplification in vfs DocxRenderer (dummy data only)."""
import io, sys, tracemalloc, zipfile
from vfs.rendering.docx import DocxRenderer
from vfs.rendering.seam import RenderLimits, RenderSource
from vfs.models.media import DOCX

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
CT = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
      '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
      '<Default Extension="xml" ContentType="application/xml"/>'
      '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
      '<Override PartName="/word/footnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/>'
      '</Types>')
RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '</Relationships>')
DOCRELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
           '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes" Target="footnotes.xml"/>'
           '</Relationships>')

def build(note_chars: int, refs: int) -> bytes:
    note = ("lorem ipsum " * (note_chars // 12 + 1))[:note_chars]
    foot = f'<?xml version="1.0" encoding="UTF-8"?><w:footnotes {W}><w:footnote w:id="1"><w:p><w:r><w:t>{note}</w:t></w:r></w:p></w:footnote></w:footnotes>'
    run = '<w:r><w:footnoteReference w:id="1"/></w:r>'
    doc = f'<?xml version="1.0" encoding="UTF-8"?><w:document {W}><w:body><w:p>{run * refs}</w:p></w:body></w:document>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr("[Content_Types].xml", CT); z.writestr("_rels/.rels", RELS)
        z.writestr("word/_rels/document.xml.rels", DOCRELS)
        z.writestr("word/document.xml", doc); z.writestr("word/footnotes.xml", foot)
    return buf.getvalue()

def main() -> None:
    note_chars = 10_000
    renderer = DocxRenderer()
    for refs in (0, 100, 1_000, 10_000):
        data = build(note_chars, refs)
        tracemalloc.start()
        r = renderer.render(RenderSource(data, DOCX, "dummy.docx"), RenderLimits())
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        out = len(r.text or "")
        print(f"refs={refs:>6} input_bytes={len(data):>7} peak_traced_MiB={peak/2**20:8.1f} "
              f"status={r.status} detail={r.detail!r} out_chars={out}")
        sys.stdout.flush()

main()
