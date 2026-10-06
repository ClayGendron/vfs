-- The engine legs isolate each test in a database of its own (MariaDB's
-- schema), created and dropped by the app user. Runs once, at first init.
GRANT ALL PRIVILEGES ON *.* TO 'vfs'@'%';
