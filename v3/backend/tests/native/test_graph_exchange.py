import sys
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace
from xml.etree import ElementTree


def test_export_preserves_relation_and_direction(monkeypatch):
    monkeypatch.setitem(sys.modules, 'app.models.errors', SimpleNamespace(BusinessProcessingError=ValueError))
    source = Path(__file__).resolve().parents[2] / 'source/app/business/case_graph_exchange.py'
    exchange = run_path(str(source))
    relation = {'name': 'connected_to', 'label': 'Connected to', 'stix_relationship': 'communicates-with'}
    graph = {
        'nodes': [
            {'key': 'asset:1', 'kind': 'asset', 'label': 'Host & gateway'},
            {'key': 'ioc:1', 'kind': 'ioc', 'label': '192.0.2.4', 'type': 'ip-dst'},
        ],
        'edges': [{'key': 'e:1', 'source': 'asset:1', 'target': 'ioc:1',
                   'directed': False, 'relation': relation}],
    }
    stix = exchange['case_graph_exchange_to_stix'](graph, [relation], 1, '2026-11-18T00:00:00Z')
    link = next(item for item in stix['objects'] if item['type'] == 'relationship')
    assert link['relationship_type'] == 'communicates-with'
    assert link['x_iris_directed'] is False
    assert link['target_ref'].startswith('ipv4-addr--')
    plan = exchange['case_graph_exchange_parse_stix'](stix)
    assert plan['edges'][0]['directed'] is False
    assert plan['edges'][0]['relation'] == 'connected_to'
    assert plan['iocs'][0]['value'] == '192.0.2.4'
    graphml = ElementTree.fromstring(exchange['case_graph_exchange_to_graphml'](graph))
    edge = graphml.find('.//{*}edge')
    assert edge.attrib['directed'] == 'false'
    assert edge.find("{*}data[@key='e_relation']").text == 'connected_to'
    assert graphml.find(".//{*}node[@id='asset:1']/{*}data[@key='n_label']").text == 'Host & gateway'


def test_json_import_skips_derived_edges(monkeypatch):
    monkeypatch.setitem(sys.modules, 'app.models.errors', SimpleNamespace(BusinessProcessingError=ValueError))
    source = Path(__file__).resolve().parents[2] / 'source/app/business/case_graph_exchange.py'
    exchange = run_path(str(source))
    graph = {'nodes': [{'key': 'node:3', 'kind': 'node', 'label': 'Pivot'}],
             'edges': [{'key': 'derived', 'editable': False}]}
    plan = exchange['case_graph_exchange_parse_json'](graph)
    assert plan['nodes'][0]['ref'] == 'node:3'
    assert plan['edges'] == []
    assert plan['skipped'] == ['derived']
