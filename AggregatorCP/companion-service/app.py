from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import socket
import time
from datetime import datetime
import urllib.request
import urllib.parse
import urllib.error
import uuid
import platform
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from db_access import ActionsRepository, LogsRepository

mysql = None

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = Path(os.environ.get("TC_COMPANION_CONFIG", DATA_DIR / "config.json"))
AUTH_PATH = Path(os.environ.get("TC_COMPANION_AUTH", DATA_DIR / "auth.json"))


TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "decision_invalid": "decision must be one of: mute, unmute, ban, kick, unflag, jail, unjail, unban",
        "reason_mode_invalid": "reason_mode must be log or notify",
        "unban_requires_account": "Unban requires valid account_id (from selected character).",
        "unban_applied": "Unban applied for account_id={account_id}. Rows updated: {changed}.",
        "unflag_applied": "Unflag applied. Removed {removed} rows.",
        "dispatched": "{decision} dispatched to bridge.",
        "fallback_wait": "Action enqueued to game queue fallback. It will apply when in-game bridge executor consumes acp_gm_command_queue.",
        "bridge_not_configured_and_failed": "Bridge not configured and local fallback failed: {error}",
        "bridge_failed": "Queued locally; bridge dispatch failed: {error}",
        "active": "Active",
        "inactive": "Inactive",
    },
    "pt-BR": {
        "decision_invalid": "decisão deve ser: mute, unmute, ban, kick, unflag, jail, unjail, unban",
        "reason_mode_invalid": "reason_mode deve ser log ou notify",
        "unban_requires_account": "Unban requer account_id válido (do personagem selecionado).",
        "unban_applied": "Unban aplicado para account_id={account_id}. Linhas atualizadas: {changed}.",
        "unflag_applied": "Unflag aplicado. {removed} linhas removidas.",
        "dispatched": "{decision} enviado para a bridge.",
        "fallback_wait": "Ação enfileirada no fallback local. Será aplicada quando o executor in-game consumir acp_gm_command_queue.",
        "bridge_not_configured_and_failed": "Bridge não configurada e fallback local falhou: {error}",
        "bridge_failed": "Enfileirado localmente; envio da bridge falhou: {error}",
        "active": "Ativo",
        "inactive": "Inativo",
    },
    "es": {
        "active": "Activo",
        "inactive": "Inactivo",
    },
    "fr": {
        "active": "Actif",
        "inactive": "Inactif",
    },
    "de": {
        "active": "Aktiv",
        "inactive": "Inaktiv",
    },
    "tl": {
        "active": "Aktibo",
        "inactive": "Hindi aktibo",
    },
}


ROLE_PRESETS: dict[str, dict[str, bool]] = {
    "community_manager": {
        "view_logs": True,
        "search_logs": True,
        "view_players": True,
        "apply_punishments": False,
        "manage_config": False,
        "manage_webhooks": False,
        "manage_roles": False,
        "view_watch": True,
        "manage_watch": False,
    },
    "game_master": {
        "view_logs": True,
        "search_logs": True,
        "view_players": True,
        "apply_punishments": True,
        "manage_config": False,
        "manage_webhooks": False,
        "manage_roles": False,
        "view_watch": True,
        "manage_watch": False,
    },
    "administrator": {
        "view_logs": True,
        "search_logs": True,
        "view_players": True,
        "apply_punishments": True,
        "manage_config": True,
        "manage_webhooks": True,
        "manage_roles": True,
        "view_watch": True,
        "manage_watch": True,
    },
}


def _auth_normalized(raw: dict[str, Any]) -> dict[str, Any]:
    users = raw.get("users")
    role_permissions = raw.get("role_permissions")
    if isinstance(users, list):
        norm_users = []
        for u in users:
            if not isinstance(u, dict):
                continue
            email = str(u.get("email", "")).strip().lower()
            if not email:
                continue
            role = str(u.get("role", "community_manager")).strip().lower()
            if role not in ROLE_PRESETS:
                role = "community_manager"
            norm_users.append(
                {
                    "email": email,
                    "salt": str(u.get("salt", "")),
                    "password_hash": str(u.get("password_hash", "")),
                    "role": role,
                    "active": bool(u.get("active", True)),
                }
            )
        if not norm_users:
            raise RuntimeError("No valid users configured")
        rp = ROLE_PRESETS.copy()
        if isinstance(role_permissions, dict):
            merged = {}
            for r, preset in ROLE_PRESETS.items():
                src = role_permissions.get(r, {}) if isinstance(role_permissions.get(r), dict) else {}
                merged[r] = {k: bool(src.get(k, v)) for k, v in preset.items()}
            rp = merged
        return {"version": 2, "users": norm_users, "role_permissions": rp}

    # legacy single-user migration
    email = str(raw.get("email", "admin@travelercompanion.com")).strip().lower()
    salt = str(raw.get("salt", ""))
    password_hash = str(raw.get("password_hash", ""))
    return {
        "version": 2,
        "users": [
            {
                "email": email,
                "salt": salt,
                "password_hash": password_hash,
                "role": "administrator",
                "active": True,
            }
        ],
        "role_permissions": ROLE_PRESETS.copy(),
    }


def _permissions_for_role(auth_data: dict[str, Any], role: str) -> dict[str, bool]:
    rp = auth_data.get("role_permissions", {})
    base = ROLE_PRESETS.get(role, ROLE_PRESETS["community_manager"])
    src = rp.get(role, {}) if isinstance(rp, dict) and isinstance(rp.get(role), dict) else {}
    return {k: bool(src.get(k, v)) for k, v in base.items()}


def _current_user(request: Request) -> dict[str, Any]:
    token = request.headers.get("Authorization", "").split(" ", 1)[1]
    return dict(app.state.tokens.get(token, {}))


def _require_permission(request: Request, permission: str) -> dict[str, Any]:
    user = _current_user(request)
    if not bool(user.get("permissions", {}).get(permission, False)):
        raise HTTPException(status_code=403, detail=f"Forbidden: missing permission '{permission}'")
    return user


def _lang_from_request(request: Request | None = None, fallback: str = "en") -> str:
    if request is None:
        return fallback
    raw = (request.headers.get("X-TC-Lang") or request.query_params.get("lang") or request.headers.get("Accept-Language") or fallback).strip()
    if not raw:
        return fallback
    lang = raw.split(",", 1)[0].split(";", 1)[0].strip()
    if lang in TRANSLATIONS:
        return lang
    if "-" in lang:
        base = lang.split("-", 1)[0]
        if base in TRANSLATIONS:
            return base
    return fallback


def tr_msg(lang: str, key: str, **kwargs: Any) -> str:
    table = TRANSLATIONS.get(lang) or TRANSLATIONS.get("en", {})
    base = table.get(key) or TRANSLATIONS.get("en", {}).get(key) or key
    try:
        return base.format(**kwargs)
    except Exception:
        return base


@dataclass
class DBConfig:
    host: str = "127.0.0.1"
    port: int = 3306
    user: str = "rathena"
    password: str = ""
    database: str = "ragnarok"
    logs_database: str = "log"


@dataclass
class AIConfig:
    lookback_hours: int = 48
    bucket_minutes: int = 60
    min_observations: int = 12
    telemetry_retention_days: int = 30
    market_retention_days: int = 30
    chat_retention_days: int = 14


@dataclass
class WebhookConfig:
    discord_url: str = ""
    telegram_url: str = ""
    notify_flagged_chars: bool = True
    notify_infra_down: bool = True
    notify_market_risk: bool = False
    notify_character_punishments: bool = True


@dataclass
class ProxyConfig:
    name: str = "Proxy"
    country_name: str = "Unknown"
    country_emoji: str = "🌐"
    host: str = "127.0.0.1"
    port: int = 0


@dataclass
class AppConfig:
    db: DBConfig
    ai: AIConfig
    webhooks: WebhookConfig
    schedule_market_minutes: int = 60
    schedule_housekeeping_minutes: int = 360
    schedule_telemetry_minutes: int = 30
    status_refresh_seconds: int = 300
    offline_notify_seconds: int = 300
    usage_refresh_seconds: int = 5
    login_server_port: int = 6900
    char_server_port: int = 6121
    map_server_port: int = 5121
    web_server_port: int = 8888
    app_host: str = "127.0.0.1"
    proxies: list[ProxyConfig] = field(default_factory=list)


class DBConfigIn(BaseModel):
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=3306)
    user: str = Field(default="rathena")
    password: str = Field(default="")
    database: str = Field(default="ragnarok")
    logs_database: str = Field(default="log")


class AIConfigIn(BaseModel):
    lookback_hours: int = Field(default=48, ge=1, le=720)
    bucket_minutes: int = Field(default=60, ge=1, le=240)
    min_observations: int = Field(default=12, ge=1, le=1000)
    telemetry_retention_days: int = Field(default=30, ge=1, le=3650)
    market_retention_days: int = Field(default=30, ge=1, le=3650)
    chat_retention_days: int = Field(default=14, ge=1, le=3650)


class WebhookConfigIn(BaseModel):
    discord_url: str = ""
    telegram_url: str = ""
    notify_flagged_chars: bool = True
    notify_infra_down: bool = True
    notify_market_risk: bool = False
    notify_character_punishments: bool = True


class ProxyConfigIn(BaseModel):
    name: str = Field(default="Proxy")
    country_name: str = Field(default="Unknown")
    country_emoji: str = Field(default="🌐")
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=0, ge=0, le=65535)


class AppConfigIn(BaseModel):
    db: DBConfigIn
    ai: AIConfigIn
    webhooks: WebhookConfigIn
    schedule_market_minutes: int = Field(default=60, ge=1, le=10080)
    schedule_housekeeping_minutes: int = Field(default=360, ge=1, le=10080)
    schedule_telemetry_minutes: int = Field(default=30, ge=1, le=10080)
    status_refresh_seconds: int = Field(default=300, ge=5, le=3600)
    offline_notify_seconds: int = Field(default=300, ge=5, le=3600)
    usage_refresh_seconds: int = Field(default=5, ge=1, le=300)
    login_server_port: int = Field(default=6900, ge=1, le=65535)
    char_server_port: int = Field(default=6121, ge=1, le=65535)
    map_server_port: int = Field(default=5121, ge=1, le=65535)
    web_server_port: int = Field(default=8888, ge=1, le=65535)
    app_host: str = Field(default="127.0.0.1")
    proxies: list[ProxyConfigIn] = Field(default_factory=list)


class DecisionIn(BaseModel):
    char_id: int
    account_id: int = 0
    decision: str
    reason: str = ""
    reason_mode: str = Field(default="log")
    duration_value: int = 0


class BulkDecisionIn(BaseModel):
    targets: list[DecisionIn] = Field(default_factory=list)


class WatchCaseIn(BaseModel):
    watch_type: str = Field(pattern="^(character|account|item)$")
    char_id: int = 0
    account_id: int = 0
    nameid: int = 0
    label: str = ""
    check_every_seconds: int = Field(default=300, ge=30, le=86400)
    severity: str = Field(default="medium")
    notify_discord: bool = True
    notify_telegram: bool = True
    enabled: bool = True
    auto_create_related: bool = False
    max_related_chars: int = Field(default=3, ge=1, le=20)
    monitor_any_change: bool = True
    monitor_item_movement: bool = False
    item_movement_threshold: int = Field(default=20, ge=1, le=1000000)
    monitor_failed_logins: bool = False
    failed_login_threshold: int = Field(default=5, ge=1, le=100000)
    monitor_zeny_increase: bool = False
    zeny_increase_threshold: int = Field(default=1000000, ge=1, le=2000000000)
    notes: str = ""


class IPCheckIn(BaseModel):
    query: str


class FlagDeleteIn(BaseModel):
    flag_id: int


def _picklog_type_label(code: str) -> str:
    mapping = {
        "T": "trade_with_player",
        "V": "player_store_purchase_or_sale",
        "S": "npc_store",
        "P": "from_floor",
        "L": "to_floor",
        "M": "from_monster",
        "N": "npc_script",
        "C": "consumable",
        "A": "admin_command",
        "E": "mail",
        "B": "buying_store",
        "X": "other",
    }
    return mapping.get((code or "").upper(), "unknown")


class LoginIn(BaseModel):
    email: str
    password: str


class ChangeEmailIn(BaseModel):
    current_email: str
    new_email: str
    confirm_email: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str


def ensure_mysql_connector() -> None:
    global mysql
    if mysql is not None:
        return
    import mysql.connector as _mysql_connector  # type: ignore

    mysql = _mysql_connector


def default_config() -> AppConfig:
    return AppConfig(db=DBConfig(), ai=AIConfig(), webhooks=WebhookConfig())


def load_config() -> AppConfig:
    if not CONFIG_PATH.exists():
        cfg = default_config()
        save_config(cfg)
        return cfg
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    webhook_raw = data.get("webhooks", {})
    if not isinstance(webhook_raw, dict):
        webhook_raw = {}
    webhook_migrated = dict(webhook_raw)
    webhook_migrated["notify_infra_down"] = bool(
        webhook_raw.get("notify_infra_down", webhook_raw.get("notify_map_server_down", True))
    )
    webhook_migrated.pop("notify_map_server_down", None)
    webhook_migrated = {
        "discord_url": str(webhook_migrated.get("discord_url", "")),
        "telegram_url": str(webhook_migrated.get("telegram_url", "")),
        "notify_flagged_chars": bool(webhook_migrated.get("notify_flagged_chars", True)),
        "notify_infra_down": bool(webhook_migrated.get("notify_infra_down", True)),
        "notify_market_risk": bool(webhook_migrated.get("notify_market_risk", False)),
        "notify_character_punishments": bool(webhook_migrated.get("notify_character_punishments", True)),
    }

    return AppConfig(
        db=DBConfig(**data.get("db", {})),
        ai=AIConfig(**data.get("ai", {})),
        webhooks=WebhookConfig(**webhook_migrated),
        schedule_market_minutes=int(data.get("schedule_market_minutes", 60)),
        schedule_housekeeping_minutes=int(data.get("schedule_housekeeping_minutes", 360)),
        schedule_telemetry_minutes=int(data.get("schedule_telemetry_minutes", 30)),
        status_refresh_seconds=int(data.get("status_refresh_seconds", 300)),
        offline_notify_seconds=int(data.get("offline_notify_seconds", 300)),
        usage_refresh_seconds=int(data.get("usage_refresh_seconds", 5)),
        login_server_port=int(data.get("login_server_port", 6900)),
        char_server_port=int(data.get("char_server_port", 6121)),
        map_server_port=int(data.get("map_server_port", 5121)),
        web_server_port=int(data.get("web_server_port", 8888)),
        app_host=str(data.get("app_host", "127.0.0.1")),
        proxies=[ProxyConfig(**x) for x in data.get("proxies", []) if isinstance(x, dict)],
    )


def save_config(cfg: AppConfig) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def ensure_default_auth() -> None:
    if AUTH_PATH.exists():
        return
    salt = secrets.token_hex(16)
    payload = {
        "version": 2,
        "users": [
            {
                "email": "admin@travelercompanion.com",
                "salt": salt,
                "password_hash": _hash_password("admin123", salt),
                "role": "administrator",
                "active": True,
            }
        ],
        "role_permissions": ROLE_PRESETS.copy(),
    }
    AUTH_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_auth() -> dict[str, Any]:
    ensure_default_auth()
    raw = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
    normalized = _auth_normalized(raw)
    if raw != normalized:
        save_auth(normalized)
    return normalized


def save_auth(payload: dict[str, Any]) -> None:
    AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUTH_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def db_connect(cfg: AppConfig, database: str | None = None):
    ensure_mysql_connector()
    db_name = (database or "").strip() or cfg.db.database
    return mysql.connect(
        host=cfg.db.host,
        port=cfg.db.port,
        user=cfg.db.user,
        password=cfg.db.password,
        database=db_name,
        autocommit=False,
    )


def db_connect_logs(cfg: AppConfig):
    return db_connect(cfg, cfg.db.logs_database)


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

def table_exists(cur, table_name: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) AS c FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name=%s",
        (table_name,),
    )
    row = cur.fetchone()
    if isinstance(row, dict):
        return int(row.get("c", 0)) > 0
    return int(row[0] if row else 0) > 0


def table_columns(cur, table_name: str) -> set[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name=%s
        """,
        (table_name,),
    )
    rows = cur.fetchall() or []
    cols: set[str] = set()
    for row in rows:
        if isinstance(row, dict):
            cols.add(str(row.get("column_name") or "").lower())
        else:
            cols.add(str(row[0] if row else "").lower())
    return cols


def check_port(host: str, port: int, timeout: float = 0.7) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def check_port_latency(host: str, port: int, timeout: float = 0.7) -> tuple[bool, int | None]:
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            latency = int((time.perf_counter() - started) * 1000)
            return True, latency
    except Exception:
        return False, None


def collect_status(cfg: AppConfig) -> dict[str, Any]:
    db_ok = False
    db_latency_ms = 0
    err = ""
    try:
        started = time.perf_counter()
        conn = db_connect(cfg)
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
        conn.close()
        db_latency_ms = int((time.perf_counter() - started) * 1000)
        db_ok = True
    except Exception as exc:
        err = str(exc)

    scheduler_running = bool(getattr(app.state, "scheduler", None))
    overload_percent = max(0, min(100, int((db_latency_ms / 2000) * 100))) if db_ok else 100

    ports = {
        "login-server": check_port(cfg.app_host, int(cfg.login_server_port)),
        "char-server": check_port(cfg.app_host, int(cfg.char_server_port)),
        "map-server": check_port(cfg.app_host, int(cfg.map_server_port)),
        "web-server": check_port(cfg.app_host, int(cfg.web_server_port)),
        "database": check_port(cfg.db.host, int(cfg.db.port)),
    }
    proxy_rows = []
    for idx, proxy in enumerate(cfg.proxies):
        pname = (proxy.name or f"proxy-{idx+1}").strip()
        pport = int(proxy.port or 0)
        if pport > 0:
            online, latency_ms = check_port_latency(proxy.host, pport)
        else:
            online, latency_ms = False, None
        ports[f"proxy:{pname}"] = online
        proxy_rows.append({"name": pname, "host": proxy.host, "port": pport, "country_name": proxy.country_name, "country_emoji": proxy.country_emoji, "online": online, "latency_ms": latency_ms})

    return {
        "db_ok": db_ok,
        "db_latency_ms": db_latency_ms,
        "scheduler_running": scheduler_running,
        "overload_percent": overload_percent,
        "ports": ports,
        "error": err,
        "ts": int(time.time()),
        "app_host": cfg.app_host,
        "db_host": cfg.db.host,
        "proxies": proxy_rows,
    }


def _send_offline_status_webhook(cfg: AppConfig, status_payload: dict[str, Any]) -> dict[str, Any]:
    ports = status_payload.get("ports", {}) or {}
    offline = sorted([name for name, ok in ports.items() if not bool(ok)])
    if not bool(status_payload.get("db_ok", False)):
        offline.append("database_query")

    if not offline:
        app.state.last_offline_signature_discord = ""
        app.state.last_offline_signature_telegram = ""
        return {"sent": False, "reason": "all_systems_online", "offline": []}

    if not cfg.webhooks.notify_infra_down:
        return {"sent": False, "reason": "notifications_disabled", "offline": offline}

    signature = "|".join(sorted(set(offline)))
    payload = {
        "event": "system_offline",
        "ts": status_payload.get("ts"),
        "offline_systems": offline,
        "db_ok": status_payload.get("db_ok"),
        "db_latency_ms": status_payload.get("db_latency_ms"),
        "ports": ports,
        "error": status_payload.get("error", ""),
    }
    formatted = []
    for name in offline:
        label = str(name)
        if label.startswith("proxy:"):
            label = label.replace("proxy:", "proxy: ", 1)
            formatted.append(f"🌍 {label}")
        elif label == "database_query":
            formatted.append("🗄️ database query")
        elif "database" in label:
            formatted.append(f"🗄️ {label}")
        elif "web-server" in label:
            formatted.append(f"🕸️ {label}")
        else:
            formatted.append(f"🔌 {label}")
    ts = status_payload.get("ts")
    ts_readable = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S") if ts else "unknown"
    text = (
        "⚠️ Aggregator Control Panel: App/Proxy offline detected\n"
        "```\n"
        + "Components offline:\n"
        + "\n".join(f"- {x}" for x in formatted)
        + "\n\n"
        + f"🗄️ DB OK      : {status_payload.get('db_ok')}\n"
        + f"⏱️ DB Latency : {status_payload.get('db_latency_ms')} ms\n"
        + f"🕒 Timestamp  : {ts_readable}\n"
        + "```"
    )


    results: dict[str, Any] = {"sent": False, "offline": offline}

    if cfg.webhooks.discord_url:
        last_sig = getattr(app.state, "last_offline_signature_discord", "")
        if signature != last_sig:
            discord_url = _sanitize_discord_url(cfg.webhooks.discord_url)
            discord_payload = {"content": text, "username": "AggregatorCP", "allowed_mentions": {"parse": []}}
            ok, msg = _send_webhook(discord_url, discord_payload if _is_discord_webhook(discord_url) else payload)
            results["discord"] = {"ok": ok, "detail": msg}
            if ok:
                app.state.last_offline_signature_discord = signature
            results["sent"] = results["sent"] or ok

    if cfg.webhooks.telegram_url:
        last_sig = getattr(app.state, "last_offline_signature_telegram", "")
        if signature != last_sig:
            ok, msg = _send_webhook(cfg.webhooks.telegram_url, {**payload, "text": text})
            results["telegram"] = {"ok": ok, "detail": msg}
            if ok:
                app.state.last_offline_signature_telegram = signature
            results["sent"] = results["sent"] or ok

    if not any(k in results for k in ("discord", "telegram")):
        results["reason"] = "no_webhook_configured"
    elif not results.get("sent") and "reason" not in results:
        results["reason"] = "state_unchanged_or_delivery_failed"

    return results


def collect_system_usage() -> dict[str, Any]:
    cpu_percent = 0.0
    memory_percent = 0.0
    memory_used_mb = 0
    memory_total_mb = 0
    try:
        import psutil  # type: ignore

        cpu_percent = float(psutil.cpu_percent(interval=None))
        vm = psutil.virtual_memory()
        memory_percent = float(vm.percent)
        memory_used_mb = int(vm.used / (1024 * 1024))
        memory_total_mb = int(vm.total / (1024 * 1024))
    except Exception:
        try:
            if hasattr(os, "getloadavg"):
                load1 = os.getloadavg()[0]
                cpus = os.cpu_count() or 1
                cpu_percent = max(0.0, min(100.0, (load1 / cpus) * 100.0))
        except Exception:
            cpu_percent = 0.0
        try:
            meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
            vals: dict[str, int] = {}
            for line in meminfo.splitlines():
                if ":" not in line:
                    continue
                k, rest = line.split(":", 1)
                num = int((rest.strip().split(" ")[0]) or 0)
                vals[k] = num
            total = vals.get("MemTotal", 0)
            avail = vals.get("MemAvailable", vals.get("MemFree", 0))
            used = max(0, total - avail)
            if total > 0:
                memory_percent = (used / total) * 100.0
                memory_used_mb = int((used / 1024))
                memory_total_mb = int((total / 1024))
        except Exception:
            memory_percent = 0.0

    return {
        "cpu_percent": round(cpu_percent, 2),
        "memory_percent": round(memory_percent, 2),
        "memory_used_mb": int(memory_used_mb),
        "memory_total_mb": int(memory_total_mb),
        "platform": platform.system().lower(),
        "ts": int(time.time()),
    }


def run_market_cycle(cfg: AppConfig) -> None:
    return


def run_telemetry_cycle(cfg: AppConfig) -> None:
    return


def run_housekeeping_cycle(cfg: AppConfig) -> None:
    conn = db_connect(cfg)
    try:
        cur = conn.cursor()
        cur.execute("CALL sp_ml_telemetry_housekeeping(%s, 5000, 100)", (cfg.ai.telemetry_retention_days,))
        while cur.nextset():
            pass
        cur.execute("CALL sp_ml_market_housekeeping(%s, 5000, 100)", (cfg.ai.market_retention_days,))
        while cur.nextset():
            pass
        cur.execute("CALL sp_ml_chat_housekeeping(%s, 5000, 100)", (cfg.ai.chat_retention_days,))
        while cur.nextset():
            pass
        conn.commit()
        cur.close()
    finally:
        conn.close()


def ensure_decisions_table(cfg: AppConfig) -> None:
    conn = db_connect(cfg)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS acp_admin_decisions (
              id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
              created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              char_id INT UNSIGNED NOT NULL,
              account_id INT UNSIGNED NOT NULL DEFAULT 0,
              decision VARCHAR(64) NOT NULL,
              reason VARCHAR(255) NULL,
              reason_mode VARCHAR(16) NOT NULL DEFAULT 'log',
              duration_value INT UNSIGNED NOT NULL DEFAULT 0,
              duration_unit VARCHAR(16) NOT NULL DEFAULT 'none',
              PRIMARY KEY (id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS acp_admin_action_queue (
              id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
              action_id VARCHAR(64) NOT NULL,
              created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              char_id INT UNSIGNED NOT NULL,
              account_id INT UNSIGNED NOT NULL DEFAULT 0,
              decision VARCHAR(32) NOT NULL,
              reason VARCHAR(255) NULL,
              reason_mode VARCHAR(16) NOT NULL DEFAULT 'log',
              duration_value INT UNSIGNED NOT NULL DEFAULT 0,
              duration_unit VARCHAR(16) NOT NULL DEFAULT 'none',
              status VARCHAR(32) NOT NULL DEFAULT 'queued',
              bridge_message TEXT NULL,
              PRIMARY KEY (id),
              UNIQUE KEY uk_acp_admin_action_queue_action (action_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

        ensure_column(cur, "acp_admin_decisions", "reason_mode", "`reason_mode` VARCHAR(16) NOT NULL DEFAULT 'log'")
        ensure_column(cur, "acp_admin_decisions", "duration_value", "`duration_value` INT UNSIGNED NOT NULL DEFAULT 0")
        ensure_column(cur, "acp_admin_decisions", "duration_unit", "`duration_unit` VARCHAR(16) NOT NULL DEFAULT 'none'")
        ensure_column(cur, "acp_admin_decisions", "account_id", "`account_id` INT UNSIGNED NOT NULL DEFAULT 0")

        ensure_column(cur, "acp_admin_action_queue", "reason_mode", "`reason_mode` VARCHAR(16) NOT NULL DEFAULT 'log'")
        ensure_column(cur, "acp_admin_action_queue", "duration_value", "`duration_value` INT UNSIGNED NOT NULL DEFAULT 0")
        ensure_column(cur, "acp_admin_action_queue", "duration_unit", "`duration_unit` VARCHAR(16) NOT NULL DEFAULT 'none'")
        ensure_column(cur, "acp_admin_action_queue", "account_id", "`account_id` INT UNSIGNED NOT NULL DEFAULT 0")

        conn.commit()
        cur.close()
    finally:
        conn.close()


def resolve_char_name(cfg: AppConfig, char_id: int) -> str:
    try:
        conn = db_connect(cfg)
        cur = conn.cursor()
        cur.execute("SELECT name FROM `char` WHERE char_id=%s LIMIT 1", (int(char_id),))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return str(row[0])
    except Exception:
        return "unknown"
    return "unknown"


def resolve_account_id(cfg: AppConfig, char_id: int) -> int:
    try:
        conn = db_connect(cfg)
        cur = conn.cursor()
        cur.execute("SELECT account_id FROM `char` WHERE char_id=%s LIMIT 1", (int(char_id),))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return int(row[0] or 0)
    except Exception:
        return 0
    return 0


def resolve_char_status(cfg: AppConfig, char_id: int) -> dict[str, Any]:
    out: dict[str, Any] = {"char_id": int(char_id), "name": "", "account_id": 0, "online": False}
    try:
        conn = db_connect(cfg)
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT char_id, account_id, name, online FROM `char` WHERE char_id=%s LIMIT 1", (int(char_id),))
        row = cur.fetchone() or {}
        cur.close()
        conn.close()
        if row:
            out["name"] = str(row.get("name") or "")
            out["account_id"] = int(row.get("account_id") or 0)
            out["online"] = bool(int(row.get("online") or 0))
    except Exception:
        pass
    return out


def _confidence_score(seed: dict[str, Any], candidate: dict[str, Any]) -> int:
    score = 0
    if (seed.get("last_ip") or "") and (seed.get("last_ip") == candidate.get("last_ip")):
        score += 60
    if (seed.get("email") or "") and (seed.get("email") == candidate.get("email")):
        score += 25
    if (seed.get("birthdate") or "") and (seed.get("birthdate") == candidate.get("birthdate")):
        score += 15
    return min(100, score)


def _flag_reason_context(reason: str, lang: str = "en") -> str:
    m = {
        "isolation_forest_account_window": "Anomaly score from account activity window; behavior diverges from baseline telemetry profile.",
        "rapid_map_transitions": "Unusually fast map transitions detected in a short time window.",
        "burst_kill_density": "High kill density detected compared with expected movement/engagement patterns.",
        "macro_like_repetition": "Highly repetitive action cadence suggests possible automation.",
    }
    key = (reason or "").strip().lower()
    base = m.get(key, "Review telemetry details and compare with normal play patterns for this account.")
    if lang == "pt-BR":
        return {
            "isolation_forest_account_window": "Pontuação de anomalia por janela de atividade da conta; comportamento fora do perfil esperado.",
            "rapid_map_transitions": "Transições de mapa incomumente rápidas em uma janela curta.",
            "burst_kill_density": "Alta densidade de abates em comparação ao padrão de movimento/combate.",
            "macro_like_repetition": "Cadência altamente repetitiva pode indicar automação.",
        }.get(key, "Revise a telemetria e compare com o padrão normal de jogo desta conta.")
    return base


def log_admin_action_submit(admin_identity: str, char_name: str, char_id: int, decision_name: str, duration_value: int, duration_unit: str) -> None:
    print(
        f"INFO AdminAction submit admin={admin_identity} char={char_name} char_id={char_id} punishment={decision_name} duration={duration_value} {duration_unit}"
    )


def bridge_dispatch(action_id: str, char_id: int, decision: str, reason: str, reason_mode: str, duration_value: int) -> tuple[bool, str]:
    endpoint = os.environ.get("TC_BRIDGE_ENDPOINT_URL", "").strip()
    secret = os.environ.get("TC_BRIDGE_SHARED_SECRET", "").strip()
    if not endpoint or not secret:
        return False, "Bridge not configured (set TC_BRIDGE_ENDPOINT_URL + TC_BRIDGE_SHARED_SECRET)."

    gm_map = {"mute": "@mute", "unmute": "@unmute", "ban": "@ban", "kick": "@kick", "jail": "@jail", "unjail": "@unjail"}
    gm_command = gm_map.get(decision)
    if not gm_command:
        return False, f"Unsupported decision for bridge: {decision}"

    unit = "minutes" if decision == "mute" else ("days" if decision == "ban" else "none")
    payload = {
        "actionId": action_id,
        "gmCommand": gm_command,
        "targetCharacterId": int(char_id),
        "reason": reason,
        "reasonMode": reason_mode,
        "durationValue": int(duration_value),
        "durationUnit": unit,
        "requestedBy": "companion-service",
    }
    body = json.dumps(payload, separators=(",", ":"))
    signature = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()

    req = urllib.request.Request(endpoint, data=body.encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Bridge-Signature", signature)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            msg = resp.read().decode("utf-8", errors="ignore")
            return 200 <= resp.status < 300, msg or f"HTTP {resp.status}"
    except Exception as exc:
        return False, str(exc)


def ensure_game_bridge_queue(cfg: AppConfig) -> None:
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
        cur.execute("UPDATE acp_gm_command_queue SET status='pending', last_error='auto-requeued stale processing row' WHERE status='processing' AND TIMESTAMPDIFF(SECOND, created_at, NOW()) > 120")
        conn.commit()
        cur.close()
    finally:
        conn.close()


def enqueue_local_bridge_action(cfg: AppConfig, action_id: str, char_id: int, decision: str, reason: str, reason_mode: str, duration_value: int) -> tuple[bool, str]:
    gm_map = {"mute": "@mute", "unmute": "@unmute", "ban": "@ban", "kick": "@kick", "jail": "@jail", "unjail": "@unjail"}
    gm_command = gm_map.get(decision)
    if not gm_command:
        return False, f"Unsupported decision for local bridge queue: {decision}"

    duration_unit = "minutes" if decision == "mute" else ("days" if decision == "ban" else "none")
    ensure_game_bridge_queue(cfg)

    conn = db_connect(cfg)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO acp_gm_command_queue (action_id, gm_command, target_char_id, reason, reason_mode, duration_value, duration_unit, requested_by, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'pending')
            ON DUPLICATE KEY UPDATE
              reason=VALUES(reason),
              reason_mode=VALUES(reason_mode),
              duration_value=VALUES(duration_value),
              duration_unit=VALUES(duration_unit),
              requested_by=VALUES(requested_by),
              status=IF(status='applied', status, 'pending')
            """,
            (action_id, gm_command, int(char_id), reason[:255], reason_mode, max(0, int(duration_value)), duration_unit, "companion-service-local"),
        )
        conn.commit()
        cur.close()
        return True, "Local queue fallback engaged (no bridge endpoint configured)."
    except Exception as exc:
        return False, str(exc)
    finally:
        conn.close()


def _send_webhook(url: str, payload: dict[str, Any]) -> tuple[bool, str]:
    if not url:
        return False, "empty webhook url"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "AggregatorCP/1.0")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return 200 <= resp.status < 300, f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="ignore")[:500]
        except Exception:
            detail = ""
        return False, f"HTTP {exc.code}: {detail or exc.reason}"
    except Exception as exc:
        return False, str(exc)


def _is_discord_webhook(url: str) -> bool:
    lowered = (url or "").lower()
    return "discord.com/api/webhooks/" in lowered or "discordapp.com/api/webhooks/" in lowered


def _sanitize_discord_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urllib.parse.urlsplit(raw)
    if not parsed.scheme or not parsed.netloc:
        return raw
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    query["wait"] = ["true"]
    new_query = urllib.parse.urlencode(query, doseq=True)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment))


def _send_punishment_webhooks(cfg: AppConfig, admin_email: str, char_name: str, char_id: int, account_id: int, decision_name: str, duration_value: int, duration_unit: str, reason: str) -> None:
    if decision_name not in {"mute", "unmute", "ban", "unban", "kick", "jail", "unjail"}:
        return
    if not cfg.webhooks.notify_character_punishments:
        return
    online_status = "Unknown"
    try:
        st = resolve_char_status(cfg, int(char_id))
        if st.get("online") is True:
            online_status = "Online"
        elif st.get("online") is False:
            online_status = "Offline"
    except Exception:
        online_status = "Unknown"

    safe_reason = (reason or "").strip() or "N/A"
    status_emoji = "🟢" if online_status == "Online" else ("⚫" if online_status == "Offline" else "⚪")
    text = (
        "```\n"
        "🤖 AggregatorCP - Character Punishment\n"
        f"👮 Admin: {admin_email}\n"
        f"⚖️ Action: {decision_name.upper()}\n"
        f"👤 Character: {char_name or 'Unknown'}\n"
        f"🆔 Char ID: {int(char_id)}\n"
        f"🔐 Account ID: {int(account_id)}\n"
        f"{status_emoji} Status: {online_status}\n"
        f"⏱️ Duration: {int(duration_value)} {duration_unit}\n"
        f"📝 Reason: {safe_reason}\n"
        "```"
    )
    payload = {
        "content": text,
        "text": text,
        "event": "character_punishment",
        "admin": admin_email,
        "decision": decision_name,
        "char_name": char_name,
        "char_id": int(char_id),
        "account_id": int(account_id),
        "duration_value": int(duration_value),
        "duration_unit": duration_unit,
        "reason": safe_reason,
        "char_status": online_status,
    }
    if cfg.webhooks.discord_url:
        discord_url = _sanitize_discord_url(cfg.webhooks.discord_url)
        discord_payload = {
            "content": text,
            "username": "AggregatorCP",
            "allowed_mentions": {"parse": []},
        }
        ok, msg = _send_webhook(discord_url, discord_payload if _is_discord_webhook(discord_url) else payload)
        hint = ""
        if not ok and "HTTP 403" in msg:
            hint = " (Discord rejected request. Check webhook token validity, channel permissions, and if webhook was regenerated/deleted.)"
        print(f"INFO PunishmentWebhook discord ok={ok} detail={msg}{hint}")
    if cfg.webhooks.telegram_url:
        ok, msg = _send_webhook(cfg.webhooks.telegram_url, {**payload, "text": text})
        print(f"INFO PunishmentWebhook telegram ok={ok} detail={msg}")


def ensure_watch_tables(cfg: AppConfig) -> None:
    conn = db_connect(cfg)
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS acp_watch_cases (
              id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
              created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
              created_by VARCHAR(191) NOT NULL DEFAULT '',
              watch_type VARCHAR(16) NOT NULL,
              char_id INT UNSIGNED NOT NULL DEFAULT 0,
              account_id INT UNSIGNED NOT NULL DEFAULT 0,
              nameid INT UNSIGNED NOT NULL DEFAULT 0,
              label VARCHAR(191) NOT NULL DEFAULT '',
              check_every_seconds INT UNSIGNED NOT NULL DEFAULT 300,
              severity VARCHAR(16) NOT NULL DEFAULT 'medium',
              notify_discord TINYINT(1) NOT NULL DEFAULT 1,
              notify_telegram TINYINT(1) NOT NULL DEFAULT 1,
              enabled TINYINT(1) NOT NULL DEFAULT 1,
              notes TEXT NULL,
              last_snapshot LONGTEXT NULL,
              last_checked_at DATETIME NULL,
              last_notified_at DATETIME NULL,
              PRIMARY KEY (id),
              KEY idx_acp_watch_cases_enabled_checked (enabled, last_checked_at),
              KEY idx_acp_watch_cases_type (watch_type),
              KEY idx_acp_watch_cases_char (char_id),
              KEY idx_acp_watch_cases_account (account_id),
              KEY idx_acp_watch_cases_item (nameid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS acp_watch_events (
              id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
              case_id BIGINT UNSIGNED NOT NULL,
              event_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              event_type VARCHAR(64) NOT NULL DEFAULT 'change_detected',
              severity VARCHAR(16) NOT NULL DEFAULT 'medium',
              summary VARCHAR(255) NOT NULL DEFAULT '',
              details_json LONGTEXT NULL,
              notified_discord TINYINT(1) NOT NULL DEFAULT 0,
              notified_telegram TINYINT(1) NOT NULL DEFAULT 0,
              PRIMARY KEY (id),
              KEY idx_acp_watch_events_case_time (case_id, event_time)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        ensure_column(cur, "acp_watch_cases", "checks_count", "checks_count INT UNSIGNED NOT NULL DEFAULT 0")
        ensure_column(cur, "acp_watch_cases", "monitor_any_change", "monitor_any_change TINYINT(1) NOT NULL DEFAULT 1")
        ensure_column(cur, "acp_watch_cases", "monitor_item_movement", "monitor_item_movement TINYINT(1) NOT NULL DEFAULT 0")
        ensure_column(cur, "acp_watch_cases", "item_movement_threshold", "item_movement_threshold INT UNSIGNED NOT NULL DEFAULT 20")
        ensure_column(cur, "acp_watch_cases", "monitor_failed_logins", "monitor_failed_logins TINYINT(1) NOT NULL DEFAULT 0")
        ensure_column(cur, "acp_watch_cases", "failed_login_threshold", "failed_login_threshold INT UNSIGNED NOT NULL DEFAULT 5")
        ensure_column(cur, "acp_watch_cases", "monitor_zeny_increase", "monitor_zeny_increase TINYINT(1) NOT NULL DEFAULT 0")
        ensure_column(cur, "acp_watch_cases", "zeny_increase_threshold", "zeny_increase_threshold BIGINT UNSIGNED NOT NULL DEFAULT 1000000")
        conn.commit()
        cur.close()
    finally:
        conn.close()


def _fetch_watch_snapshot(cfg: AppConfig, case: dict[str, Any]) -> dict[str, Any]:
    wt = str(case.get("watch_type") or "").lower()
    out: dict[str, Any] = {"watch_type": wt, "char_id": int(case.get("char_id") or 0), "account_id": int(case.get("account_id") or 0), "nameid": int(case.get("nameid") or 0)}

    conn = db_connect(cfg)
    try:
        cur = conn.cursor(dictionary=True)
        if wt == "character" and out["char_id"] > 0:
            cur.execute("SELECT char_id, account_id, name, online, zeny, last_map, last_x, last_y FROM `char` WHERE char_id=%s LIMIT 1", (out["char_id"],))
            row = cur.fetchone() or {}
            out["char"] = row
        elif wt == "account" and out["account_id"] > 0:
            cur.execute("SELECT account_id, userid, state, unban_time, last_ip FROM login WHERE account_id=%s LIMIT 1", (out["account_id"],))
            out["account"] = cur.fetchone() or {}
            cur.execute("SELECT COUNT(*) AS c FROM `char` WHERE account_id=%s", (out["account_id"],))
            out["character_count"] = int((cur.fetchone() or {}).get("c") or 0)
            cur.execute("SELECT COALESCE(SUM(zeny),0) AS s FROM `char` WHERE account_id=%s", (out["account_id"],))
            out["account_zeny_sum"] = int((cur.fetchone() or {}).get("s") or 0)
        elif wt == "item" and out["nameid"] > 0:
            total = 0
            for tbl in ("inventory", "cart_inventory", "storage"):
                if table_exists(cur, tbl):
                    if tbl == "storage":
                        if out["account_id"] > 0:
                            cur.execute("SELECT COALESCE(SUM(amount),0) AS s FROM storage WHERE account_id=%s AND nameid=%s", (out["account_id"], out["nameid"]))
                            total += int((cur.fetchone() or {}).get("s") or 0)
                    else:
                        if out["char_id"] > 0:
                            cur.execute(f"SELECT COALESCE(SUM(amount),0) AS s FROM {tbl} WHERE char_id=%s AND nameid=%s", (out["char_id"], out["nameid"]))
                            total += int((cur.fetchone() or {}).get("s") or 0)
            out["item_total_amount"] = total
        cur.close()
    finally:
        conn.close()

    connl = db_connect_logs(cfg)
    try:
        cur = connl.cursor(dictionary=True)
        picklog_cols = table_columns(cur, "picklog") if table_exists(cur, "picklog") else set()
        has_picklog = bool(picklog_cols)
        has_char_id = "char_id" in picklog_cols
        has_charid = "charid" in picklog_cols
        has_account_id = "account_id" in picklog_cols
        has_nameid = "nameid" in picklog_cols

        if wt == "character" and out["char_id"] > 0 and has_picklog:
            char_filters = []
            params = []
            if has_char_id:
                char_filters.append("char_id=%s")
                params.append(out["char_id"])
            if has_charid:
                char_filters.append("charid=%s")
                params.append(out["char_id"])
            if char_filters:
                cur.execute(
                    f"SELECT MAX(time) AS last_time, COUNT(*) AS c FROM picklog WHERE ({' OR '.join(char_filters)}) AND time >= (NOW() - INTERVAL 1 HOUR)",
                    tuple(params),
                )
                r = cur.fetchone() or {}
                out["picklog_1h_count"] = int(r.get("c") or 0)
                out["picklog_last_time"] = str(r.get("last_time") or "")
        elif wt == "account" and out["account_id"] > 0:
            if has_picklog and has_account_id:
                cur.execute("SELECT COUNT(*) AS c FROM picklog WHERE account_id=%s AND time >= (NOW() - INTERVAL 1 HOUR)", (out["account_id"],))
                out["picklog_1h_count"] = int((cur.fetchone() or {}).get("c") or 0)
            if table_exists(cur, "loginlog"):
                login_cols = table_columns(cur, "loginlog")
                user_col = "user" if "user" in login_cols else ("account_id" if "account_id" in login_cols else "")
                if user_col:
                    cur.execute(
                        f"SELECT COUNT(*) AS c FROM loginlog WHERE {user_col}=%s AND time >= (NOW() - INTERVAL 1 HOUR)",
                        (str(out["account_id"]),),
                    )
                    out["loginlog_1h_count"] = int((cur.fetchone() or {}).get("c") or 0)
                    fail_where = ""
                    if "rcode" in login_cols:
                        fail_where = " AND COALESCE(rcode,0) NOT IN (0,100)"
                    elif "result" in login_cols:
                        fail_where = " AND LOWER(COALESCE(result,'')) IN ('fail','failed','denied','error')"
                    if fail_where:
                        cur.execute(
                            f"SELECT COUNT(*) AS c FROM loginlog WHERE {user_col}=%s {fail_where} AND time >= (NOW() - INTERVAL 1 HOUR)",
                            (str(out["account_id"]),),
                        )
                        out["login_failed_1h_count"] = int((cur.fetchone() or {}).get("c") or 0)
        elif wt == "item" and out["nameid"] > 0 and has_picklog and has_nameid:
            params = [out["nameid"]]
            where_parts = ["nameid=%s"]
            if out["char_id"] > 0 and (has_char_id or has_charid):
                char_filters = []
                if has_char_id:
                    char_filters.append("char_id=%s")
                    params.append(out["char_id"])
                if has_charid:
                    char_filters.append("charid=%s")
                    params.append(out["char_id"])
                where_parts.append(f"({' OR '.join(char_filters)})")
            if out["account_id"] > 0 and has_account_id:
                where_parts.append("account_id=%s")
                params.append(out["account_id"])
            where = " AND ".join(where_parts)
            cur.execute(f"SELECT COUNT(*) AS c, MAX(time) AS last_time FROM picklog WHERE {where} AND time >= (NOW() - INTERVAL 1 HOUR)", tuple(params))
            r = cur.fetchone() or {}
            out["picklog_1h_count"] = int(r.get("c") or 0)
            out["picklog_last_time"] = str(r.get("last_time") or "")
        cur.close()
    finally:
        connl.close()
    return out


def _watch_diff_keys(prev: dict[str, Any], curr: dict[str, Any]) -> list[str]:
    keys = sorted(set(prev.keys()) | set(curr.keys()))
    return [k for k in keys if prev.get(k) != curr.get(k)]


def _to_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _watch_should_notify(case: dict[str, Any], prev: dict[str, Any], curr: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    reasons: list[str] = []
    details: dict[str, Any] = {}
    changed = _watch_diff_keys(prev, curr) if prev else []

    if bool(case.get("monitor_any_change", 1)) and changed:
        reasons.append(f"changed fields: {', '.join(changed[:6])}")
        details["changed_fields"] = changed

    if bool(case.get("monitor_item_movement", 0)):
        threshold = _to_int(case.get("item_movement_threshold"), 20)
        count = _to_int(curr.get("picklog_1h_count"), 0)
        prev_count = _to_int(prev.get("picklog_1h_count"), 0)
        if count >= threshold and (prev_count < threshold or count != prev_count):
            reasons.append(f"item movement in last hour: {count} >= {threshold}")
            details["item_movement"] = {"count_1h": count, "threshold": threshold}

    if bool(case.get("monitor_failed_logins", 0)):
        threshold = _to_int(case.get("failed_login_threshold"), 5)
        count = _to_int(curr.get("login_failed_1h_count"), 0)
        prev_count = _to_int(prev.get("login_failed_1h_count"), 0)
        if count >= threshold and (prev_count < threshold or count != prev_count):
            reasons.append(f"failed logins in last hour: {count} >= {threshold}")
            details["failed_logins"] = {"count_1h": count, "threshold": threshold}

    if bool(case.get("monitor_zeny_increase", 0)):
        threshold = _to_int(case.get("zeny_increase_threshold"), 1000000)
        prev_zeny = _to_int((prev.get("char") or {}).get("zeny"), _to_int(prev.get("account_zeny_sum"), 0))
        curr_zeny = _to_int((curr.get("char") or {}).get("zeny"), _to_int(curr.get("account_zeny_sum"), 0))
        delta = curr_zeny - prev_zeny
        if delta >= threshold:
            reasons.append(f"zeny increase: +{delta} >= {threshold}")
            details["zeny_increase"] = {"delta": delta, "threshold": threshold, "from": prev_zeny, "to": curr_zeny}

    if not reasons:
        return False, "", details
    summary = "; ".join(reasons)[:255]
    details["snapshot"] = curr
    return True, summary, details


def _send_watch_event_webhooks(cfg: AppConfig, case: dict[str, Any], summary: str, details: dict[str, Any]) -> dict[str, bool]:
    payload = {
        "event": "watch_case_change",
        "case_id": int(case.get("id") or 0),
        "watch_type": case.get("watch_type"),
        "label": case.get("label") or "",
        "severity": case.get("severity") or "medium",
        "summary": summary,
        "details": details,
    }
    text = (
        "```\n"
        "🤖 AggregatorCP - Watch Alert\n"
        f"🧾 Case ID: {payload['case_id']}\n"
        f"🎯 Type: {payload['watch_type']}\n"
        f"🏷️ Label: {payload['label'] or '-'}\n"
        f"🚨 Severity: {payload['severity']}\n"
        f"📌 Summary: {summary}\n"
        "```"
    )
    sent = {"discord": False, "telegram": False}
    if bool(case.get("notify_discord")) and cfg.webhooks.discord_url:
        durl = _sanitize_discord_url(cfg.webhooks.discord_url)
        dp = {"content": text, "username": "AggregatorCP", "allowed_mentions": {"parse": []}}
        ok, _ = _send_webhook(durl, dp if _is_discord_webhook(durl) else {**payload, "content": text})
        sent["discord"] = bool(ok)
    if bool(case.get("notify_telegram")) and cfg.webhooks.telegram_url:
        ok, _ = _send_webhook(cfg.webhooks.telegram_url, {**payload, "text": text})
        sent["telegram"] = bool(ok)
    return sent


def run_watch_cases_cycle(cfg: AppConfig) -> None:
    ensure_watch_tables(cfg)
    conn = db_connect(cfg)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT *
            FROM acp_watch_cases
            WHERE enabled=1
              AND (last_checked_at IS NULL OR TIMESTAMPDIFF(SECOND, last_checked_at, NOW()) >= check_every_seconds)
            ORDER BY id ASC
            LIMIT 200
            """
        )
        cases = cur.fetchall() or []
        for case in cases:
            try:
                prev_raw = case.get("last_snapshot")
                prev = {}
                if prev_raw:
                    try:
                        prev = json.loads(prev_raw) if isinstance(prev_raw, str) else dict(prev_raw)
                    except Exception:
                        prev = {}
                curr = _fetch_watch_snapshot(cfg, case)
                should_notify, summary, details = _watch_should_notify(case, prev, curr)
                notified = {"discord": False, "telegram": False}
                if should_notify:
                    notified = _send_watch_event_webhooks(cfg, case, summary, details)
                    cur.execute(
                        "INSERT INTO acp_watch_events (case_id, event_type, severity, summary, details_json, notified_discord, notified_telegram) VALUES (%s,'change_detected',%s,%s,%s,%s,%s)",
                        (int(case.get("id") or 0), str(case.get("severity") or "medium"), summary[:255], json.dumps(details, ensure_ascii=False), int(notified["discord"]), int(notified["telegram"]))
                    )
                    cur.execute("UPDATE acp_watch_cases SET last_notified_at=NOW() WHERE id=%s", (int(case.get("id") or 0),))
                cur.execute("UPDATE acp_watch_cases SET last_snapshot=%s, last_checked_at=NOW(), checks_count=checks_count+1 WHERE id=%s", (json.dumps(curr, ensure_ascii=False), int(case.get("id") or 0)))
            except Exception as err:
                msg = f"Watch run error: {err}"[:255]
                cur.execute(
                    "INSERT INTO acp_watch_events (case_id, event_type, severity, summary, details_json, notified_discord, notified_telegram) VALUES (%s,'watch_error','high',%s,%s,0,0)",
                    (int(case.get("id") or 0), msg, json.dumps({"error": str(err)}, ensure_ascii=False)),
                )
                cur.execute("UPDATE acp_watch_cases SET last_checked_at=NOW(), checks_count=checks_count+1 WHERE id=%s", (int(case.get("id") or 0),))
        conn.commit()
        cur.close()
    finally:
        conn.close()



app = FastAPI(title="Traveler Companion's Overview", version="0.4.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api") and not path.startswith("/api/auth"):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        token = auth.split(" ", 1)[1].strip()
        if token not in app.state.tokens:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


@app.on_event("startup")
def on_startup() -> None:
    cfg = load_config()
    ensure_default_auth()
    app.state.cfg = cfg
    app.state.tokens = {}
    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        scheduler = BackgroundScheduler()
        scheduler.add_job(run_housekeeping_cycle, "interval", minutes=cfg.schedule_housekeeping_minutes, kwargs={"cfg": cfg}, id="housekeeping", replace_existing=True)
        scheduler.add_job(run_watch_cases_cycle, "interval", seconds=60, kwargs={"cfg": cfg}, id="watch_cases", replace_existing=True)
        scheduler.start()
        app.state.scheduler = scheduler
    except Exception:
        app.state.scheduler = None


@app.on_event("shutdown")
def on_shutdown() -> None:
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler is not None:
        scheduler.shutdown(wait=False)


@app.get("/")
def root() -> FileResponse:
    return FileResponse(APP_DIR / "static" / "index.html")


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"ok": True, "configPath": str(CONFIG_PATH)}


@app.post("/api/auth/login")
def login(payload: LoginIn) -> dict[str, Any]:
    if "@" not in payload.email:
        raise HTTPException(status_code=400, detail="Invalid email")
    auth_data = load_auth()
    user = next((u for u in auth_data.get("users", []) if str(u.get("email", "")).lower() == payload.email.lower()), None)
    if not user or not bool(user.get("active", True)):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    hashed = _hash_password(payload.password, str(user.get("salt", "")))
    if hashed != str(user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    role = str(user.get("role", "community_manager"))
    perms = _permissions_for_role(auth_data, role)
    token = secrets.token_urlsafe(32)
    app.state.tokens[token] = {"email": user["email"], "role": role, "permissions": perms, "created_at": int(time.time())}
    return {"token": token, "email": user["email"], "role": role, "permissions": perms}


@app.get("/api/auth/me")
def auth_me(request: Request) -> dict[str, Any]:
    user = _current_user(request)
    return {"email": user.get("email", ""), "role": user.get("role", "community_manager"), "permissions": user.get("permissions", {})}


@app.post("/api/auth/change-email")
def change_email(payload: ChangeEmailIn, request: Request) -> dict[str, Any]:
    if "@" not in payload.new_email or "@" not in payload.current_email:
        raise HTTPException(status_code=400, detail="Invalid email")
    if payload.new_email.lower() != payload.confirm_email.lower():
        raise HTTPException(status_code=400, detail="Email confirmation does not match")
    auth_data = load_auth()
    token = request.headers.get("Authorization", "").split(" ", 1)[1]
    current_email = str(app.state.tokens.get(token, {}).get("email", "")).lower()
    if payload.current_email.lower() != current_email:
        raise HTTPException(status_code=400, detail="Current email mismatch")
    for u in auth_data.get("users", []):
        if str(u.get("email", "")).lower() == current_email:
            u["email"] = payload.new_email.lower()
            break
    save_auth(auth_data)
    app.state.tokens[token]["email"] = payload.new_email.lower()
    return {"ok": True}


@app.post("/api/auth/change-password")
def change_password(payload: ChangePasswordIn, request: Request) -> dict[str, Any]:
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Password confirmation does not match")
    token = request.headers.get("Authorization", "").split(" ", 1)[1]
    current_email = str(app.state.tokens.get(token, {}).get("email", "")).lower()
    auth_data = load_auth()
    user = next((u for u in auth_data.get("users", []) if str(u.get("email", "")).lower() == current_email), None)
    if not user:
        raise HTTPException(status_code=400, detail="Current user not found")
    current = _hash_password(payload.current_password, str(user.get("salt", "")))
    if current != str(user.get("password_hash", "")):
        raise HTTPException(status_code=400, detail="Current password mismatch")
    user["password_hash"] = _hash_password(payload.new_password, str(user.get("salt", "")) )
    save_auth(auth_data)
    return {"ok": True}


@app.get("/api/roles/config")
def get_roles_config(request: Request) -> dict[str, Any]:
    _require_permission(request, "manage_roles")
    data = load_auth()
    users = [{"email": u.get("email", ""), "role": u.get("role", "community_manager"), "active": bool(u.get("active", True))} for u in data.get("users", [])]
    return {"role_permissions": data.get("role_permissions", {}), "users": users, "roles": sorted(list(ROLE_PRESETS.keys()))}


@app.put("/api/roles/config")
@app.post("/api/roles/config")
def put_roles_config(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    _require_permission(request, "manage_roles")
    data = load_auth()
    rp_in = payload.get("role_permissions", {}) if isinstance(payload, dict) else {}
    if isinstance(rp_in, dict):
        merged = {}
        for role, preset in ROLE_PRESETS.items():
            src = rp_in.get(role, {}) if isinstance(rp_in.get(role), dict) else {}
            merged[role] = {k: bool(src.get(k, v)) for k, v in preset.items()}
        data["role_permissions"] = merged
    save_auth(data)
    # refresh live tokens permissions
    for t, info in list(app.state.tokens.items()):
        role = str(info.get("role", "community_manager"))
        app.state.tokens[t]["permissions"] = _permissions_for_role(data, role)
    return {"ok": True}


@app.put("/api/roles/user")
@app.post("/api/roles/user")
def put_user_role(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    _require_permission(request, "manage_roles")
    email = str(payload.get("email", "")).strip().lower()
    role = str(payload.get("role", "")).strip().lower()
    active = bool(payload.get("active", True))
    if role not in ROLE_PRESETS or not email:
        raise HTTPException(status_code=400, detail="Invalid role or email")
    data = load_auth()
    user = next((u for u in data.get("users", []) if str(u.get("email", "")).lower() == email), None)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user["role"] = role
    user["active"] = active
    save_auth(data)
    for t, info in list(app.state.tokens.items()):
        if str(info.get("email", "")).lower() == email:
            app.state.tokens[t]["role"] = role
            app.state.tokens[t]["permissions"] = _permissions_for_role(data, role)
    return {"ok": True}


@app.post("/api/auth/create-user")
def create_user(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    _require_permission(request, "manage_roles")
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    role = str(payload.get("role", "community_manager")).strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if role not in ROLE_PRESETS:
        raise HTTPException(status_code=400, detail="Invalid role")

    data = load_auth()
    if any(str(u.get("email", "")).lower() == email for u in data.get("users", [])):
        raise HTTPException(status_code=400, detail="Email already exists")

    salt = secrets.token_hex(16)
    data.setdefault("users", []).append(
        {
            "email": email,
            "salt": salt,
            "password_hash": _hash_password(password, salt),
            "role": role,
            "active": True,
        }
    )
    save_auth(data)
    return {"ok": True, "email": email, "role": role}


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    return asdict(load_config())


@app.put("/api/config")
def put_config(payload: AppConfigIn, request: Request) -> dict[str, Any]:
    _require_permission(request, "manage_config")
    cfg = AppConfig(
        db=DBConfig(**payload.db.model_dump()),
        ai=AIConfig(**payload.ai.model_dump()),
        webhooks=WebhookConfig(**payload.webhooks.model_dump()),
        schedule_market_minutes=payload.schedule_market_minutes,
        schedule_housekeeping_minutes=payload.schedule_housekeeping_minutes,
        schedule_telemetry_minutes=payload.schedule_telemetry_minutes,
        status_refresh_seconds=payload.status_refresh_seconds,
        offline_notify_seconds=payload.offline_notify_seconds,
        usage_refresh_seconds=payload.usage_refresh_seconds,
        login_server_port=payload.login_server_port,
        char_server_port=payload.char_server_port,
        map_server_port=payload.map_server_port,
        web_server_port=payload.web_server_port,
        app_host=payload.app_host,
        proxies=[ProxyConfig(**x.model_dump()) for x in payload.proxies],
    )
    save_config(cfg)
    app.state.cfg = cfg
    return {"saved": True, "configPath": str(CONFIG_PATH)}


@app.get("/api/status")
def status() -> dict[str, Any]:
    cfg = load_config()
    return collect_status(cfg)


@app.post("/api/status/offline-notify")
def status_offline_notify() -> dict[str, Any]:
    cfg = load_config()
    st = collect_status(cfg)
    notify = _send_offline_status_webhook(cfg, st)
    return {"status": st, "notify": notify}


@app.get("/api/system/usage")
def system_usage() -> dict[str, Any]:
    return collect_system_usage()


def _repo_root() -> Path:
    return APP_DIR.parent.parent


def _discover_emulator_root(start: Path, max_levels: int = 20, timeout_seconds: float = 3.0) -> tuple[Path | None, dict[str, Any]]:
    current = start.resolve()
    started = time.monotonic()
    deadline = started + max(0.2, float(timeout_seconds))
    checked: list[str] = []

    for _ in range(max(0, int(max_levels)) + 1):
        checked.append(str(current))
        markers = {
            "athena_start": (current / "athena-start").exists(),
            "rathena_sln": (current / "rAthena.sln").exists(),
            "install_sh": (current / "install.sh").exists(),
            "runserver_bat": (current / "tools" / "runserver.bat").exists(),
            "runserver_exe": (current / "tools" / "runserver.exe").exists(),
        }
        if markers["athena_start"] or markers["runserver_bat"] or markers["runserver_exe"] or (
            markers["rathena_sln"] and markers["install_sh"]
        ):
            return current, {"checked": checked, "elapsed_ms": int((time.monotonic() - started) * 1000), "markers": markers}

        if time.monotonic() >= deadline:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent

    return None, {"checked": checked, "elapsed_ms": int((time.monotonic() - started) * 1000)}


@app.post("/api/emulator/start")
def emulator_start() -> dict[str, Any]:
    root_hint = _repo_root()
    root, scan = _discover_emulator_root(root_hint, max_levels=25, timeout_seconds=4.0)
    if root is None:
        raise HTTPException(status_code=500, detail=f"start failed: emulator root not found. checked={scan.get('checked', [])}")

    try:
        import subprocess
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            binaries = ["login-server.exe", "char-server.exe", "map-server.exe", "web-server.exe"]
            missing = [name for name in binaries if not (root / name).exists()]
            started: list[dict[str, Any]] = []

            if not missing:
                for name in binaries:
                    target = root / name
                    proc = subprocess.Popen([str(target)], cwd=str(root), creationflags=creationflags)
                    started.append({"binary": str(target), "pid": proc.pid})
                    time.sleep(1.0)
                return {
                    "ok": True,
                    "action": "start",
                    "mode": "direct_exe",
                    "root": str(root),
                    "started": started,
                    "scan": scan,
                }

            tools_dir = root / "tools"
            runserver_exe = tools_dir / "runserver.exe"
            runserver_bat = tools_dir / "runserver.bat"
            if runserver_exe.exists():
                proc = subprocess.Popen([str(runserver_exe), "start"], cwd=str(tools_dir), creationflags=creationflags)
                return {
                    "ok": True,
                    "action": "start",
                    "mode": "runserver_exe",
                    "launcher": str(runserver_exe),
                    "pid": proc.pid,
                    "root": str(root),
                    "missing_binaries": missing,
                    "scan": scan,
                }
            if runserver_bat.exists():
                proc = subprocess.Popen(
                    ["cmd", "/c", "start", "", "/D", str(tools_dir), "cmd", "/c", "runserver.bat", "start"],
                    cwd=str(root),
                    creationflags=creationflags,
                )
                return {
                    "ok": True,
                    "action": "start",
                    "mode": "runserver_bat",
                    "launcher": str(runserver_bat),
                    "pid": proc.pid,
                    "root": str(root),
                    "missing_binaries": missing,
                    "scan": scan,
                }

            raise RuntimeError(
                f"Could not start emulator. Missing binaries={missing}. Also runserver launcher not found in {tools_dir}."
            )

        athena = root / "athena-start"
        if not athena.exists():
            raise RuntimeError(f"athena-start not found under {root}")
        proc = subprocess.Popen(["./athena-start", "start"], cwd=str(root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"ok": True, "action": "start", "mode": "athena_start", "launcher": "./athena-start", "pid": proc.pid, "root": str(root), "scan": scan}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"start failed: {exc}") from exc


@app.post("/api/emulator/restart")
def emulator_restart_compat() -> dict[str, Any]:
    return emulator_start()


@app.post("/api/emulator/stop")
def emulator_stop(confirm: bool = False) -> dict[str, Any]:
    if not confirm:
        raise HTTPException(status_code=400, detail="confirm=true is required")
    root = _repo_root()
    try:
        import subprocess
        kill_patterns = ["web-server", "map-server", "char-server", "login-server", "athena-start", "runserver", "logserv", "charserv", "mapserv", "webserv", "watch"]
        if os.name == "nt":
            ps_cmd = (
                "Get-CimInstance Win32_Process | "
                "Where-Object { $_.CommandLine -match 'runserver\\.bat|logserv\\.bat|charserv\\.bat|mapserv\\.bat|webserv\\.bat|athena-start|watch' } | "
                "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], cwd=str(root), capture_output=True, text=True)
            subprocess.run(["cmd", "/c", "taskkill /F /IM web-server.exe /IM map-server.exe /IM char-server.exe /IM login-server.exe /IM runserver.exe /T"], cwd=str(root), capture_output=True, text=True)
        else:
            subprocess.run(["pkill", "-TERM", "-f", "|".join(kill_patterns)], cwd=str(root), capture_output=True, text=True)
            subprocess.run(["pkill", "-9", "-f", "|".join(kill_patterns)], cwd=str(root), capture_output=True, text=True)
        return {"ok": True, "action": "stop", "terminated": ["web-server", "map-server", "char-server", "login-server"]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"stop failed: {exc}") from exc


@app.get("/api/emulator/maplog-tail")
def emulator_maplog_tail(lines: int = 20) -> dict[str, Any]:
    root = _repo_root()
    lim = min(max(int(lines), 1), 300)
    candidates = [
        root / "log" / "map-server.log",
        root / "map-server.log",
        root / "log" / "mapserv.log",
        root / "log" / "map-server_sql.log",
        root / "map-server_sql.log",
        root / "log" / "map-server-console.log",
    ]
    for f in candidates:
        if f.exists():
            txt = f.read_text(encoding="utf-8", errors="ignore").splitlines()
            return {"file": str(f), "lines": txt[-lim:]}
    return {"file": None, "lines": [], "warning": "map-server log file not found"}



@app.get("/api/user-items/search")
def search_user_items_chars(q: str = "", limit: int = 10) -> dict[str, Any]:
    q = (q or "").strip()
    if not q:
        return {"items": []}
    lim = min(max(int(limit), 1), 30)
    cfg = load_config()
    try:
        conn = db_connect(cfg)
        cur = conn.cursor(dictionary=True)
        if q.isdigit():
            cur.execute(
                """
                SELECT char_id, account_id, name, class
                FROM `char`
                WHERE char_id=%s OR account_id=%s
                ORDER BY name ASC
                LIMIT %s
                """,
                (int(q), int(q), lim),
            )
        else:
            cur.execute(
                """
                SELECT char_id, account_id, name, class
                FROM `char`
                WHERE name LIKE %s
                ORDER BY name ASC
                LIMIT %s
                """,
                (f"%{q}%", lim),
            )
        rows = cur.fetchall() or []
        cur.close()
        conn.close()
        return {"items": rows}
    except Exception as exc:
        return {"items": [], "warning": str(exc)}


@app.get("/api/user-items/list")
def user_items_list(char_id: int, section: str = "inventory", limit: int = 300) -> dict[str, Any]:
    sec = (section or "inventory").strip().lower()
    if sec not in {"inventory", "cart", "storage"}:
        raise HTTPException(status_code=400, detail="section must be inventory|cart|storage")
    cfg = load_config()
    try:
        conn = db_connect(cfg)
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT char_id, account_id, name, class FROM `char` WHERE char_id=%s LIMIT 1", (int(char_id),))
        ch = cur.fetchone()
        if not ch:
            cur.close()
            conn.close()
            return {"character": None, "items": []}

        lim = min(max(int(limit), 1), 1000)
        table = "inventory" if sec == "inventory" else ("cart_inventory" if sec == "cart" else "storage")
        owner_col = "char_id" if sec in {"inventory", "cart"} else "account_id"
        owner_val = int(ch["char_id"] if sec in {"inventory", "cart"} else ch["account_id"])

        if not table_exists(cur, table):
            cur.close()
            conn.close()
            return {"character": ch, "section": sec, "items": [], "warning": f"table `{table}` not found"}

        has_item_db_re = table_exists(cur, "item_db_re")
        item_name_join = "item_db_re" if has_item_db_re else "item_db"

        cur.execute(
            f"""
            SELECT i.id, i.nameid, i.amount, i.refine, i.card0, i.card1, i.card2, i.card3,
                   i.option_id0, i.option_val0, i.option_parm0,
                   i.option_id1, i.option_val1, i.option_parm1,
                   i.option_id2, i.option_val2, i.option_parm2,
                   i.option_id3, i.option_val3, i.option_parm3,
                   i.option_id4, i.option_val4, i.option_parm4,
                   i.enchantgrade, i.unique_id,
                   COALESCE(i0.name_english, CONCAT('ID ', i.nameid)) AS item_name,
                   COALESCE(c0.name_english, '') AS card0_name,
                   COALESCE(c1.name_english, '') AS card1_name,
                   COALESCE(c2.name_english, '') AS card2_name,
                   COALESCE(c3.name_english, '') AS card3_name
            FROM {table} i
            LEFT JOIN {item_name_join} i0 ON i0.id = i.nameid
            LEFT JOIN {item_name_join} c0 ON c0.id = i.card0
            LEFT JOIN {item_name_join} c1 ON c1.id = i.card1
            LEFT JOIN {item_name_join} c2 ON c2.id = i.card2
            LEFT JOIN {item_name_join} c3 ON c3.id = i.card3
            WHERE i.{owner_col}=%s
            ORDER BY i.amount DESC, i.id DESC
            LIMIT %s
            """,
            (owner_val, lim),
        )
        rows = cur.fetchall() or []
        items: list[dict[str, Any]] = []
        for r in rows:
            cards = []
            for idx in range(4):
                cid = int(r.get(f"card{idx}") or 0)
                if cid > 0:
                    cname = (r.get(f"card{idx}_name") or "").strip()
                    cards.append(cname or f"Card {cid}")

            opts = []
            for idx in range(5):
                oid = int(r.get(f"option_id{idx}") or 0)
                oval = int(r.get(f"option_val{idx}") or 0)
                oprm = int(r.get(f"option_parm{idx}") or 0)
                if oid > 0:
                    opts.append({"id": oid, "value": oval, "param": oprm})

            items.append(
                {
                    "id": int(r.get("id") or 0),
                    "nameid": int(r.get("nameid") or 0),
                    "item_name": r.get("item_name") or f"ID {int(r.get('nameid') or 0)}",
                    "amount": int(r.get("amount") or 0),
                    "refine": int(r.get("refine") or 0),
                    "cards": cards,
                    "options": opts,
                    "enchantgrade": int(r.get("enchantgrade") or 0),
                    "unique_id": int(r.get("unique_id") or 0),
                }
            )

        cart_count = 0
        try:
            cur.execute("SELECT COUNT(*) AS c FROM cart_inventory WHERE char_id=%s", (int(ch["char_id"]),))
            cc = cur.fetchone() or {"c": 0}
            cart_count = int(cc.get("c") or 0)
        except Exception:
            cart_count = 0

        out = {
            "character": {
                "char_id": int(ch.get("char_id") or 0),
                "account_id": int(ch.get("account_id") or 0),
                "name": ch.get("name") or "",
                "class": int(ch.get("class") or 0),
                "cart_applicable": cart_count > 0,
            },
            "section": sec,
            "items": items,
        }
        cur.close()
        conn.close()
        return out
    except Exception as exc:
        return {"character": None, "section": sec, "items": [], "warning": str(exc)}


@app.get("/api/user-items/logs")
def user_item_logs(char_id: int, nameid: int, limit: int = 10, offset: int = 0) -> dict[str, Any]:
    cfg = load_config()
    try:
        conn_main = db_connect(cfg)
        cur_main = conn_main.cursor(dictionary=True)
        cur_main.execute("SELECT account_id, name FROM `char` WHERE char_id=%s LIMIT 1", (int(char_id),))
        ch = cur_main.fetchone()
        cur_main.close()
        conn_main.close()
        if not ch:
            return {"items": []}

        conn = db_connect_logs(cfg)
        cur = conn.cursor(dictionary=True)
        lim = min(max(int(limit), 1), 100)
        off = max(int(offset), 0)
        cur.execute(
            """
            SELECT id, time, type, amount, refine, map
            FROM picklog
            WHERE char_id=%s AND nameid=%s
            ORDER BY time DESC
            LIMIT %s OFFSET %s
            """,
            (int(char_id), int(nameid), lim, off),
        )
        rows = cur.fetchall() or []
        out = []
        for r in rows:
            rec = dict(r)
            rec["source"] = _picklog_type_label(str(rec.get("type") or ""))
            out.append(rec)
        cur.close()
        conn.close()
        return {"character": {"char_id": int(char_id), "name": ch.get("name") or "", "account_id": int(ch.get("account_id") or 0)}, "nameid": int(nameid), "items": out}
    except Exception as exc:
        return {"character": None, "nameid": int(nameid), "items": [], "warning": str(exc)}


@app.get("/api/chars/search")
def chars_search(q: str = "", limit: int = 5) -> dict[str, Any]:
    term = (q or "").strip()
    if not term:
        return {"items": []}
    lim = min(max(int(limit), 1), 50)
    cfg = load_config()
    try:
        conn = db_connect(cfg)
        cur = conn.cursor(dictionary=True)
        if term.isdigit():
            cur.execute("SELECT char_id, account_id, name FROM `char` WHERE char_id=%s OR account_id=%s ORDER BY name ASC LIMIT %s", (int(term), int(term), lim))
        else:
            like = f"%{term}%"
            cur.execute("SELECT char_id, account_id, name FROM `char` WHERE name LIKE %s ORDER BY name ASC LIMIT %s", (like, lim))
        rows = cur.fetchall() or []
        cur.close()
        conn.close()
        return {"items": rows}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/chars/status")
def char_status(char_id: int) -> dict[str, Any]:
    cfg = load_config()
    try:
        return resolve_char_status(cfg, char_id)
    except Exception as exc:
        return {"char_id": int(char_id), "online": False, "warning": str(exc)}


@app.post("/api/ip-check")
def ip_check(payload: IPCheckIn) -> dict[str, Any]:
    q = (payload.query or "").strip()
    if not q:
        return {"seed": None, "items": []}
    cfg = load_config()
    try:
        conn = db_connect(cfg)
        cur = conn.cursor(dictionary=True)

        if q.isdigit():
            cur.execute(
                """
                SELECT c.char_id, c.account_id, c.name, l.last_ip, l.email, l.birthdate
                FROM `char` c
                JOIN login l ON l.account_id = c.account_id
                WHERE c.char_id=%s OR c.account_id=%s
                ORDER BY c.char_id ASC
                LIMIT 1
                """,
                (int(q), int(q)),
            )
        else:
            cur.execute(
                """
                SELECT c.char_id, c.account_id, c.name, l.last_ip, l.email, l.birthdate
                FROM `char` c
                JOIN login l ON l.account_id = c.account_id
                WHERE c.name=%s
                LIMIT 1
                """,
                (q,),
            )
        seed = cur.fetchone()
        if not seed:
            cur.close()
            conn.close()
            return {"seed": None, "items": []}

        cur.execute(
            """
            SELECT c.char_id, c.account_id, c.name, l.last_ip, l.email, l.birthdate
            FROM `char` c
            JOIN login l ON l.account_id = c.account_id
            WHERE l.last_ip=%s OR l.email=%s OR l.birthdate=%s
            ORDER BY c.name ASC
            LIMIT 200
            """,
            (seed.get("last_ip"), seed.get("email"), seed.get("birthdate")),
        )
        rows = cur.fetchall() or []
        items: list[dict[str, Any]] = []
        for r in rows:
            rec = dict(r)
            rec["same_user_percent"] = _confidence_score(seed, rec)
            items.append(rec)
        cur.close()
        conn.close()
        return {"seed": seed, "items": items}
    except Exception as exc:
        return {"seed": None, "items": [], "warning": str(exc)}




LOG_TABLES: dict[str, dict[str, Any]] = {
    "atcommandlog": {"label": "AtCommands", "search_cols": ["command", "map", "ip", "char_name", "account_id", "char_id"]},
    "cashlog": {"label": "Cash Flow", "search_cols": ["type", "map", "char_id", "account_id"]},
    "chatlog": {"label": "Chat", "search_cols": ["type", "src_charname", "dst_charname", "src_map", "dst_map", "msg", "src_charid", "dst_charid"]},
    "loginlog": {"label": "Login", "search_cols": ["ip", "user", "rcode", "log"]},
    "npclog": {"label": "NPC", "search_cols": ["npc", "map", "mes", "char_id", "account_id"]},
    "picklog": {"label": "Picklog", "search_cols": ["nameid", "type", "map", "charid", "account_id"]},
    "zenylog": {"label": "Zeny", "search_cols": ["type", "src_id", "dst_id", "amount", "map"]},
}


def _table_columns(conn, table: str) -> list[str]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name=%s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    rows = cur.fetchall() or []
    cur.close()
    return [str(r[0]) for r in rows]


def _char_name_map(cfg: AppConfig, char_ids: set[int]) -> dict[int, str]:
    ids = sorted({int(x) for x in char_ids if int(x) > 0})
    if not ids:
        return {}
    conn = db_connect(cfg)
    try:
        cur = conn.cursor()
        placeholders = ",".join(["%s"] * len(ids))
        cur.execute(f"SELECT char_id, name FROM `char` WHERE char_id IN ({placeholders})", tuple(ids))
        out: dict[int, str] = {}
        for cid, name in cur.fetchall() or []:
            out[int(cid)] = str(name)
        cur.close()
        return out
    finally:
        conn.close()


def _norm_int(v: Any) -> int:
    try:
        return int(v)
    except Exception:
        return 0


@app.get("/api/actions/history")
def actions_history(request: Request, decision: str = "", limit: int = 10, offset: int = 0) -> dict[str, Any]:
    _require_permission(request, "view_logs")
    cfg = load_config()
    try:
        ensure_decisions_table(cfg)
        lim = min(max(int(limit), 1), 100)
        off = max(int(offset), 0)
        dao = ActionsRepository(db_connect)
        conn, rows = dao.action_history_rows(cfg, decision, lim, off)
        req_lang = _lang_from_request(request)
        for row in rows:
            row["active"] = False
            row["remaining_seconds"] = 0
            status_name = str(row.get("status") or "").lower()
            decision_name = str(row.get("decision") or "").lower()
            if status_name in {"queued", "dispatched", "processing", "pending"}:
                row["active"] = True
            if decision_name in {"mute", "ban"} and status_name in {"applied", "queued", "dispatched", "processing", "pending"}:
                cur2 = conn.cursor()
                unit = "MINUTE" if decision_name == "mute" else "DAY"
                cur2.execute(
                    f"SELECT GREATEST(TIMESTAMPDIFF(SECOND, NOW(), DATE_ADD(%s, INTERVAL %s {unit})), 0)",
                    (row.get("created_at"), int(row.get("duration_value") or 0)),
                )
                rem = cur2.fetchone()
                cur2.close()
                row["remaining_seconds"] = int((rem or [0])[0] or 0)
                row["active"] = row["remaining_seconds"] > 0
            row["status_label"] = tr_msg(req_lang, "active") if row.get("active") else tr_msg(req_lang, "inactive")
        conn.close()
        return {"items": rows}
    except Exception as exc:
        return {"items": [], "warning": str(exc)}



@app.get("/api/logs/search")
def logs_search(request: Request, table: str, q: str = "", limit: int = 10, offset: int = 0) -> dict[str, Any]:
    _require_permission(request, "search_logs")
    tbl = (table or "").strip().lower()
    if tbl not in LOG_TABLES:
        return {"items": [], "columns": [], "warning": f"Unsupported table '{tbl}'", "available_tables": sorted(LOG_TABLES.keys())}

    cfg = load_config()
    lim = min(max(int(limit), 1), 50)
    off = max(int(offset), 0)
    term = (q or "").strip()
    try:
        dao = LogsRepository(db_connect_logs, db_connect)
        cols = dao.table_columns(cfg, tbl)
        if not cols:
            return {"items": [], "columns": [], "warning": f"Table '{tbl}' not found in logs database", "available_tables": sorted(LOG_TABLES.keys())}

        order_col = next((c for c in ["time", "tstamp", "id"] if c in cols), cols[0])
        select_cols = cols[:14]
        where = ""
        params: list[Any] = []
        if term:
            search_cols = [c for c in LOG_TABLES[tbl].get("search_cols", []) if c in cols]
            if not search_cols:
                search_cols = list(select_cols)
            where = " WHERE " + " OR ".join([f"CAST(`{c}` AS CHAR) LIKE %s" for c in search_cols])
            like = f"%{term}%"
            params.extend([like] * len(search_cols))

        items = dao.query_table(cfg, tbl, select_cols, where, params, order_col, lim, off)

        char_ids: set[int] = set()
        for rec in items:
            for key in ("char_id", "charid", "src_charid", "dst_charid"):
                if key in rec:
                    v = _norm_int(rec.get(key))
                    if v > 0:
                        char_ids.add(v)
        cmap = dao.char_name_map(cfg, char_ids)

        for rec in items:
            if tbl == "picklog" and "type" in rec:
                rec["type_label"] = _picklog_type_label(str(rec.get("type") or ""))
            if "char_id" in rec:
                rec["char_name"] = cmap.get(_norm_int(rec.get("char_id")), "")
            if "charid" in rec:
                rec["char_name"] = cmap.get(_norm_int(rec.get("charid")), "")
            if "src_charid" in rec:
                rec["src_char_name"] = cmap.get(_norm_int(rec.get("src_charid")), "")
            if "dst_charid" in rec:
                rec["dst_char_name"] = cmap.get(_norm_int(rec.get("dst_charid")), "")

        extra_cols = []
        if items:
            for c in ["char_name", "src_char_name", "dst_char_name", "type_label"]:
                if any(c in r for r in items):
                    extra_cols.append(c)
        return {
            "table": tbl,
            "label": LOG_TABLES[tbl].get("label", tbl),
            "columns": select_cols + extra_cols,
            "items": items,
            "available_tables": sorted(LOG_TABLES.keys()),
        }
    except Exception as exc:
        return {"table": tbl, "columns": [], "items": [], "warning": str(exc), "available_tables": sorted(LOG_TABLES.keys())}


@app.post("/api/decision/bulk")
def decision_bulk(payload: BulkDecisionIn, request: Request) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for target in payload.targets[:100]:
        try:
            out = decision(target, request)
            results.append({"char_id": target.char_id, "decision": target.decision, "ok": bool(out.get("ok")), "message": out.get("message", "")})
        except HTTPException as exc:
            results.append({"char_id": target.char_id, "decision": target.decision, "ok": False, "message": str(exc.detail)})
        except Exception as exc:
            results.append({"char_id": target.char_id, "decision": target.decision, "ok": False, "message": str(exc)})
    return {"ok": True, "results": results}


@app.post("/api/run/market")
def run_market_now() -> dict[str, Any]:
    return {"ok": False, "warning": "market AI disabled in AggregatorCP"}


@app.post("/api/run/housekeeping")
def run_housekeeping_now() -> dict[str, Any]:
    run_housekeeping_cycle(load_config())
    return {"ok": True}


@app.post("/api/run/telemetry")
def run_telemetry_now() -> dict[str, Any]:
    return {"ok": False, "warning": "telemetry AI disabled in AggregatorCP"}




@app.get("/api/bridge/diagnostics")
def bridge_diagnostics() -> dict[str, Any]:
    cfg = load_config()
    out: dict[str, Any] = {
        "bridge_env_configured": bool(os.environ.get("TC_BRIDGE_ENDPOINT_URL", "").strip() and os.environ.get("TC_BRIDGE_SHARED_SECRET", "").strip()),
        "queue_table": False,
        "pending": 0,
        "applied": 0,
        "failed": 0,
        "processing": 0,
        "oldest_pending_seconds": 0,
        "hint": "",
    }
    try:
        ensure_game_bridge_queue(cfg)
        conn = db_connect(cfg)
        cur = conn.cursor(dictionary=True)
        out["queue_table"] = True

        cur.execute("SELECT status, COUNT(*) AS c FROM acp_gm_command_queue GROUP BY status")
        for row in cur.fetchall():
            st = str(row.get("status", "")).lower()
            c = int(row.get("c", 0))
            if st == "pending":
                out["pending"] = c
            elif st == "applied":
                out["applied"] = c
            elif st == "failed":
                out["failed"] = c
            elif st == "processing":
                out["processing"] = c

        cur.execute("SELECT TIMESTAMPDIFF(SECOND, MIN(created_at), NOW()) AS oldest FROM acp_gm_command_queue WHERE status='pending'")
        r = cur.fetchone() or {}
        out["oldest_pending_seconds"] = int(r.get("oldest") or 0)

        if out["pending"] > 0 and out["applied"] == 0:
            out["hint"] = "Queue has pending actions but no applied actions yet. Ensure the AggregatorCP bridge executor NPC/script is loaded and running in-script timers."
        elif out["pending"] > 0:
            out["hint"] = "Queue has pending actions waiting for game-side executor cycle."
        else:
            out["hint"] = "No pending bridge actions."

        cur.close()
        conn.close()
        return out
    except Exception as exc:
        out["hint"] = f"Diagnostics query failed: {exc}"
        return out

@app.post("/api/decision")
def decision(payload: DecisionIn, request: Request) -> dict[str, Any]:
    _require_permission(request, "apply_punishments")
    req_lang = _lang_from_request(request)
    decision_name = payload.decision.strip().lower()
    if decision_name not in {"mute", "unmute", "ban", "kick", "unflag", "jail", "unjail", "unban"}:
        raise HTTPException(status_code=400, detail=tr_msg(req_lang, "decision_invalid"))

    reason_mode = payload.reason_mode.strip().lower()
    if reason_mode not in {"log", "notify"}:
        raise HTTPException(status_code=400, detail=tr_msg(req_lang, "reason_mode_invalid"))

    duration_value = max(0, int(payload.duration_value or 0))
    duration_unit = "minutes" if decision_name == "mute" else ("days" if decision_name == "ban" else "none")

    auth = request.headers.get("Authorization", "")
    token = auth.split(" ", 1)[1].strip() if auth.startswith("Bearer ") else ""
    admin_identity = app.state.tokens.get(token, {}).get("email", "unknown-admin")

    cfg = load_config()
    char_name = resolve_char_name(cfg, payload.char_id)
    resolved_account_id = int(payload.account_id or 0)
    if resolved_account_id <= 0:
        resolved_account_id = resolve_account_id(cfg, payload.char_id)
    log_admin_action_submit(admin_identity, char_name, payload.char_id, decision_name, duration_value, duration_unit)
    try:
        ensure_decisions_table(cfg)
        conn = db_connect(cfg)

        cur = conn.cursor()
        cur.execute(
            "INSERT INTO acp_admin_decisions (char_id, account_id, decision, reason, reason_mode, duration_value, duration_unit) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (payload.char_id, resolved_account_id, decision_name, payload.reason, reason_mode, duration_value, duration_unit),
        )
        conn.commit()
        cur.close()

        action_id = uuid.uuid4().hex
        q = conn.cursor()
        q.execute(
            "INSERT INTO acp_admin_action_queue (action_id, char_id, account_id, decision, reason, reason_mode, duration_value, duration_unit, status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'queued')",
            (action_id, payload.char_id, resolved_account_id, decision_name, payload.reason, reason_mode, duration_value, duration_unit),
        )
        conn.commit()
        q.close()

        if decision_name == "unban":
            if resolved_account_id <= 0:
                conn.close()
                return {"ok": False, "message": tr_msg(req_lang, "unban_requires_account")}
            u = conn.cursor()
            u.execute("UPDATE login SET state=0, unban_time=0 WHERE account_id=%s", (resolved_account_id,))
            changed = u.rowcount
            u.close()
            upd = conn.cursor()
            upd.execute("UPDATE acp_admin_action_queue SET status='applied', bridge_message=%s WHERE action_id=%s", (f"unban account_id={resolved_account_id} changed={changed}", action_id))
            conn.commit()
            upd.close()
            conn.close()
            _send_punishment_webhooks(cfg, admin_identity, char_name, payload.char_id, resolved_account_id, decision_name, duration_value, duration_unit, payload.reason)
            return {"ok": True, "message": tr_msg(req_lang, "unban_applied", account_id=resolved_account_id, changed=changed)}

        if decision_name == "unflag":
            u = conn.cursor()
            u.execute("DELETE FROM ml_admin_flags WHERE account_id=%s", (resolved_account_id,))
            removed = u.rowcount
            u.close()
            upd = conn.cursor()
            upd.execute("UPDATE acp_admin_action_queue SET status='applied', bridge_message=%s WHERE action_id=%s", (f"unflag removed={removed}", action_id))
            conn.commit()
            upd.close()
            conn.close()
            return {"ok": True, "message": tr_msg(req_lang, "unflag_applied", removed=removed)}

        ok, message = bridge_dispatch(action_id, payload.char_id, decision_name, payload.reason, reason_mode, duration_value)
        upd = conn.cursor()
        upd.execute(
            "UPDATE acp_admin_action_queue SET status=%s, bridge_message=%s WHERE action_id=%s",
            ("dispatched" if ok else "queued", message[:2000], action_id),
        )
        conn.commit()
        upd.close()
        conn.close()

        if ok:
            _send_punishment_webhooks(cfg, admin_identity, char_name, payload.char_id, resolved_account_id, decision_name, duration_value, duration_unit, payload.reason)
            return {"ok": True, "message": tr_msg(req_lang, "dispatched", decision=decision_name.title())}

        if "Bridge not configured" in message:
            local_ok, local_msg = enqueue_local_bridge_action(cfg, action_id, payload.char_id, decision_name, payload.reason, reason_mode, duration_value)
            if local_ok:
                conn2 = db_connect(cfg)
                try:
                    cur2 = conn2.cursor()
                    cur2.execute(
                        "UPDATE acp_admin_action_queue SET status=%s, bridge_message=%s WHERE action_id=%s",
                        ("queued", "Local queue fallback enqueued. Waiting game-side executor.", action_id),
                    )
                    conn2.commit()
                    cur2.close()
                finally:
                    conn2.close()
                _send_punishment_webhooks(cfg, admin_identity, char_name, payload.char_id, resolved_account_id, decision_name, duration_value, duration_unit, payload.reason)
                return {"ok": True, "message": tr_msg(req_lang, "fallback_wait")}
            return {"ok": False, "message": tr_msg(req_lang, "bridge_not_configured_and_failed", error=local_msg)}

        return {"ok": False, "message": tr_msg(req_lang, "bridge_failed", error=message)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/watch/search")
def watch_search(request: Request, q: str, watch_type: str = "character", limit: int = 20) -> dict[str, Any]:
    _require_permission(request, "view_watch")
    cfg = load_config()
    lim = min(max(int(limit), 1), 100)
    text = (q or "").strip()
    if len(text) < 1:
        return {"items": []}
    wt = (watch_type or "character").strip().lower()
    conn = db_connect(cfg)
    try:
        cur = conn.cursor(dictionary=True)
        items: list[dict[str, Any]] = []
        like = f"%{text}%"
        if wt == "character":
            cur.execute(
                """
                SELECT char_id, account_id, name
                FROM `char`
                WHERE name LIKE %s OR CAST(char_id AS CHAR)=%s OR CAST(account_id AS CHAR)=%s
                ORDER BY char_id DESC
                LIMIT %s
                """,
                (like, text, text, lim),
            )
            for row in cur.fetchall() or []:
                row["display"] = f"{row.get('name','-')} (char:{int(row.get('char_id') or 0)} / acc:{int(row.get('account_id') or 0)})"
                items.append(row)
        elif wt == "account":
            cur.execute(
                """
                SELECT account_id, userid, last_ip
                FROM login
                WHERE userid LIKE %s OR CAST(account_id AS CHAR)=%s OR last_ip LIKE %s
                ORDER BY account_id DESC
                LIMIT %s
                """,
                (like, text, like, lim),
            )
            for row in cur.fetchall() or []:
                row["display"] = f"{row.get('userid','-')} (acc:{int(row.get('account_id') or 0)} ip:{row.get('last_ip') or '-'})"
                items.append(row)
        elif wt == "item":
            if table_exists(cur, "item_db_re"):
                cur.execute(
                    """
                    SELECT id AS nameid, aegis_name, name_english
                    FROM item_db_re
                    WHERE name_english LIKE %s OR aegis_name LIKE %s OR CAST(id AS CHAR)=%s
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (like, like, text, lim),
                )
            elif table_exists(cur, "item_db"):
                cur.execute(
                    """
                    SELECT id AS nameid, aegis_name, name_english
                    FROM item_db
                    WHERE name_english LIKE %s OR aegis_name LIKE %s OR CAST(id AS CHAR)=%s
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (like, like, text, lim),
                )
            else:
                cur.close()
                return {"items": []}
            for row in cur.fetchall() or []:
                row["display"] = f"{row.get('name_english') or row.get('aegis_name') or '-'} (item:{int(row.get('nameid') or 0)})"
                items.append(row)
        cur.close()
        return {"items": items}
    finally:
        conn.close()


@app.post("/api/watch/cases")
def watch_case_create(payload: WatchCaseIn, request: Request) -> dict[str, Any]:
    _require_permission(request, "manage_watch")
    cfg = load_config()
    ensure_watch_tables(cfg)
    wt = (payload.watch_type or "").strip().lower()
    if wt == "character" and int(payload.char_id or 0) <= 0:
        raise HTTPException(status_code=400, detail="char_id is required for character watch")
    if wt == "account" and int(payload.account_id or 0) <= 0:
        raise HTTPException(status_code=400, detail="account_id is required for account watch")
    if wt == "item" and int(payload.nameid or 0) <= 0:
        raise HTTPException(status_code=400, detail="nameid is required for item watch")

    user = _current_user(request)

    def _insert_case(cur, watch_type: str, char_id: int, account_id: int, nameid: int, label: str, notes: str) -> int:
        cur.execute(
            """
            INSERT INTO acp_watch_cases (
                created_by, watch_type, char_id, account_id, nameid, label, check_every_seconds, severity,
                notify_discord, notify_telegram, enabled, notes,
                monitor_any_change, monitor_item_movement, item_movement_threshold,
                monitor_failed_logins, failed_login_threshold,
                monitor_zeny_increase, zeny_increase_threshold
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                str(user.get("email") or "unknown"), watch_type, int(char_id), int(account_id), int(nameid),
                str(label or "")[:191], int(payload.check_every_seconds), str(payload.severity or "medium")[:16],
                int(bool(payload.notify_discord)), int(bool(payload.notify_telegram)), int(bool(payload.enabled)), str(notes or ""),
                int(bool(payload.monitor_any_change)), int(bool(payload.monitor_item_movement)), int(payload.item_movement_threshold),
                int(bool(payload.monitor_failed_logins)), int(payload.failed_login_threshold),
                int(bool(payload.monitor_zeny_increase)), int(payload.zeny_increase_threshold),
            ),
        )
        return int(cur.lastrowid or 0)

    conn = db_connect(cfg)
    try:
        cur = conn.cursor(dictionary=True)
        main_id = _insert_case(cur, wt, int(payload.char_id or 0), int(payload.account_id or 0), int(payload.nameid or 0), str(payload.label or ""), str(payload.notes or ""))
        created_related: list[int] = []

        if bool(payload.auto_create_related):
            if wt == "character" and int(payload.account_id or 0) > 0:
                cur.execute("SELECT id FROM acp_watch_cases WHERE watch_type='account' AND account_id=%s LIMIT 1", (int(payload.account_id),))
                if not cur.fetchone():
                    rid = _insert_case(
                        cur,
                        "account",
                        0,
                        int(payload.account_id),
                        0,
                        f"Auto from char #{int(payload.char_id or 0)}",
                        f"Auto-created from character watch case #{main_id}",
                    )
                    created_related.append(rid)

            if wt == "account" and int(payload.account_id or 0) > 0:
                lim = min(max(int(payload.max_related_chars or 3), 1), 20)
                cur.execute(
                    "SELECT char_id, name FROM `char` WHERE account_id=%s ORDER BY char_id DESC LIMIT %s",
                    (int(payload.account_id), lim),
                )
                chars = cur.fetchall() or []
                for ch in chars:
                    cid = int((ch or {}).get("char_id") or 0)
                    if cid <= 0:
                        continue
                    cur.execute("SELECT id FROM acp_watch_cases WHERE watch_type='character' AND char_id=%s LIMIT 1", (cid,))
                    if cur.fetchone():
                        continue
                    rid = _insert_case(
                        cur,
                        "character",
                        cid,
                        int(payload.account_id),
                        0,
                        f"Auto from account #{int(payload.account_id)} - {str((ch or {}).get('name') or '')}"[:191],
                        f"Auto-created from account watch case #{main_id}",
                    )
                    created_related.append(rid)

        conn.commit()
        cur.close()
        return {"ok": True, "id": main_id, "related_ids": created_related}
    finally:
        conn.close()


@app.get("/api/watch/cases")
def watch_cases_list(request: Request) -> dict[str, Any]:
    _require_permission(request, "view_watch")
    cfg = load_config()
    ensure_watch_tables(cfg)
    conn = db_connect(cfg)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, created_at, updated_at, created_by, watch_type, char_id, account_id, nameid, label, check_every_seconds, severity, notify_discord, notify_telegram, enabled, notes, checks_count, monitor_any_change, monitor_item_movement, item_movement_threshold, monitor_failed_logins, failed_login_threshold, monitor_zeny_increase, zeny_increase_threshold, last_checked_at, last_notified_at FROM acp_watch_cases ORDER BY id DESC LIMIT 500")
        rows = cur.fetchall() or []
        cur.close()
        return {"items": rows}
    finally:
        conn.close()


@app.post("/api/watch/cases/{case_id}/run")
def watch_case_run(case_id: int, request: Request) -> dict[str, Any]:
    _require_permission(request, "manage_watch")
    cfg = load_config()
    ensure_watch_tables(cfg)
    conn = db_connect(cfg)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM acp_watch_cases WHERE id=%s LIMIT 1", (int(case_id),))
        case = cur.fetchone()
        if not case:
            cur.close()
            raise HTTPException(status_code=404, detail="watch case not found")
        prev_raw = case.get("last_snapshot")
        prev = {}
        if prev_raw:
            try:
                prev = json.loads(prev_raw) if isinstance(prev_raw, str) else dict(prev_raw)
            except Exception:
                prev = {}
        try:
            curr = _fetch_watch_snapshot(cfg, case)
            changed = _watch_diff_keys(prev, curr) if prev else []
            should_notify, criteria_summary, details = _watch_should_notify(case, prev, curr)
            notified = {"discord": False, "telegram": False}
            if should_notify:
                summary = f"Manual run: {criteria_summary}"[:255]
                notified = _send_watch_event_webhooks(cfg, case, summary, details)
                cur.execute("INSERT INTO acp_watch_events (case_id, event_type, severity, summary, details_json, notified_discord, notified_telegram) VALUES (%s,'manual_change_detected',%s,%s,%s,%s,%s)",
                            (int(case_id), str(case.get("severity") or "medium"), summary[:255], json.dumps(details, ensure_ascii=False), int(notified["discord"]), int(notified["telegram"])))
                cur.execute("UPDATE acp_watch_cases SET last_notified_at=NOW() WHERE id=%s", (int(case_id),))
            cur.execute("UPDATE acp_watch_cases SET last_snapshot=%s, last_checked_at=NOW(), checks_count=checks_count+1 WHERE id=%s", (json.dumps(curr, ensure_ascii=False), int(case_id)))
            conn.commit()
            cur.close()
            return {"ok": True, "changed_fields": changed, "notified": notified}
        except Exception as err:
            msg = f"Manual watch run error: {err}"[:255]
            cur.execute(
                "INSERT INTO acp_watch_events (case_id, event_type, severity, summary, details_json, notified_discord, notified_telegram) VALUES (%s,'watch_error','high',%s,%s,0,0)",
                (int(case_id), msg, json.dumps({"error": str(err)}, ensure_ascii=False)),
            )
            cur.execute("UPDATE acp_watch_cases SET last_checked_at=NOW(), checks_count=checks_count+1 WHERE id=%s", (int(case_id),))
            conn.commit()
            cur.close()
            raise HTTPException(status_code=400, detail=str(err))
    finally:
        conn.close()


@app.get("/api/watch/cases/{case_id}")
def watch_case_details(case_id: int, request: Request) -> dict[str, Any]:
    _require_permission(request, "view_watch")
    cfg = load_config()
    ensure_watch_tables(cfg)
    conn = db_connect(cfg)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM acp_watch_cases WHERE id=%s LIMIT 1", (int(case_id),))
        case = cur.fetchone()
        if not case:
            cur.close()
            raise HTTPException(status_code=404, detail="watch case not found")
        cur.execute("SELECT COUNT(*) AS c FROM acp_watch_events WHERE case_id=%s", (int(case_id),))
        events_count = int((cur.fetchone() or {}).get("c") or 0)
        cur.execute("SELECT COUNT(*) AS c FROM acp_watch_events WHERE case_id=%s AND event_type='watch_error'", (int(case_id),))
        errors_count = int((cur.fetchone() or {}).get("c") or 0)
        cur.execute("SELECT event_time, event_type, summary FROM acp_watch_events WHERE case_id=%s ORDER BY event_time DESC LIMIT 1", (int(case_id),))
        latest_event = cur.fetchone() or {}
        cur.close()
        auto_rules = {
            "monitor_any_change": bool(case.get("monitor_any_change")),
            "monitor_item_movement": bool(case.get("monitor_item_movement")),
            "item_movement_threshold": int(case.get("item_movement_threshold") or 0),
            "monitor_failed_logins": bool(case.get("monitor_failed_logins")),
            "failed_login_threshold": int(case.get("failed_login_threshold") or 0),
            "monitor_zeny_increase": bool(case.get("monitor_zeny_increase")),
            "zeny_increase_threshold": int(case.get("zeny_increase_threshold") or 0),
        }
        return {
            "case": case,
            "overview": {
                "checks_count": int(case.get("checks_count") or 0),
                "events_count": events_count,
                "errors_count": errors_count,
                "latest_event": latest_event,
                "automation_rules": auto_rules,
            },
        }
    finally:
        conn.close()


@app.delete("/api/watch/cases/{case_id}")
def watch_case_delete(case_id: int, request: Request) -> dict[str, Any]:
    _require_permission(request, "manage_watch")
    cfg = load_config()
    ensure_watch_tables(cfg)
    conn = db_connect(cfg)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM acp_watch_events WHERE case_id=%s", (int(case_id),))
        cur.execute("DELETE FROM acp_watch_cases WHERE id=%s", (int(case_id),))
        deleted = int(cur.rowcount or 0)
        conn.commit()
        cur.close()
        return {"ok": deleted > 0, "deleted": deleted}
    finally:
        conn.close()


@app.get("/api/watch/cases/{case_id}/events")
def watch_case_events(case_id: int, request: Request, limit: int = 100) -> dict[str, Any]:
    _require_permission(request, "view_watch")
    cfg = load_config()
    ensure_watch_tables(cfg)
    conn = db_connect(cfg)
    try:
        cur = conn.cursor(dictionary=True)
        lim = min(max(int(limit), 1), 500)
        cur.execute("SELECT id, case_id, event_time, event_type, severity, summary, details_json, notified_discord, notified_telegram FROM acp_watch_events WHERE case_id=%s ORDER BY event_time DESC LIMIT %s", (int(case_id), lim))
        rows = cur.fetchall() or []
        cur.close()
        return {"items": rows}
    finally:
        conn.close()


@app.get("/api/watch/cases/{case_id}/export.txt")
def watch_case_export(case_id: int, request: Request, limit: int = 300) -> PlainTextResponse:
    _require_permission(request, "view_watch")
    cfg = load_config()
    ensure_watch_tables(cfg)
    conn = db_connect(cfg)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM acp_watch_cases WHERE id=%s LIMIT 1", (int(case_id),))
        case = cur.fetchone()
        if not case:
            cur.close()
            raise HTTPException(status_code=404, detail="watch case not found")
        lim = min(max(int(limit), 1), 2000)
        cur.execute("SELECT event_time, event_type, severity, summary, notified_discord, notified_telegram FROM acp_watch_events WHERE case_id=%s ORDER BY event_time DESC LIMIT %s", (int(case_id), lim))
        events = cur.fetchall() or []
        cur.close()
        lines = []
        lines.append(f"AggregatorCP Watch Case Export")
        lines.append(f"Case ID: {case.get('id')}")
        lines.append(f"Type: {case.get('watch_type')}")
        lines.append(f"Label: {case.get('label') or ''}")
        lines.append(f"Char ID: {int(case.get('char_id') or 0)} | Account ID: {int(case.get('account_id') or 0)} | Item ID: {int(case.get('nameid') or 0)}")
        lines.append(f"Frequency(sec): {int(case.get('check_every_seconds') or 0)} | Severity: {case.get('severity')}")
        lines.append(f"Created by: {case.get('created_by')} | Created at: {case.get('created_at')}")
        lines.append("-" * 80)
        for ev in events:
            lines.append(f"[{ev.get('event_time')}] [{ev.get('severity')}] {ev.get('event_type')} :: {ev.get('summary')} | discord={int(ev.get('notified_discord') or 0)} telegram={int(ev.get('notified_telegram') or 0)}")
        return PlainTextResponse("\n".join(lines), media_type="text/plain; charset=utf-8")
    finally:
        conn.close()


@app.get("/api/panel-readme")
def panel_readme() -> dict[str, Any]:
    readme = _repo_root() / "AggregatorCP" / "README.md"
    text = "README unavailable."
    if readme.exists():
        text = readme.read_text(encoding="utf-8", errors="ignore")
    return {"content": text}
