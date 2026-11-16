"""Resolve and run the MaxPatrol EDR action captured in the SIEM UI."""
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
import re
from uuid import UUID

from .collector import Client, SIEMError


MODULES = ['file_remover', 'host_isolator', 'proc_terminator', 'ip_blocker', 'domain_sinkholer']
ACTION = 'fr_remove_object_file'
FIELD = 'object.fullpath'
EDR = '/app/mpx/api/edr/v1/agents'
GRID = '/api/assets_temporal_readmodel/v1/assets_grid'
HASH = re.compile(r'[a-fA-F0-9]{32}')


def event_target(event):
    asset = event.get('event_src.asset')
    assets = event.get('asset_ids')
    path = event.get(FIELD)
    if not isinstance(asset, str) or not isinstance(assets, list) or asset not in assets:
        return None
    try:
        UUID(asset)
    except ValueError:
        return None
    if not isinstance(path, str) or not path or len(path) > 4096 or not path.isprintable():
        return None
    windows = PureWindowsPath(path)
    posix = PurePosixPath(path)
    drive_path = bool(re.fullmatch(r'[A-Za-z]:', windows.drive) and windows.root)
    if '..' in windows.parts or not (drive_path or posix.root == '/'):
        return None
    if not windows.name or not posix.name:
        return None
    return asset, path


@dataclass(frozen=True)
class Target:
    agent: str
    service: str
    hostname: str
    path: str


class EdrClient(Client):
    def edr_data(self, method, path, **kwargs):
        response, _ = self._request(method, path, **kwargs)
        if response.get('status') != 'success' or not isinstance(response.get('data'), dict):
            raise SIEMError('EDR rejected the request', code='edr_request_rejected')
        return response['data']

    def discover(self, event):
        candidate = event_target(event)
        if candidate is None:
            return None
        asset, path = candidate
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
            return None
        mapping = records[0].get('xdrAgentsIds')
        if not isinstance(mapping, dict) or mapping.get('totalCount') != 1:
            return None
        ids = mapping.get('data')
        if not isinstance(ids, list) or len(ids) != 1 or not isinstance(ids[0], str) or not HASH.fullmatch(ids[0]):
            return None
        agent_id = ids[0]
        discovery = self.edr_data('GET', f'{EDR}/{agent_id}/discovery')
        agent = discovery.get('agent')
        if (not isinstance(agent, dict) or agent.get('hash') != agent_id or agent.get('status') != 'connected'
                or agent.get('auth_status') != 'authorized'):
            return None
        service_info = discovery.get('service')
        agent_info = agent.get('info')
        net = agent_info.get('net') if isinstance(agent_info, dict) else None
        service = service_info.get('hash') if isinstance(service_info, dict) else None
        hostname = net.get('hostname') if isinstance(net, dict) else None
        if not isinstance(service, str) or not HASH.fullmatch(service) or not isinstance(hostname, str) or not hostname:
            return None
        catalog = self.edr_data('GET', f'{EDR}/{agent_id}/actions', params={
            'lang': 'ru',
            'fields': [key for key, value in event.items() if value is not None],
            'modules': MODULES,
            'service_hash': service,
        })
        actions = catalog.get('actions')
        if isinstance(actions, list) and any(
            isinstance(action, dict) and action.get('module') == 'file_remover'
            and action.get('action') == ACTION and action.get('fields') == [FIELD]
            for action in actions
        ):
            return Target(agent_id, service, hostname, path)
        return None

    def execute(self, target):
        data = self.edr_data('POST', f'{EDR}/{target.agent}/modules/file_remover/actions/{ACTION}',
                            params={'lang': 'ru', 'service_hash': target.service},
                            body={'data': {FIELD: target.path}})
        status = data.get('status')
        if status not in ('success', 'failure'):
            status = 'unknown'
        reason = data.get('reason')
        return {'status': status, 'reason': reason[:500] if isinstance(reason, str) else ''}
