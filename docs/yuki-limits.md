# Yuki configurable limits

Settings → Chatbot exposes **Unlimited** for the server defaults and each
customer policy. The wire value is integer `0`; saved positive limits and
existing defaults remain unchanged.

| Setting | Zero | Default |
| --- | --- | --- |
| History turns | Send all saved messages without Yuki's history trim | 25 |
| Tool iterations per turn | Continue until the model finishes, errors or waits for write approval | 8 |
| Daily tokens per user | No Yuki daily quota | 500,000 |
| Daily tokens for the organisation | No Yuki daily quota | 10,000,000 |
| Output tokens per answer | No Yuki output token cap; provider rules below apply | 2,048 |

The same output setting applies to the final Sandbox analysis report. Internal
rolling notes stay compact. A customer policy's zero is an explicit override,
not a fallback to the server default. Existing retention_days=0 continues to
disable automatic transcript deletion.

Finite limits must be whole JSON integers in 0..2,147,483,647, matching the stored
SQL Integer fields. The UI rejects invalid values before saving; policy create
and patch and global settings use the same bounds. Use Unlimited rather than
an enormous finite number. No limit setting grants extra data access or changes
write approvals, redaction, policy selection or MCP payload guards.

The tool loop reloads configuration and checks the active conversation, current
case/war-room access and configured daily budgets before each provider request.
Archiving the conversation, disabling Yuki or revoking access stops it at the next
request boundary. Unlimited iterations can consume provider credits indefinitely
if a model keeps calling tools; the UI choice is explicit.

## Provider output semantics

- OpenAI/custom: omit max_tokens for zero, leaving the provider default/maximum.
- Ollama: send options.num_predict=-1.
- Anthropic: the Messages API requires max_tokens. Read GET /v1/models/<model>
  and use its positive max_tokens. If metadata is unavailable, return a clear
  configuration error asking for an explicit finite output limit. No arbitrary
  fallback is described as unlimited.

The stream byte guard scales with a finite output setting; zero removes the text
byte guard. The independent 48,000-byte tool-argument guard remains. Model context,
provider maximum output, rate limits, account credits and transport failures still
apply. Sending the entire history can exceed a provider's context window.

## Migration and verification

utmn_yuki_limits01 adds server_settings.chatbot_max_output_tokens and
chatbot_policy.max_output_tokens, defaulting both to 2048. The migration is
idempotent when PostInit already created the columns. Existing quotas/history/tool
limits are preserved. Follow AGENTS.md for a backup and the fixed four-file Compose
stack before applying the migration or recreating app/worker/frontend.
