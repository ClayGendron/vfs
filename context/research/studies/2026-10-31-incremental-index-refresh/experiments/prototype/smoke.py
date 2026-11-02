import sys, time, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
import statistics
t0=time.perf_counter(); docs=[make_doc(i) for i in range(1,2001)]; t1=time.perf_counter()
print("gen per doc us", (t1-t0)/2000*1e6, "mean size", statistics.mean(map(len,docs)), "min", min(map(len,docs)), "max", max(map(len,docs)))
print(docs[1][:600])
# distinct grams per doc
from vfs.models.code_grams import unique_code_grams
print("distinct grams/doc", statistics.mean(len(unique_code_grams(d, folded=True)) for d in docs[:200]))
db="/private/tmp/claude-501/-Users-claygendron-Git-Repos-vfs/1bff4c75-daaa-4734-82d6-6bf1657ce644/scratchpad/incremental/prototype/smoke.db"
for f in (db, db+"-wal", db+"-shm"):
    if os.path.exists(f): os.remove(f)
conn=open_store(db)
t=build_segment(conn, 1, [(i,0) for i in range(1,20001)])
print(t, "index_s", t.index_s)
import resource; print("maxrss MB", resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e6)
for pat,fixed in [("fn_"+RARE_POOL[5][3:],True),("return self",True),("def ",True),(r"raise (ValueError|TypeError)",False)]:
    g=plan_groups(pat,fixed); print(pat, g and [len(x) for x in g])
