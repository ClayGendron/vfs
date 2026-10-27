// Benchmark Pyodide under Node (the only way to drive it from a Python host is a node subprocess).
// Run:  node bench_pyodide_node.mjs   (from a dir with `pyodide` installed in node_modules)
// Measures loadPyodide (cold), print('hello'), a 1e6 loop, and 1,000 Python->JS host round trips.
import { loadPyodide } from "pyodide";

const now = () => performance.now();
const rss = () => Math.round(process.memoryUsage().rss / 1048576);

const rss0 = rss();
let t = now();
const py = await loadPyodide();
const cold = now() - t;
const rss1 = rss();

let out = "";
py.setStdout({ batched: (s) => { out += s + "\n"; } });

const hello = [];
for (let i = 0; i < 20; i++) { t = now(); py.runPython("print('hello')"); hello.push(now() - t); }
if (!out.includes("hello")) throw new Error("no hello");

const loop = [];
let r;
for (let i = 0; i < 5; i++) { t = now(); r = py.runPython("s = 0\nfor i in range(1000000):\n    s += i\ns"); loop.push(now() - t); }
if (Number(r) !== 499999500000) throw new Error("bad loop " + r);

let calls = 0;
py.globals.set("host_add", (a, b) => { calls += 1; return a + b; });
const rt = [];
for (let i = 0; i < 5; i++) {
  calls = 0; t = now();
  r = py.runPython("acc = 0\nfor i in range(1000):\n    acc = host_add(acc, 1)\nacc");
  rt.push(now() - t);
  if (Number(r) !== 1000 || calls !== 1000) throw new Error("bad rt");
}
const med = (a) => a.slice().sort((x, y) => x - y)[Math.floor(a.length / 2)];
console.log(`pyodide ${py.version} under node ${process.version}`);
console.log(`loadPyodide cold: ${cold.toFixed(0)} ms`);
console.log(`print('hello') (median of 20): ${med(hello).toFixed(3)} ms`);
console.log(`1e6-iteration loop (median of 5): ${med(loop).toFixed(1)} ms`);
console.log(`1000 host round trips via globals.set (median of 5): ${med(rt).toFixed(2)} ms -> ${(med(rt)).toFixed(1)} us/call`);
console.log(`node RSS: before=${rss0} MB after load=${rss1} MB end=${rss()} MB`);
console.log("interruptibility: no mechanism in this mode (needs a Worker + SharedArrayBuffer interrupt buffer)");
