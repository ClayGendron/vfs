// S10: what `import js` reaches when Pyodide runs under Deno with no permissions
// beyond reading the pyodide directory (langchain-sandbox's shape).
// usage: deno run --no-prompt --allow-read=<deno npm cache> pyodide_deno_door.ts  (see out_pyodide_deno_door.json for the flags used)
const here = new URL(".", import.meta.url).pathname;
const pyodideDir = here + "pyodide_untrusted/node_modules/pyodide/";
const { loadPyodide } = await import("npm:pyodide@0.28.3");
const t0 = performance.now();
const py = await loadPyodide({ stdout: () => {}, stderr: () => {} });
const load_ms = Math.round(performance.now() - t0);
const r = py.runPython(`
import json
r = {}
try:
    import js
    r["has_Deno"] = hasattr(js, "Deno")
    r["has_process"] = hasattr(js, "process")
    try:
        r["Deno_env_HOME"] = str(js.Deno.env.get("HOME"))
    except Exception as e:
        r["Deno_env_HOME"] = f"{type(e).__name__}: {str(e)[:120]}"
    try:
        r["Deno_readTextFileSync_etc_hosts"] = str(js.Deno.readTextFileSync("/etc/hosts"))[:40]
    except Exception as e:
        r["Deno_readTextFileSync_etc_hosts"] = f"{type(e).__name__}: {str(e)[:140]}"
    try:
        r["Deno_cwd"] = str(js.Deno.cwd())
    except Exception as e:
        r["Deno_cwd"] = f"{type(e).__name__}: {str(e)[:120]}"
    try:
        r["Deno_Command"] = str(js.Deno.Command.new("id").outputSync().code)
    except Exception as e:
        r["Deno_Command"] = f"{type(e).__name__}: {str(e)[:140]}"
    try:
        r["Deno_readTextFileSync_pyodide_dir"] = len(str(js.Deno.readTextFileSync("${pyodideDir}package.json")))
    except Exception as e:
        r["Deno_readTextFileSync_pyodide_dir"] = f"{type(e).__name__}: {str(e)[:140]}"
except Exception as e:
    r["import_js"] = f"{type(e).__name__}: {e}"
json.dumps(r)
`);
console.log(JSON.stringify({ deno: Deno.version.deno, load_ms, door: JSON.parse(r) }, null, 2));
