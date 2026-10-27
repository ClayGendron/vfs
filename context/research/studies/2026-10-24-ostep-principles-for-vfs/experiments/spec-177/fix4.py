import pathlib, sys
p = pathlib.Path(sys.argv[1])
s = p.read_text()
e_start = s.index("**E. `posture_twice.py`**")
d_start = s.index("**D. `payload_compress.py`**")
e_block = s[e_start:d_start]
s = s[:e_start] + s[d_start:]
land = s.index("## Landing notes")
s = s[:land] + e_block + s[land:]
p.write_text(s)
