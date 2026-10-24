-- Execute with psql while connected to a maintenance DB (e.g. postgres).
-- The uppercase quoted name "COT" is intentional.
SELECT 'CREATE DATABASE "COT"'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'COT')
\gexec
