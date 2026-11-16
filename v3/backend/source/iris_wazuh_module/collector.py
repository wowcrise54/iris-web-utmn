"""Wazuh Indexer query and alert conversion."""
from datetime import datetime, timezone


def collect_window(hits, store, end):
    """Advance only after the complete window has been durably processed."""
    count = 0
    for hit in hits:
        if not store.seen(hit):
            store.create(hit)
            count += 1
    store.advance(end)
    return count


def search_body(start, end, level):
    return {'size': 200, 'sort': [{'timestamp': 'asc'}, '_doc'], 'query': {'bool': {'filter': [
        {'range': {'rule.level': {'gte': level}}},
        {'range': {'timestamp': {'gte': start, 'lt': end}}},
    ]}}}


def make_alert(hit, customer, severity, status):
    index, identifier, source = hit['_index'], hit['_id'], hit['_source']
    if not isinstance(source, dict) or not index or not identifier:
        raise ValueError('Invalid Wazuh hit')
    timestamp = datetime.fromisoformat(source['timestamp'].replace('Z', '+00:00'))
    if timestamp.tzinfo is None:
        raise ValueError('Wazuh timestamp has no timezone')
    rule = source.get('rule') or {}
    return {'alert_title': str(rule.get('description') or 'Wazuh alert'),
            'alert_description': str(rule.get('description') or 'Wazuh alert'),
            'alert_source': 'Wazuh', 'alert_source_ref': f'{index}:{identifier}',
            'alert_source_content': source,
            'alert_source_event_time': timestamp.astimezone(timezone.utc).replace(tzinfo=None),
            'alert_customer_id': customer, 'alert_severity_id': severity, 'alert_status_id': status}


class Client:
    def __init__(self, url, username, password, index, timeout=30, verify=True, session=None):
        from urllib.parse import urlsplit
        import re
        import requests
        parts = urlsplit(url)
        if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError('Indexer URL must be HTTPS without credentials, query or fragment')
        if not re.fullmatch(r'[a-z0-9._*,-]+', index):
            raise ValueError('Invalid index pattern')
        if not username or not password:
            raise ValueError('Indexer credentials are required')
        self.url, self.index = url.rstrip('/'), index
        self.auth, self.timeout, self.verify = (username, password), timeout, verify
        self.session = session or requests.Session()

    def hits(self, start, end, level):
        scroll_id = None
        try:
            response = self.session.post(f'{self.url}/{self.index}/_search', params={'scroll': '2m'},
                                         json=search_body(start, end, level), auth=self.auth,
                                         timeout=self.timeout, verify=self.verify)
            while True:
                response.raise_for_status()
                body = response.json()
                if not isinstance(body, dict) or type(body.get('timed_out')) is not bool:
                    raise ValueError('Malformed Indexer search response')
                shards = body.get('_shards')
                if not isinstance(shards, dict) or type(shards.get('failed')) is not int:
                    raise ValueError('Malformed Indexer shard status')
                if body['timed_out'] or shards['failed'] != 0:
                    raise ValueError('Indexer returned incomplete search results')
                scroll_id = body['_scroll_id']
                if not isinstance(scroll_id, str) or not scroll_id:
                    raise ValueError('Malformed Indexer scroll identifier')
                hits = body['hits']['hits']
                if not isinstance(hits, list):
                    raise ValueError('Invalid Indexer search response')
                if not hits:
                    return
                yield from hits
                response = self.session.post(f'{self.url}/_search/scroll', json={'scroll': '2m', 'scroll_id': scroll_id},
                                             auth=self.auth, timeout=self.timeout, verify=self.verify)
        finally:
            if scroll_id:
                try:
                    self.session.delete(f'{self.url}/_search/scroll', json={'scroll_id': [scroll_id]},
                                        auth=self.auth, timeout=self.timeout, verify=self.verify)
                except Exception:
                    pass

    def close(self):
        self.session.close()
