// S10: the Worker. Loads Pyodide, mounts VFSFS (an Emscripten filesystem whose every
// node_op/stream_op is a synchronous bridge call answered by vfs verbs), runs the guest
// script from inside vfs (/vfs/scripts/job.py), and reports timings.
//
// Design (described from just-bash's HOSTFS and Emscripten's MEMFS/NODEFS, written fresh):
//   lookup/getattr -> stat          readdir -> ls          mkdir -> mkdir
//   open(read)     -> read (whole row staged into the node)
//   close(dirty)   -> write (whole buffer; text if UTF-8 else bytes)
//   mknod(file)    -> no verb; the row is minted at close      unlink/rmdir -> delete (to the trash)
//   rename         -> move

import { parentPort, workerData } from "node:worker_threads";
import { performance } from "node:perf_hooks";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const pyodideDir = path.join(here, "pyodide_untrusted", "node_modules", "pyodide");
const { loadPyodide } = await import(path.join(pyodideDir, "pyodide.mjs"));

const { sab, script } = workerData;
const i32 = new Int32Array(sab);
const u8 = new Uint8Array(sab);
const dec = new TextDecoder();
const timing = {};
let bridgeCalls = 0;
let bridgeWaitMs = 0;

function bridge(req) {
  // Synchronous call: post, block until the main thread flips status, read the reply.
  bridgeCalls++;
  const t = performance.now();
  Atomics.store(i32, 0, 0);
  parentPort.postMessage({ type: "req", req });
  Atomics.wait(i32, 0, 0);
  const n = Atomics.load(i32, 1);
  const reply = JSON.parse(dec.decode(u8.subarray(8, 8 + n)));
  bridgeWaitMs += performance.now() - t;
  return reply;
}

const b64decode = (s) => Uint8Array.from(Buffer.from(s, "base64"));
const b64encode = (u) => Buffer.from(u).toString("base64");

const t0 = performance.now();
const py = await loadPyodide({
  indexURL: pyodideDir,
  packageCacheDir: path.join(here, "pyodide_untrusted", "pkgcache"),
  stdout: (text) => parentPort.postMessage({ type: "stdout", text: text + "\n" }),
  stderr: (text) => parentPort.postMessage({ type: "stderr", text: text + "\n" }),
});
timing.loadPyodide_ms = Math.round(performance.now() - t0);
const t1 = performance.now();
await py.loadPackage(["numpy", "pandas", "matplotlib"], { messageCallback: () => {} });
timing.loadPackages_ms = Math.round(performance.now() - t1);

const FS = py.FS;
const S_IFDIR = 0o40000, S_IFREG = 0o100000;
const O_ACCMODE = 3, O_TRUNC = 512, O_APPEND = 1024;
const ENOENT = 44, EIO = 29, EFBIG = 22, EINVAL = 28;
const MAX_FILE = 16 * 1024 * 1024;
const MOUNT_TIME = new Date();

function vpath(node) {
  // Path inside vfs: strip the mount point.
  const parts = [];
  for (let n = node; n && n.parent !== n; n = n.parent) parts.unshift(n.name);
  return "/" + parts.join("/");
}
function errno(reply) {
  return new FS.ErrnoError(reply.errno ?? EIO);
}

const VFSFS = {
  mount(_mount) {
    return VFSFS.createNode(null, "/", S_IFDIR | 0o755, 0);
  },
  createNode(parent, name, mode, dev) {
    const node = FS.createNode(parent, name, mode, dev);
    node.node_ops = VFSFS.node_ops;
    node.stream_ops = VFSFS.stream_ops;
    node.contents = null; // staged bytes while open
    node.dirty = false;
    node.openCount = 0;
    return node;
  },
  node_ops: {
    getattr(node) {
      let size, mtime;
      if (node.contents) {
        size = node.contents.length;
        mtime = new Date();
      } else if (node === node.parent) {
        // The mount root: a stable mtime, or importlib's FileFinder re-lists cwd on every import.
        size = 4096; mtime = MOUNT_TIME;
      } else {
        const r = bridge({ op: "stat", path: vpath(node) });
        if (!r.ok) throw errno(r);
        size = r.kind === "directory" ? 4096 : r.size;
        mtime = new Date(r.mtime * 1000);
      }
      return { dev: 1, ino: node.id, mode: node.mode, nlink: 1, uid: 0, gid: 0, rdev: 0, size,
               atime: mtime, mtime, ctime: mtime, blksize: 4096, blocks: Math.ceil(size / 512) };
    },
    setattr(node, attr) {
      if (attr.size !== undefined) {
        if (attr.size > MAX_FILE) throw new FS.ErrnoError(EFBIG);
        if (!node.contents) {
          const r = bridge({ op: "read", path: vpath(node) });
          if (!r.ok) throw errno(r);
          node.contents = b64decode(r.data);
        }
        const next = new Uint8Array(attr.size);
        next.set(node.contents.subarray(0, attr.size));
        node.contents = next;
        node.dirty = true;
        if (node.openCount === 0) VFSFS.flush(node);
      }
      // mode/timestamps: accepted and ignored (vfs has no mode bits).
    },
    lookup(parent, name) {
      const p = vpath(parent);
      const full = p === "/" ? "/" + name : p + "/" + name;
      const r = bridge({ op: "stat", path: full });
      if (!r.ok) throw errno(r);
      return VFSFS.createNode(parent, name, r.kind === "directory" ? S_IFDIR | 0o755 : S_IFREG | 0o644, 0);
    },
    mknod(parent, name, mode, dev) {
      const node = VFSFS.createNode(parent, name, mode, dev);
      if (FS.isDir(mode)) {
        const r = bridge({ op: "mkdir", path: vpath(node) });
        if (!r.ok) { FS.destroyNode(node); throw errno(r); }
      } else {
        node.contents = new Uint8Array(0); // minted at close
        node.dirty = true;
      }
      return node;
    },
    rename(oldNode, newDir, newName) {
      const from = vpath(oldNode);
      const to = (vpath(newDir) === "/" ? "" : vpath(newDir)) + "/" + newName;
      const r = bridge({ op: "rename", path: from, to });
      if (!r.ok) throw errno(r);
      oldNode.name = newName;
      oldNode.parent = newDir;
    },
    unlink(parent, name) {
      const r = bridge({ op: "unlink", path: (vpath(parent) === "/" ? "" : vpath(parent)) + "/" + name });
      if (!r.ok) throw errno(r);
    },
    rmdir(parent, name) {
      const r = bridge({ op: "unlink", path: (vpath(parent) === "/" ? "" : vpath(parent)) + "/" + name });
      if (!r.ok) throw errno(r);
    },
    readdir(node) {
      const r = bridge({ op: "readdir", path: vpath(node) });
      if (!r.ok) throw errno(r);
      return [".", "..", ...r.entries];
    },
    symlink() { throw new FS.ErrnoError(EINVAL); },
    readlink() { throw new FS.ErrnoError(EINVAL); },
  },
  flush(node) {
    if (!node.dirty) return;
    const r = bridge({ op: "write", path: vpath(node), data: b64encode(node.contents) });
    if (!r.ok) throw errno(r);
    node.dirty = false;
  },
  stream_ops: {
    open(stream) {
      const node = stream.node;
      if (FS.isDir(node.mode)) return;
      const acc = stream.flags & O_ACCMODE;
      if (stream.flags & O_TRUNC) {
        node.contents = new Uint8Array(0);
        node.dirty = true;
      } else if (!node.contents) {
        const r = bridge({ op: "read", path: vpath(node) });
        if (!r.ok) throw errno(r);
        node.contents = b64decode(r.data);
        if (node.contents.length > MAX_FILE) throw new FS.ErrnoError(EFBIG);
      }
      node.openCount++;
      if (stream.flags & O_APPEND) stream.position = node.contents.length;
      void acc;
    },
    close(stream) {
      const node = stream.node;
      if (FS.isDir(node.mode)) return;
      node.openCount--;
      if (node.openCount === 0) {
        VFSFS.flush(node);
        node.contents = null; // drop the staging buffer; the next open re-reads
      }
    },
    read(stream, buffer, offset, length, position) {
      const c = stream.node.contents;
      if (position >= c.length) return 0;
      const n = Math.min(c.length - position, length);
      buffer.set(c.subarray(position, position + n), offset);
      return n;
    },
    write(stream, buffer, offset, length, position) {
      const node = stream.node;
      const end = position + length;
      if (end > MAX_FILE) throw new FS.ErrnoError(EFBIG);
      if (end > node.contents.length) {
        const grown = new Uint8Array(Math.max(end, node.contents.length * 2));
        grown.set(node.contents);
        node.contents = grown.subarray(0, end);
        // keep an exact-length view; the backing store may be larger
        node.contents = grown.subarray(0, end);
      }
      node.contents.set(buffer.subarray(offset, offset + length), position);
      node.dirty = true;
      return length;
    },
    llseek(stream, offset, whence) {
      let position = offset;
      if (whence === 1) position += stream.position;
      else if (whence === 2 && FS.isFile(stream.node.mode)) position += stream.node.contents.length;
      if (position < 0) throw new FS.ErrnoError(EINVAL);
      return position;
    },
  },
};

FS.mkdir("/vfs");
FS.mount(VFSFS, {}, "/vfs");
FS.chdir("/vfs");

const t2 = performance.now();
let exit = 0, error = null;
try {
  const src = py.FS.readFile(script, { encoding: "utf8" }); // the script itself comes from vfs
  py.runPython(src);
} catch (e) {
  exit = 1;
  error = String(e).slice(0, 2000);
}
timing.run_ms = Math.round(performance.now() - t2);
timing.bridge_calls = bridgeCalls;
timing.bridge_wait_ms = Math.round(bridgeWaitMs);
timing.rss_MB = Math.round(process.memoryUsage().rss / 1048576);
parentPort.postMessage({ type: "timing", data: timing });
parentPort.postMessage({ type: "done", exit, error });
