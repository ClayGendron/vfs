"""The workspace: one vfs kernel, the people who use it, and the log every call lands in.

A person signs in as a principal. The agent never signs in: it acts *on
behalf of* whoever is signed in, as its own actor, so the kernel judges
every call by the person's rights and records that the agent made it.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from typing import Any

from pluto_demo import seed
from pluto_demo.shell import ShellOutput, run_line
from vfs import VirtualFileSystem
from vfs.authority import Authority, Principal
from vfs.embedding import Model2VecEmbeddingProvider
from vfs.models import Edge, Entry
from vfs.storage.backends import DatabaseStorage

log = logging.getLogger("pluto")

MAX_LOG = 500


@dataclass
class LogEntry:
    ts: float
    principal: str
    actor: str
    command: str
    verb: str
    ok: bool
    elapsed_ms: float
    output: str


class Workspace:
    """The seeded Halyard namespace with a signed-in principal and a shared command log."""

    def __init__(self) -> None:
        self.embedder_name = "lexical"
        embedder = _load_embedder()
        if embedder is not None:
            self.embedder_name = "model2vec"
        self.storage = DatabaseStorage(url="sqlite+aiosqlite:///:memory:", embedder=embedder, posture="read_write")
        self.fs = VirtualFileSystem(storage=self.storage)
        self.people = {person.principal.sub: person for person in seed.PEOPLE}
        self.principal = seed.PEOPLE[0].principal.sub
        self.log: list[LogEntry] = []

    # -------------------------------------------------------------------
    # Seeding
    # -------------------------------------------------------------------

    async def seed(self) -> None:
        system = self.fs.session(Authority.system())
        entries = [Entry(path=path, content=content) for path, content in seed.FILES.items()]
        written = await system.write(entries, parents=True)
        if not written.success:
            msg = f"seeding failed: {written.error_message}"
            raise RuntimeError(msg)
        edges = [Edge(source=link.source, target=link.target, edge_type=link.edge_type) for link in seed.LINKS]
        linked = await system.mkedge(edges, provenance="system")
        if not linked.success:
            msg = f"seeding edges failed: {linked.error_message}"
            raise RuntimeError(msg)
        posture = await system.posture(seed.RESTRICTED_PREFIX, "none")
        if not posture.success:
            msg = f"hiding {seed.RESTRICTED_PREFIX} failed: {posture.error_message}"
            raise RuntimeError(msg)
        for principal, level in seed.RESTRICTED_GRANTS:
            granted = await system.grant(seed.RESTRICTED_PREFIX, principal, level)  # ty: ignore[invalid-argument-type]
            if not granted.success:
                msg = f"granting {principal} failed: {granted.error_message}"
                raise RuntimeError(msg)
        if self.embedder_name != "lexical":
            await self.storage.reindex()

    async def close(self) -> None:
        await self.storage.close()

    # -------------------------------------------------------------------
    # Principals
    # -------------------------------------------------------------------

    def principals(self) -> list[dict[str, str]]:
        people = [
            {"id": p.principal.sub, "name": p.name, "role": p.role, "kind": p.principal.kind}
            for p in self.people.values()
        ]
        people.append({"id": seed.AGENT.sub, "name": seed.AGENT_NAME, "role": seed.AGENT_ROLE, "kind": seed.AGENT.kind})
        people.append(
            {
                "id": seed.CLAUDE_CODE.sub,
                "name": seed.CLAUDE_CODE_NAME,
                "role": seed.CLAUDE_CODE_ROLE,
                "kind": seed.CLAUDE_CODE.kind,
            }
        )
        return people

    def switch(self, principal: str) -> bool:
        if principal not in self.people:
            return False
        self.principal = principal
        return True

    def authority(self, *, actor: Principal | None = None) -> Authority:
        """The signed-in person acting as themselves, or a service *actor* acting on their behalf."""
        subject = self.people[self.principal].principal
        if actor is not None:
            return Authority.on_behalf_of({subject}, actor=actor)
        return Authority.of(subject)

    # -------------------------------------------------------------------
    # Running commands
    # -------------------------------------------------------------------

    async def run(self, command: str, *, actor: Principal | None = None) -> ShellOutput:
        """Run one shell line as the signed-in principal, logging it; a service *actor* runs on their behalf."""
        session = self.fs.session(self.authority(actor=actor))
        actor_name = actor.sub if actor is not None else self.principal
        started = time.perf_counter()
        out = await run_line(session, command, principal=self.principal)
        elapsed = (time.perf_counter() - started) * 1000
        if out.switched_to is not None:
            if actor is not None:
                out = ShellOutput("su", False, "ERROR an agent cannot sign in as someone else")
            elif not self.switch(out.switched_to):
                names = ", ".join(sorted(self.people))
                out = ShellOutput("su", False, f"ERROR no principal named {out.switched_to!r}; try one of {names}")
        self.log.append(
            LogEntry(time.time(), self.principal, actor_name, command, out.verb, out.ok, round(elapsed, 2), out.output)
        )
        del self.log[:-MAX_LOG]
        return out

    async def tree(self) -> dict[str, Any]:
        """The namespace as the signed-in principal sees it, nested for the sidebar."""
        session = self.fs.session(self.authority())
        listing = await session.glob("**/*")
        root: dict[str, Any] = {"name": "/", "path": "/", "kind": "directory", "children": []}
        for obs in sorted(listing, key=lambda o: str(o.path)):
            parts = str(obs.path).strip("/").split("/")
            node = root
            for depth, part in enumerate(parts):
                path = "/" + "/".join(parts[: depth + 1])
                child = next((c for c in node["children"] if c["path"] == path), None)
                if child is None:
                    is_last = depth == len(parts) - 1
                    kind = "file" if is_last and getattr(obs, "kind", "file") == "file" else "directory"
                    child = {"name": part, "path": path, "kind": kind}
                    if kind == "directory":
                        child["children"] = []
                    node["children"].append(child)
                node = child
        _sort_tree(root)
        return root

    def log_payload(self) -> list[dict[str, Any]]:
        return [asdict(entry) for entry in self.log]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_embedder() -> Model2VecEmbeddingProvider | None:
    """The local semantic model, or ``None`` when it cannot load here (offline, no extra)."""
    try:
        return Model2VecEmbeddingProvider()
    except Exception as exc:
        log.warning("semantic index unavailable, glean answers lexically: %s", exc)
        return None


def _sort_tree(node: dict[str, Any]) -> None:
    children = node.get("children")
    if not children:
        return
    children.sort(key=lambda c: (c["kind"] != "directory", c["name"]))
    for child in children:
        _sort_tree(child)


__all__ = ["LogEntry", "Principal", "Workspace"]
