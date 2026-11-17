"""Regression tests for the MCP alert update mutation boundary.

Execute the real handler with inert schema/business doubles, without a database.
"""
import ast
import copy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


SOURCE = Path(__file__).resolve().parents[2] / 'source/app/blueprints/rest/v2/mcp/tools/alerts.py'


class MCPError(Exception):
    pass


class ValueErrorWithMessages(ValueError):
    messages = {'alert_title': ['Invalid value']}


class AlertUpdateBoundaryTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
        nodes = []
        for node in tree.body:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == '_ALERT_UPDATE_PROPERTIES':
                nodes.append(node)
            elif isinstance(node, ast.FunctionDef) and node.name == 'iris_alerts_update':
                node.decorator_list = []
                nodes.append(node)
        self.alert = SimpleNamespace(alert_id=1, alert_customer_id=10, alert_title='Original')
        self.schema = Mock()
        def load(payload, instance, partial):
            for key, value in payload.items():
                setattr(instance, key, value)
            return instance
        self.schema.load.side_effect = load
        self.schema.dump.side_effect = lambda alert: vars(alert).copy()
        self.update = Mock(side_effect=lambda pristine, updated, activity: updated)
        self.scope = dict(copy=copy, MCPError=MCPError,
                          protocol=SimpleNamespace(INVALID_PARAMS=-32602, INTERNAL_ERROR=-32603),
                          _get_alert=Mock(return_value=self.alert), _alert_schema=self.schema,
                          alerts_update=self.update, ValidationError=ValueError,
                          BusinessProcessingError=RuntimeError)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), self.scope)
        self.call = self.scope['iris_alerts_update']

    def test_immutable_audit_relationship_and_unknown_fields_are_rejected_atomically(self):
        for key in ('alert_id', 'alert_uuid', 'comments', 'alert_customer_id', 'alert_creation_time',
                    'date_update', 'resolved_at', 'modification_history',
                    'customer', 'owner', 'severity', 'status', 'classification',
                    'resolution_status', 'cases', 'iocs', 'alert_iocs', 'assets',
                    'artifacts', 'clusters', 'investigation_flow',
                    'alert_customer_id\\u0000', 'ALERT_CUSTOMER_ID', 'future_field'):
            with self.subTest(key=key):
                before = vars(self.alert).copy()
                with self.assertRaises(MCPError):
                    self.call({'alert_identifier': 1, 'payload': {'alert_title': 'Changed', key: 20}})
                self.assertEqual(before, vars(self.alert))
                self.schema.load.assert_not_called()
                self.update.assert_not_called()

    def test_all_advertised_fields_still_reach_schema(self):
        payload = {
            'alert_title': 'Changed', 'alert_description': 'Details',
            'alert_source': 'SIEM', 'alert_source_ref': 'event-1',
            'alert_source_link': 'https://example.invalid/event',
            'alert_source_event_time': '2026-10-18T00:00:00',
            'alert_note': 'Analyst note', 'alert_tags': 'tag',
            'alert_severity_id': 2, 'alert_status_id': 3,
            'alert_resolution_status_id': None, 'alert_classification_id': None,
            'alert_owner_id': 5, 'alert_context': {'alert_customer_id': 20},
        }
        self.call({'alert_identifier': 1, 'payload': payload})
        self.schema.load.assert_called_once_with(payload, instance=self.alert, partial=True)
        self.update.assert_called_once()
        self.assertEqual(10, self.alert.alert_customer_id)

    def test_owner_unassignment_and_input_preservation(self):
        for value in (-1, '-1', None):
            with self.subTest(value=value):
                payload = {'alert_owner_id': value}
                self.call({'alert_identifier': 1, 'payload': payload})
                self.assertIsNone(self.alert.alert_owner_id)
                self.assertEqual(value, payload['alert_owner_id'])

    def test_schema_validation_error_keeps_protocol_error(self):
        self.schema.load.side_effect = ValueErrorWithMessages()
        with self.assertRaises(MCPError):
            self.call({'alert_identifier': 1, 'payload': {'alert_title': 'Changed'}})
        self.update.assert_not_called()

    def test_empty_payload_is_rejected(self):
        with self.assertRaises(MCPError):
            self.call({'alert_identifier': 1, 'payload': {}})
        self.schema.load.assert_not_called()


if __name__ == '__main__':
    unittest.main()
