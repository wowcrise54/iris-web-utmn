"""Exercise legacy handler boundaries with inert persistence and response doubles."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


CASE_ROUTES = Path(__file__).resolve().parents[2] / 'source/app/blueprints'


def load_handler(layer, module, handler, **namespace):
    path = CASE_ROUTES / layer / 'case' / f'case_{module}_routes.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == handler)
    function.decorator_list = []
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace[handler]


class LegacyCaseOwnershipTests(unittest.TestCase):
    def test_reads_reject_foreign_objects_and_keep_same_case_access(self):
        for module, handler, lookup, owner, schema in (
            ('tasks', 'deprecated_case_task_view', 'get_task', 'task_case_id', 'CaseTaskSchema'),
            ('ioc', 'deprecated_case_view_ioc', 'iocs_get', 'case_id', 'IocSchema'),
            ('evidences', 'case_get_evidence', 'get_rfile', 'case_id', 'CaseEvidenceSchema'),
        ):
            with self.subTest(module=module):
                obj = SimpleNamespace(**{owner: 20})
                serialize = Mock()
                success = Mock()
                error = Mock()
                call = load_handler('rest', module, handler, response_error=error,
                                    response_success=success, ObjectNotFoundError=LookupError,
                                    **{lookup: Mock(return_value=obj), schema: Mock(return_value=serialize)})

                self.assertIs(error.return_value, call(123, 10))
                serialize.dump.assert_not_called()
                success.assert_not_called()

                self.assertIs(success.return_value, call(123, 20))
                serialize.dump.assert_called_once_with(obj)

    def test_cross_case_revision_never_reaches_delete(self):
        remove = Mock()
        error = Mock()
        call = load_handler('rest', 'notes', 'case_note_revision_delete',
                            get_note=Mock(return_value=SimpleNamespace(note_case_id=20)),
                            notes_delete_revision=remove, response_error=error,
                            response_success=Mock(), BusinessProcessingError=RuntimeError)
        self.assertIs(error.return_value, call(123, 2, 10))
        remove.assert_not_called()
        call(123, 2, 20)
        remove.assert_called_once_with(123, 2)

    def test_cross_case_event_never_reaches_preload_hook_or_delete(self):
        hook = Mock()
        remove = Mock()
        error = Mock()
        event = SimpleNamespace(case_id=20)
        user = object()
        call = load_handler('rest', 'timeline', 'case_delete_event',
                            get_case_event=Mock(return_value=event), call_modules_hook=hook,
                            events_delete=remove, iris_current_user=user,
                            response_error=error, response_success=Mock())
        self.assertIs(error.return_value, call(123, 10))
        hook.assert_not_called()
        remove.assert_not_called()
        call(123, 20)
        hook.assert_called_once_with('on_preload_event_delete', 123, caseid=20)
        remove.assert_called_once_with(user, event)

    def test_foreign_note_comments_modal_does_not_render(self):
        render = Mock()
        error = Mock()
        note = SimpleNamespace(note_case_id=20, note_title='Private')
        call = load_handler('pages', 'notes', 'case_comment_note_modal',
                            get_note=Mock(return_value=note), render_template=render, response_error=error)
        self.assertIs(error.return_value, call(123, 10, False))
        render.assert_not_called()
        self.assertIs(render.return_value, call(123, 20, False))
        render.assert_called_once()

    def test_create_evidence_ignores_record_and_case_overrides(self):
        payload = {'id': 123, 'case': 20, 'filename': 'evidence.txt'}
        create = Mock(return_value=object())
        schema = Mock()
        call = load_handler('rest', 'evidences', 'case_add_rfile',
                            request=Mock(), CaseEvidenceSchema=Mock(return_value=schema),
                            call_deprecated_on_preload_modules_hook=Mock(return_value=payload),
                            evidences_create=create, response_success=Mock(),
                            ValidationError=ValueError, BusinessProcessingError=RuntimeError)
        call(10)
        schema.load.assert_called_once_with({'filename': 'evidence.txt'})
        create.assert_called_once_with(10, schema.load.return_value)

    def test_directory_with_foreign_note_is_rejected_before_any_delete(self):
        path = CASE_ROUTES.parent / 'datamgmt/case/case_notes_db.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'delete_directory')
        delete_note = Mock()
        delete_row = Mock()
        scope = dict(NoteDirectory=SimpleNamespace, delete_note=delete_note, db_delete=delete_row)
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), scope)
        note = SimpleNamespace(note_id=123, note_case_id=20)
        child = SimpleNamespace(id=2, case_id=10, notes=[note], subdirectories=[])
        directory = SimpleNamespace(id=1, case_id=10, notes=[], subdirectories=[child])

        self.assertFalse(scope['delete_directory'](directory))
        delete_note.assert_not_called()
        delete_row.assert_not_called()

        note.note_case_id = 10
        self.assertTrue(scope['delete_directory'](directory))
        delete_note.assert_called_once_with(123, 10)
        self.assertEqual([child, directory], [call.args[0] for call in delete_row.call_args_list])
