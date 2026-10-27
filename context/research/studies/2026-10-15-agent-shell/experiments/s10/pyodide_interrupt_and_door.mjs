// S10: two facts about Pyodide under node. (1) Can a runaway guest be interrupted
// from the main thread with the SharedArrayBuffer interrupt buffer, and killed with
// worker.terminate()? (2) What does `import js` reach under plain node (no Deno)?
import { Worker, isMainThread, parentPort, workerData } from "node:worker_threads";
import { performance } from "node:perf_hooks";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const pyodideDir = path.join(here, "pyodide_untrusted", "node_modules", "pyodide");

if (isMainThread) {
  const out = {};
  const sab = new SharedArrayBuffer(4);
  const buf = new Uint8Array(sab);
  const run = (mode) =>
    new Promise((resolve) => {
      const w = new Worker(new URL(import.meta.url), { workerData: { sab, mode } });
      const t0 = performance.now();
      w.on("message", (m) => {
        if (m.type === "ready") {
          setTimeout(() => {
            if (mode === "interrupt") buf[0] = 2; // SIGINT
            else w.terminate();
          }, 300);
        } else if (m.type === "result") {
          resolve({ ...m, elapsed_ms: Math.round(performance.now() - t0) });
          w.terminate();
        }
      });
      w.on("exit", (code) => resolve({ type: "exit", code, elapsed_ms: Math.round(performance.now() - t0) }));
    });
  out.interrupt = await run("interrupt");
  out.terminate = await run("terminate");
  out.door = await run("door");
  console.log(JSON.stringify(out, null, 2));
} else {
  const { loadPyodide } = await import(path.join(pyodideDir, "pyodide.mjs"));
  const py = await loadPyodide({ indexURL: pyodideDir, stdout: () => {}, stderr: () => {} });
  const { sab, mode } = workerData;
  if (mode === "interrupt" || mode === "terminate") {
    py.setInterruptBuffer(new Uint8Array(sab));
    parentPort.postMessage({ type: "ready" });
    const t = performance.now();
    try {
      py.runPython("while True:\n    pass");
      parentPort.postMessage({ type: "result", outcome: "loop ended?!" });
    } catch (e) {
      parentPort.postMessage({ type: "result", outcome: String(e).split("\n").slice(-2).join(" | "), loop_ms: Math.round(performance.now() - t) });
    }
  } else {
    const r = py.runPython(`
import json
r = {}
try:
    import js
    r["process_pid"] = int(js.process.pid)
    r["env_HOME"] = str(js.process.env.HOME)
    r["cwd"] = str(js.process.cwd())
    r["argv0"] = str(js.process.argv[0])
    r["has_process_binding"] = hasattr(js.process, "binding")
    r["globalThis_keys_sample"] = [k for k in dir(js) if k in ("fetch","process","require","Buffer","WebAssembly","globalThis")]
except Exception as e:
    r["import_js"] = f"{type(e).__name__}: {e}"
try:
    import os
    r["os_environ_HOME"] = os.environ.get("HOME")
except Exception as e:
    r["os"] = str(e)
json.dumps(r)
`);
    parentPort.postMessage({ type: "result", door: JSON.parse(r) });
  }
}
