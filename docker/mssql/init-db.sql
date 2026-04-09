IF DB_ID('grover_test') IS NULL
BEGIN
    CREATE DATABASE grover_test;
END;
GO
-- Full-text support is installed at the instance level via mssql-server-fts.
-- The actual catalog + index are created by tests/conftest.py::_provision_mssql_fulltext.
