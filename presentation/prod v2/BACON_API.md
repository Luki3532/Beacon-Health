# BACON API Reference

**B**eacon **A**PI **C**redential **O**nline **N**avigation · Version **1.0** · Beacon Health System

> **Demonstration document.** BACON is a proposed product. All hosts, tokens,
> people, employee IDs, NPIs, ARRT IDs, and results below are **fictional
> sample data** written for a presentation. No such service is running, and
> the sample ARRT responses do not reflect a live ARRT integration.

---

## Contents

1. [Overview](#1-overview)
2. [Getting started](#2-getting-started)
3. [Authentication](#3-authentication)
4. [Conventions](#4-conventions)
5. [Employees](#5-employees)
6. [Credentials](#6-credentials)
7. [Verifications](#7-verifications)
8. [Screening](#8-screening)
9. [Managers](#9-managers)
10. [Notifications](#10-notifications)
11. [Webhooks](#11-webhooks)
12. [Summary](#12-summary)
13. [Errors](#13-errors)
14. [Rate limits](#14-rate-limits)
15. [Client examples](#15-client-examples)
16. [Changelog](#16-changelog)

---

## 1. Overview

BACON gives Beacon systems, including Oracle Fusion HCM, one place to answer:

- **Is this clinician's credential current?** Status, expiration, and days remaining.
- **Who verified it, when, and against what source?** An append-only audit ledger.
- **Is anyone excluded or sanctioned?** OIG LEIE, Michigan sanctions, and the ARRT disciplinary list.
- **Who needs a warning?** Manager notifications and webhooks before a credential lapses.

### Environments

| Environment | Base URL | Purpose |
| --- | --- | --- |
| Production | `https://api.beaconhealth.example/bacon/v1` | Live Beacon data |
| Sandbox | `https://sandbox.api.beaconhealth.example/bacon/v1` | Test data; no email is sent |

### Resource model

```
Manager ──< Employee ──< Credential ──< Verification
                │
                └──< ScreeningResult >── ScreeningSource
```

---

## 2. Getting started

**1.** Request a token.

```bash
curl -X POST https://api.beaconhealth.example/oauth/token \
  -d grant_type=client_credentials \
  -d client_id=hcm-integration-7f3a \
  -d client_secret=$BACON_CLIENT_SECRET \
  -d "scope=credentials:read screening:read"
```

**2.** Make your first call.

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.beaconhealth.example/bacon/v1/summary"
```

```json
{
  "asOf": "2026-10-04",
  "employees": 4812,
  "credentials": { "current": 4501, "due": 214, "lapsed": 19, "unknown": 78 },
  "screeningFlags": 6
}
```

---

## 3. Authentication

BACON uses OAuth 2.0 **client credentials**. Send the access token in every request:

```
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6ImJhY29uLTIwMjYtMDEifQ...
```

### Request a token

`POST /oauth/token` — `application/x-www-form-urlencoded`

| Field | Required | Description |
| --- | --- | --- |
| `grant_type` | yes | Always `client_credentials` |
| `client_id` | yes | Issued when your integration is registered |
| `client_secret` | yes | Keep server-side; never ship in browser code |
| `scope` | no | Space-separated list; defaults to all scopes granted to the client |

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsImtpZCI6ImJhY29uLTIwMjYtMDEifQ...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "credentials:read screening:read"
}
```

### Scopes

| Scope | Allows |
| --- | --- |
| `credentials:read` | Read employees, credentials, managers, summary |
| `verifications:write` | Record verification results |
| `screening:read` | Read screening sources, matches, and runs |
| `screening:run` | Start a sanctions refresh; resolve matches |
| `notifications:send` | Send expiration warnings |
| `webhooks:manage` | Create and delete webhook subscriptions |

---

## 4. Conventions

- **Format:** JSON (`application/json`), UTF-8.
- **Dates:** ISO 8601, `YYYY-MM-DD`; timestamps include a UTC offset.
- **Credential status:** `CURRENT`, `DUE` (within the warning window, default 30 days), `LAPSED`, or `UNKNOWN` (no verified source).
- **Provenance:** Credential data always includes `source`. Values that are not verified are `null`; they are never guessed.
- **Pagination:** Cursor-based. Use `limit` (default 50, max 200) and `cursor`.

```json
{
  "data": [ ],
  "page": { "limit": 50, "next": "eyJvIjoxMDB9", "hasMore": true }
}
```

- **Idempotency:** Send `Idempotency-Key: <uuid>` on `POST` requests. A retry with the same key returns the original result and never double-logs or double-emails. Keys are kept for 24 hours.
- **Tracing:** Every response includes `X-Request-Id`. Quote it when contacting support.
- **Versioning:** The version is in the path (`/v1`). Backward-compatible additions do not change the version.

---

## 5. Employees

### List employees

`GET /employees` · scope `credentials:read`

| Query | Type | Description |
| --- | --- | --- |
| `status` | string | Comma list: `current`, `due`, `lapsed`, `unknown` |
| `manager` | string | Manager ID, e.g. `mgr_204` |
| `department` | string | Department code |
| `flagged` | boolean | Only employees with a screening flag |
| `q` | string | Name or employee ID search |
| `limit`, `cursor` | | Pagination |

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.beaconhealth.example/bacon/v1/employees?status=due,lapsed&manager=mgr_204"
```

```json
{
  "asOf": "2026-10-04",
  "windowDays": 30,
  "data": [
    {
      "id": "BHS-20117",
      "name": "Jimmy John",
      "department": "Radiology",
      "manager": { "id": "mgr_204", "name": "Lucas Carpenter" },
      "credential": {
        "status": "DUE",
        "validThru": "2026-10-29",
        "daysRemaining": 25,
        "source": "ARRT_EMPLOYER_FEED"
      },
      "flagged": false
    }
  ],
  "page": { "limit": 50, "next": null, "hasMore": false }
}
```

### Get an employee

`GET /employees/{employeeId}` · scope `credentials:read`

```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://api.beaconhealth.example/bacon/v1/employees/BHS-20117
```

```json
{
  "id": "BHS-20117",
  "name": "Jimmy John",
  "department": "Radiology",
  "title": "Radiologic Technologist",
  "manager": { "id": "mgr_204", "name": "Lucas Carpenter", "email": "l.carpenter@beaconhealth.example" },
  "hireDate": "2021-05-17",
  "credential": {
    "status": "DUE",
    "type": "ARRT Registration",
    "designation": "R.T.(R)(ARRT)",
    "validThru": "2026-10-29",
    "daysRemaining": 25,
    "source": "ARRT_EMPLOYER_FEED",
    "lastVerifiedOn": "2026-09-22",
    "lastVerifiedBy": "service:arrt-feed"
  },
  "screening": { "federal": 0, "michigan": 0, "arrt": 0, "flagged": false },
  "links": {
    "credentials": "/bacon/v1/employees/BHS-20117/credentials",
    "verifications": "/bacon/v1/employees/BHS-20117/verifications",
    "screening": "/bacon/v1/employees/BHS-20117/screening"
  }
}
```

---

## 6. Credentials

### List an employee's credentials

`GET /employees/{employeeId}/credentials` · scope `credentials:read`

```json
{
  "employeeId": "BHS-20117",
  "data": [
    {
      "id": "cred_9Q2L4M",
      "type": "ARRT Registration",
      "designation": "R.T.(R)(ARRT)",
      "status": "DUE",
      "validThru": "2026-10-29",
      "daysRemaining": 25,
      "source": "ARRT_EMPLOYER_FEED"
    },
    {
      "id": "cred_3B8TXP",
      "type": "State License",
      "designation": "MI Limited Radiography License",
      "status": "CURRENT",
      "validThru": "2027-06-30",
      "daysRemaining": 269,
      "source": "MANUAL_VERIFICATION"
    }
  ]
}
```

### ARRT certification and registration

`GET /employees/{employeeId}/credentials/arrt` · scope `credentials:read`

```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://api.beaconhealth.example/bacon/v1/employees/BHS-20117/credentials/arrt
```

```json
{
  "employeeId": "BHS-20117",
  "arrtId": "2481937",
  "registrationStatus": "REGISTERED",
  "disciplineStatus": "NONE",
  "designations": [
    { "code": "R.T.(R)(ARRT)", "pathway": "Radiography", "earnedOn": "2021-04-02" }
  ],
  "registrationYear": "2025-2026",
  "validThru": "2026-10-29",
  "daysRemaining": 25,
  "continuingEducation": { "required": 24, "completed": 21, "cycleEnds": "2026-10-29" },
  "retrievedAt": "2026-10-04T05:30:12-04:00",
  "source": "ARRT_EMPLOYER_FEED"
}
```

| Field | Values |
| --- | --- |
| `registrationStatus` | `REGISTERED`, `LAPSED`, `NOT_FOUND`, `UNDER_REVIEW` |
| `disciplineStatus` | `NONE`, `SANCTIONED` |
| `source` | `ARRT_EMPLOYER_FEED` or `MANUAL_VERIFICATION` |

---

## 7. Verifications

The verification ledger is **append-only**. Corrections are new entries, never edits.
Automated systems do not complete ARRT's public lookup check; a person performs
any manual lookup and records the result.

### Record a verification

`POST /verifications` · scope `verifications:write` · supports `Idempotency-Key`

| Field | Required | Description |
| --- | --- | --- |
| `employeeId` | yes | Employee being verified |
| `outcome` | yes | `verified`, `discrepancy`, or `not-found` |
| `credentials` | if `verified` | e.g. `R.T.(R)(ARRT)` |
| `validThru` | if `verified` | `MM/YYYY` |
| `verifiedOn` | yes | Lookup date; cannot be in the future |
| `verifiedBy` | yes | Name of the person who performed the lookup |
| `source` | yes | e.g. `ARRT primary source verification` |
| `notes` | no | Free text |

```bash
curl -X POST https://api.beaconhealth.example/bacon/v1/verifications \
  -H "Authorization: Bearer $TOKEN" \
  -H "Idempotency-Key: 7c1e4b52-2b1a-4d6e-9d0a-1f3b6a9e5c11" \
  -H "Content-Type: application/json" \
  -d '{
    "employeeId": "BHS-10482",
    "outcome": "verified",
    "credentials": "R.T.(R)(ARRT)",
    "validThru": "03/2027",
    "verifiedOn": "2026-10-04",
    "verifiedBy": "Teresa Whitfield",
    "source": "ARRT primary source verification",
    "notes": "Matched on name and ARRT ID."
  }'
```

```http
HTTP/1.1 201 Created
Location: /bacon/v1/verifications/ver_01JA4Z7K
X-Request-Id: req_5d2c91
```

```json
{
  "id": "ver_01JA4Z7K",
  "loggedAt": "2026-10-04T14:20:11-04:00",
  "employeeId": "BHS-10482",
  "outcome": "verified",
  "credentials": "R.T.(R)(ARRT)",
  "validThru": "03/2027",
  "verifiedOn": "2026-10-04",
  "verifiedBy": "Teresa Whitfield",
  "source": "ARRT primary source verification",
  "resultingStatus": "CURRENT",
  "daysRemaining": 178
}
```

### List verifications

`GET /employees/{employeeId}/verifications` · scope `credentials:read`

```json
{
  "data": [
    {
      "id": "ver_01JA4Z7K",
      "loggedAt": "2026-10-04T14:20:11-04:00",
      "outcome": "verified",
      "verifiedBy": "Teresa Whitfield",
      "source": "ARRT primary source verification",
      "validThru": "03/2027"
    },
    {
      "id": "ver_01J7R2D9",
      "loggedAt": "2026-03-12T09:02:44-04:00",
      "outcome": "verified",
      "verifiedBy": "Teresa Whitfield",
      "source": "ARRT primary source verification",
      "validThru": "03/2027"
    }
  ],
  "page": { "limit": 50, "next": null, "hasMore": false }
}
```

### Get a verification

`GET /verifications/{verificationId}` · scope `credentials:read`

---

## 8. Screening

### List sources

`GET /screening/sources` · scope `screening:read`

```json
{
  "data": [
    {
      "key": "leie",
      "name": "OIG LEIE - Federal Exclusions",
      "status": "CONNECTED",
      "lastSync": "2026-10-03",
      "records": 84001,
      "refresh": "Monthly"
    },
    {
      "key": "michigan-sanctions",
      "name": "Michigan LARA Sanctions",
      "status": "CONNECTED",
      "lastSync": "2026-10-02",
      "records": 3190,
      "refresh": "Weekly"
    },
    {
      "key": "arrt-sanctions",
      "name": "ARRT - Disciplinary Sanctioned List",
      "status": "CONNECTED",
      "lastSync": "2026-10-04",
      "records": 2147,
      "refresh": "Daily"
    }
  ]
}
```

### Start a refresh

`POST /screening/sources/{sourceKey}/runs` · scope `screening:run`

```bash
curl -X POST \
  https://api.beaconhealth.example/bacon/v1/screening/sources/arrt-sanctions/runs \
  -H "Authorization: Bearer $TOKEN"
```

```http
HTTP/1.1 202 Accepted
Location: /bacon/v1/screening/runs/run_8f21c4
```

```json
{
  "id": "run_8f21c4",
  "source": "arrt-sanctions",
  "status": "running",
  "startedAt": "2026-10-04T14:31:02-04:00"
}
```

### Get a run

`GET /screening/runs/{runId}` · scope `screening:read`

```json
{
  "id": "run_8f21c4",
  "source": "arrt-sanctions",
  "status": "succeeded",
  "startedAt": "2026-10-04T14:31:02-04:00",
  "completedAt": "2026-10-04T14:31:09-04:00",
  "sourceRows": 2147,
  "employeesScreened": 4812,
  "newMatches": 1,
  "note": "Name matches are leads for review, not proof of identity."
}
```

A truncated or malformed upstream list produces `"status": "failed"` and
keeps the previous results in place.

### List matches

`GET /screening/matches` · scope `screening:read`

| Query | Description |
| --- | --- |
| `state` | `open`, `confirmed`, `dismissed` |
| `source` | Source key |
| `employeeId` | One employee |

```json
{
  "data": [
    {
      "id": "match_61ac07",
      "employeeId": "BHS-30551",
      "source": "arrt-sanctions",
      "state": "open",
      "confidence": "NAME_ONLY",
      "matchedOn": ["lastName", "firstName"],
      "sourceRecord": {
        "name": "Daniel R. Okafor",
        "state": "OH",
        "sanction": "Reprimand",
        "date": "2022-08-15"
      },
      "createdAt": "2026-10-04T14:31:08-04:00"
    }
  ]
}
```

### Resolve a match

`POST /screening/matches/{matchId}/resolution` · scope `screening:run`

```bash
curl -X POST \
  https://api.beaconhealth.example/bacon/v1/screening/matches/match_61ac07/resolution \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "decision": "dismissed",
    "reviewedBy": "Priya Raman",
    "reason": "Different state and birth date; not the same person."
  }'
```

```json
{
  "id": "match_61ac07",
  "state": "dismissed",
  "reviewedBy": "Priya Raman",
  "reviewedAt": "2026-10-04T14:44:50-04:00",
  "reason": "Different state and birth date; not the same person."
}
```

### Employee screening results

`GET /employees/{employeeId}/screening`

```json
{
  "employeeId": "BHS-30551",
  "federal": { "checkedOn": "2026-10-03", "matches": 0 },
  "michigan": { "checkedOn": "2026-10-02", "matches": 0 },
  "arrt": { "checkedOn": "2026-10-04", "matches": 1, "openMatchIds": ["match_61ac07"] },
  "flagged": true
}
```

### NPPES identity lookup

`GET /identity/nppes?employeeId={id}` · scope `screening:read`

```json
{
  "employeeId": "BHS-10482",
  "cachedAt": "2026-09-30",
  "candidates": [
    {
      "npi": "1234567893",
      "name": "Maria Delgado",
      "taxonomy": "Radiologic Technologist",
      "state": "MI"
    }
  ],
  "note": "Candidates are identity leads. They do not confirm a credential."
}
```

---

## 9. Managers

### List managers

`GET /managers` · scope `credentials:read`

```json
{
  "data": [
    { "id": "mgr_204", "name": "Lucas Carpenter", "email": "l.carpenter@beaconhealth.example", "reports": 2, "lapsed": 0, "due": 1, "flagged": 0 },
    { "id": "mgr_118", "name": "Kimberly Gjeltema", "email": "k.gjeltema@beaconhealth.example", "reports": 31, "lapsed": 2, "due": 5, "flagged": 1 }
  ]
}
```

### Manager's direct reports

`GET /managers/{managerId}/reports`

```json
{
  "manager": { "id": "mgr_204", "name": "Lucas Carpenter" },
  "total": 2,
  "data": [
    { "id": "BHS-20117", "name": "Jimmy John",  "validThru": "2026-10-29", "daysRemaining": 25, "status": "DUE" },
    { "id": "BHS-20118", "name": "Wendy King",  "validThru": "2026-12-03", "daysRemaining": 60, "status": "CURRENT" }
  ]
}
```

---

## 10. Notifications

### Send expiration warnings

`POST /notifications/expiration-warnings` · scope `notifications:send` · supports `Idempotency-Key`

Sends one message per manager listing only the employees who are lapsed or
inside the warning window.

| Field | Default | Description |
| --- | --- | --- |
| `windowDays` | `30` | Warn when this many days or fewer remain |
| `managerIds` | all | Limit to specific managers |
| `dryRun` | `false` | Return recipients without sending |

```bash
curl -X POST https://api.beaconhealth.example/bacon/v1/notifications/expiration-warnings \
  -H "Authorization: Bearer $TOKEN" \
  -H "Idempotency-Key: 3a8d2f10-61c7-4e1b-b0a2-9d4f0c7e2b66" \
  -H "Content-Type: application/json" \
  -d '{ "windowDays": 30, "managerIds": ["mgr_204"], "dryRun": false }'
```

```json
{
  "id": "ntf_4c91ab",
  "asOf": "2026-10-04",
  "status": "queued",
  "deliveries": [
    {
      "manager": { "id": "mgr_204", "name": "Lucas Carpenter" },
      "recipient": "l.carpenter@beaconhealth.example",
      "employees": [
        { "id": "BHS-20117", "name": "Jimmy John", "validThru": "2026-10-29", "daysRemaining": 25 }
      ],
      "status": "queued"
    }
  ],
  "skipped": [
    { "id": "BHS-20118", "name": "Wendy King", "reason": "60 days remaining; outside the 30-day window." }
  ]
}
```

### Get delivery status

`GET /notifications/{notificationId}`

Delivery states: `queued`, `accepted` (mail server accepted it), `failed`.
`accepted` means the receiving mail server took the message; it is not a guarantee of inbox placement.

---

## 11. Webhooks

Subscribe instead of polling.

### Create a subscription

`POST /webhooks` · scope `webhooks:manage`

```bash
curl -X POST https://api.beaconhealth.example/bacon/v1/webhooks \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "url": "https://hcm.beaconhealth.example/hooks/bacon",
    "events": ["credential.due", "credential.lapsed", "screening.match", "verification.recorded"]
  }'
```

```json
{
  "id": "wh_5e07b2",
  "url": "https://hcm.beaconhealth.example/hooks/bacon",
  "events": ["credential.due", "credential.lapsed", "screening.match", "verification.recorded"],
  "secret": "whsec_3fT9kQ7vN2mXc81LpR4aZ6dY",
  "createdAt": "2026-10-04T14:50:00-04:00"
}
```

The `secret` is shown once. Also: `GET /webhooks` and `DELETE /webhooks/{id}`.

### Events

| Event | Fires when |
| --- | --- |
| `credential.due` | A credential enters the warning window |
| `credential.lapsed` | A credential passes its expiration date |
| `screening.match` | A new open screening match is found |
| `verification.recorded` | A verification is added to the ledger |

```json
{
  "id": "evt_71d3c0",
  "type": "credential.due",
  "occurredAt": "2026-09-29T06:00:00-04:00",
  "data": {
    "employeeId": "BHS-20117",
    "name": "Jimmy John",
    "validThru": "2026-10-29",
    "daysRemaining": 30,
    "managerId": "mgr_204"
  }
}
```

### Verify the signature

Each delivery includes `BACON-Signature: t=<unix>,v1=<hmac>`. The HMAC is
SHA-256 over `"<t>.<raw body>"` using your subscription `secret`. Reject
timestamps older than 5 minutes.

```python
import hashlib, hmac, time

def valid(secret: str, header: str, body: bytes) -> bool:
    parts = dict(p.split("=", 1) for p in header.split(","))
    if abs(time.time() - int(parts["t"])) > 300:
        return False
    expected = hmac.new(secret.encode(), f"{parts['t']}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts["v1"])
```

Respond with any `2xx` within 10 seconds. Failed deliveries retry with
exponential backoff for up to 24 hours.

---

## 12. Summary

`GET /summary` · scope `credentials:read`

| Query | Description |
| --- | --- |
| `asOf` | Evaluate status as of this date (default today) |
| `department` | Limit to one department |

```json
{
  "asOf": "2026-10-04",
  "employees": 4812,
  "managers": 96,
  "credentials": { "current": 4501, "due": 214, "lapsed": 19, "unknown": 78 },
  "screening": {
    "flagged": 6,
    "sources": [
      { "key": "leie", "lastSync": "2026-10-03", "matches": 2 },
      { "key": "michigan-sanctions", "lastSync": "2026-10-02", "matches": 3 },
      { "key": "arrt-sanctions", "lastSync": "2026-10-04", "matches": 1 }
    ]
  },
  "verifications": { "last30Days": 412 }
}
```

---

## 13. Errors

Errors use `application/problem+json`.

```json
{
  "type": "https://api.beaconhealth.example/problems/validation",
  "title": "Validation failed",
  "status": 422,
  "detail": "validThru is required when outcome is 'verified'.",
  "instance": "/bacon/v1/verifications",
  "requestId": "req_5d2c91",
  "errors": [
    { "field": "validThru", "message": "Required in MM/YYYY format." }
  ]
}
```

| Status | Meaning |
| --- | --- |
| `200` `201` `202` | Success, created, accepted for processing |
| `400` | Malformed request |
| `401` | Missing or expired token |
| `403` | Token lacks the required scope |
| `404` | Resource not found |
| `409` | Idempotency key reused with a different request |
| `422` | Validation failed |
| `429` | Rate limit exceeded; see `Retry-After` |
| `503` | Upstream source unavailable; retry later |

---

## 14. Rate limits

| Client type | Limit |
| --- | --- |
| Standard | 600 requests / minute |
| Bulk read | 60 requests / minute, up to 200 records per page |

Headers on every response:

```
RateLimit-Limit: 600
RateLimit-Remaining: 571
RateLimit-Reset: 38
```

On `429`, wait `Retry-After` seconds before retrying.

---

## 15. Client examples

### Python

```python
import requests

BASE = "https://api.beaconhealth.example/bacon/v1"

token = requests.post(
    "https://api.beaconhealth.example/oauth/token",
    data={"grant_type": "client_credentials",
          "client_id": "hcm-integration-7f3a",
          "client_secret": "<secret>"},
).json()["access_token"]

resp = requests.get(
    f"{BASE}/employees",
    headers={"Authorization": f"Bearer {token}"},
    params={"status": "due,lapsed"},
)
resp.raise_for_status()
for e in resp.json()["data"]:
    c = e["credential"]
    print(e["name"], c["status"], c["validThru"], c["daysRemaining"])
```

### JavaScript

```javascript
const res = await fetch(
  "https://api.beaconhealth.example/bacon/v1/employees/BHS-20117",
  { headers: { Authorization: `Bearer ${token}` } }
);
if (!res.ok) throw new Error((await res.json()).detail);
const employee = await res.json();
console.log(employee.credential.status, employee.credential.daysRemaining);
```

---

## 16. Changelog

| Version | Date | Changes |
| --- | --- | --- |
| **1.0** | 2026-10-04 | Initial release: employees, credentials, verification ledger, screening, managers, notifications, webhooks |

**Support:** `bacon-support@beaconhealth.example` — include the `X-Request-Id` from the failing call.
