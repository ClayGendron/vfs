import functools, collections
from sqlalchemy import event
from vfs.storage.backends.database.engine import EngineHost
n=collections.Counter()
_orig=EngineHost.__init__
@functools.wraps(_orig)
def init(self, *a, **k):
    _orig(self, *a, **k)
    se=self.engine.sync_engine
    event.listen(se, "commit", lambda conn: n.__setitem__("commit", n["commit"]+1))
    event.listen(se, "before_cursor_execute", lambda conn, cur, st, p, ctx, em: n.__setitem__("stmt", n["stmt"]+1))
EngineHost.__init__=init
def pytest_sessionfinish(session, exitstatus): print(f"\n=== commits={n['commit']} statements={n['stmt']}")
