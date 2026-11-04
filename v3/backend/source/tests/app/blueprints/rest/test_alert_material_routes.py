"""Ownership and object scope checks use the real route bodies without a database."""
import inspect
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from app.blueprints.rest.v2.alerts_routes import artifacts, iocs
from app.business import alert_materials
from app.models.errors import ObjectNotFoundError
from app.models.errors import BusinessProcessingError


class TestMaterialRouteAccess(TestCase):
    def setUp(self):
        self.alert = SimpleNamespace(alert_id=1, alert_owner_id=7, iocs=[])
        self.context = [
            patch.object(artifacts, '_alert', return_value=self.alert),
            patch.object(artifacts, 'iris_current_user', SimpleNamespace(id=8)),
            patch.object(artifacts, 'ac_api_return_access_denied', return_value='denied'),
        ]
        for item in self.context:
            item.start()
            self.addCleanup(item.stop)

    def test_non_owner_cannot_create(self):
        with patch.object(artifacts, 'create_artifact') as create:
            self.assertEqual('denied', inspect.unwrap(artifacts.add_artifact)(1))
            create.assert_not_called()

    def test_non_owner_cannot_edit(self):
        with patch.object(artifacts, 'get_artifact') as get:
            self.assertEqual('denied', inspect.unwrap(artifacts.edit_artifact)(1, 2))
            get.assert_not_called()

    def test_non_owner_cannot_delete(self):
        with patch.object(artifacts, 'delete_artifact') as delete:
            self.assertEqual('denied', inspect.unwrap(artifacts.remove_artifact)(1, 2))
            delete.assert_not_called()

    def test_unassigned_alert_has_no_material_editor(self):
        self.alert.alert_owner_id = None
        self.assertEqual('denied', inspect.unwrap(artifacts.add_artifact)(1))

    def test_owner_loses_write_after_reassignment(self):
        with patch.object(artifacts, 'iris_current_user', SimpleNamespace(id=7)), \
                patch.object(artifacts, 'request', SimpleNamespace(get_json=lambda: {})), \
                patch.object(artifacts, 'update_artifact', return_value=SimpleNamespace(serialize=lambda: 'saved')), \
                patch.object(artifacts, 'get_artifact', return_value=object()), \
                patch.object(artifacts, 'response_api_success', side_effect=lambda data: data):
            self.assertEqual('saved', inspect.unwrap(artifacts.edit_artifact)(1, 2))
            self.alert.alert_owner_id = 9
            self.assertEqual('denied', inspect.unwrap(artifacts.edit_artifact)(1, 2))

    def test_reader_can_list_without_ownership(self):
        self.alert.artifacts = [SimpleNamespace(serialize=lambda: {'id': 2})]
        with patch.object(artifacts, 'response_api_success', side_effect=lambda data: data):
            self.assertEqual([{'id': 2}], inspect.unwrap(artifacts.list_artifacts)(1))

    def test_unreadable_alert_is_not_found(self):
        with patch.object(artifacts, '_alert', side_effect=ObjectNotFoundError), \
                patch.object(artifacts, 'response_api_not_found', return_value='missing'):
            self.assertEqual('missing', inspect.unwrap(artifacts.download_artifact)(1, 2))

    def test_download_is_scoped_and_forced_as_attachment(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'file'
            path.write_bytes(b'pcap')
            row = SimpleNamespace(kind='file', value='sample.html')
            response = SimpleNamespace(headers={})
            with patch.object(artifacts, 'get_artifact', return_value=row) as get, \
                    patch.object(artifacts, 'artifact_path', return_value=path), \
                    patch.object(artifacts, 'send_file', return_value=response) as send:
                self.assertIs(response, inspect.unwrap(artifacts.download_artifact)(1, 2))
                get.assert_called_once_with(self.alert, 2)
                self.assertTrue(send.call_args.kwargs['as_attachment'])
                self.assertEqual('application/octet-stream', send.call_args.kwargs['mimetype'])
                self.assertEqual('nosniff', response.headers['X-Content-Type-Options'])


class TestIocMaterialAccess(TestCase):
    def test_unlink_preserves_ioc_and_other_alerts(self):
        ioc = SimpleNamespace(ioc_id=2, case_id=4)
        alert = SimpleNamespace(alert_id=1, iocs=[ioc])
        other = SimpleNamespace(iocs=[ioc])
        with patch.object(iocs, '_owned_alert', return_value=alert), \
                patch.object(iocs, 'material_history'), patch.object(iocs, 'response_api_success'), \
                patch.object(iocs, 'db') as db:
            inspect.unwrap(iocs.remove_alert_ioc)(1, 2)
            self.assertEqual([], alert.iocs)
            self.assertEqual([ioc], other.iocs)
            self.assertEqual(4, ioc.case_id)
            db.session.delete.assert_not_called()

    def test_non_owner_cannot_edit_existing_ioc(self):
        with patch.object(iocs, 'alerts_get', return_value=SimpleNamespace(alert_owner_id=7)), \
                patch.object(iocs, 'iris_current_user', SimpleNamespace(id=8)), \
                patch.object(iocs, 'session', {}), \
                patch.object(iocs, 'ac_api_return_access_denied', return_value='denied'), \
                patch.object(iocs, 'alerts_get_ioc') as lookup:
            self.assertEqual('denied', iocs.alert_iocs_operations.update(1, 2))
            lookup.assert_not_called()

    def test_foreign_ioc_cannot_be_unlinked(self):
        with patch.object(iocs, '_owned_alert', return_value=SimpleNamespace(iocs=[])), \
                patch.object(iocs, 'response_api_not_found', return_value='missing'):
            self.assertEqual('missing', inspect.unwrap(iocs.remove_alert_ioc)(1, 2))


class TestArtifactStorageFailure(TestCase):
    def test_editing_file_description_preserves_import_selection(self):
        row = SimpleNamespace(kind='file', value='sample.pcap', description='old', include_in_case=False, id=2)
        with patch.object(alert_materials, 'material_history'):
            alert_materials.update_artifact(SimpleNamespace(alert_id=1), row, 7, {'description': 'new'})
        self.assertFalse(row.include_in_case)
        self.assertEqual('new', row.description)

    def test_merge_denies_access_before_changing_alert_or_case(self):
        from app.business import alerts as business
        alert = SimpleNamespace(artifacts=[SimpleNamespace(include_in_case=True)])
        with patch.object(business, 'get_case', return_value=SimpleNamespace(case_id=4)), \
                patch.object(business, '_resolve_caller', return_value=SimpleNamespace(id=7)), \
                patch.object(business, 'require_artifact_import_access', side_effect=BusinessProcessingError('denied')), \
                patch.object(business, 'db') as db, patch.object(business, 'merge_alert_in_case') as merge:
            with self.assertRaises(BusinessProcessingError):
                business.alerts_merge(alert, 4)
            merge.assert_not_called()
            db.session.commit.assert_not_called()

    def test_alert_deletion_removes_file_after_database_success(self):
        from app.datamgmt.alerts import alerts_db
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'upload'
            path.write_bytes(b'pcap')
            with patch.object(alerts_db, '_alert_artifact_paths', return_value=[path]), \
                    patch.object(alerts_db, 'db_delete'):
                alerts_db.delete_alert(SimpleNamespace(alert_id=1))
            self.assertFalse(path.exists())

    def test_failed_alert_deletion_keeps_file(self):
        from app.datamgmt.alerts import alerts_db
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'upload'
            path.write_bytes(b'pcap')
            with patch.object(alerts_db, '_alert_artifact_paths', return_value=[path]), \
                    patch.object(alerts_db, 'db_delete', side_effect=RuntimeError('db failure')):
                with self.assertRaises(RuntimeError):
                    alerts_db.delete_alert(SimpleNamespace(alert_id=1))
            self.assertTrue(path.exists())

    def test_migration_accepts_table_created_by_post_init(self):
        import importlib.util
        migration_path = Path(__file__).parents[4] / 'app/alembic/versions/utmn_alert_materials01_add_alert_artifacts.py'
        spec = importlib.util.spec_from_file_location('alert_artifacts_migration', migration_path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with patch.object(migration, 'op') as op, patch.object(migration.sa, 'inspect') as inspect_db:
            inspect_db.return_value.has_table.return_value = True
            migration.upgrade()
            op.create_table.assert_not_called()

    def test_export_requires_full_case_access(self):
        row = SimpleNamespace(include_in_case=True)
        with patch('app.business.access_controls.ac_fast_check_user_has_case_access', return_value=None), \
                patch('app.datamgmt.datastore.datastore_db.datastore_get_root') as root:
            with self.assertRaises(BusinessProcessingError):
                alert_materials.export_artifacts_to_case(SimpleNamespace(artifacts=[row]), SimpleNamespace(case_id=4), 7)
            root.assert_not_called()

    def test_export_copies_only_selected_files_and_preserves_case_copy(self):
        from unittest.mock import Mock
        with TemporaryDirectory() as directory:
            source = Path(directory) / 'source'
            destination = Path(directory) / 'case-copy'
            source.write_bytes(b'pcap-bytes')
            row = SimpleNamespace(id=2, include_in_case=True, kind='file', value='sample.pcap',
                                  description='network', size_bytes=10, sha256='hash')
            alert = SimpleNamespace(alert_id=1, artifacts=[row, SimpleNamespace(include_in_case=False)])
            with patch('app.business.access_controls.ac_fast_check_user_has_case_access', return_value=True), \
                    patch('app.datamgmt.datastore.datastore_db.datastore_get_root', return_value=SimpleNamespace(path_id=1)), \
                    patch('app.datamgmt.datastore.datastore_db.datastore_get_standard_path', return_value=destination), \
                    patch('app.models.models.DataStoreFile') as model, \
                    patch.object(alert_materials, 'artifact_path', return_value=source), \
                    patch.object(alert_materials, 'add_obj_history_entry'), \
                    patch.object(alert_materials, 'material_history'), patch.object(alert_materials, 'db'):
                model.query.filter_by.return_value.first.return_value = None
                model.return_value = Mock()
                alert_materials.export_artifacts_to_case(alert, SimpleNamespace(case_id=4), 7)
                model.assert_called_once()
                source.unlink()
                self.assertEqual(b'pcap-bytes', destination.read_bytes())

    def test_database_failure_removes_uploaded_bytes(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'uuid'
            upload = SimpleNamespace(filename='../../sample.exe', stream=io.BytesIO(b'installer'))
            with patch.object(alert_materials, 'artifact_path', return_value=path), \
                    patch.object(alert_materials, 'material_history', side_effect=RuntimeError('db failure')), \
                    patch.object(alert_materials, 'db'):
                with self.assertRaises(RuntimeError):
                    alert_materials.create_artifact(SimpleNamespace(alert_id=1), 7, {}, upload)
                self.assertFalse(path.exists())

    def test_foreign_artifact_is_not_found(self):
        with patch.object(alert_materials, 'AlertArtifact') as model:
            model.query.filter_by.return_value.first.return_value = None
            with self.assertRaises(ObjectNotFoundError):
                alert_materials.get_artifact(SimpleNamespace(alert_id=1), 99)
            model.query.filter_by.assert_called_once_with(alert_id=1, id=99)
