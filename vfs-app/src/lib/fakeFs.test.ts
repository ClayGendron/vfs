// Locks in the pure path logic behind the /terminal fake filesystem.
import { describe, expect, it } from "vitest"
import { ROOT, listDir, lookup, normalize } from "./fakeFs"

describe("normalize", () => {
  it("passes absolute paths through, ignoring cwd", () => {
    expect(normalize("/workspace", "/enterprise")).toBe("/workspace")
  })

  it("resolves relative paths against cwd", () => {
    expect(normalize("auth.py", "/workspace")).toBe("/workspace/auth.py")
    expect(normalize("workspace", "/")).toBe("/workspace")
  })

  it("collapses '.' segments", () => {
    expect(normalize("./auth.py", "/workspace")).toBe("/workspace/auth.py")
    expect(normalize(".", "/workspace")).toBe("/workspace")
  })

  it("pops one segment per '..'", () => {
    expect(normalize("../spec", "/workspace")).toBe("/spec")
    expect(normalize("..", "/workspace")).toBe("/")
  })

  it("clamps '..' past root back to '/'", () => {
    expect(normalize("../..", "/")).toBe("/")
    expect(normalize("../../../x", "/workspace")).toBe("/x")
  })

  it("drops trailing and repeated slashes", () => {
    expect(normalize("/workspace/", "/")).toBe("/workspace")
    expect(normalize("/workspace//auth.py", "/")).toBe("/workspace/auth.py")
  })

  it("normalizes root to '/'", () => {
    expect(normalize("/", "/")).toBe("/")
    expect(normalize("", "/")).toBe("/")
  })
})

describe("lookup", () => {
  it("returns a file node for an existing file", () => {
    const node = lookup("/workspace/auth.py")
    expect(node?.kind).toBe("file")
    if (node?.kind === "file") expect(node.content).toContain("AuthService")
  })

  it("returns a dir node for an existing directory", () => {
    expect(lookup("/workspace")?.kind).toBe("dir")
  })

  it("returns ROOT for '/'", () => {
    expect(lookup("/")).toBe(ROOT)
  })

  it("returns null for a missing path", () => {
    expect(lookup("/workspace/nope.py")).toBeNull()
    expect(lookup("/nope")).toBeNull()
  })

  it("returns null when descending through a file", () => {
    expect(lookup("/workspace/auth.py/foo")).toBeNull()
  })
})

describe("listDir", () => {
  it("sorts directories before files, alpha within each group", () => {
    const entries = listDir("/")
    expect(entries).not.toBeNull()
    const firstFile = entries!.findIndex((e) => !e.endsWith("/"))
    // every entry after the first file is also a file (dirs-first holds)
    expect(entries!.slice(firstFile).every((e) => !e.endsWith("/"))).toBe(true)
    // localeCompare is case-insensitive: 'install.sh' (i) precedes 'README.md' (R)
    expect(entries!.slice(firstFile)).toEqual(["install.sh", "README.md"])
  })

  it("suffixes directory names with '/' and leaves files bare", () => {
    expect(listDir("/.vfs/workspace/auth.py/__meta__")).toEqual([
      "chunks/",
      "edges/",
      "versions/",
    ])
    expect(listDir("/workspace")).toEqual([
      "auth.py",
      "session.py",
      "utils.py",
    ])
  })

  it("returns null for a file target", () => {
    expect(listDir("/workspace/auth.py")).toBeNull()
  })

  it("returns null for a missing target", () => {
    expect(listDir("/nope")).toBeNull()
  })
})
