// Measures the size of the Cloudflare API catalog in three shapes, from the spec file as data.
// Usage: node measure.mjs <path to spec.json.txt>. No code from any reference repository is loaded.
import { readFileSync } from "node:fs";

const text = readFileSync(process.argv[2], "utf8");
const spec = JSON.parse(text);
const METHODS = ["get", "put", "post", "delete", "patch", "head", "options"];
const tok = (s) => Math.round(s.length / 4);

const tools = [];
const tags = new Map();
for (const [path, item] of Object.entries(spec.paths ?? {})) {
  for (const m of METHODS) {
    const op = item?.[m];
    if (!op) continue;
    const properties = {};
    const required = [];
    for (const p of op.parameters ?? []) {
      if (!p?.name) continue;
      properties[p.name] = { ...(p.schema ?? {}), ...(p.description ? { description: p.description } : {}) };
      if (p.required) required.push(p.name);
    }
    const body = op.requestBody?.content?.["application/json"]?.schema;
    if (body) {
      properties.body = body;
      if (op.requestBody?.required) required.push("body");
    }
    const summary = op.summary || op.description || `${m.toUpperCase()} ${path}`;
    tools.push({ method: m, path, summary, inputSchema: { type: "object", properties, ...(required.length ? { required } : {}) } });
    for (const t of op.tags ?? []) tags.set(t, (tags.get(t) ?? 0) + 1);
  }
}

const full = JSON.stringify(tools.map((t) => ({ name: `${t.method}_${t.path}`, description: t.summary, inputSchema: t.inputSchema })));
const requiredOnly = JSON.stringify(tools.map((t) => {
  const req = new Set(t.inputSchema.required ?? []);
  const props = Object.fromEntries(Object.entries(t.inputSchema.properties).filter(([k]) => req.has(k)).map(([k, v]) => [k, { type: v.type ?? "object" }]));
  return { name: `${t.method}_${t.path}`, description: t.summary, inputSchema: { type: "object", properties: props } };
}));
const index = tools.map((t) => `${t.method.toUpperCase()} ${t.path}  ${t.summary}`).join("\n");
const perTool = tools.map((t) => JSON.stringify(t.inputSchema).length).sort((a, b) => a - b);
const pct = (q) => perTool[Math.min(perTool.length - 1, Math.floor(q * perTool.length))];

console.log(JSON.stringify({
  spec_chars: text.length,
  spec_tokens_at_4_chars: tok(text),
  operations: tools.length,
  distinct_tags: tags.size,
  full_listing_tokens_at_4_chars: tok(full),
  required_only_listing_tokens_at_4_chars: tok(requiredOnly),
  one_line_index_tokens_at_4_chars: tok(index),
  input_schema_chars_p50: pct(0.5),
  input_schema_chars_p90: pct(0.9),
  input_schema_chars_p99: pct(0.99),
  input_schema_chars_max: perTool[perTool.length - 1],
}, null, 1));
