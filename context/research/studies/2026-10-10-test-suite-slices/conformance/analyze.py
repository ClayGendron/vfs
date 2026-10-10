import pstats, sys
st = pstats.Stats(sys.argv[1])
total = st.total_tt
print("total profiled time %.1fs" % total)
want = {
 "first touch": ("engine.py", "_first_touch"),
 "  create_all": ("schema.py", "create_all"),
 "  _can_create_table (checkfirst)": ("ddl.py", "_can_create_table"),
 "  _provision": ("engine.py", "_provision"),
 "  _apply_file_settings": ("engine.py", "_apply_file_settings"),
 "  _probe_sqlite_vec": ("engine.py", "_probe_sqlite_vec"),
 "  _load_sqlite_vec": ("engine.py", "_load_sqlite_vec"),
 "build_vfs_tables (construct)": ("rows.py", "build_vfs_tables"),
 "DatabaseStorage.__init__": ("backend.py", "__init__"),
 "close": ("engine.py", "close"),
 "engine.dispose": ("engine.py", "dispose"),
 "HashEmbeddingProvider.embed": ("embedding", "embed"),
 "pytest runtestprotocol": ("runner.py", "runtestprotocol"),
 "pytest call_and_report setup": ("runner.py", "pytest_runtest_setup"),
 "pytest teardown": ("runner.py", "pytest_runtest_teardown"),
 "pytest call": ("runner.py", "pytest_runtest_call"),
 "new_event_loop": ("events.py", "new_event_loop"),
 "selectors.select (idle wait)": ("selectors.py", "select"),
 "greenlet_spawn": ("_concurrency_py3k.py", "greenlet_spawn"),
 "session.execute": ("asyncio/session.py", "execute"),
 "monkeypatch tracking init": ("conftest.py", "tracking"),
}
verbs = ["write","read","stat","ls","mkdir","delete","restore","move","copy","grep","glob","glean","reindex","tree","grant","grants","revoke","edges","rmedge","addedge","label","find","walk","posture","trash","purge","chmod","link","unlink","explain","graph"]
for label,(fn,name) in want.items():
    tt=ct=nc=0
    for (f,l,n),(cc,ncalls,t,c,callers) in st.stats.items():
        if n==name and fn in f:
            nc+=ncalls; tt+=t; ct+=c
    print(f"{label:38s} ncalls={nc:7d} cum={ct:7.2f}s ({ct/total*100:4.1f}%) own={tt:6.2f}s")
print("--- public verbs on backend.py (cumulative, includes first touch when it is the first verb)")
rows=[]
for (f,l,n),(cc,ncalls,t,c,callers) in st.stats.items():
    if f.endswith("database/backend.py") and n in verbs:
        rows.append((c,ncalls,n))
for c,ncalls,n in sorted(rows,reverse=True)[:25]:
    print(f"  {n:12s} ncalls={ncalls:6d} cum={c:6.2f}s")
