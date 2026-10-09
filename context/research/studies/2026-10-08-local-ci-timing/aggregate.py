import re, sys, collections
pat = re.compile(r'^\s*([0-9.]+)s (call|setup|teardown)\s+(\S+)')
by_file = collections.Counter(); by_phase = collections.Counter(); by_test = collections.Counter()
by_dir = collections.Counter(); by_func = collections.Counter(); n_tests=set()
for line in open(sys.argv[1]):
    m = pat.match(line)
    if not m: continue
    t, phase, node = float(m[1]), m[2], m[3]
    f = node.split('::')[0]; n_tests.add(node)
    by_file[f] += t; by_phase[phase] += t; by_test[node] += t
    by_dir['/'.join(f.split('/')[:3])] += t
    by_func[node.split('[')[0]] += t
total = sum(by_phase.values())
print(f"TOTAL measured {total:.1f}s over {len(n_tests)} tests")
print("\nBY PHASE"); [print(f"  {k:9} {v:7.1f}s {v/total:5.1%}") for k,v in by_phase.most_common()]
print("\nBY DIRECTORY"); [print(f"  {v:7.1f}s {v/total:5.1%}  {k}") for k,v in by_dir.most_common(15)]
print("\nTOP 25 FILES"); [print(f"  {v:7.1f}s {v/total:5.1%}  {k}") for k,v in by_file.most_common(25)]
print("\nTOP 25 TEST FUNCTIONS (params summed)"); [print(f"  {v:7.1f}s  {k}") for k,v in by_func.most_common(25)]
print("\nTOP 20 SINGLE TESTS"); [print(f"  {v:7.1f}s  {k}") for k,v in by_test.most_common(20)]
# distribution
vals = sorted(by_test.values(), reverse=True)
cum=0
for frac in (0.5,0.8,0.9):
    cum=0
    for i,v in enumerate(vals):
        cum+=v
        if cum>=total*frac: print(f"\n{frac:.0%} of time is in the slowest {i+1} tests ({(i+1)/len(vals):.1%} of tests)"); break
print(f"tests over 1s: {sum(1 for v in vals if v>1)}, over 0.1s: {sum(1 for v in vals if v>0.1)}")
