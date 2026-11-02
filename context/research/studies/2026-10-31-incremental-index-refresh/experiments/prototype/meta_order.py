"""Side check: does column order (blob before meta columns) make the meta read walk overflow pages in SQLite?"""
import sys, os, time, sqlite3, statistics as st
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import open_store, fetch_meta, plan_groups
import exp2_read
HERE = os.path.dirname(os.path.abspath(__file__))
conn = open_store(os.path.join(HERE, "exp2.db"))
conn.execute("ATTACH DATABASE ':memory:' AS m")
conn.execute("CREATE TABLE m.meta_first (segment INTEGER NOT NULL, gram_key INTEGER NOT NULL, doc_count INTEGER NOT NULL, byte_size INTEGER NOT NULL, postings BLOB NOT NULL, PRIMARY KEY (segment, gram_key)) WITHOUT ROWID")
conn.execute("INSERT INTO m.meta_first SELECT segment, gram_key, doc_count, byte_size, postings FROM posting_list WHERE segment IN (0,1,2,3,4,5,6,7,8,9,10,11,12)")
qs = exp2_read.queries()
def bench(table, K, reps=5):
    segs = list(range(K + 1)); out = []
    for _ in range(reps):
        t = 0.0
        for _n, pat, fixed in qs:
            grams = sorted({g for grp in plan_groups(pat, fixed) for g in grp})
            q = f"SELECT segment, gram_key, doc_count, byte_size FROM {table} WHERE segment IN ({','.join('?'*len(segs))}) AND gram_key IN ({','.join('?'*len(grams))})"
            t0 = time.perf_counter(); conn.execute(q, [*segs, *grams]).fetchall(); t += time.perf_counter() - t0
        out.append(t / len(qs) * 1e3)
    return st.median(out)
print("plan:", conn.execute("EXPLAIN QUERY PLAN SELECT segment, gram_key, doc_count, byte_size FROM posting_list WHERE segment IN (0,1) AND gram_key IN (1,2,3)").fetchall())
for K in (0, 12):
    print(f"K={K}: blob-before-meta (vfs shape) {bench('posting_list', K):.2f} ms/query warm; meta-before-blob {bench('m.meta_first', K):.2f} ms/query")
