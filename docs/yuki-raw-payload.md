# Reading large alert payloads in Yuki

## Accepted design

Keep the 40,000-byte MCP result guard. Add a read-only, default-visible
`iris_alerts_source_get` tool that reads `alert_source_content` or `alert_context`
in bounded text pages. Reuse the existing alert permission and customer ACL path.
Point the alert tool description, truncation hint and Yuki prompt at this recovery
path. No database migration or frontend change is needed.

Implementation: add regression coverage through the dispatcher, implement and
classify the tool, update Yuki guidance, then verify payload reconstruction,
response budgets, permissions and invalid arguments.

## Tool contract

Start with `{"alert_identifier":306}`. The default field is
`alert_source_content`; set `field` to `alert_context` to read that field instead.
Objects and arrays become compact JSON with sorted keys; strings are returned
unchanged. JSON null becomes `null` and an empty string remains empty.

Each result includes `text`, `offset`, `total_chars`, `next_offset`,
`source_sha256` and `untrusted_data`. Offsets count Unicode characters in the
serialized field, not UTF-8 bytes. A page may split a JSON value or event.
Concatenate the text before parsing it.

For each subsequent call, pass `offset=next_offset` and
`expected_sha256=source_sha256` from the first response. Continue until
`next_offset` is null. A changed field is rejected when the expected hash is
supplied; restart from zero instead of mixing versions. Permissions are checked
again for every page.

`limit` is an optional character ceiling, default/maximum 30,000. The tool
shortens pages to fit escaped JSON under the MCP budget, reserving 1,024 bytes
for metadata. This accounts for Cyrillic, emoji, quotes and control characters.
Normal MCP truncation must not alter any page.

## Operational limits

Pagination removes the single-response barrier; it does not expand the model's
context window or change Yuki's configured tool-iteration, history or token
limits. A large payload can require more calls than one turn permits. Resume
from the returned offset in a subsequent message, preserving the hash. Yuki
must disclose incomplete coverage rather than give a verdict based on unseen
events. Provider/model context limits still apply even when every page fits.

The code requires deployment of the updated backend before the new tool appears
in Yuki. Follow the repository AGENTS.md for the selected Compose stack and
backup requirements when deploying.

## Verification in this change

- 24 new pagination tests pass, including reconstruction of structured and
  Unicode payloads larger than 361 KB through the actual handler and dispatcher
  with inert business/ACL doubles. Every page survives the normal result guard.
- Five existing alert-update boundary tests pass. Ruff on the changed Python
  files and `git diff --check` pass.
- 36 existing budget/prompt unit tests pass using isolated imports of the pure
  modules. `test_read_only_appended_to_end` fails both at HEAD before this change
  and with this change: the existing Sandbox paragraph follows the read-only
  paragraph. That unrelated prompt-order issue is unchanged.
- Full application/database/provider integration and a live read of alert 306
  are not verified. The local Docker Linux Engine pipe is unavailable, so no
  rebuild or deployment was performed.
