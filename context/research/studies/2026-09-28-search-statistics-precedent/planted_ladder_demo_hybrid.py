"""Does glean reveal whether hidden files mention a word? Run on today's code.

Bob can see /team only. /hr is hidden from him. Bob wants to know: does
any HR file mention his employee id, E48213?

Grants are not built yet, so "Bob can only see /team" is modelled by
scoping every glean to /team — results come only from /team, while the
ranking statistics are counted over the whole index, exactly as they
would be under a grant that hides /hr.
"""

import asyncio
import random
import sys
import tempfile

from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends import DatabaseStorage
from vfs.embedding import HashEmbeddingProvider

WORDS = (
    "project roadmap quarter review meeting notes budget design customer launch "
    "timeline feature release planning status update team goals metrics hiring "
    "onboarding process policy document draft summary action items follow up "
    "engineering sales support marketing finance legal office travel expense"
).split()


def filler(rng: random.Random, lines: int = 25) -> str:
    return "\n".join(" ".join(rng.choice(WORDS) for _ in range(10)) for _ in range(lines))


def company(hidden_mentions: int) -> list[Entry]:
    """200 team files Bob can see, 40 HR files he cannot."""
    rng = random.Random(7)
    files = [Entry(path=Path(f"/team/doc{i:03}.md"), content=filler(rng)) for i in range(200)]
    for i in range(40):
        body = filler(rng)
        if i < hidden_mentions:
            body += "\ninvestigation opened regarding employee E48213 conduct complaint"
        files.append(Entry(path=Path(f"/hr/case{i:03}.md"), content=body))
    return files


def bobs_plants() -> list[Entry]:
    """What Bob writes into his own folder. Every file has the same body.

    probe.md carries the word Bob is asking about. Each ladder word is a
    made-up word Bob plants in exactly k files, so he knows its count is k.
    """
    body = filler(random.Random(99), lines=3)
    plants = [Entry(path=Path("/team/bob/probe.md"), content=body + "\nE48213")]
    for k in (1, 2, 3, 4, 5, 6, 8):
        word = f"zqx{k}vk"
        for copy in range(k):
            plants.append(Entry(path=Path(f"/team/bob/ladder{k}_{copy}.md"), content=body + f"\n{word}"))
    return plants


async def attack(hidden_mentions: int) -> None:
    workdir = tempfile.mkdtemp()
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{workdir}/demo.sqlite", embedder=HashEmbeddingProvider())
    await storage.write(entries=company(hidden_mentions) + bobs_plants(), parents=True)
    await storage.reindex()

    # Step 0: Bob greps everything he can see. Only his own probe mentions E48213.
    seen = await storage.grep(pattern="E48213", globs=("team/**",))
    print(f"  grep E48213 over what Bob can see: {sorted(str(o.path) for o in seen.observations)}")

    # Step 1: one search. Bob reads only the ORDER of his own files.
    query = "E48213 " + " ".join(f"zqx{k}vk" for k in (1, 2, 3, 4, 5, 6, 8))
    result = await storage.glean(query=query, limit=40, globs=("team/bob/probe.md", "team/bob/ladder*_0.md"))
    order = [str(o.path).rsplit("/", 1)[-1] for o in result.observations]
    print(f"  ranked order: {' > '.join(order)}")
    print(result.to_str(projection=("path", "score")).replace("\n", "\n    ").join(("    ", "")))
    await storage.close()


async def main() -> None:
    for hidden in (0, 3):
        print(f"\nWORLD: {hidden} hidden HR files mention E48213")
        await attack(hidden)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
