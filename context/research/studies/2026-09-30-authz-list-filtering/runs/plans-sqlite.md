## sqlite — 50,000 entries, 500 folder grants, the count statement

### like (first 400 arms)

```
4 | 0 | 216 | SCAN azq_8665e532_docs
6 | 0 | 45 | SEARCH azq_8665e532_entry USING INTEGER PRIMARY KEY (rowid=?)
```

### tree (first 1,000 ranges)

```
4 | 0 | 216 | SCAN azq_8665e532_docs
6 | 0 | 45 | SEARCH azq_8665e532_entry USING INTEGER PRIMARY KEY (rowid=?)
```

### drive

```
7 | 0 | 62 | SEARCH azq_8665e532_cover USING INDEX sqlite_autoindex_azq_8665e532_cover_1 (set_id=?)
12 | 0 | 156 | SEARCH azq_8665e532_entry USING COVERING INDEX ix_azq_8665e532_entry_path (path>? AND path<?)
17 | 0 | 62 | SEARCH azq_8665e532_docs USING INDEX ix_azq_8665e532_docs_entry_id (entry_id=?)
```

### values (first 1,000 ranges)

```
2 | 0 | 0 | CO-ROUTINE vc
3 | 2 | 0 | SCAN 1000 CONSTANT ROWS
3009 | 0 | 1016 | SCAN vc
3012 | 0 | 156 | SEARCH azq_8665e532_entry USING COVERING INDEX ix_azq_8665e532_entry_path (path>? AND path<?)
3021 | 0 | 62 | SEARCH azq_8665e532_docs USING INDEX ix_azq_8665e532_docs_entry_id (entry_id=?)
```
