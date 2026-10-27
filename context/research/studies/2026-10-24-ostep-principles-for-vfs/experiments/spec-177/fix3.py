import pathlib, sys
p = pathlib.Path(sys.argv[1])
s = p.read_text()
pairs = [
("| `posture` | success, `grants=`, `relabel=` | success, `relabel=` zero rows | idempotent | `grants(path)`: the everyone row |",
 "| `posture` | success, `grants=`, `relabel=` | success; the labels beneath are rewritten to the same value again (EXECUTED: 6 rows, then 6 again) | idempotent | `grants(path)`: the everyone row |"),
("""Rules the table follows:

- A verb's **shape**""",
"""Rules the table follows:

- The table shows some forms on their own lines, for reading.
  `REPLAY` (§0.2) holds one row per verb; its `replay` text names each
  form.
- A verb's **shape**"""),
("""**D. `payload_compress.py`**""",
"""**E. `posture_twice.py`**: a posture sent twice over five files.

```text
posture #1: ok=True relabel={'rows': 6, 'statements': 2, 'transactions': 1}
posture #2: ok=True relabel={'rows': 6, 'statements': 2, 'transactions': 1}
```

**D. `payload_compress.py`**"""),
]
for old, new in pairs:
    if s.count(old) != 1:
        print("MISS:", old[:80]); continue
    s = s.replace(old, new)
p.write_text(s)
