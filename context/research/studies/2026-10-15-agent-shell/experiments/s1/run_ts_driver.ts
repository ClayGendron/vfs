// Run run_ts.ts once per (id, dialect) with a 20 s timeout; a timeout is
// recorded as a refusal with error "TIMEOUT (parser hang)".
//   bun run run_ts_driver.ts corpus.jsonl > results/corpus.ts.jsonl
import { readFileSync } from "node:fs";

const corpus = process.argv[2];
const rows = readFileSync(corpus, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
for (const r of rows) {
  for (const dialect of ["just-bash", "lifo"]) {
    const proc = Bun.spawn(["bun", "run", import.meta.dir + "/run_ts.ts", corpus, String(r.id), dialect], {
      stdout: "pipe", stderr: "pipe", timeout: 20000, killSignal: "SIGKILL",
    });
    const out = await new Response(proc.stdout).text();
    await proc.exited;
    if (out.trim()) console.log(out.trim());
    else console.log(JSON.stringify({ id: r.id, dialect, ok: false, error: "TIMEOUT (parser hang)" }));
  }
}
