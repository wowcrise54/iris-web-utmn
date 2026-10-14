"""Admin-only provider probe. Sends a fixed greeting, never case data."""
from dataclasses import replace
from urllib.parse import urlsplit

import requests

from app.iris_engine.llm.client import get_llm_provider


def _request(method, url, **kwargs):
    try:
        with requests.request(method, url, timeout=(10, 30),
                              allow_redirects=False, **kwargs) as response:
            if response.status_code != 200:
                return None, f'http_{response.status_code}'
            payload = response.json()
            if not isinstance(payload, dict) or payload.get('error'):
                return None, 'invalid_response'
            return payload, None
    except requests.Timeout:
        return None, 'timeout'
    except requests.RequestException:
        return None, 'connection_error'
    except ValueError:
        return None, 'invalid_response'


def check_connection(config):
    # Checking works before enabling Yuki or selecting a model.
    adapter = get_llm_provider(replace(
        config, enabled=True, model=config.model or '__connection_check__'))
    base = adapter._base_url
    parsed = urlsplit(base)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError('Base URL must be HTTP(S) without credentials, query, or fragment.')
    headers = {}
    if config.api_key:
        headers['Authorization'] = f'Bearer {config.api_key}'
    if adapter.name == 'anthropic':
        headers = {'x-api-key': config.api_key, 'anthropic-version': '2023-06-01'}
        models_url, completion_url = f'{base}/v1/models', f'{base}/v1/messages'
    elif adapter.name == 'ollama':
        models_url, completion_url = f'{base}/api/tags', f'{base}/api/chat'
    else:
        models_url = adapter.api_url('models')
        completion_url = adapter.api_url('chat/completions')

    listing, models_error = _request('GET', models_url, headers=headers)
    models = []
    if listing is not None:
        key = 'models' if adapter.name == 'ollama' else 'data'
        entries = listing.get(key)
        if not isinstance(entries, list):
            models_error = 'invalid_response'
        else:
            models = sorted({entry.get('name' if adapter.name == 'ollama' else 'id')
                             for entry in entries if isinstance(entry, dict)
                             and isinstance(entry.get('name' if adapter.name == 'ollama' else 'id'), str)
                             and entry.get('name' if adapter.name == 'ollama' else 'id')})

    result = dict(models=models, models_error=models_error,
                  model=config.model, model_accessible=None, model_error=None)
    if not config.model:
        return result
    body = {'model': config.model,
            'messages': [{'role': 'user', 'content': 'Reply OK.'}]}
    if adapter.name == 'anthropic':
        body['max_tokens'] = 16
    elif adapter.name == 'ollama':
        body.update(stream=False, options={'num_predict': 16})
    else:
        body.update(stream=False, max_completion_tokens=16)
        # Custom servers commonly implement the original Chat Completions limit.
        if adapter.name == 'custom':
            body['max_tokens'] = body.pop('max_completion_tokens')
    reply, error = _request('POST', completion_url, headers=headers, json=body)
    if reply is not None:
        if adapter.name == 'anthropic':
            valid = isinstance(reply.get('content'), list)
        elif adapter.name == 'ollama':
            valid = isinstance(reply.get('message'), dict) and reply.get('done') is True
        else:
            choices = reply.get('choices')
            valid = (isinstance(choices, list) and bool(choices)
                     and isinstance(choices[0], dict)
                     and isinstance(choices[0].get('message'), dict))
        if not valid:
            error = 'invalid_response'
    result.update(model_accessible=error is None, model_error=error)
    return result
