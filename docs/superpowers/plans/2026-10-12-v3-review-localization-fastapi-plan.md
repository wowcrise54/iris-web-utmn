# IRIS v3 code review, localization, and API migration plan

Date: 2026-10-12  
Scope: active `v3/backend` and `v3/frontend` trees. The root `source/` tree is
the retained v2.4.29 recovery source, not the active v3 application.

This is a read-only static review. No application code or tests were changed or
run, and no Docker containers or data were accessed. Findings below are tied to
the checked-in source and should be revalidated while implementing.

## Confirmed code review findings

### P1 — Public Sentry envelope route can relay to arbitrary hosts

`v3/frontend/src/routes/monitoring/envelope/+server.ts:44-52,124-146` disables
host validation when `IRIS_UI_SENTRY_DSN` is unset, then takes the target DSN
from the public request body. `parseDsn` accepts arbitrary URL hosts and
protocols, and `forwardEnvelope` sends the request and returns the upstream
status/body. A remote caller can therefore make the frontend server reach
internal or attacker-controlled hosts and observe their responses.

**Fix:** derive the allowed destination from trusted server-side configuration
and reject the request if no trusted destination is available. Require HTTPS,
reject private/link-local destinations unless explicitly needed for a configured
deployment, and bound request size, connect time, and total response size. Add
regression checks for arbitrary hosts, non-HTTPS schemes, oversized bodies, and
the configured Sentry destination.

### P2 — Language switch rejects configured alternate hostnames

`v3/frontend/src/routes/locale/+server.ts:4-7` requires the request Origin to
equal `url.origin`. The shared request guard in
`v3/frontend/src/hooks.server.ts:329-351` allows normalized origins listed in
`IRIS_ALLOW_ORIGIN`, and `:72-84` explains that adapter-node `ORIGIN` can pin
`url.origin` to one hostname. On a listed alternate/custom hostname, the shared
guard can accept the request while `/locale` rejects it with 403.

**Fix:** use the same normalized same-origin/served-origin validation as the
shared guard. Keep rejection for origins outside the configured allow-list.
Cover a pinned primary origin, an allowed alternate, and a disallowed origin.

## Localization findings

The generated inventory contains 3,093 strings and each inventory key is
present in `v3/frontend/src/lib/i18n/ru.json` (4,464 entries); the generated
`missing.json` is empty. This only checks strings already in the inventory and
does not detect raw Svelte literals, accessibility text, or dynamic server
messages.

### P2 — Static page titles bypass the locale catalog

A source scan found 55 Svelte `<title>` tags; 54 do not call `irisT()`. In
Russian mode, tab titles remain English. Examples:

- `v3/frontend/src/routes/(app)/+page.svelte:593` — `Dashboard`
- `v3/frontend/src/routes/(app)/alerts/+page.svelte:1251` — `Alerts`
- `v3/frontend/src/routes/(app)/settings/access-control/+page.svelte:112` —
  `Access Control`
- `v3/frontend/src/routes/(app)/cases/import/+page.svelte:412` — `Import case`
- Case, alert, dashboard, war-room, MFA, and settings detail titles also contain
  untranslated English labels.

**Fix:** localize static title fragments and preserve user-provided case,
dashboard, and war-room names verbatim. Add a source check so new static titles
cannot bypass the locale helper unnoticed.

### P2 — Confirmation messages and some accessibility labels remain English

There are 15 literal Svelte `message="..."` confirmation/status messages that
bypass the catalog. They occur in:

- `v3/frontend/src/routes/(app)/alerts/+page.svelte:1914`
- `v3/frontend/src/routes/(app)/alerts/[alert_id]/+page.svelte:270`
- `v3/frontend/src/routes/(app)/alerts/components/alert-detail-dialog.svelte:360`
- `v3/frontend/src/routes/(app)/case/[case_id]/assets/[asset_id]/timeline-tab.svelte:374`
- `v3/frontend/src/routes/(app)/[components]/CaseModals/CaseManageModal.svelte:155`
- `v3/frontend/src/routes/(app)/case/[case_id]/assets/components/assets-sidebar.svelte:662`
- `v3/frontend/src/routes/(app)/case/[case_id]/notes/[note_id]/note-header.svelte:392`
- `v3/frontend/src/routes/(app)/case/[case_id]/notes/+layout.svelte:520`
- `v3/frontend/src/routes/(app)/war-rooms/[war_room_id]/notes/+layout.svelte:503`
- `v3/frontend/src/routes/(app)/case/[case_id]/tasks/components/tasks-sidebar.svelte:490`
- `v3/frontend/src/routes/(app)/case/[case_id]/iocs/components/iocs-sidebar.svelte:595`
- `v3/frontend/src/routes/(app)/war-rooms/[war_room_id]/notes/[note_id]/note-header.svelte:271`
- `v3/frontend/src/routes/(app)/case/[case_id]/evidence/components/evidence-sidebar.svelte:566`
- `v3/frontend/src/routes/(app)/settings/webhooks/+page.svelte:487`
- `v3/frontend/src/routes/(app)/settings/webhooks/components/WebhookEditor.svelte:841`

The alert deletion wording says “All associated data will be deleted,” while the
delete operation removes the alert and dependent records/associations; linked
cases, assets, and IOCs are not themselves deleted. The same singular message is
also used for bulk deletion. Correct the claim and make the message plural-aware
where multiple records can be selected.

A static scan flagged 70 `aria-label` attributes without an `irisT()` call (an
upper bound because some use localized interpolated values). Confirmed English
examples include:

- `v3/frontend/src/routes/(app)/alerts/components/AlertsSplitView/AlertsSplitView.svelte:1019,1062`
  — sort instructions and “Select alert” labels
- `v3/frontend/src/routes/(app)/cases/+page.svelte:1075` — sort instructions
- `v3/frontend/src/lib/components/common/SeenElsewhereBadge.svelte:99` —
  accessible label for the translated popover
- `v3/frontend/src/lib/components/common/CaseTitleCell.svelte:31` — hover title

**Fix:** move user-facing messages and accessible labels into the catalog,
including plural variants. Review the remaining flagged attributes to separate
actual user-visible English from identifiers, user data, and technical values.

### P2/P3 — Russian catalog entries conflict with the UI action or terminology

- `v3/frontend/src/lib/i18n/ru.json:2808` — `Import case` → `Импортный случай`
  reads as “imported case”; use `Импорт инцидента`.
- `v3/frontend/src/lib/i18n/ru.json:3442` — `Resolve` → `Решить`; in the case
  import wizard (`routes/(app)/cases/import/+page.svelte:404-407`) it means
  matching principals/reference records. Use a matching verb or step name.
- `v3/frontend/src/lib/i18n/ru.json:2602` — `Escalate` → `Эскалация`; it is an
  action button, so use `Эскалировать`.
- `v3/frontend/src/lib/i18n/ru.json:1837` — `Review` → `Проверка:`; the case
  menu uses it as a section label, so remove the stray colon.

**Fix:** correct these entries and do a source-backed review of action verbs,
workflow step names, destructive copy, and the established `Case` → `Инцидент`
terminology. Add focused translation tests for the corrected strings.

## FastAPI and API parity findings

There are no confirmed HTTP handlers left outside FastAPI in the active v3
runtime. `v3/backend/source/app/web.py:489-497,563-588` defines a FastAPI app
and registers legacy URL rules as FastAPI routes with worker-thread dispatch.
Legacy Flask-shaped blueprints and handler APIs remain as a compatibility
adapter; they do not mean the HTTP server is still Flask/WSGI. The root
`source/` tree is retained v2 recovery code.

The actual remaining work is API contract parity: eight explicit TODO comments
identify nine legacy routes with no or partial `/api/v2` equivalent. These old
routes still work through the FastAPI adapter today.

| Legacy route | Missing or partial v2 behavior | Source |
| --- | --- | --- |
| `GET /datastore/list/filter` | `q` filter-tree semantics are absent from the flat file list/tree APIs | `v3/backend/source/app/blueprints/rest/datastore_routes.py:94-102` |
| `GET /dashboard/case_charts` | Rolling-year daily case histogram is absent; deferred because current v3 UI has no consumer | `v3/backend/source/app/blueprints/rest/dashboard_routes.py:112-118` |
| `GET /case/meta` | v2 case detail lacks `protagonists` and `status_name` | `v3/backend/source/app/blueprints/rest/case/case_routes.py:130-139` |
| `GET /manage/compromise-status/list` | v2 does not expose the `CompromiseStatus` enum | `v3/backend/source/app/blueprints/rest/manage/manage_analysis_status_routes.py:49-59` |
| `GET /manage/outcome-status/list` | v2 does not expose the `CaseStatus` enum | `v3/backend/source/app/blueprints/rest/manage/manage_analysis_status_routes.py:62-78` |
| `GET /manage/customers/{client_id}/cases` | v2 customer resource lacks per-customer case statistics | `v3/backend/source/app/blueprints/rest/manage/manage_customers_routes.py:147-154` |
| `GET /manage/users/filter` | v2 user search lacks `user_ids`, `customer_id`, and `sort` filters | `v3/backend/source/app/blueprints/rest/manage/manage_users.py:99-119` |
| `GET /manage/users/lookup/id/{cur_id}` | no v2 non-admin lookup equivalent | `v3/backend/source/app/blueprints/rest/manage/manage_users.py:478-485` |
| `GET /manage/users/lookup/login/{login}` | no v2 non-admin lookup equivalent; port only the intended reduced fields | `v3/backend/source/app/blueprints/rest/manage/manage_users.py:500-506` |

**Fix:** define and implement equivalent `/api/v2` contracts for the required
features, including explicit field-level authorization for non-admin user
lookups. Keep each legacy route until its v2 behavior and known consumers are
covered; only then mark it deprecated. Decide whether the unused dashboard
histogram belongs in v2 now or stays explicitly deferred.

### P3 — Backend README describes the old framework as current

`v3/backend/README.md:5,25,31-33` describes the local active backend as Flask,
while `v3/README.md:27-29` and `v3/backend/source/app/web.py` describe the native
FastAPI routing layer. Update the backend README to describe FastAPI transport
and Flask-shaped compatibility handlers accurately.

## Implementation order

1. Close the unauthenticated envelope relay and add destination, scheme, and
   resource-limit regression coverage.
2. Align `/locale` Origin validation with the shared allow-list and cover
   alternate-host behavior.
3. Correct the confirmed Russian terminology errors and false/ambiguous
   confirmation copy.
4. Localize static titles, confirmation messages, and confirmed accessibility
   labels; review the remaining static-scan candidates and dynamic server text.
5. Implement or explicitly defer each of the nine `/api/v2` parity items, with
   contract and authorization checks before any legacy deprecation.
6. Correct the backend README and run the relevant frontend/backend checks and
   API parity verification.

## Acceptance criteria for the follow-up implementation

- The envelope route cannot be used to reach arbitrary destinations and only
  forwards to a configured trusted ingest service.
- Language selection works from every configured served hostname and rejects
  unlisted origins.
- Static user-facing titles, confirmations, and accessibility labels use the
  locale system; user-created names and protocol identifiers remain unchanged.
- The four confirmed Russian catalog errors are corrected and covered by tests.
- Each required legacy API feature has a documented and verified v2 contract,
  or an explicit defer decision; old routes are not removed before parity.
- Review findings and checks are reported with their verification limits.
