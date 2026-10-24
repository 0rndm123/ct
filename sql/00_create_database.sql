-- Run while connected to postgres, as a PostgreSQL admin (typically postgres).
-- "COT" is a quoted UPPERCASE database name: use dbname=COT when connecting.
-- This script is idempotent. It never stores or resets passwords.
SELECT 'CREATE ROLE cot_loader LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cot_loader')
\gexec
SELECT 'CREATE ROLE cot_app LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cot_app')
\gexec

SELECT 'CREATE DATABASE "COT" OWNER cot_loader'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'COT')
\gexec

-- Remove default PUBLIC database access and explicitly grant approved roles.
REVOKE ALL ON DATABASE "COT" FROM PUBLIC;
GRANT CONNECT, TEMPORARY, CREATE ON DATABASE "COT" TO cot_loader;
GRANT CONNECT ON DATABASE "COT" TO cot_app;
