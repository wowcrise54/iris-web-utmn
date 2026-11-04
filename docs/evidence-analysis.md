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

The worker reads the report and every available text log sequentially, in blocks
of 12,000 characters. There is no eight-window sampling or 64-page ceiling.
Gzip and zstd are decoded as bounded streams. Each source has its own rolling
notes and exact character offsets; the final report combines all source notes
and checks up to four cited full-page excerpts against the original cached text.
It must give a qualified verdict, confidence, a chronology, supporting evidence,
benign alternatives and limitations. Processing all available text does not prove
that all activity was observable or that the system was safe.

Limits are explicit: 100 MiB compressed per log, 256 MiB decoded per log and
512 MiB of decoded UTF-8 cache per job. A corrupt, unavailable or capped text
source makes coverage incomplete and the completed job partial. Truncated intermediate notes also make the result partial, even when all input blocks were delivered to the model. Binary/graph/video
attachments are excluded and separately labelled, without pretending to analyse
them as text. The UI shows processed blocks and characters per source. Source
links can read past the old 16 MiB prefix. At most 200 recent page links are
returned; source IDs and exact offsets remain valid for older citations.

The private cache is next to DATASTORE_PATH under evidence-analysis/<job-id>,
with directory/file modes 0700/0600. Only the worker reads it; it is not a public
file endpoint. Original evidence stays unchanged. Cache/index metadata and
per-source notes are excluded from public job projections. Successful jobs remove
the cache; caches unused for 72 hours are pruned. Failed jobs retain checkpoints;
a missing cache is rebuilt from unchanged source metadata on continuation.
Legacy sampled checkpoints restart from block zero instead of claiming full
coverage. New state fits the existing job JSON; no database migration is needed.

A complete pass can require thousands of provider calls, unlike the earlier
sampled pass. The Sandbox launch form states this beside the existing explicit
provider consent. Existing user/organisation daily token budgets apply to every
block and retry. A budget failure preserves progress for explicit continuation.
Only derived summaries enter chat history. The ordinary notes formatting target is 1,024
tokens, with bounded empty-answer retries for small finite budgets described below; final output remains
limited to 2,048 tokens by default; the Yuki output setting can change or disable that cap (see yuki-limits.md).

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

## Empty responses and Sandbox attachments

Intermediate notes have a soft 1,024-token formatting goal. The provider request
honours a configured unlimited output setting or a positive limit above 8,192.
For small finite notes budgets only, if a model ends with
`max_tokens` and no visible answer, the worker requeues the same page with a larger budget, capped at 8,192
unless a higher output limit is configured. An unlimited setting is never reduced
to that retry ceiling. Each attempt has its own egress accounting and rechecks
case access, the pinned policy and daily budgets. Progress advances only after a
visible answer. Final responses use the configured Yuki output setting (default 2,048; zero delegates to the provider). Exhaustion, empty
completed responses and broken streams have distinct errors; hidden reasoning is
never displayed or substituted for evidence findings.

The analysis page selects either a case datastore file or a Sandbox check and its
PCAP/PCAPNG attachment (including gzip/zstd wrappers). Sandbox sources are read
through their existing case-scoped log storage. The report's PCAP action starts
a job directly using `scan_id` and `log_id`; no copying into datastore is required.
Text logs, proprietary `graph.bin` files and MP4 are not offered as captures.
Capture magic validation remains authoritative on the backend.
