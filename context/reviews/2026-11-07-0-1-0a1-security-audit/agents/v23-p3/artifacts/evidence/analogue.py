"""SQLite analogue: path columns forced to a case-insensitive collation (models a non-binary Oracle/GENERIC compare)."""
import asyncio, sys
from sqlalchemy import String
from vfs.models import rows as rows_mod
from vfs.authority import Authority, Principal
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.memory import InMemoryStorage

MODE = sys.argv[1]
if MODE == "nocase":
    def _ci(self, dialect):
        return dialect.type_descriptor(String(self.length, collation="NOCASE"))
    rows_mod.BytewiseString.load_dialect_impl = _ci

SYSTEM = Authority.system()
ANN, BOB, CAROL = (Authority.of(Principal(n)) for n in ("ann", "bob", "carol"))

def show(label, r):
    errs = [(e.kind, getattr(e, "detail", None)) for e in r.errors] if not r.success else []
    print(f"{label}: success={r.success} errors={errs}")

async def main():
    s = InMemoryStorage()
    try:
        show("system posture / read_write", await s.posture(path=Path("/"), posture="read_write", authority=SYSTEM))
        show("bob writes /projects/secret.md", await s.write(entries=[Entry(path=Path("/projects/secret.md"), content="bob private")], parents=True, authority=BOB))
        show("bob posture /projects none", await s.posture(path=Path("/projects"), posture="none", authority=BOB))
        show("carol read /projects/secret.md (before)", await s.read(path=Path("/projects/secret.md"), authority=CAROL))
        show("ann posture /projects read (control: direct path)", await s.posture(path=Path("/projects"), posture="read", authority=ANN))
        show("ann posture /Projects read (case variant)", await s.posture(path=Path("/Projects"), posture="read", authority=ANN))
        g = await s.grants(path=Path("/"), authority=SYSTEM)
        print("grant rows:", [ (getattr(o,'path',None), getattr(o,'principal',None), getattr(o,'level',None)) for o in g.observations] if g.success else g.errors)
        r = await s.read(path=Path("/projects/secret.md"), authority=CAROL)
        show("carol read /projects/secret.md (after)", r)
        if r.success:
            print("carol saw content:", [getattr(o, "content", None) for o in r.observations])
    finally:
        await s.close()

asyncio.run(main())
