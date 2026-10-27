"""S11 probe: PythonMonkey (SpiderMonkey in-process): WebAssembly, JSPI, sync Python callbacks from JS."""
import sys, time
t = time.perf_counter()
import pythonmonkey as pm
print("import pythonmonkey", round((time.perf_counter() - t) * 1000), "ms", "version", getattr(pm, "__version__", "?"), flush=True)
print("globals:", pm.eval('["WebAssembly","SharedArrayBuffer","Atomics","TextDecoder","TextEncoder","setTimeout","fetch","crypto","process","require","read","load","console","performance","queueMicrotask","python"].map(n=>n+"="+typeof globalThis[n]).join(" ")'), flush=True)
print("JSPI:", pm.eval('typeof WebAssembly.Suspending + " " + typeof WebAssembly.promising'), flush=True)
wasm = "new Uint8Array([0,97,115,109,1,0,0,0,1,7,1,96,2,127,127,1,127,3,2,1,0,7,7,1,3,97,100,100,0,0,10,9,1,7,0,32,0,32,1,106,11])"
print("wasm add(2,3) =", pm.eval(f"(()=>{{const m=new WebAssembly.Module({wasm}); return new WebAssembly.Instance(m,{{}}).exports.add(2,3)}})()"), flush=True)
print("wasm memory 4 GiB max:", pm.eval("new WebAssembly.Memory({initial:1, maximum:65536}).buffer.byteLength"), flush=True)
# a synchronous Python callback from JS
calls = []
def host_read(path):
    calls.append(path)
    return "hello from python for " + path
f = pm.eval("(cb) => { const r = cb('/data/x.csv'); return typeof r + ':' + r; }")
print("sync callback:", f(host_read), "calls", calls, flush=True)
# bytes across the boundary
g = pm.eval("(cb) => { const u = cb(); return u.constructor.name + ':' + u.length + ':' + u[0]; }")
print("bytes:", g(lambda: bytearray(b"\x89PNG")), flush=True)
sys.exit(0)
