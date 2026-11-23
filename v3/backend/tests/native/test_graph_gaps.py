from pathlib import Path
from runpy import run_path


def test_graph_gaps_classify_unsupported_connections_and_assets():
    source = Path(__file__).resolve().parents[2] / 'source/app/business/case_graph_gaps.py'
    compute = run_path(str(source))['case_graph_gaps_compute']
    graph = {
        'nodes': [
            {'key': 'asset:1', 'kind': 'asset', 'compromised': True},
            {'key': 'asset:2', 'kind': 'asset', 'compromised': True,
             'analysis_status': 'Done', 'event_count': 1},
            {'key': 'ioc:3', 'kind': 'ioc'},
        ],
        'edges': [{'key': 'e:1', 'id': 1, 'editable': True, 'directed': True,
                   'source': 'asset:1', 'target': 'asset:2'}],
    }
    rows = compute(graph)
    assert [(row['code'], row['node_keys']) for row in rows] == [
        ('initial_access_unknown', ['asset:1']),
        ('compromised_without_event', ['asset:1']),
        ('unanalysed_compromised', ['asset:1']),
        ('unsupported_edge', ['asset:1', 'asset:2']),
        ('isolated_ioc', ['ioc:3']),
    ]
    assert rows[3]['edge_keys'] == ['e:1']
