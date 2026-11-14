#!/usr/bin/python3 -I
import json, sys, unicodedata
out = sys.argv[1]
DI, MS, RE, SC, AI = "DATA-ISOLATION-AND-LIFECYCLE.md", "MEMORY-SAFETY-AND-BINARY.md", "RESOURCE-EXHAUSTION-AND-AVAILABILITY.md", "SUPPLY-CHAIN-AND-RELEASE.md", "AI-AND-LLM.md"
SECTIONS = {
 DI: ["Tenant and object-isolation attack classes", "Derived-data and disclosure attack classes", "Export, backup, restore, and migration attack classes", "Deletion, revocation, and lifecycle attack classes"],
 MS: ["Bounds, integer, and representation attack classes", "Lifetime, type, and concurrency attack classes", "FFI and ABI attack classes", "Binary loading and runtime attack classes", "Kernel and privileged-interface attack classes"],
 RE: ["Computational amplification attack classes", "Resource accumulation attack classes", "Quota and scheduling attack classes", "Failure and recovery attack classes"],
 SC: ["Dependency and build-input attack classes", "CI and automation attack classes", "Release and update attack classes"],
 AI: ["Context, retrieval, and memory attack classes", "Tool and action attack classes", "MCP and sub-agent trust classes", "Output and disclosure attack classes"],
}
NOT_SELECTED_FILES = {
 "WEB-PROTOCOL-AND-AUTH.md": "no HTTP, token, session or identity protocol exists in source; the host supplies the Authority in-process",
 "CLIENT-SIDE.md": "no browser, DOM or webview code in source",
 "CLOUD-AND-DEPLOYMENT.md": "no IaC or runtime deployment config in source; Docker is test-only",
 "PROTOCOLS-RPC-AND-MESSAGING.md": "no RPC, wire protocol, queue or broker in source",
 "DESKTOP-MOBILE-AND-LOCAL-IPC.md": "no native app, IPC endpoint or privileged helper in source",
}
def enc(s):
    assert unicodedata.normalize("NFC", s) == s and s == s.strip()
    return "".join(chr(b) if (chr(b).isascii() and (chr(b).isalnum() or chr(b) in "-._~")) else "%%%02X" % b for b in s.encode())
def unit(hunter, surface, boundary, subsystem, ordinary, comps, paths, why):
    sel = []
    for f, secs in comps.items():
        sel += [f"{f}#Core discipline"] + [f"{f}#{s}" for s in secs] + [f"{f}#Universal moves", f"{f}#Validation rules"]
    excl = [{"block": f"{f}#{s}", "reason": why.get(f"{f}#{s}", "considered; this unit's boundary does not reach this class, and a peer unit owns it where it applies")}
            for f, secs in SECTIONS.items() for s in secs if f"{f}#{s}" not in sel]
    excl += [{"block": f"{f}#Core discipline", "reason": r} for f, r in NOT_SELECTED_FILES.items()]
    ac = ordinary or (comps and f"{list(comps)[0]}#{list(comps.values())[0][0]}")
    refs = {"surface": surface, "boundary": boundary, "subsystem": subsystem, "attack_class": ac}
    return {"coverage_id": "::".join(enc(refs[k]) for k in ("surface", "boundary", "subsystem", "attack_class")),
            "canonical_refs": refs, "surface": surface, "boundary": boundary, "subsystem": subsystem, "attack_class": ac.split("#", 1)[1],
            "starting_paths": [p.rstrip("/") for p in paths], "ordinary_attack_class_block": ordinary, "selected_companion_blocks": sel, "excluded_blocks": excl,
            "prior_status": "none", "attempts": [], "wave": 1, "status": "planned", "agent_id": None, "reviewed_paths": [], "local_checks": [],
            "result_fingerprints": [], "unresolved": [], "x_planned_hunter": hunter}
A = "ATTACK-CLASSES.md#"
D = "src/vfs/storage/backends/database/"
U = [
 unit("h01-grants", "src/vfs/base.py#grant revoke posture", D+"rights.py#grant and posture gate", "src/vfs/storage", A+"Access control", {DI: ["Tenant and object-isolation attack classes"]}, [D+"rights.py", "src/vfs/storage/grants.py", D+"backend.py", "src/vfs/base.py"], {}),
 unit("h01-grants", "src/vfs/base.py#add_member remove_member and default posture", D+"rights.py#membership and posture defaults", "src/vfs/storage", A+"Business logic", {}, [D+"rights.py", D+"membership.py", D+"engine.py", "src/vfs/storage/grants.py", "src/vfs/storage/backends/memory.py"], {}),
 unit("h02-reads", "src/vfs/base.py#read stat ls tree glob", D+"rights.py#Visibility", "src/vfs/storage", A+"Access control", {DI: ["Tenant and object-isolation attack classes"]}, [D+"rights.py", D+"reads.py", D+"scope.py", D+"backend.py"], {}),
 unit("h02-reads", "src/vfs/base.py#grep glean graph", D+"rights.py#Visibility over derived copies", "src/vfs/storage", A+"Feature abuse and data leakage", {DI: ["Derived-data and disclosure attack classes"]}, [D+"grep.py", D+"glean.py", D+"graph.py", D+"lexical.py", D+"links.py", "src/vfs/rerank.py"], {}),
 unit("h03-mutations", "src/vfs/base.py#write edit mkdir mkedge", D+"rights.py#WriteGate", "src/vfs/storage", A+"Access control", {DI: ["Tenant and object-isolation attack classes"]}, [D+"rights.py", D+"writes.py", D+"staging.py", D+"edges.py", "src/vfs/storage/editing.py"], {}),
 unit("h03-mutations", "src/vfs/base.py#delete restore sweep move copy", D+"trash.py#subtree checks", "src/vfs/storage", A+"Chained vulnerabilities and trust boundaries", {DI: ["Deletion, revocation, and lifecycle attack classes", "Export, backup, restore, and migration attack classes"]}, [D+"trash.py", D+"topology.py", D+"backend.py", D+"versions.py"], {}),
 unit("h04-router", "src/vfs/base.py#_gate_entry", "src/vfs/permissions.py#PermissionMap and deny_ops", "src/vfs", A+"Access control", {}, ["src/vfs/base.py", "src/vfs/permissions.py", "src/vfs/params.py", "src/vfs/session.py", "src/vfs/sync.py", "src/vfs/authority.py"], {}),
 unit("h04-router", "src/vfs/paths.py#normalize_path", "src/vfs/base.py#mount boundary and reserved namespaces", "src/vfs", A+"Resource and file handling", {}, ["src/vfs/paths.py", "src/vfs/base.py"], {}),
 unit("h05-sql", D+"#statement builders", D+"dialects.py#bound parameters and escape_like", D.rstrip("/"), A+"Injection", {}, [D+"labels.py", D+"descent.py", D+"reads.py", D+"dialects.py", D+"ranges.py", D+"engine.py", D+"membership.py"], {}),
 unit("h06-native", "crates/vfs-core/src/python.rs#pyo3 entry points", "crates/vfs-core/src#bounds and panic containment", "crates/vfs-core", A+"Resource and file handling", {MS: ["Bounds, integer, and representation attack classes", "Lifetime, type, and concurrency attack classes", "FFI and ABI attack classes"]}, ["crates/vfs-core/src/python.rs", "crates/vfs-core/src/postings.rs", "crates/vfs-core/src/lexical.rs", "crates/vfs-core/src/chunk.rs", "crates/vfs-core/src/signals.rs", "src/vfs/native.py"], {f"{MS}#Kernel and privileged-interface attack classes": "no kernel module or privileged interface", f"{MS}#Binary loading and runtime attack classes": "no binary loader; sqlite-vec load is covered by h05-sql's engine path"}),
 unit("h07-compute", "src/vfs/params.py#pattern query edit graph arguments", "src/vfs/storage/backends/database/grep.py#budgets and caps", "src/vfs", None, {RE: ["Computational amplification attack classes", "Failure and recovery attack classes"]}, ["src/vfs/pattern_matching/glob.py", "src/vfs/pattern_matching/grep.py", "src/vfs/storage/replace.py", "src/vfs/params.py", D+"grep.py", D+"graph.py", D+"glean.py"], {}),
 unit("h08-render", "src/vfs/rendering#renderers", "src/vfs/rendering/seam.py#RenderLimits", "src/vfs/rendering", A+"Resource and file handling", {RE: ["Computational amplification attack classes", "Resource accumulation attack classes"]}, ["src/vfs/rendering/", D+"render.py", "src/vfs/models/media.py", "src/vfs/models/chunking.py"], {}),
 unit("h09-supply", ".github/workflows#push and pull_request", ".github/workflows#token permissions secrets and pinning", ".github/workflows", None, {SC: ["CI and automation attack classes", "Dependency and build-input attack classes"]}, [".github/workflows/", "pyproject.toml", "uv.lock", "Cargo.lock", "docker/"], {}),
 unit("h09-supply", ".github/workflows/publish.yml#release published", "scripts/check_release_tag.py#tag check and environment pypi", ".github/workflows", None, {SC: ["Release and update attack classes"]}, [".github/workflows/publish.yml", "scripts/check_release_tag.py", "scripts/bump_version.py", "pyproject.toml"], {}),
 unit("h10-obvious", "repository#tracked files", "repository#secrets debug gates and dangerous calls", "repository", A+"Obvious things", {}, ["src/", "scripts/", "tests/", ".github/", "docker/", ".gitignore"], {}),
 unit("h10-obvious", "repository#tracked files", "repository#secrets randomness and comparisons", "repository", A+"Cryptography and secrets", {}, ["src/vfs/", "src/vfs/embedding/", "src/vfs/models/"], {}),
 unit("h10-obvious", "src/vfs#all modules", "src/vfs#any", "src/vfs", A+"Wildcard", {}, ["src/vfs/"], {}),
 unit("h11-agents", "src/vfs/paths.py#/.agents namespace and src/vfs/skills.py", "src/vfs/base.py#run dispatch and /.agents write rights", "src/vfs", None, {AI: ["Tool and action attack classes", "Context, retrieval, and memory attack classes"]}, ["src/vfs/skills.py", "src/vfs/paths.py", "src/vfs/base.py", "src/vfs/storage/protocol.py", "src/vfs/models/links.py"], {f"{AI}#MCP and sub-agent trust classes": "no MCP client or server exists in source"}),
]
U.sort(key=lambda u: u["coverage_id"])
ids = [u["coverage_id"] for u in U]; assert len(ids) == len(set(ids))
json.dump(U, open(f"{out}/coverage-ledger.json", "w"), indent=1, ensure_ascii=False)
print(len(U), "units")
