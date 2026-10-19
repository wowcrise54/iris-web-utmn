# Bounded Sandbox and PCAP analysis

The case Sandbox page links to **Evidence analysis** (`/case/<id>/analysis`).
Choose a case file or follow the PCAP/graph link on a Sandbox log. The original
file is read only. Video and arbitrary binaries are rejected by content signature.

## Local PCAP worker

The native backend image packages TShark and libseccomp. The Celery worker runs
TShark as a separate process with a clean environment, closed inherited file
descriptors, no-new-privileges, and a denied socket/ptrace/mount syscall set.
Landlock ABI 3+ restricts filesystem reads to runtime libraries and the selected capture,
and denies new file writes and access to other case files or application settings.
Root workers drop the parser to uid/gid 65534. Isolation failures fail closed;
there is no unrestricted fallback. This is process/syscall isolation, not a VM.

The parser receives only a generated temporary path and fixed field options.
No interfaces, URLs, display filters, Lua scripts, user arguments, payload
exports, decryption keys, HTTP paths/headers or file extraction are accepted.
Only IP/port/protocol/frame/time/count/size and DNS/HTTP-host/TLS-SNI metadata
are retained. Temporary input/output is removed after success or failure.

Limits: 100 MiB compressed and expanded input; 100,000 frames; 120 seconds wall
time; 60 seconds CPU; 512 MiB address space; 16 MiB metadata output. Graphs are
bounded to 100 IP nodes and 150 directed connections; indicators to 100 names.
Frame numbers and timestamps refer to the original (or decompressed) capture.
Capture and original-wrapper SHA-256 are both recorded. A capped capture/graph
is explicitly partial. Malformed capture, timeout or other process resource failures
produce a failed job; original evidence is still downloadable.

PCAP metadata is not a malware verdict. Encrypted traffic is not decrypted.
A host/domain appearing in a capture is an observable, not proof of maliciousness.

## Sandbox summaries

Instead of replaying raw pages through the interactive chat history, the worker
reads up to 64 pages of 12,000 characters across the report and available text
logs. For large sources, up to eight windows are sampled across the beginning,
middle and end. Windows are interleaved across sources, and sampling is explicitly
reported as non-exhaustive. Every step folds one page into a rolling factual summary of at most 1,024
tokens; the final answer is limited to 2,048 tokens. Log IDs, character offsets,
coverage and skipped binary/video/unavailable logs are retained. The existing
16 MiB decoded text limit still applies. Only derived summaries enter the chat.

Every provider call rechecks user/case access, keeps the conversation pinned policy,
rejects a stricter live case policy, and applies redaction
settings and daily token budgets, and records the normal egress audit. Credentials
are loaded at execution time and never saved in job state. Completed and partial
results can be opened in Yuki. A failed provider stream keeps its checkpoint and
partial response; **Continue analysis** retries the interrupted step. Continuation
can spend more provider tokens. Interrupted workers mark jobs failed rather than
silently repeating a potentially charged provider request.

## Interfaces and permissions

- `POST /api/v2/cases/<case>/analysis`: `{kind: "pcap", file_id}` OR
  `{kind: "pcap", scan_id, log_id}` OR `{kind: "sandbox", scan_id, conversation_id?}`.
- `GET /api/v2/cases/<case>/analysis`: caller job list (last 50).
- `GET /api/v2/cases/<case>/analysis/<id>`: status, coverage, sources and bounded graph.
- `POST /api/v2/cases/<case>/analysis/<id>/continue`: continue a failed job.
- MCP `iris_case_evidence_analyze` / `iris_case_evidence_analysis_get`: start/read
  derived analysis with case-scoped ACLs and a compact LLM projection, not the full graph.

Derived jobs require case read access; job results are also owner-scoped. They do
not change case evidence or create IOC records. At most two jobs per user may be
active. Case/user deletion cascades job data. The migration is
`utmn_evidence01` and tolerates bootstrap metadata creation before Alembic.

## Diagnose 502

Nginx writes `/var/log/nginx/analysis_trace.log`: request ID, URI (without query),
status/upstream status, duration and byte counts. It forwards `X-Request-ID`.
`iris.chatbot.namespace` logs that ID with conversation ID. Provider telemetry
uses `chat-<conversation>-<audit>` or `analysis-<job>-<page>` IDs and logs only
provider/status/category/timing/byte counts. Match the analysis-start request ID
to the job, then its provider records. An HTTP 502 inside a provider event is
reported as a provider error; a Nginx HTTP 502 before the Socket.IO connection
is established is a separate upstream/transport failure. Timeouts have their own
category. No buffers or timeouts are increased by this change.

## Deployment

Rebuild app/worker and nginx as well as frontend. Follow repository AGENTS.md:
identify the selected Compose project and its four files, verify records/mounts,
and take a fresh pg_dump before recreating or migrating the selected application.
Do not reset/replace existing volumes. The verification image/container names
used during development must not replace the selected production stack.
