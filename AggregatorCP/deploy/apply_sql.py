#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

mysql = None
MySQLError = Exception

MESSAGES: Dict[str, Dict[str, str]] = {
    "en": {
        "connector_missing": "mysql-connector-python not found. Attempting automatic install...",
        "connector_install_fail": "Could not install mysql-connector-python automatically.",
        "manifest_missing": "Missing migration manifest: {path}",
        "manifest_invalid": "Invalid manifest line: {line}",
        "db_engine": "DB engine: {engine}",
        "schema_mode": "Schema apply mode: {mode}",
        "missing_sql": "Missing SQL file: {path}",
        "apply_error": "ERROR applying [{label}] {migration_key}: {error}",
        "applied": "[{label}] applied {migration_key}",
        "skipped": "[{label}] skipped {migration_key} (already applied)",
        "bundle_written": "Wrote processed SQL bundle: {path}",
        "verification_ok": "Database verification passed.",
        "missing_table": "Verification failed: missing required table {name}",
        "missing_proc": "Verification failed: missing procedure {name}",
        "prompt_lang": "Select language / Selecione o idioma: [1] English [2] Português (default: English): ",
        "prompt_tools": "Apply optional SQL tools/procedures too? [Y/N] (default: N): ",
        "tools_enabled": "Tools/procedure SQL apply: enabled",
        "tools_disabled": "Tools/procedure SQL apply: disabled",
    },
    "pt": {
        "connector_missing": "mysql-connector-python não encontrado. Tentando instalação automática...",
        "connector_install_fail": "Não foi possível instalar mysql-connector-python automaticamente.",
        "manifest_missing": "Manifesto de migrações não encontrado: {path}",
        "manifest_invalid": "Linha inválida no manifesto: {line}",
        "db_engine": "Motor do banco: {engine}",
        "schema_mode": "Modo de aplicação do schema: {mode}",
        "missing_sql": "Arquivo SQL ausente: {path}",
        "apply_error": "ERRO ao aplicar [{label}] {migration_key}: {error}",
        "applied": "[{label}] aplicado {migration_key}",
        "skipped": "[{label}] ignorado {migration_key} (já aplicado)",
        "bundle_written": "Bundle SQL processado gravado em: {path}",
        "verification_ok": "Verificação do banco concluída com sucesso.",
        "missing_table": "Falha na verificação: tabela obrigatória ausente {name}",
        "missing_proc": "Falha na verificação: procedure ausente {name}",
        "prompt_lang": "Selecione o idioma / Select language: [1] Português [2] English (padrão: Português): ",
        "prompt_tools": "Aplicar também os SQLs/procedures opcionais de /tools/? [S/N] (padrão: N): ",
        "tools_enabled": "Aplicação de SQLs/procedures de tools: habilitada",
        "tools_disabled": "Aplicação de SQLs/procedures de tools: desabilitada",
    },
}

TOLERATED_CODES = {1060, 1061, 1091}


@dataclass
class MigrationEntry:
    order: str
    relative: str


def pick_language(lang_arg: str) -> str:
    if lang_arg in {"en", "pt"}:
        return lang_arg

    if sys.stdin.isatty():
        choice = input(MESSAGES["en"]["prompt_lang"]).strip().lower()
        if choice in {"2", "pt", "portugues", "português", "p"}:
            return "pt"
        return "en"
    return "en"


def t(lang: str, key: str, **kwargs: str) -> str:
    template = MESSAGES.get(lang, MESSAGES["en"])[key]
    return template.format(**kwargs)


def ensure_mysql_connector(lang: str) -> None:
    global mysql, MySQLError
    if mysql is not None:
        return
    try:
        import mysql.connector as _mysql_connector  # type: ignore

        mysql = _mysql_connector
        MySQLError = _mysql_connector.Error
        return
    except Exception:
        pass

    print(t(lang, "connector_missing"), file=sys.stderr)
    import subprocess

    proc = subprocess.run(
        [sys.executable, "-m", "pip", "install", "mysql-connector-python"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print(proc.stdout, file=sys.stderr)
        raise RuntimeError(t(lang, "connector_install_fail"))

    import mysql.connector as _mysql_connector  # type: ignore

    mysql = _mysql_connector
    MySQLError = _mysql_connector.Error


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="TravelerCompanion SQL migrator")
    p.add_argument("--db-host", default="127.0.0.1")
    p.add_argument("--db-port", default=3306, type=int)
    p.add_argument("--db-user", default="rathena")
    p.add_argument("--db-pass", default="")
    p.add_argument("--db-name", default="ragnarok")
    p.add_argument("--mode", choices=["auto", "fresh", "migrate"], default="auto")
    p.add_argument("--lang", choices=["auto", "en", "pt"], default="auto")
    p.add_argument("--no-prompt", action="store_true", help="Disable interactive prompts")
    tools = p.add_mutually_exclusive_group()
    tools.add_argument("--apply-tools", dest="apply_tools", action="store_true")
    tools.add_argument("--skip-tools", dest="apply_tools", action="store_false")
    p.set_defaults(apply_tools=None)
    p.add_argument("--emit-sql", default="", help="Write processed SQL bundle for GUI tools (e.g. HeidiSQL)")
    return p.parse_args()


def parse_manifest(path: Path, lang: str) -> List[MigrationEntry]:
    entries: List[MigrationEntry] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|", 2)
        if len(parts) < 2:
            raise RuntimeError(t(lang, "manifest_invalid", line=raw))
        entries.append(MigrationEntry(order=parts[0], relative=parts[1]))
    return entries


def split_sql_with_delimiters(sql_text: str) -> Iterable[str]:
    delimiter = ";"
    buff: List[str] = []

    for line in sql_text.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("DELIMITER "):
            pending = "\n".join(buff).strip()
            if pending:
                yield pending
            buff = []
            delimiter = stripped.split(None, 1)[1]
            continue

        buff.append(line)
        joined = "\n".join(buff)
        if joined.rstrip().endswith(delimiter):
            stmt = joined.rstrip()
            stmt = stmt[: -len(delimiter)].strip()
            if stmt:
                yield stmt
            buff = []

    trailing = "\n".join(buff).strip()
    if trailing:
        yield trailing


def preprocess_sql(sql_text: str, mode: str) -> str:
    out = sql_text

    if mode == "fresh":
        alter_regex = re.compile(r"(?is)ALTER\s+TABLE\s+`[^`]+`\s+.*?;")

        def _replace(match: re.Match[str]) -> str:
            block = match.group(0)
            if (
                re.search(r"(?im)^\s*ALTER\s+TABLE", block)
                and re.search(r"(?im)\bIF\s+NOT\s+EXISTS\b", block)
                and not re.search(r"(?im)\bALTER\s+COLUMN\b", block)
            ):
                return "-- skipped in fresh mode (already covered by CREATE TABLE)\n"
            return block

        out = alter_regex.sub(_replace, out)

    out = re.sub(r"(?im)(ADD\s+COLUMN\s+)IF\s+NOT\s+EXISTS\s+", r"\1", out)
    out = re.sub(r"(?im)(ADD\s+INDEX\s+)IF\s+NOT\s+EXISTS\s+", r"\1", out)
    out = re.sub(r"(?im)(ADD\s+KEY\s+)IF\s+NOT\s+EXISTS\s+", r"\1", out)
    out = re.sub(r"(?im)(ADD\s+UNIQUE\s+KEY\s+)IF\s+NOT\s+EXISTS\s+", r"\1", out)

    return out


def connect_db(args: argparse.Namespace):
    return mysql.connect(
        host=args.db_host,
        port=args.db_port,
        user=args.db_user,
        password=args.db_pass,
        database=args.db_name,
        autocommit=False,
    )


def ensure_migration_table(conn) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tc_schema_migrations (
          id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
          migration_key VARCHAR(255) NOT NULL,
          checksum CHAR(64) NOT NULL,
          applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          UNIQUE KEY uk_tc_schema_migrations_key_checksum (migration_key, checksum)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    conn.commit()
    cur.close()


def has_existing_ml_tables(conn) -> bool:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = DATABASE() AND table_name LIKE 'ml\\_%'
        """
    )
    (count,) = cur.fetchone()
    cur.close()
    return int(count) > 0


def detect_mariadb(conn) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT VERSION()")
    (version,) = cur.fetchone()
    cur.close()
    return "mariadb" in str(version).lower()


def already_applied(conn, key: str, checksum: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM tc_schema_migrations WHERE migration_key=%s AND checksum=%s LIMIT 1",
        (key, checksum),
    )
    found = cur.fetchone() is not None
    cur.close()
    return found


def mark_applied(conn, key: str, checksum: str) -> None:
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO tc_schema_migrations (migration_key, checksum) VALUES (%s, %s)",
        (key, checksum),
    )
    conn.commit()
    cur.close()


def apply_sql(conn, label: str, migration_key: str, sql_text: str, checksum: str, lang: str) -> None:
    cur = conn.cursor()
    try:
        for stmt in split_sql_with_delimiters(sql_text):
            try:
                cur.execute(stmt)
                if getattr(cur, "with_rows", False):
                    cur.fetchall()
                while cur.nextset():
                    if getattr(cur, "with_rows", False):
                        cur.fetchall()
            except MySQLError as exc:
                if exc.errno in TOLERATED_CODES:
                    continue
                conn.rollback()
                print(t(lang, "apply_error", label=label, migration_key=migration_key, error=str(exc)), file=sys.stderr)
                raise
        conn.commit()
        mark_applied(conn, migration_key, checksum)
        print(t(lang, "applied", label=label, migration_key=migration_key))
    finally:
        cur.close()


def verify(conn, apply_tools: bool, lang: str) -> None:
    required_tables = [
        "ml_telemetry",
        "ml_advice",
        "ml_market_log",
        "ml_chat_log",
        "ml_challenges",
    ]
    cur = conn.cursor()
    for table in required_tables:
        cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name=%s", (table,))
        (count,) = cur.fetchone()
        if int(count) == 0:
            raise RuntimeError(t(lang, "missing_table", name=table))

    if apply_tools:
        for proc in [
            "sp_ml_telemetry_housekeeping",
            "sp_ml_market_housekeeping",
            "sp_ml_chat_housekeeping",
        ]:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.routines WHERE routine_schema = DATABASE() AND routine_type='PROCEDURE' AND routine_name=%s",
                (proc,),
            )
            (count,) = cur.fetchone()
            if int(count) == 0:
                raise RuntimeError(t(lang, "missing_proc", name=proc))

    cur.close()


def decide_apply_tools(args: argparse.Namespace, lang: str) -> bool:
    if args.apply_tools is not None:
        return bool(args.apply_tools)

    if args.no_prompt or not sys.stdin.isatty():
        return False

    reply = input(t(lang, "prompt_tools")).strip().lower()
    if lang == "pt":
        return reply in {"s", "sim", "y", "yes"}
    return reply in {"y", "yes", "s", "sim"}


def main() -> int:
    args = parse_args()
    lang = pick_language(args.lang)
    ensure_mysql_connector(lang)

    root = Path(__file__).resolve().parent.parent
    manifest = root / "sql-files" / "MIGRATIONS.manifest"
    if not manifest.exists():
        print(t(lang, "manifest_missing", path=str(manifest)), file=sys.stderr)
        return 1

    entries = parse_manifest(manifest, lang)
    tool_entries = [
        MigrationEntry(order="tool-1", relative="tools/ml_telemetry_housekeeping.sql"),
        MigrationEntry(order="tool-2", relative="tools/ml_market_chat_housekeeping.sql"),
    ]

    apply_tools = decide_apply_tools(args, lang)
    print(t(lang, "tools_enabled" if apply_tools else "tools_disabled"))

    conn = connect_db(args)
    try:
        ensure_migration_table(conn)
        is_mariadb = detect_mariadb(conn)
        mode = args.mode
        if mode == "auto":
            mode = "migrate" if has_existing_ml_tables(conn) else "fresh"

        print(t(lang, "db_engine", engine=("MariaDB" if is_mariadb else "MySQL")))
        print(t(lang, "schema_mode", mode=mode))

        bundle_parts: List[str] = []

        for entry in entries + (tool_entries if apply_tools else []):
            sql_path = root / "sql-files" / entry.relative
            if not sql_path.exists():
                raise RuntimeError(t(lang, "missing_sql", path=str(sql_path)))
            raw = sql_path.read_text(encoding="utf-8")
            processed = preprocess_sql(raw, mode if entry.order.isdigit() else "migrate")
            checksum = hashlib.sha256(processed.encode("utf-8")).hexdigest()
            key = entry.relative

            if already_applied(conn, key, checksum):
                print(t(lang, "skipped", label=entry.order, migration_key=entry.relative))
                continue

            apply_sql(conn, entry.order, key, processed, checksum, lang)
            bundle_parts.append(f"-- >>> {entry.relative}\n{processed}\n")

        if args.emit_sql:
            out = Path(args.emit_sql)
            out.write_text("\n".join(bundle_parts), encoding="utf-8")
            print(t(lang, "bundle_written", path=str(out)))

        verify(conn, apply_tools, lang)
        print(t(lang, "verification_ok"))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
