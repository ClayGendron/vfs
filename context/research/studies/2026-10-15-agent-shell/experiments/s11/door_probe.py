# Runs INSIDE the Pyodide guest: what does `import js` reach in this realm?
import js
out = []
def probe(label, fn):
    try:
        out.append(label + " -> " + repr(fn())[:70])
    except Exception as e:
        out.append(label + " -> " + type(e).__name__ + ": " + str(e)[:70])
probe("js.python.eval(getpid)", lambda: js.python.eval('__import__("os").getpid()'))
probe("js.python.eval(open /etc/hosts)", lambda: js.python.eval('open("/etc/hosts").read(20)'))
probe("js.python.exec(import vfs)", lambda: js.python.exec('import sys; sys.modules["vfs"]') or "exec ok")
probe("js.__host.readText", lambda: js.__host.readText("/pyodide/package.json")[:30])
probe("js.read", lambda: js.read("/pyodide/package.json")[:30])
probe("js.load", lambda: js.load)
probe("js.os.system", lambda: js.os.system("sh", ["-c", "head -c4 /dev/urandom | base64"]))
probe("js.eval", lambda: js.eval("1+1"))
probe("js.WebAssembly", lambda: type(js.WebAssembly).__name__)
"\n".join(out)
