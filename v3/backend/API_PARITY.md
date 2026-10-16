# Legacy REST to `/api/v2` parity

The legacy routes remain available. They are not deprecated until known consumers have moved to
the equivalent `/api/v2` contract and the integration suite covers that migration.

| Legacy contract | `/api/v2` equivalent | Authorization and response |
| --- | --- | --- |
| `GET /datastore/list/filter?caseid={id}&q={json}` | `GET /api/v2/cases/{id}/datastore/filter?q={json}` | Any authenticated caller with read-only or full case access. Returns the filtered datastore tree. Array filters accept strings for `id`, `uuid`, `sha256`, `name`, `storage_name`, `tag`, and `description`; `is_ioc`, `is_evidence`, and `has_password` are booleans where `true` enables the filter and `false` leaves it disabled. Malformed shapes return 400. |
| `GET /case/meta?caseid={id}` fields `status_name`, `protagonists` | `GET /api/v2/cases/{id}` | Existing case-read authorization. The normal case payload now includes both fields. |
| `GET /manage/compromise-status/list` | `GET /api/v2/manage/compromise-statuses` | Any authenticated caller. Returns `[{value, name}]` for every `CompromiseStatus` member. |
| `GET /manage/outcome-status/list` | `GET /api/v2/manage/outcome-statuses` | Any authenticated caller. Returns `[{value, name}]` for every `CaseStatus` member. |
| `GET /manage/customers/{id}/cases` | `GET /api/v2/manage/customers/{id}/cases` | Requires `customers_read` and access to that customer. Returns `{cases, stats}` with the legacy statistic names. `average_case_duration` is the mean across closed cases; this corrects the legacy route, which returned the sum when every case was closed. |
| `GET /manage/users/filter` | `GET /api/v2/manage/users` | Server administrator only. Adds `user_ids`, `customer_id`, and `sort=asc|desc` to the existing pagination and search parameters. |
| `GET /manage/users/lookup/id/{id}` | `GET /api/v2/users/lookup/id/{id}` | Any authenticated caller. Returns exactly `user_id`, `user_login`, and `user_name`. |
| `GET /manage/users/lookup/login/{login}` | `GET /api/v2/users/lookup/login/{login}` | Any authenticated caller. Returns exactly `user_id`, `user_login`, and `user_name`; email, UUID, active state, roles, and permissions are excluded. |

`GET /dashboard/case_charts` remains intentionally deferred. The active v3 frontend has no
consumer for its rolling-year daily histogram, so adding and maintaining a second unused
aggregation endpoint would not improve migration coverage.

The v2 customer statistics count the complete previous calendar month. January refers to
December (`last_month=12`), and 31-day months do not drop the previous month's cases.
This corrects the legacy partial-30-day interval; the legacy route itself is unchanged.
