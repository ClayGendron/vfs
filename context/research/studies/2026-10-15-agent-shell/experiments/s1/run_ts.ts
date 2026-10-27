// Parse one corpus command (by id) with just-bash's parser or lifo's lexer+parser.
// Driven by run_ts_driver.ts, which gives each (id, dialect) its own process
// and a timeout, because lifo's parser can loop forever on some inputs.
//   bun run run_ts.ts corpus.jsonl <id> <just-bash|lifo>
import { readFileSync } from "node:fs";
import { parse as jbParse } from "/Users/claygendron/Git/Repos/just-bash/packages/just-bash/src/parser/parser.ts";
import { lex as lifoLex } from "/Users/claygendron/Git/Repos/lifo/packages/core/src/shell/lexer.ts";
import { parse as lifoParse } from "/Users/claygendron/Git/Repos/lifo/packages/core/src/shell/parser.ts";

const rows = readFileSync(process.argv[2], "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
const id = Number(process.argv[3]);
const dialect = process.argv[4];
const r = rows.find((x) => x.id === id);
try {
  if (dialect === "just-bash") jbParse(r.cmd);
  else lifoParse(lifoLex(r.cmd));
  console.log(JSON.stringify({ id, dialect, ok: true }));
} catch (e: any) {
  console.log(JSON.stringify({ id, dialect, ok: false, error: String(e?.message ?? e) }));
}
