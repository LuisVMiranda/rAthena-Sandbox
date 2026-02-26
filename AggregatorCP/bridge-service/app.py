from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

mysql = None


@dataclass
class DBConfig:
    host: str = os.environ.get("TC_BRIDGE_DB_HOST", os.environ.get("TC_DB_HOST", "127.0.0.1"))
    port: int = int(os.environ.get("TC_BRIDGE_DB_PORT", os.environ.get("TC_DB_PORT", "3306")))
    user: str = os.environ.get("TC_BRIDGE_DB_USER", os.environ.get("TC_DB_USER", "rathena"))
    password: str = os.environ.get("TC_BRIDGE_DB_PASSWORD", os.environ.get("TC_DB_PASSWORD", ""))
    database: str = os.environ.get("TC_BRIDGE_DB_NAME", os.environ.get("TC_DB_NAME", "ragnarok"))


class BridgePayload(BaseModel):
    actionId: str = Field(min_length=8, max_length=64)
    gmCommand: str
    targetCharacterId: int = Field(gt=0)
    reason: str = ""
    reasonMode: str = "log"
    durationValue: int = 0
    durationUnit: str = "none"
    requestedBy: str = "companion-service"


def ensure_mysql_connector() -> None:
    global mysql
    if mysql is not None:
        return
    import mysql.connector as _mysql_connector  # type: ignore

    mysql = _mysql_connector


def db_connect(cfg: DBConfig):
    ensure_mysql_connector()
    return mysql.connect(host=cfg.host, port=cfg.port, user=cfg.user, password=cfg.password, database=cfg.database, autocommit=False)


def ensure_queue_table(cfg: DBConfig) -> None:
    conn = db_connect(cfg)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS acp_gm_command_queue (
              id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
              action_id VARCHAR(64) NOT NULL,
              created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              gm_command VARCHAR(24) NOT NULL,
              target_char_id INT UNSIGNED NOT NULL,
              reason VARCHAR(255) NULL,
              reason_mode VARCHAR(16) NOT NULL DEFAULT 'log',
              duration_value INT UNSIGNED NOT NULL DEFAULT 0,
              duration_unit VARCHAR(16) NOT NULL DEFAULT 'none',
              requested_by VARCHAR(64) NULL,
              status VARCHAR(24) NOT NULL DEFAULT 'pending',
              attempts SMALLINT UNSIGNED NOT NULL DEFAULT 0,
              last_error TEXT NULL,
              applied_at DATETIME NULL,
              PRIMARY KEY (id),
              UNIQUE KEY uk_acp_gm_command_queue_action (action_id),
              KEY idx_acp_gm_command_queue_status_created (status, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        ensure_column(cur, "acp_gm_command_queue", "reason_mode", "`reason_mode` VARCHAR(16) NOT NULL DEFAULT 'log'")
        ensure_column(cur, "acp_gm_command_queue", "duration_value", "`duration_value` INT UNSIGNED NOT NULL DEFAULT 0")
        ensure_column(cur, "acp_gm_command_queue", "duration_unit", "`duration_unit` VARCHAR(16) NOT NULL DEFAULT 'none'")

        conn.commit()
        cur.close()
    finally:
        conn.close()




def ensure_column(cur, table_name: str, column_name: str, ddl_fragment: str) -> None:
    cur.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name=%s AND column_name=%s
        """,
        (table_name, column_name),
    )
    row = cur.fetchone()
    exists = int(row[0] if row else 0) > 0
    if not exists:
        cur.execute(f"ALTER TABLE `{table_name}` ADD COLUMN {ddl_fragment}")

def verify_signature(secret: str, body: bytes, provided_sig: str) -> bool:
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, (provided_sig or "").strip())


app = FastAPI(title="AggregatorCP Bridge Service", version="0.2.0")


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"ok": True, "service": "bridge-service"}


@app.post("/bridge/admin-action")
async def bridge_admin_action(req: Request, x_bridge_signature: str = Header(default="", alias="X-Bridge-Signature")) -> dict[str, Any]:
    secret = os.environ.get("TC_BRIDGE_SHARED_SECRET", "").strip()
    require_sig = os.environ.get("TC_BRIDGE_REQUIRE_SIGNATURE", "1") != "0"
    dry_run = os.environ.get("TC_BRIDGE_DRY_RUN", "0") == "1"

    if require_sig and not secret:
        raise HTTPException(status_code=500, detail="TC_BRIDGE_SHARED_SECRET not configured")

    body = await req.body()
    if require_sig and not verify_signature(secret, body, x_bridge_signature):
        raise HTTPException(status_code=401, detail="Invalid bridge signature")

    try:
        payload = BridgePayload.model_validate_json(body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid payload: {exc}") from exc

    if payload.gmCommand not in {"@mute", "@kick", "@ban"}:
        raise HTTPException(status_code=400, detail="gmCommand must be @mute, @kick, or @ban")
    if payload.reasonMode not in {"log", "notify"}:
        raise HTTPException(status_code=400, detail="reasonMode must be log or notify")

    if dry_run:
        return {"ok": True, "queued": False, "message": "Dry-run mode active; payload validated.", "actionId": payload.actionId}

    cfg = DBConfig()
    ensure_queue_table(cfg)

    conn = db_connect(cfg)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO acp_gm_command_queue (action_id, gm_command, target_char_id, reason, reason_mode, duration_value, duration_unit, requested_by, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending')
            ON DUPLICATE KEY UPDATE
              reason=VALUES(reason),
              reason_mode=VALUES(reason_mode),
              duration_value=VALUES(duration_value),
              duration_unit=VALUES(duration_unit),
              requested_by=VALUES(requested_by),
              status=IF(status='applied', status, 'pending')
            """,
            (
                payload.actionId,
                payload.gmCommand,
                payload.targetCharacterId,
                payload.reason[:255],
                payload.reasonMode,
                max(0, int(payload.durationValue)),
                payload.durationUnit[:16],
                payload.requestedBy[:64],
            ),
        )
        conn.commit()
        cur.close()
        return {"ok": True, "queued": True, "actionId": payload.actionId}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        conn.close()
