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
