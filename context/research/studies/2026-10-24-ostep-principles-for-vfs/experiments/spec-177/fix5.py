import pathlib, sys
p = pathlib.Path(sys.argv[1])
s = p.read_text()
old = """  call under `Authority.anonymous()` refuses `invalid` ("a request key
  needs a named caller"). The system actor may: it is one trust tier
  (in process, ADR 068), and an ETL job that reuses its own keys is
  replaying its own calls."""
new = """  call under `Authority.anonymous()` refuses `invalid` ("a request key
  needs a named caller"). The system actor may: it is one trust tier
  (in process, ADR 068), and an ETL job that reuses its own keys is
  replaying its own calls. A direct storage call that names no
  authority acts as the system actor (`backend.py` `_named`), so it
  may use a key too."""
assert s.count(old) == 1
s = s.replace(old, new)
p.write_text(s)
