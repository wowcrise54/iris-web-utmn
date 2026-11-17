import ast
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, and_, create_engine, or_, select
from sqlalchemy.dialects.postgresql import dialect as postgresql_dialect


APP = Path(__file__).resolve().parents[2] / 'source/app'


def load_function(path, name, **namespace):
    tree = ast.parse((APP / path).read_text(encoding='utf-8'))
    function = next((node for node in tree.body
                     if isinstance(node, ast.FunctionDef) and node.name == name), None)
    assert function is not None, f'{name} is missing from {path}'
    exec(compile(ast.Module(body=[function], type_ignores=[]), path, 'exec'), namespace)
    return namespace[name]


def test_query_is_read_alongside_existing_filters():
    read = load_function(
        'blueprints/rest/v2/case_routes/events.py', '_read_filter_args',
        _MULTI_VALUE_FILTER_KEYS=(),
    )
    args = SimpleNamespace(
        get={'query': '  PowerShell  ', 'lucene_query': ' title:login ', 'start_date': '2026-11-01'}.get,
        getlist=lambda key: [],
    )
    assert read(args) == {
        'query': 'PowerShell', 'lucene_query': 'title:login', 'start_date': '2026-11-01',
    }


def test_search_matches_any_field_and_treats_wildcards_as_literal():
    metadata = MetaData()
    events = Table(
        'events', metadata, Column('id', Integer, primary_key=True),
        Column('event_title', String), Column('event_content', String),
        Column('event_source', String),
    )
    search = load_function(
        'datamgmt/case/case_events_db.py', '_event_text_search',
        CasesEvent=events.c, or_=or_,
    )
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        metadata.create_all(conn)
        conn.execute(events.insert(), [
            {'id': 1, 'event_title': 'LOAD_50%', 'event_content': None, 'event_source': None},
            {'id': 2, 'event_title': None, 'event_content': 'load_50% done', 'event_source': None},
            {'id': 3, 'event_title': None, 'event_content': None, 'event_source': 'load_50%'},
            {'id': 4, 'event_title': 'loadX500', 'event_content': None, 'event_source': None},
        ])
        statement = select(events.c.id).where(search('load_50%')).order_by(events.c.id)
        assert conn.execute(statement).scalars().all() == [1, 2, 3]


def test_lucene_matches_fields_and_reports_unknown_names(monkeypatch):
    # Load the real parser and compiler pieces without initializing the web app.
    def load(path, namespace, names=None):
        module_name = 'timeline_test_' + Path(path).stem
        module = ModuleType(module_name)
        module.__dict__.update(namespace)
        monkeypatch.setitem(sys.modules, module_name, module)
        tree = ast.parse((APP / path).read_text(encoding='utf-8'))
        if names is None:
            tree.body = [node for node in tree.body if not (
                isinstance(node, ast.ImportFrom) and node.module.startswith('app.')
            )]
        else:
            tree.body = [node for node in tree.body if getattr(node, 'name', None) in names]
        exec(compile(tree, path, 'exec'), module.__dict__)
        return module

    errors = load('models/errors.py', {})
    parser = load('datamgmt/lucene/query_parser.py', {'SearchQueryError': errors.SearchQueryError})
    shared = load('datamgmt/lucene/query_compiler.py', {
        **vars(parser), '__name__': 'timeline_test_query_compiler', 'and_': and_, 'or_': or_,
        'LIKE_ESCAPE_CHARACTER': '\\',
    }, {'LuceneQueryCompiler', '_escape_like_character', '_like_pattern', '_substring_pattern'})
    metadata = MetaData()
    events = Table('events', metadata, Column('id', Integer, primary_key=True),
                   Column('event_title', String), Column('event_content', String),
                   Column('event_source', String), Column('event_tags', String))
    compiler = load('datamgmt/lucene/event_query_compiler.py', {
        'CasesEvent': events.c, 'or_': or_, 'lucene_parse': parser.lucene_parse,
        'TermValue': parser.TermValue, 'SearchQueryError': errors.SearchQueryError,
        'LIKE_ESCAPE_CHARACTER': '\\', '_substring_pattern': shared._substring_pattern,
        'LuceneQueryCompiler': shared.LuceneQueryCompiler,
    })
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        metadata.create_all(conn)
        conn.execute(events.insert(), [
            {'id': 1, 'event_title': 'Login failed', 'event_tags': None},
            {'id': 2, 'event_title': 'Login failed', 'event_tags': 'routine'},
            {'id': 3, 'event_title': 'PowerShell start', 'event_tags': None},
            {'id': 4, 'event_title': 'Login successful', 'event_tags': None},
        ])
        condition = compiler.compile_event_query('(title:"login failed" OR title:power*) AND NOT tag:routine')
        statement = select(events.c.id).where(condition).order_by(events.c.id)
        assert conn.execute(statement).scalars().all() == [1, 3]

    if psql := os.getenv('IRIS_TIMELINE_TEST_PSQL'):
        dialect = postgresql_dialect(paramstyle='named')
        # The live dialect sets this from SHOW standard_conforming_strings.
        dialect._backslash_escapes = False
        sql = statement.compile(dialect=dialect,
                                compile_kwargs={'literal_binds': True})
        fixture = """
            SET standard_conforming_strings = on;
            CREATE TEMP TABLE events (id integer, event_title text, event_tags text);
            INSERT INTO events VALUES (1, 'Login failed', NULL), (2, 'Login failed', 'routine'),
                                      (3, 'PowerShell start', NULL), (4, 'Login successful', NULL);
        """
        result = subprocess.run(
            [psql, '-XqAt', '-v', 'ON_ERROR_STOP=1'], input=f'{fixture}\n{sql};\n',
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == ['1', '3']

    with pytest.raises(errors.SearchQueryError) as error:
        compiler.compile_event_query('unknown:login')
    assert error.value.get_position() == 0


def test_timeline_statistics_include_empty_buckets_and_rank_matching_fields():
    stats = load_function(
        'business/events.py', '_timeline_statistics',
        Counter=Counter, datetime=datetime, timedelta=timedelta, timezone=timezone,
        _HISTOGRAM_STEPS=(60, 300, 900, 3600, 21600, 86400),
    )
    rows = [
        SimpleNamespace(event_date=datetime(2026, 11, 17, 9, 0, 5),
                        event_source='Sysmon', category_name='Execution'),
        SimpleNamespace(event_date=datetime(2026, 11, 17, 9, 2),
                        event_source='Sysmon', category_name='Execution'),
        SimpleNamespace(event_date=datetime(2026, 11, 17, 9, 2, 50),
                        event_source='EDR', category_name=None),
    ]

    result = stats(rows)
    assert result['interval_seconds'] == 60
    assert result['histogram'] == [
        {'start': '2026-11-17T09:00:00+00:00', 'count': 1},
        {'start': '2026-11-17T09:01:00+00:00', 'count': 0},
        {'start': '2026-11-17T09:02:00+00:00', 'count': 2},
    ]
    assert result['sources'] == [{'value': 'Sysmon', 'count': 2}, {'value': 'EDR', 'count': 1}]
    assert result['categories'] == [{'value': 'Execution', 'count': 2}]
    assert stats([])['histogram'] == []


def test_timeline_list_reports_statistics_for_all_matching_pages():
    from collections import namedtuple

    event = namedtuple('Event', 'event_id event_date event_date_wtz event_added '
                                'event_source category_name parent_event_id')
    timestamp = datetime(2026, 11, 17, 9)
    rows = [event(i, timestamp, None, timestamp, 'Sysmon', 'Execution', None) for i in (1, 2, 3)]
    summarize = load_function(
        'business/events.py', '_timeline_statistics',
        Counter=Counter, datetime=datetime, timedelta=timedelta, timezone=timezone,
        _HISTOGRAM_STEPS=(60,),
    )
    list_events = load_function(
        'business/events.py', 'events_list_filtered',
        get_filtered_case_events=lambda _case_id, _filters: (rows, [], []),
        get_case_event_timelines_map=lambda _ids: {},
        get_case_events_comments_count=lambda _ids: [],
        get_case_iocs_light=lambda _case_id: [],
        get_events_categories=lambda: [],
        get_timeline_state=lambda **_kwargs: None,
        _timeline_statistics=summarize,
    )

    response = list_events(1, {}, page=2, per_page=1, include_stats=True)
    assert [row['event_id'] for row in response['tim']] == [2]
    assert response['pagination']['total'] == 3
    assert response['statistics']['histogram'][0]['count'] == 3
    assert 'statistics' not in list_events(1, {}, page=2, per_page=1)
