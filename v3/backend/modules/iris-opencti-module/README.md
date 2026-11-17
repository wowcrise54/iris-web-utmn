# IRIS OpenCTI module

Optional processor DIM for the repository's IRIS v3.0.0-beta.6 and the shipped
`iris-interface==1.2.0`. It is installed in the backend image used by **both app
and worker** and is disabled by default. No schema migration is required.

## Build and install

From this directory, with setuptools and wheel available:

```powershell
python -c "from setuptools.build_meta import build_wheel; build_wheel('../../source/dependencies')"
```

The backend requirements install the resulting wheel using IRIS's existing
dependency mechanism. Rebuild app and worker together following the repository's
AGENTS.md and its required stack/data checks. This source change alone does not
install anything in an already running image.

On an existing installation, open **Settings → Modules**, add the Python package
`iris_opencti_module`, enter **OpenCTI URL** (base URL, no `/graphql`) and the
**OpenCTI API token**, then enable the module. A new IRIS database registers it
with the other default modules, disabled. Saving settings while disabled does
not connect to OpenCTI or register hooks. Enabling checks authentication and the
query schema; a failed check leaves the module disabled and removes its hooks.
Use a read-only OpenCTI account whose permitted markings and organizations match
the IRIS audience: the returned snapshot follows normal IRIS object permissions.
TLS verification is enabled. An internal HTTP URL is supported; redirects and
system proxy configuration are not used. Tokens are never stored in enrichment.

## Operation

Native asynchronous DIM hooks handle alert create/update/merge/escalate/unmerge,
IOC create/update and case creation/update. Unlinking an alert also refreshes the
former case's summary. Manual actions **OpenCTI: refresh enrichment**
are available on alerts, cases and IOCs using the existing DIM actions and APIs.
Tasks recheck the enabled state and current settings before querying and saving;
disabling also makes already queued tasks stop without making requests.
An already in-flight request may finish, but its result is discarded after disable.
If the broker is unavailable, the original save still succeeds and IRIS logs the
enqueue failure; retry enrichment manually after the broker recovers.

A case includes its own IOCs and the IOCs of its currently linked alerts. The
module stores provider results at `ioc_enrichment.opencti`, preserving all other
providers and original IOC fields. The reserved `custom_attributes.__iris_opencti`
field stores the timestamped case summary rendered on its overview. This is a
snapshot; refresh the page after the native module task completes. Existing data
remains readable when the module is disabled. The module never creates IOCs,
changes severity or verdicts, or sends mutations/sightings to OpenCTI.

Supported inputs: IP source/destination (IPv4/IPv6), domain, hostname, URL/URI,
email source/destination, MD5, SHA-1, SHA-256 and SHA-512. Composite types such as
`domain|ip` are explicitly unsupported. IPs, domains and hashes are normalized;
email local parts and complete URL path/query remain case sensitive.

Queries use exact typed observable filters and verify the returned values again.
For hashes, the algorithm and hash are checked rather than a file's display name.
Linked Indicators are included as context, not proof that an entire compound STIX
pattern matched. Unlinked Indicators are found by an exact canonical simple STIX
equality pattern; alternative whitespace, complex patterns, Sigma and YARA are
not evaluated. Observable matches alone do not imply malicious activity.
Revoked, expired and future Indicators are retained with explicit validity states.

Successful results and no-match results are cached for six hours, scoped by
source URL, credential fingerprint, typed value and the IOC's customer scope.
Identical values in one batch share a request. PostgreSQL advisory locks serialize
the same cache key across workers; cached data is re-read after taking the lock.
Manual refresh ignores results older than its own invocation. Error results are
not reused on later invocations. Provider-only atomic JSONB writes also prevent
overwriting a concurrent provider; stale IOC values/types are not updated.

Each HTTP request has a 10-second timeout, each IOC lookup a 30-second deadline,
each response a 4 MiB cap, and each connection a 1,000-result pagination cap.
More than 100 linked Indicators on one Observable yields `partial`; global
pagination limits yield `result_limit`, not `no_match`. Remote failures have
sanitized statuses (`unauthorized`, `timeout`, `unavailable`, `schema_error`, etc.).
The JSON view contains complete retained metadata, references and relationships.

## Verification and compatibility

```powershell
$env:PYTHONPATH='.'
python -m unittest discover -s tests -v
```

Tests cover typed matching, validity, direct Indicators, pagination, HTTP contract,
sanitized failures, caching/deduplication, disabled tasks, module lifecycle against
the shipped DIM interface and worker snapshot preservation. SQLAlchemy is needed
for the worker and storage tests; no real OpenCTI token is used.

Install the `test` extra (`python -m pip install -e ".[test]"`) to include GraphQL
validation of relationship endpoints against a reduced OpenCTI 7.260902.0 schema
contract. Endpoints are unions; their identity fields must use typed fragments.

The client follows OpenCTI's GraphQL `FilterGroup`, observable, Indicator and
relationship API. Enable-time probes check the target deployment's actual schema.
Local fixture tests are not certification against a live OpenCTI version.
Live OpenCTI/PostgreSQL/worker/UI acceptance requires a configured test deployment.

Primary references:

- https://docs.dfir-iris.org/3.0.0-beta/development/modules/quick_start/processor/
- https://docs.opencti.io/latest/reference/api/
- https://github.com/OpenCTI-Platform/client-python/tree/master/pycti/entities

## Logging

The `iris_opencti_module` Python logger uses the existing IRIS/Celery handlers.
INFO is the default: registration, hook/batch start and completion, IOC IDs,
result statuses, match counts and duration in milliseconds. WARNING reports
provider failures and partial results; ERROR reports registration, processing
and persistence failures. Exceptions still follow the existing error handling.
A completed hook means processing finished; inspect IOC statuses for provider errors.

Set `IRIS_OPENCTI_LOG_LEVEL=DEBUG` in the environment of **both app and worker**
to include cache source (`miss`, `batch`, `persistent`), request stages and page
counts. In the current live stack this can be added to `.env.v3.live`; recreate
app and worker following the root AGENTS.md after rebuilding the wheel/image.
Supported levels: TRACE, DEBUG, INFO, WARNING, ERROR, CRITICAL; invalid values fall back
to INFO. Restart is required when changing the environment. Existing handler
filters still apply. Return to INFO after diagnosis to reduce volume.

Normal INFO/DEBUG logs omit tokens, credential fingerprints, IOC values, URLs,
GraphQL variables, response bodies and exception text. Match the numeric `ioc_id` to IRIS records.
Concurrent worker logs can interleave; request/page DEBUG events describe their
operation rather than an individual IOC. No separate log files are created.

### TRACE request/response bodies

Set `IRIS_OPENCTI_LOG_LEVEL=TRACE` in both app and worker environments, then
restart/recreate them using the root AGENTS.md procedure. Alternatively,
`IRIS_OPENCTI_LOG_PAYLOADS=true` enables the same payload logging with DEBUG.
TRACE records use Python DEBUG severity and an explicit `OpenCTI TRACE` marker
so existing IRIS/Celery handlers can process them; handler DEBUG filters must
allow these records.

Each request logs the GraphQL document and variables. Responses include the raw
body (including GraphQL errors and HTTP error bodies), HTTP status, duration and
a matching `request_id`. Transport failures without a response retain the normal
sanitized warning. Headers are never logged; appearances of the configured API
token in bodies are replaced with `[REDACTED]` before truncation. Bodies are
limited to 16,384 characters per record, with `truncated=true` for larger bodies.
Bodies are JSON-escaped onto a single log line.

TRACE includes IOC values and returned threat intelligence. Enable it temporarily
and restrict access to logs. To switch it off, restore INFO and remove/set false
`IRIS_OPENCTI_LOG_PAYLOADS`, then restart both services. No payload logs are
produced by default or by DEBUG alone.
