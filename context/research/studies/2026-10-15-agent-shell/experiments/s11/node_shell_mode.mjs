// S11 control: run Pyodide's "shell" (d8-style) loader path under node by hiding `process`,
// to learn whether the shell path itself works in 0.28.3 or whether the in-process failures
// are engine-specific. read/readbuffer/load/print come from node's fs.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
const here = path.dirname(fileURLToPath(import.meta.url));
const dir = path.join(here, "..", "s10", "pyodide_untrusted", "node_modules", "pyodide");
const pkg = path.join(here, "..", "s10", "pyodide_untrusted", "pkgcache");
const resolve = (p) => { const n = path.basename(p); for (const d of [dir, pkg]) { const f = path.join(d, n); if (fs.existsSync(f)) return f; } throw new Error("no file " + p); };
const nodeProcess = process;
globalThis.read = (p, mode) => mode === "binary" ? new Uint8Array(fs.readFileSync(resolve(p))) : fs.readFileSync(resolve(p), "utf8");
globalThis.readbuffer = (p) => { const b = fs.readFileSync(resolve(p)); return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength); };
globalThis.load = (p) => (0, eval)(fs.readFileSync(resolve(p), "utf8"));
const out = [], err = [];
globalThis.print = (s) => out.push(String(s));
globalThis.printErr = (s) => err.push(String(s));
const useShim = nodeProcess.argv.includes("--shim");
if (useShim) {
  
  const nodeRead = globalThis.read;
  globalThis.__host = { urandom: (n) => new Uint8Array(n).map(() => (Math.random() * 256) | 0), print: globalThis.print, printErr: globalThis.printErr,
    readText: (p) => nodeRead(p), readBinary: (p) => nodeRead(p, "binary") };
  (0, eval)(fs.readFileSync(path.join(here, "pyodide_pm_shim.js"), "utf8"));
}
globalThis.process = undefined;
(0, eval)(fs.readFileSync(path.join(dir, "pyodide.asm.js"), "utf8"));
(0, eval)(fs.readFileSync(path.join(dir, "pyodide.js"), "utf8"));
const t0 = Date.now();
try {
  const py = await loadPyodide({ indexURL: "/pyodide/", stdout: globalThis.print, stderr: globalThis.printErr });
  console.error("loaded in", Date.now() - t0, "ms;", py.runPython("import sys; sys.version"));
  await py.loadPackage(["numpy"]);
  console.error("numpy:", py.runPython("import numpy; numpy.__version__"));
} catch (e) {
  console.error("FAILED:", String(e).slice(0, 400), (e && e.stack || "").split("\n").slice(0, 6).join("\n"));
}
console.error("stdout:", out.join("\n").slice(-300)); console.error("stderr:", err.join("\n").slice(-300));
nodeProcess.exit(0);
