// S10: node main thread. Relays the Worker's synchronous filesystem requests to the
// Python host over stdio JSON lines and wakes the Worker through a SharedArrayBuffer.
//
// SAB layout: int32[0] = status (0 pending, 1 ready), int32[1] = reply byte length,
// bytes from offset 8 = the JSON reply (UTF-8). 32 MiB total; a reply past that is an error.

import { Worker } from "node:worker_threads";
import path from "node:path";
import readline from "node:readline";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const script = process.argv[2];
const SAB_BYTES = 32 * 1024 * 1024;
const sab = new SharedArrayBuffer(SAB_BYTES);
const i32 = new Int32Array(sab);
const u8 = new Uint8Array(sab);
const enc = new TextEncoder();

const pending = new Map(); // id -> resolve
let nextId = 1;
const rl = readline.createInterface({ input: process.stdin });
rl.on("line", (line) => {
  const reply = JSON.parse(line);
  const resolve = pending.get(reply.id);
  if (resolve) {
    pending.delete(reply.id);
    resolve(reply);
  }
});

const send = (obj) => process.stdout.write(JSON.stringify(obj) + "\n");

const worker = new Worker(path.join(here, "pyodide_bridge_worker.mjs"), { workerData: { sab, script } });
worker.on("message", async (msg) => {
  if (msg.type === "req") {
    const id = nextId++;
    const reply = await new Promise((resolve) => {
      pending.set(id, resolve);
      send({ type: "req", id, req: msg.req });
    });
    delete reply.id;
    const bytes = enc.encode(JSON.stringify(reply));
    if (bytes.byteLength > SAB_BYTES - 8) {
      const err = enc.encode(JSON.stringify({ ok: false, errno: 22, kind: "bridge.too_large" }));
      u8.set(err, 8);
      Atomics.store(i32, 1, err.byteLength);
    } else {
      u8.set(bytes, 8);
      Atomics.store(i32, 1, bytes.byteLength);
    }
    Atomics.store(i32, 0, 1);
    Atomics.notify(i32, 0);
  } else {
    send(msg); // stdout / stderr / timing / done
    if (msg.type === "done") {
      process.exit(0);
    }
  }
});
worker.on("error", (e) => {
  send({ type: "done", exit: 1, error: String(e) });
  process.exit(1);
});
