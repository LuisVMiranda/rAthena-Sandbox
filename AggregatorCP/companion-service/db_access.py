from __future__ import annotations

from typing import Any, Callable


class LogsDomainDAO:
    def __init__(self, connect_logs: Callable[[Any], Any], connect_main: Callable[[Any], Any]):
        self.connect_logs = connect_logs
        self.connect_main = connect_main

    def table_columns(self, cfg: Any, table: str) -> list[str]:
        conn = self.connect_logs(cfg)
        try:
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
        finally:
            conn.close()

    def query_table(self, cfg: Any, table: str, select_cols: list[str], where: str, params: list[Any], order_col: str, limit: int, offset: int) -> list[dict[str, Any]]:
        conn = self.connect_logs(cfg)
        try:
            cur = conn.cursor(dictionary=True)
            query = f"SELECT {', '.join([f'`{c}`' for c in select_cols])} FROM `{table}`{where} ORDER BY `{order_col}` DESC LIMIT %s OFFSET %s"
            run_params = list(params) + [int(limit), int(offset)]
            cur.execute(query, tuple(run_params))
            rows = cur.fetchall() or []
            cur.close()
            return rows
        finally:
            conn.close()

    def char_name_map(self, cfg: Any, char_ids: set[int]) -> dict[int, str]:
        ids = sorted({int(x) for x in char_ids if int(x) > 0})
        if not ids:
            return {}
        conn = self.connect_main(cfg)
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


class ActionsDomainDAO:
    def __init__(self, connect_main: Callable[[Any], Any]):
        self.connect_main = connect_main

    def action_history_rows(self, cfg: Any, decision: str, limit: int, offset: int) -> tuple[Any, list[dict[str, Any]]]:
        conn = self.connect_main(cfg)
        cur = conn.cursor(dictionary=True)
        dec = (decision or "").strip().lower()
        if dec:
            cur.execute(
                """
                SELECT q.id, q.action_id, q.created_at, q.char_id, q.account_id, q.decision, q.reason, q.reason_mode, q.duration_value, q.duration_unit, q.status, q.bridge_message,
                       (SELECT c.name FROM `char` c WHERE c.char_id=q.char_id LIMIT 1) AS char_name
                FROM acp_admin_action_queue q
                WHERE q.decision=%s
                ORDER BY q.created_at DESC
                LIMIT %s OFFSET %s
                """,
                (dec, int(limit), int(offset)),
            )
        else:
            cur.execute(
                """
                SELECT q.id, q.action_id, q.created_at, q.char_id, q.account_id, q.decision, q.reason, q.reason_mode, q.duration_value, q.duration_unit, q.status, q.bridge_message,
                       (SELECT c.name FROM `char` c WHERE c.char_id=q.char_id LIMIT 1) AS char_name
                FROM acp_admin_action_queue q
                ORDER BY q.created_at DESC
                LIMIT %s OFFSET %s
                """,
                (int(limit), int(offset)),
            )
        rows = cur.fetchall() or []
        cur.close()
        return conn, rows


# Backward-compatible aliases
class LogsRepository(LogsDomainDAO):
    pass


class ActionsRepository(ActionsDomainDAO):
    pass
