import re, sys, collections
pat = re.compile(r'^\s*([0-9.]+)s (call|setup|teardown)\s+(\S+)')
by_file = collections.Counter(); by_file_n = collections.defaultdict(set)
by_file_phase = collections.defaultdict(collections.Counter)
by_func = collections.Counter(); by_func_n = collections.defaultdict(set)
by_phase = collections.Counter()
for line in open(sys.argv[1]):
    m = pat.match(line)
    if not m: continue
    t, phase, node = float(m[1]), m[2], m[3]
    f = node.split('::')[0]
    if not f.startswith('tests/storage/database/') or f.endswith('test_rights.py'): continue
    by_file[f] += t; by_file_n[f].add(node); by_file_phase[f][phase] += t
    fn = node.split('[')[0]; by_func[fn] += t; by_func_n[fn].add(node)
    by_phase[phase] += t
total = sum(by_file.values())
print(f"SLICE total {total:.1f}s, tests {sum(len(v) for v in by_file_n.values())}")
print("phases:", {k: round(v,1) for k,v in by_phase.items()})
print("\n| File | tests | total s | mean s | setup s | call s |")
print("|---|---|---|---|---|---|")
for f,v in by_file.most_common():
    n=len(by_file_n[f]); p=by_file_phase[f]
    print(f"| {f.split('/')[-1]} | {n} | {v:.1f} | {v/n:.3f} | {p['setup']:.1f} | {p['call']:.1f} |")
print("\n| Function | params | total s |")
print("|---|---|---|")
for fn,v in by_func.most_common(20):
    print(f"| {fn.replace('tests/storage/database/','')} | {len(by_func_n[fn])} | {v:.2f} |")
