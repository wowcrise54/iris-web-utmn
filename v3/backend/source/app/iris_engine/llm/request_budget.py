"""Guard the complete serialized provider request before sending any completion.

Unmapped token counts are never advertised as exact. The fallback is a byte cap,
not a characters-per-token estimate. Optional counting is restricted to the
configured provider origin, without redirects or diagnostic payload logging.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import json
import math
import os
import threading
import time
from urllib.parse import urlsplit, urlunsplit

import requests


@dataclass(frozen=True)
class BudgetDecision:
    fits: bool
    input_tokens: int | None
    method: str
    request_bytes: int
    limit: int
    reason: str


_CAPABILITIES: OrderedDict = OrderedDict()
_COUNTS: OrderedDict = OrderedDict()
_LOCK = threading.Lock()
_TTL = 300
_CACHE_SIZE = 128


def _get(cache, key):
    with _LOCK:
        entry = cache.get(key)
        if entry is not None and time.monotonic() - entry[0] < _TTL:
            cache.move_to_end(key)
            return entry[1]
        cache.pop(key, None)
    return None


def _put(cache, key, value):
    with _LOCK:
        cache[key] = (time.monotonic(), value)
        cache.move_to_end(key)
        while len(cache) > _CACHE_SIZE:
            cache.popitem(last=False)


def _counter_url(provider):
    base = getattr(provider, '_base_url', '') or ''
    parsed = urlsplit(base)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        return None
    path = parsed.path.rstrip('/')
    if path.endswith('/v1'):
        path = path[:-3]
    return urlunsplit((parsed.scheme, parsed.netloc, path + '/utils/token_counter', '', ''))


def _token_count(provider, model: str, body: dict, serialized: bytes) -> tuple[int | None, str]:
    url = _counter_url(provider)
    if url is None:
        return None, 'utf8_bytes_fallback'
    # Keys contain only hashes. Neither raw credentials nor source text is cached.
    api_key = getattr(provider, '_api_key', '') or ''
    scope = hashlib.sha256((url + '\0' + api_key + '\0' + model).encode()).hexdigest()
    key = (scope, hashlib.sha256(serialized).hexdigest())
    cached = _get(_COUNTS, key)
    if cached is not None:
        return cached
    if _get(_CAPABILITIES, scope) is False:
        return None, 'utf8_bytes_fallback'
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = 'Bearer ' + api_key
    try:
        # Include all serialized fields; model aliases may require deployment
        # resolution by the configured proxy. Its own tokenizer must establish
        # that mapping explicitly before its answer is trusted.
        response = requests.post(url, json=body, headers=headers, timeout=2,
                                 params={'call_endpoint': 'true'}, allow_redirects=False)
        if response.status_code != 200:
            _put(_CAPABILITIES, scope, False)
            return None, 'utf8_bytes_fallback'
        data = response.json()
        count = data.get('total_tokens')
        mapped = data.get('request_model') == model and bool(data.get('model_used'))
        valid_count = isinstance(count, int) and not isinstance(count, bool) and count > 0 and not data.get('error')
        provider_count = data.get('count_source') == 'provider'
        # Stock LiteLLM local counts are estimates. An operator must verify the
        # exact alias -> underlying tokenizer mapping before enabling this path.
        try:
            verified_models = json.loads(os.environ.get('IRIS_CHATBOT_TOKENIZER_MODELS', '{}'))
        except ValueError:
            verified_models = {}
        local_count = (isinstance(verified_models, dict) and verified_models.get(model) == data.get('model_used')
                       and data.get('tokenizer_type') == 'huggingface_tokenizer'
                       and data.get('count_source') in (None, 'local_estimate'))
        explicit_count = bool(data.get('tokenizer')) and data.get('exact') is True
        reliable = valid_count and mapped and (provider_count or local_count or explicit_count)
        _put(_CAPABILITIES, scope, reliable)
        method = 'verified_tokenizer_estimate' if local_count and not provider_count else 'mapped_token_counter'
        result = (count, method) if reliable else (None, 'utf8_bytes_fallback')
        _put(_COUNTS, key, result)
        return result
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        _put(_CAPABILITIES, scope, False)
        return None, 'utf8_bytes_fallback'


def check_request_budget(provider, *, model: str, system: str, messages: list,
                         tools: list, max_output_tokens: int | None,
                         context_window_tokens: int = 0, working_input_tokens: int = 32768,
                         fallback_bytes: int = 16384) -> BudgetDecision:
    """Budget the same complete wire body as the selected provider adapter.

    Physical context reserves ten percent of its window plus the configured
    output allowance (8192 when unknown). Without a trusted tokenizer, UTF-8
    bytes form a deliberately conservative input bound, never an exact count.
    """
    body = provider._build_body(model, system, messages, tools, max_output_tokens)
    # requests' default JSON serialization uses ensure_ascii=True and includes
    # separators' spaces. Match it, rather than undercount escaped Unicode wire.
    serialized = json.dumps(body, allow_nan=False).encode('utf-8')
    request_bytes = len(serialized)
    tokens, method = _token_count(provider, model, body, serialized)
    reserve = max_output_tokens if max_output_tokens and max_output_tokens > 0 else 8192
    physical_limit = (max(0, context_window_tokens - reserve - math.ceil(context_window_tokens * .1))
                      if context_window_tokens > 0 else None)
    if tokens is not None:
        limit = max(0, working_input_tokens)
        if physical_limit is not None:
            limit = min(limit, physical_limit)
        fits = tokens <= limit and (physical_limit is None or physical_limit > 0)
        reason = ('Complete request fits token budget' if fits else
                  f'Complete request requires {tokens} input tokens; limit {limit} after output/context reserve')
    else:
        limit = min(16384, max(0, fallback_bytes), max(0, working_input_tokens))
        if physical_limit is not None:
            limit = min(limit, physical_limit)
        fits = request_bytes <= limit and (physical_limit is None or physical_limit > 0)
        reason = ('Complete request fits conservative byte budget; tokenizer unverified' if fits else
                  f'Complete request is {request_bytes} bytes; conservative limit {limit}; tokenizer unverified')
    return BudgetDecision(fits, tokens, method, request_bytes, limit, reason)


def check_chat_request_budget(provider, *, model: str, system: str, messages: list,
                              tools: list, max_output_tokens: int | None,
                              context_window_tokens: int = 0,
                              working_input_tokens: int = 32768) -> BudgetDecision:
    """Guard interactive chat without applying the analysis-packet byte cap.

    A complete interactive tool catalog can exceed 16 KiB before the first user
    message. Trusted token counts still enforce the working and physical token
    limits. Without a mapped tokenizer, a known physical context uses complete
    wire bytes as a conservative input bound after output/margin reservations.
    With no declared physical context, a 1 MiB whole-request safety cap stops
    uncontrolled page accumulation. That cap is an operational estimate, not a
    claim that the request fits a particular model's physical token window.
    Bounded background analysis continues to use ``check_request_budget``.
    """
    decision = check_request_budget(
        provider, model=model, system=system, messages=messages, tools=tools,
        max_output_tokens=max_output_tokens, context_window_tokens=context_window_tokens,
        working_input_tokens=working_input_tokens,
    )
    if decision.input_tokens is not None:
        return decision
    limit = 1024 * 1024
    method = 'chat_utf8_bytes_safety_cap'
    qualifier = 'tokenizer and physical context unverified; operational byte safety cap'
    if context_window_tokens > 0:
        reserve = max_output_tokens if max_output_tokens and max_output_tokens > 0 else 8192
        limit = min(limit, max(0, context_window_tokens - reserve - math.ceil(context_window_tokens * .1)))
        method = 'chat_utf8_bytes_physical_bound'
        qualifier = 'tokenizer unverified; conservative byte bound after output/context reserve'
    fits = decision.request_bytes <= limit and limit > 0
    reason = f'Complete chat request is {decision.request_bytes} bytes; limit {limit}; {qualifier}'
    return BudgetDecision(fits, None, method, decision.request_bytes, limit, reason)
