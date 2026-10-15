"""Review 165, check 2: the pure resolver under a six-rung ladder, monkeypatched in-process.

Questions: (a) is the Literal enforced at runtime? (b) does Rights(list) == Rights(read) when no row sits
exactly at list (the aliasing claim)? (c) what does `admits` answer through an aliased object?
(d) does a pending posture at exactly `list` break the alias? (e) the meet over subjects at six rungs.
Run from the vfs root:  uv run python <this file>
"""

from __future__ import annotations

from typing import Literal

import vfs.storage.grants as g
from vfs.storage.grants import GrantRow, Rights, resolve

SIX = Literal["none", "list", "read", "add", "contribute", "read_write"]
g.GrantLevel = SIX  # type: ignore[misc]
g.LEVEL_RANK = {w: g.Rank(i) for i, w in enumerate(("none", "list", "read", "add", "contribute", "read_write"))}  # type: ignore[assignment]
print("ranks:", dict(g.LEVEL_RANK))

# (a) the Literal at runtime: an unknown word only fails when LEVEL_RANK is indexed.
try:
    resolve({"ann": frozenset()}, [GrantRow("ann", "/x", "bogus")], "read")  # type: ignore[arg-type]
    print("(a) unknown level word: accepted silently")
except KeyError as exc:
    print(f"(a) unknown level word: KeyError {exc} — the Literal is not enforced; LEVEL_RANK is the only check")

closures = {"ann": frozenset()}
rows = [GrantRow("ann", "/eng", "read"), GrantRow("ann", "/pub", "read_write")]
at = {lvl: resolve(closures, rows, lvl) for lvl in ("list", "read", "add", "contribute", "read_write")}  # type: ignore[arg-type]
print("\n(b) no row at exactly list/add/contribute:")
for a, b in (("list", "read"), ("add", "contribute"), ("contribute", "read_write")):
    print(f"   Rights({a}) == Rights({b}): {at[a] == at[b]};  spans equal: {at[a].spans == at[b].spans};"
          f"  owner_arms equal: {at[a].owner_arms == at[b].owner_arms};  need {at[a].need} vs {at[b].need}")

print("\n(c) admits on a row labelled `list` (everyone_level=1) outside the spans, no owner:")
for lvl in ("list", "read"):
    print(f"   Rights({lvl}).admits('/other.md', None, 1) = {at[lvl].admits('/other.md', None, 1)}")
print("   -> an `at('list')` that hands back the read object would answer False on a list-labelled row.")

print("\n(d) a pending posture at exactly `list` under /eng/sub:")
pend = rows + [GrantRow("*", "/", "none"), GrantRow("*", "/eng/sub", "list")]
lst = resolve(closures, pend, "list", pending=["/eng/sub"])  # type: ignore[arg-type]
rd = resolve(closures, pend, "read", pending=["/eng/sub"])  # type: ignore[arg-type]
print(f"   Rights(list).spans == Rights(read).spans: {lst.spans == rd.spans}; holes list={lst.holes} read={rd.holes}")
pend2 = rows + [GrantRow("*", "/", "none"), GrantRow("*", "/zz", "read_write")]
lst2 = resolve(closures, pend2, "list", pending=["/zz"])  # type: ignore[arg-type]
rd2 = resolve(closures, pend2, "read", pending=["/zz"])  # type: ignore[arg-type]
print(f"   pending at read_write instead: spans equal {lst2.spans == rd2.spans}, holes equal {lst2.holes == rd2.holes}")

print("\n(e) the meet over a set {ann: contribute on /inbox, bob: add on /inbox}:")
two = {"ann": frozenset(), "bob": frozenset()}
rows2 = [GrantRow("ann", "/inbox", "contribute"), GrantRow("bob", "/inbox", "add")]
for lvl in ("list", "read", "add", "contribute", "read_write"):
    r = resolve(two, rows2, lvl)  # type: ignore[arg-type]
    print(f"   level={lvl:11} spans={r.spans} owner_arms={[(a.owner, a.prefixes) for a in r.owner_arms]}")
print("   (a set never holds the floor on a shared row: owner arms name each member's *exclusive* reach only)")

print("\n(f) single named caller at `add` on /inbox — the floor rides every compile:")
one = resolve({"bob": frozenset()}, [GrantRow("bob", "/inbox", "add")], "read_write")  # type: ignore[arg-type]
print(f"   Rights(read_write).spans={one.spans} owner_arms={[(a.owner, a.prefixes) for a in one.owner_arms]}")
print(f"   admits own row /inbox/b.md: {one.admits('/inbox/b.md', 'bob', 0)}; another's: {one.admits('/inbox/a.md', 'ann', 0)}")
print(f"   admits own row OUTSIDE the prefix, /elsewhere/b.md: {one.admits('/elsewhere/b.md', 'bob', 0)}")
