# AggregatorCP Bridge Service

Simple, reusable bridge API that receives signed admin actions and enqueues game commands for rAthena execution.

## Purpose

- Accept AggregatorCP Companion Service actions (`@mute`, `@kick`, `@ban`) over HTTP.
- Verify HMAC signature (`X-Bridge-Signature`).
- Persist actions to SQL queue table `acp_gm_command_queue`.
- Let an in-game NPC/script executor apply queued commands.

## Endpoint contract

- `POST /bridge/admin-action`
- Headers:
  - `Content-Type: application/json`
  - `X-Bridge-Signature: <hex hmac sha256>`
- Body:

```json
{
  "actionId": "unique-action-id",
  "gmCommand": "@mute",
  "targetCharacterId": 150001,
  "reason": "spam",
  "reasonMode": "log|notify",
  "durationValue": 10,
  "durationUnit": "minutes|days|none",
  "requestedBy": "companion-service"
}
```

## Required environment variables

- `TC_BRIDGE_SHARED_SECRET` (must match AggregatorCP Companion Service)

## Optional environment variables

- `TC_BRIDGE_DB_HOST` (default: `127.0.0.1`)
- `TC_BRIDGE_DB_PORT` (default: `3306`)
- `TC_BRIDGE_DB_USER` (default: `rathena`)
- `TC_BRIDGE_DB_PASSWORD` (default: empty)
- `TC_BRIDGE_DB_NAME` (default: `ragnarok`)
- `TC_BRIDGE_REQUIRE_SIGNATURE` (`1` default, set `0` only for local testing)
- `TC_BRIDGE_DRY_RUN` (`1` validates payload/signature only, skips SQL enqueue)

## Run

```bash
python3 -m pip install -r AggregatorCP/bridge-service/requirements.txt
python3 -m uvicorn app:app --app-dir AggregatorCP/bridge-service --host 127.0.0.1 --port 8099
```

## AggregatorCP Companion Service configuration

Set these in the same environment where unified AggregatorCP Companion Service runs:

```bat
setx TC_BRIDGE_ENDPOINT_URL "http://127.0.0.1:8099/bridge/admin-action"
setx TC_BRIDGE_SHARED_SECRET "REPLACE_WITH_LONG_RANDOM_SECRET"
```

(Use the same secret in bridge service env.)

## SQL queue table

Bridge auto-creates:

- `acp_gm_command_queue`
  - `action_id` unique id
  - `gm_command` one of `@mute/@kick/@ban`
  - `target_char_id`
  - `reason` + `reason_mode` (`log|notify`)
  - `duration_value` + `duration_unit`
  - `status` (`pending|applied|failed`)
  - `attempts`, `last_error`, `applied_at`

## Reuse in other projects

This service is framework-agnostic and can be reused if your producer can:

1. Send same JSON contract
2. Sign body with HMAC SHA256
3. Share the same secret

You can swap the SQL enqueue with direct game API/RCON execution if your server stack supports it.
