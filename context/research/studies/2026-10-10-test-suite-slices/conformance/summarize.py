import sys
from collections import defaultdict
d=defaultdict(list)
for l in open(sys.argv[1]):
    p=l.split()
    if len(p)==3 and p[0].endswith("s") and "::" in p[2]:
        cls=p[2].split("::")[1]
        if cls in ("TestMemoryConformance","TestSqliteConformance"):
            d[(cls,p[1])].append(float(p[0][:-1]))
tot=0
for k,v in sorted(d.items()):
    v=sorted(v); n=len(v); tot+=sum(v)
    print(f"{k[0]:24s} {k[1]:9s} n={n:3d} sum={sum(v):6.2f} median={v[n//2]:.3f} max={v[-1]:.3f} top3={v[-3:]}")
print("total", round(tot,2))
