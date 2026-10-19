"""Provider failure categories and safe telemetry (never request/response bodies)."""
import logging
import time
import re
import json
import requests
from app.iris_engine.llm.providers.base import Error, TextDelta, ToolUseDelta, ToolUseEnd

log = logging.getLogger('iris.chatbot.provider')


def provider_events(provider, *, correlation_id, max_response_bytes=48000, **kwargs):
    started, received = time.monotonic(), 0
    stream = provider.stream_completion(**kwargs)
    streamed_tools = set()
    tool_bytes = 0
    try:
        for event in stream:
            chunk_bytes = 0
            if isinstance(event, TextDelta):
                chunk_bytes = len(event.text.encode('utf-8'))
            elif isinstance(event, ToolUseDelta):
                streamed_tools.add(event.tool_use_id)
                chunk_bytes = len(event.partial_json.encode('utf-8'))
                tool_bytes += chunk_bytes
            elif isinstance(event, ToolUseEnd) and event.tool_use_id not in streamed_tools:
                chunk_bytes = len(json.dumps(event.arguments).encode('utf-8'))
                tool_bytes += chunk_bytes
            received += chunk_bytes
            if (max_response_bytes is not None and received > max_response_bytes) or tool_bytes > 48000:
                yield Error('Provider response exceeded the safe output limit.', provider_code='output_limit')
                return
            if isinstance(event, Error):
                log.warning('llm_failure request_id=%s provider=%s status=%s code=%s elapsed_ms=%d response_bytes=%d',
                            correlation_id, provider.name, event.http_status, re.sub(r'[^a-zA-Z0-9_:-]', '_', str(event.provider_code))[:64],
                            (time.monotonic() - started) * 1000, received)
            yield event
    except requests.Timeout:
        log.warning('llm_timeout request_id=%s provider=%s elapsed_ms=%d response_bytes=%d',
                    correlation_id, provider.name, (time.monotonic() - started) * 1000, received)
        yield Error('Provider request timed out. You can continue the analysis.', provider_code='timeout')
    except (ValueError, TypeError):
        yield Error('Provider returned an invalid stream. You can continue the analysis.', provider_code='invalid_stream')
    except requests.RequestException:
        log.warning('llm_transport_failure request_id=%s provider=%s response_bytes=%d', correlation_id, provider.name, received)
        yield Error('Provider connection interrupted. You can continue the analysis.', provider_code='connection')
    except Exception as exc:
        log.error('llm_stream_failure request_id=%s provider=%s category=%s', correlation_id, provider.name, type(exc).__name__)
        yield Error('Provider response could not be processed. You can continue the analysis.', provider_code='stream_failure')
    finally:
        if hasattr(stream, 'close'):
            stream.close()
        log.info('llm_request request_id=%s provider=%s elapsed_ms=%d response_bytes=%d',
                 correlation_id, provider.name, (time.monotonic() - started) * 1000, received)
