"""S11 probe: JSPI in mini_racer's V8, and the JSPromise/close behaviour."""
import inspect, sys
from py_mini_racer import MiniRacer
import py_mini_racer._objects as o
ctx = MiniRacer()
print("JSPI:", ctx.eval('typeof WebAssembly.Suspending + " " + typeof WebAssembly.promising + " " + typeof WebAssembly.Exception + " " + typeof WebAssembly.Tag'), flush=True)
print([n for n in dir(o) if "Promise" in n], flush=True)
print(inspect.getsource(o.JSPromise)[:2500], flush=True)
ctx.close()
print("closed", flush=True)
