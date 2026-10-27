"""S11 probe: does py_mini_racer's V8 expose WebAssembly, and what host globals exist?"""
import sys, time
print("python", sys.version.split()[0], flush=True)
t = time.perf_counter()
import py_mini_racer
print("import py_mini_racer", round((time.perf_counter() - t) * 1000), "ms", "version", getattr(py_mini_racer, "__version__", "?"), flush=True)
t = time.perf_counter()
ctx = py_mini_racer.MiniRacer()
print("MiniRacer() ms", round((time.perf_counter() - t) * 1000), flush=True)
print("v8", ctx.v8_version, flush=True)
print("globals:", ctx.eval('["WebAssembly","SharedArrayBuffer","Atomics","TextDecoder","TextEncoder","setTimeout","fetch","crypto","process","require","read","load","console","performance","queueMicrotask"].map(n=>n+"="+typeof globalThis[n]).join(" ")'), flush=True)
wasm = "new Uint8Array([0,97,115,109,1,0,0,0,1,7,1,96,2,127,127,1,127,3,2,1,0,7,7,1,3,97,100,100,0,0,10,9,1,7,0,32,0,32,1,106,11])"
print("wasm add(2,3) =", ctx.eval(f"(()=>{{const m=new WebAssembly.Module({wasm}); return new WebAssembly.Instance(m,{{}}).exports.add(2,3)}})()"), flush=True)
print("wasm memory 4 GiB max ok:", ctx.eval("new WebAssembly.Memory({initial:1, maximum:65536}).buffer.byteLength"), flush=True)
print("attrs:", [a for a in dir(ctx) if not a.startswith("_")], flush=True)
