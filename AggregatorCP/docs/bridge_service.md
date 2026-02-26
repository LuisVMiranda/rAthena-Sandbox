# Bridge Service Integration Guide (Reusable)

This guide explains the complete "admin action -> in-game effect" pipeline and is intended to be reused across projects.

## Architecture

1. Companion UI sends decision (`mute`, `kick`, `ban`).
2. Companion Service signs payload and POSTs to bridge endpoint.
3. Bridge Service verifies HMAC and enqueues into `tc_gm_command_queue`.
4. In-game NPC bridge executor consumes queue and executes server command.

## Security contract

- Signature header: `X-Bridge-Signature`
- Algorithm: `HMAC_SHA256(secret, raw_request_body)`
- Shared secret variable on both services: `TC_BRIDGE_SHARED_SECRET`

## Payload contract

```json
{
  "actionId": "uuid-like-string",
  "gmCommand": "@mute|@kick|@ban",
  "targetCharacterId": 12345,
  "reason": "text",
  "reasonMode": "log|notify",
  "durationValue": 10,
  "durationUnit": "minutes|days|none",
  "requestedBy": "companion-service"
}
```

## Windows quick setup

### 1) Start bridge service

```bat
set TC_BRIDGE_SHARED_SECRET=CHANGE_ME
set TC_BRIDGE_DB_HOST=127.0.0.1
set TC_BRIDGE_DB_PORT=3306
set TC_BRIDGE_DB_USER=rathena
set TC_BRIDGE_DB_PASSWORD=your_password
set TC_BRIDGE_DB_NAME=ragnarok
python -m pip install -r TravelerCompanion\bridge-service\requirements.txt
python -m uvicorn app:app --app-dir TravelerCompanion\bridge-service --host 127.0.0.1 --port 8099
```

### 2) Point Companion Service to bridge

```bat
setx TC_BRIDGE_ENDPOINT_URL "http://127.0.0.1:8099/bridge/admin-action"
setx TC_BRIDGE_SHARED_SECRET "CHANGE_ME"
```

Restart Companion Service terminal after `setx`.

### 3) Enable in-game queue executor

Include NPC draft:

- `TravelerCompanion/npc/custom/traveler_companion_bridge_executor_draft.txt`

Then tune command syntax in script for your exact server command format.

## Notes for other projects

To reuse this bridge in another project, keep:

- same JSON payload shape,
- same signature header,
- same queue table semantics.

Then only swap consumer logic (NPC, plugin, webhook, RCON adapter, etc.).


## Admin action behavior

- `mute`: uses `durationValue` as minutes.
- `ban`: uses `durationValue` as days.
- `kick`: ignores duration fields.
- `unmute`: character-based command with no duration field.
- `jail` / `unjail`: character-based commands with no duration field.
- `unban`: account-based DB action (login table), not a queue command.
- `reasonMode=notify`: executor attempts `dispbottom` to the target player in addition to logging.


## Common hiccups (why queueing works but punishment does not)

1. **NPC executor script not loaded** in `npc/custom` includes.
2. **Server script timers disabled/reloaded** after edit (run script reload/restart emulator).
3. **Command syntax mismatch** for your specific `@mute/@ban` command variants (adjust in executor draft).
4. **Permission context**: `atcommand` from scripts may require correct command permissions in your server settings.
5. **Target offline edge-cases**: `dispbottom` notify mode needs attach-able RID/account; punishment command may still apply but notify can be skipped.

Use diagnostics endpoint from panel backend:

- `GET /api/bridge/diagnostics`

If `pending > 0` and `applied == 0`, game-side executor is likely not consuming queue.


Executor timing: draft runs every `OnTimer10000` (10 seconds).
