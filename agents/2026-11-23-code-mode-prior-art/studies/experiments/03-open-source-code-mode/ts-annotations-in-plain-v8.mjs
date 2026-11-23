// Does TypeScript-annotated tool-chain code compile when handed to V8 untranspiled,
// as a library that wraps the model's code in an async function and compiles it as script would?
import vm from "node:vm";
const bodies = {
  plain_js: "const r = { n: 1 }; return r.n;",
  ts_annotation: "const r: { n: number } = { n: 1 }; return r.n;",
  ts_interface: "interface R { n: number }\nconst r: R = { n: 1 }; return r.n;",
};
for (const [name, body] of Object.entries(bodies)) {
  const wrapped = `(async function() { const __result = await (async function() { ${body} })(); return __result; })()`;
  try {
    const value = await new vm.Script(wrapped).runInNewContext({});
    console.log(JSON.stringify({ name, compiled: true, value }));
  } catch (e) {
    console.log(JSON.stringify({ name, compiled: false, error: `${e.name}: ${e.message}` }));
  }
}
