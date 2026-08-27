"""No database needed: what does insert(entry).values(binds) compile to per
dialect, and do .inline() / for_executemany=True strip the implicit
RETURNING/OUTPUT clause?"""
from sqlalchemy import bindparam, insert
from sqlalchemy.dialects import mssql, mysql, oracle, postgresql, sqlite

import rl_common as C

t = C.tables("cc")
names = ("entry_id", "path", "name", "kind")
for label, d in (("sqlite", sqlite.dialect()), ("mysql", mysql.dialect()), ("postgresql", postgresql.dialect()), ("mssql", mssql.dialect()), ("oracle", oracle.dialect())):
    stmt = insert(t.entry).values({n: bindparam(n) for n in names})
    plain = str(stmt.compile(dialect=d))
    inline = str(stmt.inline().compile(dialect=d))
    fem = str(stmt.compile(dialect=d, for_executemany=True))
    def tail(s):
        for word in ("OUTPUT", "RETURNING"):
            if word in s:
                return s[s.index(word):].replace("\n", " ")[:40]
        return "-"
    print(f"{label:11} plain: {tail(plain)!r:24} inline: {tail(inline)!r:6} for_executemany: {tail(fem)!r:6} | insert_returning={d.insert_returning} favor_returning_over_lastrowid={getattr(d, 'favor_returning_over_lastrowid', None)} postfetch_lastrowid={d.postfetch_lastrowid}")
print(str(insert(t.lex_postings).values({n: bindparam(n) for n in ("epoch", "term", "block_no", "doc_count", "doc_ids", "tfs", "dls")}).compile(dialect=mssql.dialect())))
