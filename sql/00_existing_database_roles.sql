-- Run in pgAdmin 4 > Query Tool, connected specifically to database "COT"
-- as PostgreSQL administrator (normally postgres).
-- No passwords are stored in SQL or GitHub. Set via pgAdmin Role Properties.
-- Safe for the database that was already created manually.

DO $cot$
BEGIN
  IF current_database() <> 'COT' THEN
     RAISE EXCEPTION 'Connected to %, expected COT', current_database();
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cot_loader') THEN
     CREATE ROLE cot_loader LOGIN;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cot_app') THEN
     CREATE ROLE cot_app LOGIN;
  END IF;
END
$cot$;

-- Schema owner / ingestion process. CREATE is required when COT was
-- created manually and therefore belongs to another PostgreSQL role.
REVOKE ALL ON DATABASE "COT" FROM PUBLIC;
GRANT CONNECT, TEMPORARY, CREATE ON DATABASE "COT" TO cot_loader;

-- Applications need only to connect and read objects granted in 01_schema.sql.
GRANT CONNECT ON DATABASE "COT" TO cot_app;

SELECT current_database() AS database_name,
       rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole
FROM pg_roles
WHERE rolname IN ('cot_loader', 'cot_app')
ORDER BY rolname;
