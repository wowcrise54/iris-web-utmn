"""Exercise the registered v2 contracts without connecting to a database.

Authentication state and database results are fixtures; route registration,
permission checks, parsing and field selection use the actual application.
"""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from marshmallow import ValidationError
from sqlalchemy import select

from app import app
from app.blueprints import access_controls
from app.blueprints.rest.v2 import avatars
from app.blueprints.rest.v2 import cases as case_routes
from app.blueprints.rest.v2.case_routes import datastore
from app.blueprints.rest.v2.manage_routes import customers, users
from app.models.authorization import Permissions, User
from app.schema.marshables import CaseSchemaForAPIV2, CaseDetailsSchema


@pytest.fixture
def auth(monkeypatch):
    state = {'authenticated': True, 'permissions': 0}
    monkeypatch.setattr(access_controls, 'is_user_authenticated', lambda _request: state['authenticated'])
    monkeypatch.setattr(access_controls, 'ac_get_effective_permissions_of_user', lambda _user: state['permissions'])
    monkeypatch.setitem(app.config, 'SECRET_KEY', 'isolated-contract-key')
    return state


def get(path):
    return app.test_client().get(path)


@pytest.mark.parametrize('path', [
    '/api/v2/manage/compromise-statuses', '/api/v2/manage/outcome-statuses',
    '/api/v2/users/lookup/id/1', '/api/v2/users/lookup/login/analyst',
    '/api/v2/cases/1/datastore/filter?q={}', '/api/v2/manage/customers/1/cases',
    '/api/v2/manage/users?user_ids=1',
])
def test_new_contracts_require_authentication(auth, path):
    auth['authenticated'] = False
    assert get(path).status_code == 401


@pytest.mark.parametrize('route,expected', [
    ('compromise-statuses', [
        {'value': 0, 'name': 'To be determined'}, {'value': 1, 'name': 'Compromised'},
        {'value': 2, 'name': 'Not compromised'}, {'value': 3, 'name': 'Unknown'},
    ]),
    ('outcome-statuses', [
        {'value': 0, 'name': 'Unknown'}, {'value': 1, 'name': 'False positive'},
        {'value': 2, 'name': 'True positive with impact'}, {'value': 3, 'name': 'Not applicable'},
        {'value': 4, 'name': 'True positive without impact'}, {'value': 5, 'name': 'Legitimate'},
    ]),
])
def test_enum_contracts_do_not_require_admin(auth, route, expected):
    response = get('/api/v2/manage/' + route)
    assert response.status_code == 200
    assert response.json == expected


@pytest.mark.parametrize('suffix', ['id/1', 'login/analyst'])
def test_lookup_returns_only_the_intended_public_fields(auth, monkeypatch, suffix):
    user = SimpleNamespace(id=1, user='analyst', name='Analyst', email='private',
                           uuid='private', active=True, password='private', permissions=65535)
    query = Mock()
    query.filter.return_value.first.return_value = user
    monkeypatch.setattr(avatars, 'User', SimpleNamespace(query=query, id=User.id, user=User.user))
    response = get('/api/v2/users/lookup/' + suffix)
    assert response.status_code == 200
    assert response.json == {'user_id': 1, 'user_login': 'analyst', 'user_name': 'Analyst'}


def test_lookup_missing_user_is_404(auth, monkeypatch):
    query = Mock()
    query.filter.return_value.first.return_value = None
    monkeypatch.setattr(avatars, 'User', SimpleNamespace(query=query, id=User.id, user=User.user))
    assert get('/api/v2/users/lookup/id/999').status_code == 404


@pytest.mark.parametrize('q', [[], {'id': [1]}, {'name': 'file'}, {'has_password': 'true'}, {'unknown': []}])
def test_datastore_filter_rejects_bad_shapes(auth, monkeypatch, q):
    monkeypatch.setattr(datastore, 'cases_exists', lambda _identifier: True)
    monkeypatch.setattr(datastore, 'ac_fast_check_current_user_has_case_access', lambda *_args: True)
    response = get('/api/v2/cases/1/datastore/filter?q=' + json.dumps(q))
    assert response.status_code == 400


def test_datastore_filter_preserves_literal_plus_and_false_flag_semantics(auth, monkeypatch):
    monkeypatch.setattr(datastore, 'cases_exists', lambda _identifier: True)
    monkeypatch.setattr(datastore, 'ac_fast_check_current_user_has_case_access', lambda *_args: True)

    def filtered(value, identifier):
        assert value == {'name': ['C++'], 'is_ioc': True}
        assert identifier == 1
        return {'id': 'root', 'children': []}, None
    monkeypatch.setattr(datastore, 'datastore_filter_tree', filtered)
    # One normal query-string encoding; JSON must not be form-decoded twice.
    from urllib.parse import urlencode
    q = urlencode({'q': json.dumps({'name': ['C++'], 'is_ioc': True, 'has_password': False})})
    response = get('/api/v2/cases/1/datastore/filter?' + q)
    assert response.status_code == 200
    assert response.json == {'id': 'root', 'children': []}


def test_datastore_filter_checks_case_access_before_query(auth, monkeypatch):
    monkeypatch.setattr(datastore, 'cases_exists', lambda _identifier: True)
    monkeypatch.setattr(datastore, 'ac_fast_check_current_user_has_case_access', lambda *_args: False)
    assert get('/api/v2/cases/1/datastore/filter?q={}').status_code == 403


def test_customer_statistics_checks_customer_permission_and_membership(auth, monkeypatch):
    assert get('/api/v2/manage/customers/1/cases').status_code == 403
    auth['permissions'] = Permissions.customers_read.value
    monkeypatch.setattr(customers, 'customers_get', lambda _identifier: object())
    monkeypatch.setattr(customers, 'ac_current_user_has_customer_access', lambda _identifier: False)
    assert get('/api/v2/manage/customers/1/cases').status_code == 403
    monkeypatch.setattr(customers, 'ac_current_user_has_customer_access', lambda _identifier: True)
    monkeypatch.setattr(customers, 'customers_list_cases', lambda _identifier: [])
    response = get('/api/v2/manage/customers/1/cases')
    assert response.status_code == 200
    assert response.json['cases'] == []
    assert response.json['stats']['cases_total'] == 0


class UserQuery:
    def __init__(self):
        self.statement = select(User)

    def filter(self, condition):
        self.statement = self.statement.where(condition)
        return self

    def join(self, *args):
        self.statement = self.statement.join(*args)
        return self

    def order_by(self, order):
        self.statement = self.statement.order_by(order)
        return self

    def paginate(self, **kwargs):
        return SimpleNamespace(total=0, items=[], pages=0, page=kwargs['page'], has_next=False)


def test_admin_user_filters_emit_scoped_and_sorted_query(auth, monkeypatch):
    assert get('/api/v2/manage/users?user_ids=1,2').status_code == 403
    auth['permissions'] = Permissions.server_administrator.value
    query = UserQuery()
    monkeypatch.setattr(users, 'User', SimpleNamespace(query=query, id=User.id, user=User.user, name=User.name))
    response = get('/api/v2/manage/users?user_ids=1,2&customer_id=7&sort=asc')
    assert response.status_code == 200
    compiled = query.statement.compile()
    assert sorted(compiled.params.values(), key=str) == [7, [1, 2]]
    sql = str(compiled)
    assert 'JOIN user_client' in sql
    assert 'ORDER BY' in sql and ' ASC' in sql


@pytest.mark.parametrize('query', ['user_ids=one', 'customer_id=bad', 'sort=random'])
def test_admin_user_filter_rejects_invalid_parameters(auth, query):
    auth['permissions'] = Permissions.server_administrator.value
    assert get('/api/v2/manage/users?' + query).status_code == 400


def test_case_detail_includes_metadata_without_querying_protagonists_in_list_schema(auth, monkeypatch):
    case = SimpleNamespace(case_id=1, status_id=2)
    monkeypatch.setattr(case_routes, 'cases_get_by_identifier', lambda _identifier: case)
    monkeypatch.setattr(case_routes, 'ac_fast_check_current_user_has_case_access', lambda *_args: True)
    protagonists = [{'name': 'Responder', 'role': 'analyst'}]
    monkeypatch.setattr(CaseDetailsSchema, 'get_protagonists', lambda _schema, _obj: protagonists)
    response = get('/api/v2/cases/1')
    assert response.status_code == 200
    assert response.json['status_name'] == 'true_positive_with_impact'
    assert response.json['protagonists'] == protagonists
    assert 'protagonists' not in CaseSchemaForAPIV2().dump(case)


@pytest.mark.parametrize('value', ['name', [1], None])
def test_protagonist_input_preserves_list_of_dict_validation(value):
    with pytest.raises(ValidationError):
        CaseSchemaForAPIV2().fields['protagonists'].deserialize(value)
