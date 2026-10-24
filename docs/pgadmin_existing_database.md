# Continue from a manually created PostgreSQL "COT" database (pgAdmin 4)

Do not recreate or rename the manually created `"COT"` database. The Git repository stays at
`D:\OD\OneDrive\tech\GitHub\rndm123\ct`; raw CFTC files are written to
`D:\OD\OneDrive\Fin\data\COT` by the Python loader.

## 1. Fetch the latest code

```powershell
cd "D:\OD\OneDrive\tech\GitHub\rndm123\ct"
git remote set-url origin git@github-rndm123:0rndm123/ct.git
git pull origin main
```

If SSH authentication fails, verify `ssh -T github-rndm123` and the configured SSH host alias.

## 2. Provision roles in existing COT via pgAdmin

1. Launch pgAdmin 4, connect with your PostgreSQL **administrator** role (usually `postgres`).
2. Under **Servers > ... > Databases > COT**, right-click `COT`, then **Query Tool**.
3. Verify the Query Tool is connected to `COT` (uppercase).
4. Open and execute the repository file `sql/00_existing_database_roles.sql`.

This creates two login roles with no hardcoded credentials:

- `cot_loader` to write data and own the objects of the `cot` schema.
- `cot_app` for read-only application queries.

The script also grants `CREATE` on the **already existing** database to `cot_loader`. This is intentional: the manual database owner may not be `cot_loader`. The loader account is **not** a superuser, does **not** get CREATEDB, and does **not** get CREATEROLE.

## 3. Choose passwords using pgAdmin GUI, not SQL in the Git repository

In pgAdmin expand **Login/Group Roles** under your server. For **cot_loader** and **cot_app** separately:

1. Right-click the role > **Properties** > **Definition**.
2. Enter a **different, strong password** for each role; save.
3. Check the role has **Can login? Yes** and **Superuser? No**.

Store the passwords in a password manager. Do not put them into a tracked SQL/BAT/configuration file or chat.

## 4. Initialize the tables as PostgreSQL admin through pgAdmin

Still in the **COT** Query Tool, open `sql/01_schema.sql` and execute the **entire** file as the PostgreSQL administrator (usually `postgres`).

The SQL begins with a transaction, temporarily switches to `cot_loader` for object creation, and finally grants SELECT to `cot_app`. If the file fails, inspect the first error and stop; a failed transaction should not be partially committed.

Check with:

```sql
SELECT current_database();
SELECT schema_name FROM information_schema.schemata WHERE schema_name='cot';
SELECT table_schema,table_name
FROM information_schema.tables
WHERE table_schema='cot' ORDER BY table_name;
SELECT grantee,table_name,privilege_type
FROM information_schema.table_privileges
WHERE table_schema='cot' AND grantee='cot_app' ORDER BY table_name;
```

The current SQL includes the `archive_manifest` reference which connects each DB ingestion window to the original JSON files stored in OneDrive.

## 5. Test read-only and loader logins

Use a different pgAdmin connection for each role, or PostgreSQL client. Do not use the administrator account for routine ingestion.

A read-only connection string for applications:

```text
postgresql://cot_app@localhost:5432/COT
```

A separate connection string for the extraction/ingestion scripts:

```text
postgresql://cot_loader@localhost:5432/COT
```

Choose your server host and port if not localhost:5432. Avoid embedding passwords in code or tracked files. Use
`%APPDATA%\postgresql\pgpass.conf` or your existing OS-approved secret manager.

Set `COT_DATABASE_URL` for the extraction process to the `cot_loader` DSN,
and run the offline tests before loading a single pilot year:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:COT_DATABASE_URL = "postgresql://cot_loader@localhost:5432/COT"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\scripts\load_history.bat --start-year 2025 --end-year 2025
.\scripts\verify.bat
```

The raw JSON pages are saved and checksummed under `D:\OD\OneDrive\Fin\data\COT` **before** report records are inserted in PostgreSQL.

If the user previously saw `psql not found on PATH`, following the pgAdmin Query Tool instructions avoids needing `psql.exe` for provisioning. The BAT launchers `init_db.bat` and `set_passwords.bat` still require it.

### Security caveats

- Do not use `postgres` as the credential of an application.
- Do not grant `cot_app` permissions to INSERT, UPDATE, DELETE, CREATE or DROP.
- Granting `CREATE` on the existing database is needed so `cot_loader` can initially create the `cot` schema; after creating the schema, this database-level CREATE grant can be revoked as a hardening step, provided future migrations are designed accordingly.
- If PostgreSQL is accessed remotely, configure `pg_hba.conf`, TLS/firewall and network restrictions deliberately rather than exposing port 5432 publicly.
