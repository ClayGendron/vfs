-- The engine legs isolate each test in a schema of its own (an Oracle
-- user), created and dropped by the app user. Runs once, at first init.
ALTER SESSION SET CONTAINER = FREEPDB1;
GRANT DBA TO vfs;
