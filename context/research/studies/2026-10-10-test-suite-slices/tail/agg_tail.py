import re, sys, collections
pat = re.compile(r'^\s*([0-9.]+)s (call|setup|teardown)\s+(\S+)')
EXCL = ("tests/ranking/test_harness.py", "tests/storage/test_conformance.py", "tests/storage/test_grants.py")
def excluded(f): return f in EXCL or f.startswith("tests/storage/database/")
by_file=collections.Counter(); by_dir=collections.Counter(); by_func=collections.Counter(); by_phase=collections.Counter(); by_file_phase=collections.defaultdict(collections.Counter); nfile=collections.Counter()
tests=set(); total_all=0
for line in open(sys.argv[1]):
    m=pat.match(line)
    if not m: continue
    t,phase,node=float(m[1]),m[2],m[3]; f=node.split("::")[0]; total_all+=t
    if excluded(f): continue
    if node not in tests: tests.add(node); nfile[f]+=1
    by_file[f]+=t; by_phase[phase]+=t; by_func[node.split("[")[0]]+=t; by_file_phase[f][phase]+=t
    d=f.rsplit("/",1)[0]; by_dir[d]+=t
tot=sum(by_phase.values())
print(f"SLICE total {tot:.1f}s over {len(tests)} tests (whole run measured {total_all:.1f}s)")
print("\nBY PHASE"); [print(f"  {k:9}{v:7.1f}s {v/tot:5.1%}") for k,v in by_phase.most_common()]
print("\nBY DIRECTORY"); [print(f"  {v:7.1f}s {v/tot:5.1%}  {k}") for k,v in by_dir.most_common()]
print("\nTOP 20 FILES (tests, setup/call/teardown)")
for k,v in by_file.most_common(20):
    p=by_file_phase[k]; print(f"  {v:6.1f}s {v/tot:5.1%} n={nfile[k]:4d} mean={v/nfile[k]*1000:6.1f}ms  s={p['setup']:.1f} c={p['call']:.1f} t={p['teardown']:.1f}  {k}")
print("\nTOP 25 FUNCTIONS"); [print(f"  {v:6.2f}s  {k}") for k,v in by_func.most_common(25)]
