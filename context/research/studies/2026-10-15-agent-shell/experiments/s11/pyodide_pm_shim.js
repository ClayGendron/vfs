// S11: the JavaScript side of "Pyodide inside the Python process" under PythonMonkey.
//
// The realm is bare SpiderMonkey: no node, no browser, no Deno. Pyodide's loader has a
// "shell" mode (d8/jsshell: `read`, `readbuffer`, `load`, `print`) that we feed from Python
// host functions. Everything Pyodide needs from a host is listed here, polyfilled or routed:
//   TextEncoder/TextDecoder (utf-8 only), performance.now, crypto.getRandomValues,
//   read/readbuffer/load/print, setTimeout (PythonMonkey has one).
// VFSFS is the same Emscripten filesystem object S10 wrote for the Deno/node sidecar,
// except that every node_op/stream_op calls the Python host *synchronously* — PythonMonkey
// lets JS call a Python function and get the return value on the same thread, so there is
// no SharedArrayBuffer, no Atomics.wait, no relay thread.

(function () {
  // ---- polyfills ---------------------------------------------------------------------
  if (typeof globalThis.TextEncoder === "undefined") {
    globalThis.TextEncoder = class {
      get encoding() { return "utf-8"; }
      encode(s) {
        s = String(s ?? "");
        const out = [];
        for (let i = 0; i < s.length; i++) {
          let c = s.charCodeAt(i);
          if (c >= 0xd800 && c < 0xdc00 && i + 1 < s.length) {
            const d = s.charCodeAt(i + 1);
            if (d >= 0xdc00 && d < 0xe000) { c = 0x10000 + ((c - 0xd800) << 10) + (d - 0xdc00); i++; }
          }
          if (c < 0x80) out.push(c);
          else if (c < 0x800) out.push(0xc0 | (c >> 6), 0x80 | (c & 63));
          else if (c < 0x10000) out.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63));
          else out.push(0xf0 | (c >> 18), 0x80 | ((c >> 12) & 63), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63));
        }
        return new Uint8Array(out);
      }
      encodeInto(s, u8) { const b = this.encode(s); const n = Math.min(b.length, u8.length); u8.set(b.subarray(0, n)); return { read: s.length, written: n }; }
    };
  }
  if (typeof globalThis.TextDecoder === "undefined") {
    globalThis.TextDecoder = class {
      constructor(label = "utf-8", opts = {}) { this.encoding = String(label).toLowerCase(); this.fatal = !!opts.fatal; this.ignoreBOM = !!opts.ignoreBOM; }
      decode(input) {
        if (input === undefined) return "";
        let u8 = input instanceof Uint8Array ? input : new Uint8Array(input.buffer ?? input, input.byteOffset ?? 0, input.byteLength);
        if (this.encoding === "utf-16le") { let s = ""; for (let i = 0; i + 1 < u8.length; i += 2) s += String.fromCharCode(u8[i] | (u8[i + 1] << 8)); return s; }
        let out = ""; let i = 0;
        if (!this.ignoreBOM && u8.length >= 3 && u8[0] === 0xef && u8[1] === 0xbb && u8[2] === 0xbf) i = 3;
        const chunk = [];
        for (; i < u8.length; i++) {
          const b = u8[i]; let c;
          if (b < 0x80) c = b;
          else if (b >> 5 === 6) { c = ((b & 31) << 6) | (u8[++i] & 63); }
          else if (b >> 4 === 14) { c = ((b & 15) << 12) | ((u8[++i] & 63) << 6) | (u8[++i] & 63); }
          else if (b >> 3 === 30) { c = ((b & 7) << 18) | ((u8[++i] & 63) << 12) | ((u8[++i] & 63) << 6) | (u8[++i] & 63); }
          else { if (this.fatal) throw new TypeError("invalid utf-8"); c = 0xfffd; }
          if (c > 0xffff) { c -= 0x10000; chunk.push(0xd800 + (c >> 10), 0xdc00 + (c & 1023)); } else chunk.push(c);
          if (chunk.length > 8192) { out += String.fromCharCode.apply(null, chunk); chunk.length = 0; }
        }
        return out + String.fromCharCode.apply(null, chunk);
      }
    };
  }
  globalThis.performance ??= { now: () => Date.now() };
  globalThis.queueMicrotask ??= (f) => Promise.resolve().then(f);
  globalThis.crypto ??= {
    getRandomValues(view) {
      // Entropy from the Python host (os.urandom); not Math.random.
      const bytes = globalThis.__host.urandom(view.byteLength);
      new Uint8Array(view.buffer, view.byteOffset, view.byteLength).set(new Uint8Array(bytes.buffer ?? bytes, 0, view.byteLength));
      return view;
    },
  };
})();

// ---- the d8-style shell API Pyodide's loader looks for ----------------------------------
// Emscripten's shell-mode entropy source is `os.system("sh", ["-c", "head -c N /dev/urandom | base64"])`
// (a d8 extension). Serve it from the host instead of a shell: parse N, return base64 of N host bytes.
globalThis.os ??= {
  system(cmd, args) {
    const m = /head -c(\d+)/.exec(String(args?.[1] ?? ""));
    const n = m ? Number(m[1]) : 32;
    const bytes = new Uint8Array(globalThis.__host.urandom(n).buffer ?? globalThis.__host.urandom(n), 0, n);
    let bin = ""; for (let i = 0; i < n; i++) bin += String.fromCharCode(bytes[i]);
    return globalThis.btoa ? globalThis.btoa(bin) : globalThis.__btoa(bin);
  },
};
globalThis.__btoa = (bin) => { const T = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"; let o = "";
  for (let i = 0; i < bin.length; i += 3) { const a = bin.charCodeAt(i), b = bin.charCodeAt(i + 1), c = bin.charCodeAt(i + 2);
    const t = (a << 16) | ((b || 0) << 8) | (c || 0);
    o += T[(t >> 18) & 63] + T[(t >> 12) & 63] + (isNaN(b) ? "=" : T[(t >> 6) & 63]) + (isNaN(c) ? "=" : T[t & 63]); }
  return o; };
globalThis.read = (path) => globalThis.__host.readText(path);
globalThis.readbuffer = (path) => {
  const b = globalThis.__host.readBinary(path);           // Python bytearray -> Uint8Array
  return b.buffer instanceof ArrayBuffer && b.byteOffset === 0 && b.byteLength === b.buffer.byteLength
    ? b.buffer : new Uint8Array(b).buffer;
};
globalThis.load = (path) => (0, eval)(globalThis.read(path));   // indirect eval: global scope
globalThis.print = (s) => globalThis.__host.print(String(s));
globalThis.printErr = (s) => globalThis.__host.printErr(String(s));

// ---- VFSFS: Emscripten filesystem over vfs verbs, synchronous ---------------------------
globalThis.__mountVFSFS = function (py, bridge, mountPoint) {
  const FS = py.FS;
  const S_IFDIR = 0o40000, S_IFREG = 0o100000;
  const O_TRUNC = 512, O_APPEND = 1024;
  const EIO = 29, EFBIG = 22, EINVAL = 28;
  const MAX_FILE = 16 * 1024 * 1024;
  const MOUNT_TIME = new Date();
  const stats = { calls: 0, ms: 0 };

  function call(op, path, extra) {
    stats.calls++;
    const t = Date.now();
    const r = bridge(op, path, extra ?? null);   // synchronous Python call
    stats.ms += Date.now() - t;
    return r;
  }
  function vpath(node) {
    const parts = [];
    for (let n = node; n && n.parent !== n; n = n.parent) parts.unshift(n.name);
    return "/" + parts.join("/");
  }
  const errno = (r) => new FS.ErrnoError(Number(r.errno ?? EIO));
  const join = (dir, name) => (dir === "/" ? "" : dir) + "/" + name;
  const toU8 = (b) => (b instanceof Uint8Array ? b : new Uint8Array(b.buffer ?? b));

  const VFSFS = {
    mount() { return VFSFS.createNode(null, "/", S_IFDIR | 0o755, 0); },
    createNode(parent, name, mode, dev) {
      const node = FS.createNode(parent, name, mode, dev);
      node.node_ops = VFSFS.node_ops;
      node.stream_ops = VFSFS.stream_ops;
      node.contents = null; node.dirty = false; node.openCount = 0;
      return node;
    },
    node_ops: {
      getattr(node) {
        let size, mtime;
        if (node.contents) { size = node.contents.length; mtime = new Date(); }
        else if (node === node.parent) { size = 4096; mtime = MOUNT_TIME; }
        else {
          const r = call("stat", vpath(node));
          if (!r.ok) throw errno(r);
          size = r.kind === "directory" ? 4096 : Number(r.size);
          mtime = new Date(Number(r.mtime) * 1000);
        }
        return { dev: 1, ino: node.id, mode: node.mode, nlink: 1, uid: 0, gid: 0, rdev: 0, size,
                 atime: mtime, mtime, ctime: mtime, blksize: 4096, blocks: Math.ceil(size / 512) };
      },
      setattr(node, attr) {
        if (attr.size !== undefined) {
          if (attr.size > MAX_FILE) throw new FS.ErrnoError(EFBIG);
          if (!node.contents) {
            const r = call("read", vpath(node));
            if (!r.ok) throw errno(r);
            node.contents = toU8(r.data);
          }
          const next = new Uint8Array(attr.size);
          next.set(node.contents.subarray(0, attr.size));
          node.contents = next; node.dirty = true;
          if (node.openCount === 0) VFSFS.flush(node);
        }
      },
      lookup(parent, name) {
        const r = call("stat", join(vpath(parent), name));
        if (!r.ok) throw errno(r);
        return VFSFS.createNode(parent, name, r.kind === "directory" ? S_IFDIR | 0o755 : S_IFREG | 0o644, 0);
      },
      mknod(parent, name, mode, dev) {
        const node = VFSFS.createNode(parent, name, mode, dev);
        if (FS.isDir(mode)) {
          const r = call("mkdir", vpath(node));
          if (!r.ok) { FS.destroyNode(node); throw errno(r); }
        } else { node.contents = new Uint8Array(0); node.dirty = true; }
        return node;
      },
      rename(oldNode, newDir, newName) {
        const r = call("rename", vpath(oldNode), join(vpath(newDir), newName));
        if (!r.ok) throw errno(r);
        oldNode.name = newName; oldNode.parent = newDir;
      },
      unlink(parent, name) { const r = call("unlink", join(vpath(parent), name)); if (!r.ok) throw errno(r); },
      rmdir(parent, name) { const r = call("unlink", join(vpath(parent), name)); if (!r.ok) throw errno(r); },
      readdir(node) {
        const r = call("readdir", vpath(node));
        if (!r.ok) throw errno(r);
        return [".", "..", ...Array.from(r.entries)];
      },
      symlink() { throw new FS.ErrnoError(EINVAL); },
      readlink() { throw new FS.ErrnoError(EINVAL); },
    },
    flush(node) {
      if (!node.dirty) return;
      const r = call("write", vpath(node), node.contents);   // Uint8Array crosses as bytes
      if (!r.ok) throw errno(r);
      node.dirty = false;
    },
    stream_ops: {
      open(stream) {
        const node = stream.node;
        if (FS.isDir(node.mode)) return;
        if (stream.flags & O_TRUNC) { node.contents = new Uint8Array(0); node.dirty = true; }
        else if (!node.contents) {
          const r = call("read", vpath(node));
          if (!r.ok) throw errno(r);
          node.contents = toU8(r.data);
          if (node.contents.length > MAX_FILE) throw new FS.ErrnoError(EFBIG);
        }
        node.openCount++;
        if (stream.flags & O_APPEND) stream.position = node.contents.length;
      },
      close(stream) {
        const node = stream.node;
        if (FS.isDir(node.mode)) return;
        node.openCount--;
        if (node.openCount === 0) { VFSFS.flush(node); node.contents = null; }
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
  FS.mkdir(mountPoint);
  FS.mount(VFSFS, {}, mountPoint);
  FS.chdir(mountPoint);
  return stats;
};

globalThis.btoa ??= globalThis.__btoa;
globalThis.atob ??= (s) => { const T = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"; let o = ""; let b = 0, n = 0;
  for (const c of s) { if (c === "=") break; b = (b << 6) | T.indexOf(c); n += 6; if (n >= 8) { n -= 8; o += String.fromCharCode((b >> n) & 255); } }
  return o; };
