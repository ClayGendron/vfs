"""Characters of name+description per SKILL.md frontmatter, and SKILL.md sizes, in a skills checkout."""
import glob
import re
import sys

root = sys.argv[1]
rows = []
for f in sorted(glob.glob(f"{root}/skills/*/SKILL.md")):
    t = open(f, encoding="utf-8").read()
    fm = re.search(r"^---\n(.*?)\n---", t, re.S).group(1)
    name = re.search(r"^name:\s*(.*)$", fm, re.M).group(1)
    desc = re.search(r"^description:\s*(.*)$", fm, re.M).group(1)
    rows.append((f.split("/")[-2], len(name) + len(desc), len(t.encode("utf-8"))))
for r in rows:
    print(*r, sep="\t")
meta = sum(r[1] for r in rows)
body = sorted(r[2] for r in rows)
print(f"skills={len(rows)} metadata_chars={meta} metadata_chars_per_skill={meta / len(rows):.0f} skill_md_bytes_median={body[len(body) // 2]} max={body[-1]}")
