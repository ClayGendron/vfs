## vfs's own vector-leg statement on SQLite, 50,000 files, dim 64, 5 runs each

### 1 grant (1 vector statement(s)); first: 12 ms
    SCAN vfs_c64c25fe
    SEARCH vfs_c64c25fe_chunks USING INDEX ix_vfs_c64c25fe_chunks_entry_id (entry_id=?)
    USE TEMP B-TREE FOR ORDER BY

    admitted-first, path arms only: 0 ms — plan: MATERIALIZE v; MULTI-INDEX OR; INDEX 1; SEARCH vfs_c64c25fe USING INDEX ix_vfs_c64c25fe_path (path=?)
    admitted-first, path arms UNION owner arm: 5 ms — plan: MATERIALIZE v; COMPOUND QUERY; LEFT-MOST SUBQUERY; MULTI-INDEX OR

### 10 grants (1 vector statement(s)); first: 32 ms
    SCAN vfs_c64c25fe
    SEARCH vfs_c64c25fe_chunks USING INDEX ix_vfs_c64c25fe_chunks_entry_id (entry_id=?)
    USE TEMP B-TREE FOR ORDER BY

    admitted-first, path arms only: 1 ms — plan: MATERIALIZE v; MULTI-INDEX OR; INDEX 1; SEARCH vfs_c64c25fe USING INDEX ix_vfs_c64c25fe_path (path=?)
    admitted-first, path arms UNION owner arm: 5 ms — plan: MATERIALIZE v; COMPOUND QUERY; LEFT-MOST SUBQUERY; MULTI-INDEX OR

### 100 grants (1 vector statement(s)); first: 215 ms
    SCAN vfs_c64c25fe
    SEARCH vfs_c64c25fe_chunks USING INDEX ix_vfs_c64c25fe_chunks_entry_id (entry_id=?)
    USE TEMP B-TREE FOR ORDER BY

    admitted-first, path arms only: 9 ms — plan: MATERIALIZE v; MULTI-INDEX OR; INDEX 1; SEARCH vfs_c64c25fe USING INDEX ix_vfs_c64c25fe_path (path=?)
    admitted-first, path arms UNION owner arm: 14 ms — plan: MATERIALIZE v; COMPOUND QUERY; LEFT-MOST SUBQUERY; MULTI-INDEX OR

### 500 grants (3 vector statement(s)); first: 391 ms
    SCAN vfs_c64c25fe
    SEARCH vfs_c64c25fe_chunks USING INDEX ix_vfs_c64c25fe_chunks_entry_id (entry_id=?)
    USE TEMP B-TREE FOR ORDER BY

    admitted-first, path arms only: 41 ms — plan: MATERIALIZE v; MULTI-INDEX OR; INDEX 1; SEARCH vfs_c64c25fe USING INDEX ix_vfs_c64c25fe_path (path=?)
    admitted-first, path arms UNION owner arm: 48 ms — plan: MATERIALIZE v; COMPOUND QUERY; LEFT-MOST SUBQUERY; MULTI-INDEX OR

