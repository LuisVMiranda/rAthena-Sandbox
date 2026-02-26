# AggregatorCP SQL guide

Use the migration wrappers in `deploy/`:

- Linux/macOS: `deploy/apply_sql.sh`
- Windows PowerShell: `deploy/apply_sql.ps1`

Both call `deploy/apply_sql.py` (mysql-connector-python) and execute required migrations in `MIGRATIONS.manifest`.

## Required
- `sql-files/upgrades/*.sql` (schema/data migrations)

## Minimal example (Linux)

```bash
DB_HOST=127.0.0.1 DB_PORT=3306 DB_USER=rathena DB_PASS=secret DB_NAME=ragnarok ./deploy/apply_sql.sh
```
