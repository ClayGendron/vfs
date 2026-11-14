"""Bounded growth check: docx gridSpan expansion in vfs DocxRenderer (counts work, reports RSS)."""
import io, resource, sys, json, time
import docx
from docx.oxml.ns import qn
from docx.table import _Cell
from vfs.rendering.registry import RendererRegistry
from vfs.rendering.seam import RenderLimits, RenderSource
from vfs.models.media import DOCX

def make(span, text_len):
    d = docx.Document()
    t = d.add_table(rows=1, cols=1)
    tc = t.rows[0].cells[0]._tc
    tc.paragraphs = None
    t.rows[0].cells[0].text = "x" * text_len
    tcPr = tc.get_or_add_tcPr()
    gs = tcPr.makeelement(qn("w:gridSpan"), {qn("w:val"): str(span)})
    tcPr.append(gs)
    b = io.BytesIO(); d.save(b); return b.getvalue()

calls = 0
orig = _Cell.text.fget
def counted(self):
    global calls; calls += 1; return orig(self)
_Cell.text = property(counted, _Cell.text.fset)

span, text_len = int(sys.argv[1]), int(sys.argv[2])
data = make(span, text_len)
before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
t0 = time.monotonic()
r = RendererRegistry.bundled().render(RenderSource(data, DOCX, "a.docx"), RenderLimits(seconds=1.0))
dt = time.monotonic() - t0
after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(json.dumps({"gridSpan": span, "cell_text_len": text_len, "input_bytes": len(data),
  "cell_text_calls": calls, "status": getattr(r, "status", None), "detail": str(getattr(r, "detail", ""))[:120],
  "output_chars": len(getattr(r, "text", "") or ""), "peak_rss_before_MiB": round(before/2**20,1),
  "peak_rss_after_MiB": round(after/2**20,1), "render_wall_s_info_only": round(dt,3), "seconds_limit": 1.0}))
