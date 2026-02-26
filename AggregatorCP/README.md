# AggregatorCP deployment guide

This package is the **unified FastAPI control panel** for rAthena operations.
It supports Windows and Linux and ships with:

- `companion-service/` (API + built-in web panel)
- `bridge-service/` (optional signed in-game action bridge)
- `sql-files/` (required migrations + optional tooling SQL)
- `deploy/` (cross-platform install/start scripts)

## Minimal production install

1. Copy modules into your rAthena tree:
   - Linux: `deploy/install_modules.sh /path/to/rathena`
   - Windows: `deploy/install_modules.ps1 -RathenaTree C:\path\to\rathena`
2. Apply SQL migrations:
   - Linux: `deploy/apply_sql.sh`
   - Windows: `deploy/apply_sql.ps1`
3. Start services:
   - Linux: `deploy/start_all_linux.sh`
   - Windows: `deploy/start_all_windows.bat`
4. Open panel: `http://127.0.0.1:4310`

## Notes

- `bridge-service` is optional (only needed for signed game-side action execution).
- `sql-files/upgrades/` are required migration scripts.
- `sql-files/tools/` are optional operational helpers.
