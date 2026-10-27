"""Probe 1 for the spec 171 review: can the envelope publish an outputSchema, does
every payload shape conform to it, and does from_payload rebuild an honest
"not fetched" row once the wire strips bytes?

Run from the repo root:
    uv run --with jsonschema python context/research/studies/2026-10-15-agent-shell/experiments/r171/p1_schema_and_payload.py
"""

from __future__ import annotations

import asyncio
import base64
import json

import jsonschema

from vfs.authority import Authority, Principal
from vfs.base import VirtualFileSystem
from vfs.models.entry import Observation
from vfs.results.envelope import Result

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
)


def strip_bytes(payload: dict) -> dict:
    """What spec 167 task zero promises: no row bytes, and data out of the mask."""
    out = dict(payload)
    rows = []
    for row in payload.get("observations", []):
        row = dict(row)
        row.pop("data", None)
        if "populated" in row:
            row["populated"] = [f for f in row["populated"] if f != "data"]
        rows.append(row)
    out["observations"] = rows
    return out


def check(label: str, validator: jsonschema.Draft202012Validator, payload: dict) -> None:
    errors = list(validator.iter_errors(payload))
    verdict = "VALID" if not errors else "INVALID " + "; ".join(
        f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message[:90]}" for e in errors[:3]
    )
    print(f"  {label}: {verdict}")


async def main() -> None:
    print("=== A. Result.model_json_schema() ===")
    schemas = {}
    for mode in ("validation", "serialization"):
        try:
            schema = Result.model_json_schema(mode=mode)
        except Exception as exc:  # noqa: BLE001
            print(f"{mode}: FAILED {type(exc).__name__}: {exc}")
            continue
        jsonschema.Draft202012Validator.check_schema(schema)
        schemas[mode] = schema
        obs = schema["$defs"]["Observation"]["properties"]
        print(f"{mode}: ok, {len(json.dumps(schema))} chars, $defs={sorted(schema['$defs'])}")
        print(f"  root additionalProperties={schema.get('additionalProperties')!r} required={schema.get('required')!r}"
              f" 'success' declared={'success' in schema['properties']}")
        print(f"  Observation.additionalProperties={schema['$defs']['Observation'].get('additionalProperties')!r}")
        print(f"  Observation.data={json.dumps(obs['data'])}")
        print(f"  Observation.path={json.dumps(obs['path'])}")
        print(f"  Observation.populated={json.dumps(obs['populated'])}")
        print(f"  Observation.content_hash={json.dumps(obs['content_hash'])}")
        print(f"  Observation.created_at={json.dumps(obs['created_at'])}")
    validator = jsonschema.Draft202012Validator(schemas["serialization"])

    print("\n=== B. live payloads against the serialization-mode schema ===")
    fs = VirtualFileSystem()
    sysa = Authority.system()
    alice = Authority.of(Principal("alice"))
    await fs.write(path="/notes/a.md", content="# hello\n", parents=True, authority=sysa)
    await fs.write(path="/photos/pixel.png", data=PNG, parents=True, authority=sysa)
    await fs.mkedge(source="/notes/a.md", target="/photos/pixel.png", edge_type="cites", authority=sysa)
    await fs.grant("/notes", "alice", "read", authority=sysa)
    cases: dict[str, Result] = {
        "read text": await fs.read("/notes/a.md", authority=sysa),
        "read png default": await fs.read("/photos/pixel.png", authority=sysa),
        "read png columns={data}": await fs.read("/photos/pixel.png", columns=frozenset({"data"}), authority=sysa),
        "read png columns={data,mime_type}": await fs.read(
            "/photos/pixel.png", columns=frozenset({"data", "mime_type"}), authority=sysa
        ),
        "ls /": await fs.ls("/", authority=sysa),
        "stat png": await fs.stat("/photos/pixel.png", authority=sysa),
        "glob **": await fs.glob("**", authority=sysa),
        "graph outbound": await fs.graph("outbound", "/notes/a.md", authority=sysa),
        "grants /notes": await fs.grants("/notes", authority=sysa),
        "grant (write)": await fs.grant("/photos", "alice", "read", authority=sysa),
        "read missing (error)": await fs.read("/nope.md", authority=sysa),
        "alice read hidden": await fs.read("/photos/pixel.png", authority=alice),
        "write two": await fs.write(path="/notes/b.md", content="b\n", authority=sysa),
    }
    for label, result in cases.items():
        payload = result.to_payload()
        extras = sorted(set(payload) - {"success", "ops", "observations", "errors"})
        rows = payload.get("observations", [])
        print(f"- {label}: success={result.success} rows={len(rows)} errors={[str(e.kind) for e in result.errors]} extras={extras}")
        for row in rows[:2]:
            print(f"    row keys={sorted(k for k in row if k != 'populated')} populated={sorted(row.get('populated', []))}")
        check("raw to_payload", validator, payload)
        check("stripped", validator, strip_bytes(payload))
        print(f"    rendered: {result.to_str()[:140]!r}")

    print("\n=== C. from_payload after the wire strips bytes ===")
    row = cases["read png columns={data,mime_type}"].observations[0]
    print("in-process row populated:", sorted(row.populated), "data len:", len(row.data or b""))
    honest = strip_bytes(cases["read png columns={data,mime_type}"].to_payload())
    back = Result.from_payload(honest)
    print("honest strip -> populated:", sorted(back.observations[0].populated), "data:", back.observations[0].data,
          "errors:", back.errors)
    dishonest = cases["read png columns={data,mime_type}"].to_payload()
    for r in dishonest["observations"]:
        r.pop("data", None)
    back2 = Result.from_payload(dishonest)
    print("data dropped but mask kept -> populated:", sorted(back2.observations[0].populated),
          "data:", back2.observations[0].data, "('data' in populated claims fetched-and-null)")
    bare = Result.from_payload({"ops": ["read"], "observations": [{"path": "/x.png", "mime_type": "image/png"}]})
    print("row with no populated key -> populated:", sorted(bare.observations[0].populated))
    print("success key ignored inbound; payload success=False with no error ->",
          [str(e.kind) for e in Result.from_payload({"success": False}).errors])

    print("\n=== D. size: 10,000 rows ===")
    big = Result(ops=("ls",), observations=[
        Observation(path=f"/d/file-{i:05d}.md", kind="file", size_bytes=1234, version=1,
                    mime_type="text/markdown") for i in range(10_000)
    ])
    payload_chars = len(json.dumps(big.to_payload()))
    print(f"ls of 10,000 rows: to_payload JSON = {payload_chars:,} chars; rendered text = {len(big.to_str()):,} chars")
    imgs = Result(ops=("read",), observations=[
        Observation(path=f"/img/{i:05d}.png", kind="file", mime_type="image/png", size_bytes=70, version=1,
                    content="PNG 1x1 RGB") for i in range(10_000)
    ])
    print(f"read of 10,000 images (no bytes): to_payload JSON = {len(json.dumps(imgs.to_payload())):,} chars")
    errs = Result(ops=("read",), errors=[
        __import__("vfs.results.envelope", fromlist=["classified"]).classified("not_found", f"/m/{i}.md")
        for i in range(10_000)
    ]) if False else None
    _ = errs


asyncio.run(main())
