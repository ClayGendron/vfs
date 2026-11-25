"""Run the shell cases of chosen Oils spec files under host bash and under vfs-shell; report disagreements.

Nothing from the spec files is written anywhere but the scratch output; the report names cases by file and title.
"""
import json, os, re, subprocess, sys, tempfile

OILS, RAW = sys.argv[1], sys.argv[2]
files = sys.argv[3:]
SKIP = re.compile(r"\$SH\b|\$REPO_ROOT|\$TMP|_tmp|spec/|/tmp|\$\$|RANDOM|SECONDS|\bsleep\b|\bdate\b|\bwait\b|\bkill\b|\bulimit\b|\$PPID|BASHPID|\bpython|\becho \$0|\bexec\b|\beval\b|\bsource\b|^\s*\. |\btrap\b|\balias\b|\bcd\b|\benv\b|\bset -x|\bPS4|\bhistory|\bLANG|\bLC_|\bTZ\b|\bulimit|/dev/|\bhostname|\bwhoami|\bid\b|\btype\b|\bcommand -v|\bhash\b|\bcompgen|\bprintenv|\bexport -p|\bdeclare -p\b|\bset\s*$|\bshopt -p|\bumask")
results = []
for name in files:
    text = open(os.path.join(OILS, "spec", name), encoding="utf-8", errors="replace").read()
    for block in text.split("\n#### ")[1:]:
        title, _, body = block.partition("\n")
        script = []
        for line in body.split("\n"):
            if line.startswith("## "):
                break
            script.append(line)
        src = "\n".join(script) + "\n"
        if SKIP.search(src):
            results.append({"file": name, "case": title, "verdict": "skipped"})
            continue
        with tempfile.TemporaryDirectory() as d:
            sp = os.path.join(d, "s.sh")
            open(sp, "w").write(src)
            work = os.path.join(d, "w"); os.mkdir(work)
            try:
                b = subprocess.run(["bash", "--norc", "--noprofile", sp], cwd=work, capture_output=True, timeout=10,
                                   env={"PATH": "/usr/bin:/bin", "HOME": "/"})
                bash = (b.stdout, b.returncode)
            except subprocess.TimeoutExpired:
                bash = (b"<timeout>", -1)
            try:
                v = subprocess.run([RAW, sp], capture_output=True, timeout=10)
                vfs = (v.stdout, v.returncode, v.stderr[-300:])
            except subprocess.TimeoutExpired:
                vfs = (b"<timeout>", -1, b"")
        same = bash[0] == vfs[0] and (bash[1] == 0) == (vfs[1] == 0)
        results.append({"file": name, "case": title, "verdict": "agree" if same else "differ",
                        "bash": [bash[0].decode(errors="replace")[:300], bash[1]],
                        "vfs": [vfs[0].decode(errors="replace")[:300], vfs[1], vfs[2].decode(errors="replace")]})
json.dump(results, sys.stdout, indent=1)
