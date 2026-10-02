## vfs's own vector-leg statement on SQLite, 50,000 files, dim 64, 5 runs each

### 1 grant (1 vector statement(s)); first: 11 ms
    SEARCH vfs_88fc7062 USING INDEX ix_vfs_88fc7062_kind (kind=?)
    SEARCH vfs_88fc7062_chunks USING INDEX ix_vfs_88fc7062_chunks_entry_id (entry_id=?)
    USE TEMP B-TREE FOR ORDER BY

    admitted-first, path arms only: 0 ms — plan: MATERIALIZE v; MULTI-INDEX OR; INDEX 1; SEARCH vfs_88fc7062 USING INDEX ix_vfs_88fc7062_path (path=?)
    admitted-first, path arms UNION owner arm: 0 ms — plan: MATERIALIZE v; COMPOUND QUERY; LEFT-MOST SUBQUERY; MULTI-INDEX OR

### 10 grants (1 vector statement(s)); first: 31 ms
    SEARCH vfs_88fc7062 USING INDEX ix_vfs_88fc7062_kind (kind=?)
    SEARCH vfs_88fc7062_chunks USING INDEX ix_vfs_88fc7062_chunks_entry_id (entry_id=?)
    USE TEMP B-TREE FOR ORDER BY

    admitted-first, path arms only: 1 ms — plan: MATERIALIZE v; MULTI-INDEX OR; INDEX 1; SEARCH vfs_88fc7062 USING INDEX ix_vfs_88fc7062_path (path=?)
    admitted-first, path arms UNION owner arm: 1 ms — plan: MATERIALIZE v; COMPOUND QUERY; LEFT-MOST SUBQUERY; MULTI-INDEX OR

### 100 grants (1 vector statement(s)); first: 214 ms
    SEARCH vfs_88fc7062 USING INDEX ix_vfs_88fc7062_kind (kind=?)
    SEARCH vfs_88fc7062_chunks USING INDEX ix_vfs_88fc7062_chunks_entry_id (entry_id=?)
    USE TEMP B-TREE FOR ORDER BY

    admitted-first, path arms only: 9 ms — plan: MATERIALIZE v; MULTI-INDEX OR; INDEX 1; SEARCH vfs_88fc7062 USING INDEX ix_vfs_88fc7062_path (path=?)
    admitted-first, path arms UNION owner arm: 10 ms — plan: MATERIALIZE v; COMPOUND QUERY; LEFT-MOST SUBQUERY; MULTI-INDEX OR

### 500 grants (3 vector statement(s)); first: 393 ms
    SEARCH vfs_88fc7062 USING INDEX ix_vfs_88fc7062_kind (kind=?)
    SEARCH vfs_88fc7062_chunks USING INDEX ix_vfs_88fc7062_chunks_entry_id (entry_id=?)
    USE TEMP B-TREE FOR ORDER BY

    admitted-first, path arms only: 42 ms — plan: MATERIALIZE v; MULTI-INDEX OR; INDEX 1; SEARCH vfs_88fc7062 USING INDEX ix_vfs_88fc7062_path (path=?)
    admitted-first, path arms UNION owner arm: 44 ms — plan: MATERIALIZE v; COMPOUND QUERY; LEFT-MOST SUBQUERY; MULTI-INDEX OR

