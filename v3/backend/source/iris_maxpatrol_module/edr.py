"""Resolve and run actions advertised by a MaxPatrol EDR agent."""
from dataclasses import dataclass
from os import getenv
from pathlib import PurePosixPath, PureWindowsPath
import re
from uuid import UUID

from .collector import Client, SIEMError, event_uuid


MODULES = ['file_remover', 'host_isolator', 'proc_terminator', 'ip_blocker', 'domain_sinkholer']
EDR = '/app/mpx/api/edr/v1/agents'
GRID = '/api/assets_temporal_readmodel/v1/assets_grid'
HASH = re.compile(r'[a-fA-F0-9]{32}')
IDENTIFIER = re.compile(r'[a-zA-Z][a-zA-Z0-9_]{0,127}')
ENABLED_PARAMETER = 'edr_response_enabled'
EDR_RESPONSE_PARAMETER = {
    'param_name': ENABLED_PARAMETER,
    'param_human_name': 'Выполнение действий MaxPatrol EDR',
    'param_description': 'Разрешает запуск выбранного действия EDR из кейса после подтверждения.',
    'default': False,
    'mandatory': False,
    'type': 'bool',
}


def execution_enabled(parameters):
    for parameter in parameters or ():
        if parameter['param_name'] == ENABLED_PARAMETER and 'value' in parameter:
            return parameter['value'] is True
    return getenv('IRIS_EDR_RESPONSE_ENABLED', '').lower() == 'true'


def event_asset(event):
    asset = event.get('event_src.asset')
    assets = event.get('asset_ids')
    if not isinstance(asset, str) or not isinstance(assets, list) or asset not in assets:
        return None
    try:
        UUID(asset)
    except ValueError:
        return None
    return asset


def valid_file_path(path):
    if not isinstance(path, str) or not path or len(path) > 4096 or not path.isprintable():
        return False
    windows = PureWindowsPath(path)
    posix = PurePosixPath(path)
    drive_path = bool(re.fullmatch(r'[A-Za-z]:', windows.drive) and windows.root)
    if '..' in windows.parts or not (drive_path or posix.root == '/'):
        return False
    return bool(windows.name and posix.name)


def eligible_events(events):
    if isinstance(events, list):
        for event in events:
            if isinstance(event, dict) and event_asset(event) is not None:
                uid = event_uuid(event)
                if uid:
                    yield uid, event


EVENT_DETAIL_FIELDS = (
    'subject.account.name', 'subject.process.name', 'subject.process.id', 'subject.process.fullpath',
    'action', 'object.account.name', 'object.process.name', 'object.process.id',
    'object.process.fullpath', 'object.name', 'object.fullpath', 'status',
    'event_src.ip', 'event_src.title', 'event_src.subsys', 'msgid',
)


def event_display(event):
    fields = ('time', 'text', 'event_src.host', 'event_src.fqdn', 'event_src.hostname', *EVENT_DETAIL_FIELDS)
    values = {
        key: value[:2048] if isinstance(value, str) else value
        for key in fields if (value := event.get(key)) is not None
        and (isinstance(value, str) and value.strip() or type(value) in (int, bool))
    }
    return {
        'time': values.get('time'),
        'host': values.get('event_src.host') or values.get('event_src.fqdn') or values.get('event_src.hostname'),
        'text': values.get('text'),
        'details': {key: values[key] for key in EVENT_DETAIL_FIELDS if key in values},
    }


def summarize_events(alerts):
    events = []
    counts = {'matched_alerts': 0, 'saved_events': 0}
    for alert_id, title, saved in alerts:
        counts['matched_alerts'] += 1
        if isinstance(saved, list):
            counts['saved_events'] += len(saved)
        events.extend({'alert_id': alert_id, 'alert_title': title, 'event_id': uid,
                       'asset': event['event_src.asset'], **event_display(event)}
                      for uid, event in eligible_events(saved))
    return events, counts


@dataclass(frozen=True)
class Target:
    agent: str
    service: str
    hostname: str
    module: str
    action: str
    parameters: dict
    title: str


def catalog_targets(actions, event, agent, service, hostname):
    targets = {}
    ambiguous = set()
    for item in actions if isinstance(actions, list) else ():
        if not isinstance(item, dict):
            continue
        module, action, fields = (item.get(key) for key in ('module', 'action', 'fields'))
        if module not in MODULES or not isinstance(action, str) or not IDENTIFIER.fullmatch(action):
            continue
        if not isinstance(fields, list) or not all(isinstance(field, str) for field in fields):
            continue
        parameters = {field: event.get(field) for field in fields}
        if not all(
            type(value) in (bool, int)
            or isinstance(value, str) and 0 < len(value) <= 4096 and value.strip() and value.isprintable()
            for value in parameters.values()
        ):
            continue
        if module == 'file_remover' and (
            not parameters or not all(valid_file_path(value) for value in parameters.values())
        ):
            continue
        localization = item.get('localization')
        labels = localization.get('action') if isinstance(localization, dict) else None
        title = labels.get('title') if isinstance(labels, dict) else None
        key = module, action
        if key in targets and targets[key].parameters != parameters:
            ambiguous.add(key)
        targets[key] = Target(agent, service, hostname, module, action, parameters,
                              title[:200] if isinstance(title, str) and title.strip() else action)
    return [target for key, target in targets.items() if key not in ambiguous]


class EdrClient(Client):
    def edr_data(self, method, path, **kwargs):
        response, _ = self._request(method, path, **kwargs)
        if response.get('status') != 'success' or not isinstance(response.get('data'), dict):
            raise SIEMError('EDR rejected the request', code='edr_request_rejected')
        return response['data']

    def discover(self, event):
        asset = event_asset(event)
        if asset is None:
            return []
        query, _ = self._request('POST', GRID, body={
            'pdql': 'select(compact(Core:Host.Softs<XDRAgent>.AgentID) AS xdrAgentsIds)',
            'additionalFilterParameters': {'assetIds': [asset]},
            'includeNestedGroups': False,
        })
        token = query.get('token')
        if not isinstance(token, str) or not token:
            raise SIEMError('Missing asset query token', code='invalid_asset_query')
        result, _ = self._request('GET', GRID + '/data', params={'pdqlToken': token, 'limit': 2})
        records = result.get('records')
        if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
            return []
        mapping = records[0].get('xdrAgentsIds')
        if not isinstance(mapping, dict) or mapping.get('totalCount') != 1:
            return []
        ids = mapping.get('data')
        if not isinstance(ids, list) or len(ids) != 1 or not isinstance(ids[0], str) or not HASH.fullmatch(ids[0]):
            return []
        agent_id = ids[0]
        discovery = self.edr_data('GET', f'{EDR}/{agent_id}/discovery')
        agent = discovery.get('agent')
        if (not isinstance(agent, dict) or agent.get('hash') != agent_id or agent.get('status') != 'connected'
                or agent.get('auth_status') != 'authorized'):
            return []
        service_info = discovery.get('service')
        agent_info = agent.get('info')
        net = agent_info.get('net') if isinstance(agent_info, dict) else None
        service = service_info.get('hash') if isinstance(service_info, dict) else None
        hostname = net.get('hostname') if isinstance(net, dict) else None
        if not isinstance(service, str) or not HASH.fullmatch(service) or not isinstance(hostname, str) or not hostname:
            return []
        catalog = self.edr_data('GET', f'{EDR}/{agent_id}/actions', params={
            'lang': 'ru',
            'fields': [key for key, value in event.items() if value is not None],
            'modules': MODULES,
            'service_hash': service,
        })
        return catalog_targets(catalog.get('actions'), event, agent_id, service, hostname)

    def execute(self, target):
        data = self.edr_data('POST', f'{EDR}/{target.agent}/modules/{target.module}/actions/{target.action}',
                            params={'lang': 'ru', 'service_hash': target.service},
                            body={'data': target.parameters})
        status = data.get('status')
        if status not in ('success', 'failure'):
            status = 'unknown'
        reason = data.get('reason')
        return {'status': status, 'reason': reason[:500] if isinstance(reason, str) else ''}
