// S10: Pyodide 0.28.3 under node 22 — can the scientific stack load, how long,
// how much memory, and does matplotlib render a PNG headless into bytes?
//
// usage: node bench_pyodide_sci.mjs
// The pyodide npm package lives in ./pyodide_untrusted/node_modules (untrusted data,
// run only under node). Packages not in the npm tarball are fetched from the
// jsdelivr CDN on first use and cached in ./pyodide_untrusted/pkgcache.

import { performance } from "node:perf_hooks";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const pyodideDir = path.join(here, "pyodide_untrusted", "node_modules", "pyodide");
const { loadPyodide } = await import(path.join(pyodideDir, "pyodide.mjs"));

const rss = () => Math.round(process.memoryUsage().rss / 1048576);
const t = () => performance.now();

const out = {};
let t0 = t();
const py = await loadPyodide({
  indexURL: pyodideDir,
  packageCacheDir: path.join(here, "pyodide_untrusted", "pkgcache"),
  stdout: () => {},
  stderr: () => {},
});
out.loadPyodide_ms = Math.round(t() - t0);
out.rss_after_load_MB = rss();
out.version = py.version;

// 1. Package set the lockfile declares (counts only).
const lock = JSON.parse(py.runPython("import json, pyodide_js; '{}'") === "{}" ? "{}" : "{}");

// 2. Load the scientific stack.
const sets = [
  ["numpy"],
  ["pandas"],
  ["matplotlib"],
  ["scipy"],
  ["pillow", "pyyaml", "beautifulsoup4", "python-dateutil", "pydantic", "sqlite3", "lxml", "micropip"],
];
out.loads = [];
for (const s of sets) {
  const a = t();
  const rssBefore = rss();
  try {
    const loaded = await py.loadPackage(s, { messageCallback: () => {} });
    out.loads.push({ asked: s, loaded: loaded.map((p) => p.name), ms: Math.round(t() - a), rss_delta_MB: rss() - rssBefore });
  } catch (e) {
    out.loads.push({ asked: s, error: String(e).slice(0, 200), ms: Math.round(t() - a) });
  }
}
out.rss_after_packages_MB = rss();
// Pure-Python packages absent from the lockfile: micropip from PyPI (needs network; a host could pre-stage the wheels instead).
{
  const a = t();
  try {
    await py.runPythonAsync("import micropip; await micropip.install(['openpyxl', 'python-docx'])");
    out.micropip = { ok: true, ms: Math.round(t() - a) };
  } catch (e) {
    out.micropip = { ok: false, ms: Math.round(t() - a), error: String(e).slice(0, 300) };
  }
}

// 3. Import each named package and report.
const importProbe = `
import importlib, json, sys
names = ["numpy","pandas","scipy","matplotlib","PIL","yaml","openpyxl","docx","bs4","dateutil","pydantic","sqlite3","lxml","json","csv","threading","multiprocessing","socket","ssl","ctypes","zlib"]
res = {}
for n in names:
    try:
        m = importlib.import_module(n)
        res[n] = getattr(m, "__version__", "ok")
    except BaseException as e:
        res[n] = f"{type(e).__name__}: {str(e)[:120]}"
try:
    import threading
    th = threading.Thread(target=lambda: None); th.start(); th.join(); res["thread_start"] = "ok"
except BaseException as e:
    res["thread_start"] = f"{type(e).__name__}: {e}"
res["platform"] = sys.platform
res["version"] = sys.version
json.dumps(res)
`;
out.imports = JSON.parse(py.runPython(importProbe));

// 4. matplotlib → PNG bytes in memory, headless (AGG), then hand to JS as bytes.
const plotProbe = `
import io, time
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("agg")
import matplotlib.pyplot as plt
t0 = time.perf_counter()
df = pd.DataFrame({"x": np.arange(100), "y": np.sin(np.arange(100) / 10.0)})
fig, ax = plt.subplots(figsize=(4, 3), dpi=100)
ax.plot(df["x"], df["y"]); ax.set_title("sin from pandas")
buf = io.BytesIO()
fig.savefig(buf, format="png")
png = buf.getvalue()
plt.close(fig)
elapsed = time.perf_counter() - t0
(len(png), png[:8].hex(), elapsed, matplotlib.get_backend())
`;
const a = t();
const r = py.runPython(plotProbe);
const [pngLen, magic, inner, backend] = r.toJs();
r.destroy();
out.matplotlib_png = { bytes: pngLen, magic_hex: magic, python_s: Number(inner.toFixed(3)), wall_ms: Math.round(t() - a), backend };

// Bytes crossing to JS: fetch the PNG as a Uint8Array copy (the media row body).
const pngBytes = py.runPython("png").toJs();
out.matplotlib_png.js_byte_length = pngBytes.byteLength;
out.matplotlib_png.js_is_png = pngBytes[0] === 0x89 && pngBytes[1] === 0x50;

// 5. The `import js` door and the sandbox posture under plain node.
out.js_door = JSON.parse(py.runPython(`
import json
r = {}
try:
    import js
    r["import_js"] = "ok: " + str(type(js))
    r["js_process_pid"] = int(js.process.pid)
    r["js_require"] = str(type(js.require)) if hasattr(js, "require") else "no js.require attribute"
except Exception as e:
    r["import_js"] = f"{type(e).__name__}: {e}"
try:
    import pyodide_js
    r["pyodide_js"] = "ok"
except Exception as e:
    r["pyodide_js"] = f"{type(e).__name__}: {e}"
try:
    import os
    r["os_listdir_root"] = os.listdir("/")[:12]
except Exception as e:
    r["os_listdir_root"] = f"{type(e).__name__}: {e}"
json.dumps(r)
`));

// 6. A second interpreter in the same process? (Pyodide: one per JS realm.)
try {
  const b = t();
  const py2 = await loadPyodide({ indexURL: pyodideDir, stdout: () => {}, stderr: () => {} });
  out.second_instance = { ok: true, ms: Math.round(t() - b), rss_MB: rss(), version: py2.version };
} catch (e) {
  out.second_instance = { ok: false, error: String(e).slice(0, 200) };
}

console.log(JSON.stringify(out, null, 2));
