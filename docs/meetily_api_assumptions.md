# Meetily Pro Automation API - Assumptions and Contracts

This document records all interface assumptions and confirmed facts regarding the **Meetily Pro Automation API** (version 1.11.0+) and incoming webhooks.

Canonical Source of Truth: The live OpenAPI 3.1 specification at `GET http://127.0.0.1:8420/openapi.json`.

---

## 1. Gateway & Connectivity

| Item | Value / Behavior | Status | Notes |
|---|---|---|---|
| Gateway URL | `http://127.0.0.1:8420` | **CONFIRMED** | Stated in Meetily Developer Guide (Section 4). Disabled by default. |
| Transport | HTTP on loopback interface | **CONFIRMED** | Loopback access stays on local computer; LAN requires explicit approval. |
| Authentication | Bearer token (`Authorization: Bearer <TOKEN>`) | **CONFIRMED** | Generated in Meetily Pro settings. Built-in loopback is read-only. |
| Permission Scopes | `read`, `record`, `write`, `delete` | **CONFIRMED** | `read` scope is sufficient for Meetily Clean Room. |
| Health Endpoint | `GET /health` | **CONFIRMED** | Standard gateway status check. |
| WhoAmI Endpoint | `GET /v1/whoami` | **ASSUMED** | Verifies token validity and returns active scopes. |
| OpenAPI Endpoint | `GET /openapi.json` | **CONFIRMED** | Canonical OpenAPI 3.1 manifest. |

---

## 2. Meeting REST Endpoints & Schemas

| Endpoint | Method | Status | Assumptions & Tolerance |
|---|---|---|---|
| `/v1/meetings` | GET | **ASSUMED** | Returns list of meetings. Tolerates array or `{meetings: []}` or `{items: []}`. Cursor pagination supported. |
| `/v1/meetings/{id}` | GET | **ASSUMED** | Returns meeting metadata. Tolerates fields: `id`/`meetily_id`, `title`/`name`/`subject`, `created_at`/`timestamp`, `duration_seconds`/`duration`. |
| `/v1/meetings/{id}/transcript` | GET | **ASSUMED** | Returns transcript. Tolerates structured segment array (`[{speaker, start_time, end_time, text}]`) or flat string. |
| `/v1/meetings/{id}/summary` | GET | **ASSUMED** | Returns summary notes. Tolerates `{summary_text, action_items, key_decisions}` or flat string. |
| `/v1/meetings/{id}/export` | GET | **ASSUMED** | Full export bundle (`format=json`). |
| `/v1/search` | GET | **ASSUMED** | Full-text query across transcripts. |

*Tolerance Rule:* `backend/meetily/schema_adapter.py` is the single point of conversion into Clean Room's internal models. Unknown fields are ignored; missing optional fields yield `None` without exceptions.

---

## 3. Webhook Delivery & Verification

| Item | Value / Format | Status | Notes |
|---|---|---|---|
| Delivery Trigger | `summary.completed` | **CONFIRMED** | Triggered when AI summary generation finishes (Section 5 & 8 of Guide). |
| Payload Character | Thin notification | **CONFIRMED** | Event does not contain full transcript; contains `resource.id` pointing to meeting. |
| Idempotency Key | `event_id` | **CONFIRMED** | At-least-once delivery requires deduplication on `event_id`. |
| Signature Scheme | HMAC-SHA256 over raw request bytes | **CONFIRMED** | Uses one-time webhook secret generated upon webhook registration. |
| Signature Header | `X-Meetily-Signature` | **UNVERIFIED** | Default assumption. Configurable via `WEBHOOK_SIGNATURE_HEADER`. |
| Signature Prefix | Optional `sha256=` or raw hex | **ASSUMED** | Configurable via `WEBHOOK_SIGNATURE_PREFIX`. |
| Unsigned Mode | Strictly blocked | **CONFIRMED** | Allowed only when `APP_ENV=development` AND `WEBHOOK_ALLOW_UNSIGNED=true`. |

---

## 4. Contract Discovery & Snapshot

To verify these assumptions against a running Meetily Pro instance:
```bash
python scripts/discover_api.py
```
This fetches `http://127.0.0.1:8420/openapi.json` into `docs/openapi.snapshot.json` and runs a schema compatibility test.
