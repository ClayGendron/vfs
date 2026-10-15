"""Executed on SQLite (stdlib sqlite3): recursive CTE semantics on a cyclic graph."""
import sqlite3
c = sqlite3.connect(":memory:")
print("sqlite", sqlite3.sqlite_version)
c.executescript("""
CREATE TABLE vfs_entries(id INTEGER PRIMARY KEY, path TEXT, deleted_at INTEGER, everyone_level INTEGER);
CREATE TABLE vfs_edges(source_id INTEGER, target_id INTEGER, edge_type TEXT, UNIQUE(source_id,target_id,edge_type));
CREATE INDEX fwd ON vfs_edges(source_id, edge_type);
INSERT INTO vfs_entries VALUES (1,'/a',NULL,1),(2,'/b',NULL,1),(3,'/c',NULL,1),(4,'/d',NULL,0),(5,'/e',NULL,1),(6,'/dead',1,1);
-- cycle 1->2->3->1 ; 1->4 (hidden, level 0) ->5 ; 2->5 ; 3->6 (tombstoned)
INSERT INTO vfs_edges VALUES (1,2,'x'),(2,3,'x'),(3,1,'x'),(1,4,'x'),(4,5,'x'),(2,5,'x'),(3,6,'x');
""")
def run(title, sql, params=()):
    print("\n##", title); print(sql.strip())
    try:
        rows = c.execute(sql, params).fetchall(); print("->", rows)
    except Exception as e: print("-> ERROR:", e)

run("UNION + depth, hard bound 3 (depth makes cycle rows distinct)", """
WITH RECURSIVE walk(id, depth) AS (
  SELECT id, 0 FROM vfs_entries WHERE id IN (1) AND deleted_at IS NULL
  UNION
  SELECT e.id, walk.depth + 1 FROM walk JOIN vfs_edges g ON g.source_id = walk.id AND g.edge_type = 'x'
  JOIN vfs_entries e ON e.id = g.target_id WHERE e.deleted_at IS NULL AND e.everyone_level >= 1 AND walk.depth < 3)
SELECT id, depth FROM walk""")
run("UNION, no depth column, no bound: UNION dedup terminates the cycle", """
WITH RECURSIVE walk(id) AS (
  SELECT id FROM vfs_entries WHERE id IN (1)
  UNION
  SELECT g.target_id FROM walk JOIN vfs_edges g ON g.source_id = walk.id)
SELECT id FROM walk""")
run("UNION ALL + depth bound 2: output order (FIFO queue = BFS by level?)", """
WITH RECURSIVE walk(id, depth) AS (
  SELECT id, 0 FROM vfs_entries WHERE id IN (1, 2)
  UNION ALL
  SELECT g.target_id, walk.depth + 1 FROM walk JOIN vfs_edges g ON g.source_id = walk.id WHERE walk.depth < 2)
SELECT id, depth FROM walk""")
run("Visited check via path string (portable floor): node 5 once per distinct path, cycle cut", """
WITH RECURSIVE walk(id, depth, trail) AS (
  SELECT id, 0, ',' || id || ',' FROM vfs_entries WHERE id IN (1)
  UNION ALL
  SELECT g.target_id, walk.depth + 1, walk.trail || g.target_id || ','
  FROM walk JOIN vfs_edges g ON g.source_id = walk.id
  WHERE walk.depth < 10 AND instr(walk.trail, ',' || g.target_id || ',') = 0)
SELECT id, depth, trail FROM walk""")
run("Recursive member joins a UNION ALL derived table (three-seek shape)", """
WITH RECURSIVE walk(id, depth) AS (
  SELECT id, 0 FROM vfs_entries WHERE id IN (1)
  UNION ALL
  SELECT e.id, walk.depth + 1 FROM walk JOIN vfs_edges g ON g.source_id = walk.id
  JOIN vfs_entries e ON e.id = g.target_id
  JOIN (SELECT id AS entry_id FROM vfs_entries WHERE everyone_level >= 1
        UNION ALL SELECT id FROM vfs_entries WHERE path = '/zzz') v ON v.entry_id = e.id
  WHERE e.deleted_at IS NULL AND walk.depth < 2)
SELECT id, depth FROM walk""")
run("Recursive member joins a second (non-recursive) CTE 'visible'", """
WITH RECURSIVE visible(entry_id) AS (SELECT id FROM vfs_entries WHERE everyone_level >= 1),
walk(id, depth) AS (
  SELECT id, 0 FROM vfs_entries WHERE id IN (1)
  UNION ALL
  SELECT e.id, walk.depth + 1 FROM walk JOIN vfs_edges g ON g.source_id = walk.id
  JOIN vfs_entries e ON e.id = g.target_id JOIN visible v ON v.entry_id = e.id
  WHERE e.deleted_at IS NULL AND walk.depth < 2)
SELECT id, depth FROM walk""")
run("Recursive reference inside a subquery (expect error)", """
WITH RECURSIVE walk(id) AS (
  SELECT 1 UNION SELECT target_id FROM vfs_edges WHERE source_id IN (SELECT id FROM walk))
SELECT * FROM walk""")
run("Two references to the recursive table (expect error)", """
WITH RECURSIVE walk(id) AS (
  SELECT 1 UNION SELECT g.target_id FROM walk w1 JOIN vfs_edges g ON g.source_id = w1.id JOIN walk w2 ON w2.id = g.target_id)
SELECT * FROM walk""")
run("Aggregate in recursive member (expect error)", """
WITH RECURSIVE walk(id) AS (
  SELECT 1 UNION SELECT max(g.target_id) FROM walk JOIN vfs_edges g ON g.source_id = walk.id)
SELECT * FROM walk""")
run("LEFT JOIN with the CTE on the left (allowed?)", """
WITH RECURSIVE walk(id, depth) AS (
  SELECT 1, 0 UNION ALL SELECT g.target_id, walk.depth+1 FROM walk LEFT JOIN vfs_edges g ON g.source_id = walk.id WHERE walk.depth < 1)
SELECT * FROM walk""")
run("ORDER BY depth + LIMIT inside the recursive CTE (SQLite extension)", """
WITH RECURSIVE walk(id, depth) AS (
  SELECT 1, 0 UNION ALL SELECT g.target_id, walk.depth+1 FROM walk JOIN vfs_edges g ON g.source_id = walk.id WHERE walk.depth < 5
  ORDER BY 2 LIMIT 6)
SELECT * FROM walk""")
run("Anchor from json_each (bound seed list unpacked)", """
WITH RECURSIVE walk(id, depth) AS (
  SELECT e.id, 0 FROM json_each(?) s JOIN vfs_entries e ON e.id = s.value
  UNION ALL SELECT g.target_id, walk.depth+1 FROM walk JOIN vfs_edges g ON g.source_id = walk.id WHERE walk.depth < 1)
SELECT * FROM walk""", ("[1,2]",))
run("EXPLAIN QUERY PLAN: is fwd index used inside the recursive step?", """
EXPLAIN QUERY PLAN WITH RECURSIVE walk(id, depth) AS (
  SELECT id, 0 FROM vfs_entries WHERE id IN (1)
  UNION ALL
  SELECT e.id, walk.depth + 1 FROM walk JOIN vfs_edges g ON g.source_id = walk.id AND g.edge_type = 'x'
  JOIN vfs_entries e ON e.id = g.target_id WHERE e.deleted_at IS NULL AND walk.depth < 3)
SELECT id, depth FROM walk""")
