"""Standalone initialization without a database, application import or Docker."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
import ast
from types import SimpleNamespace
from unittest.mock import MagicMock


path = Path(__file__).resolve().parents[1] / 'docker/standalone/init.py'
spec = importlib.util.spec_from_file_location('standalone_init', path)
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class BootstrapTests(unittest.TestCase):
    def test_configured_admin_password_is_not_logged_during_initialization(self):
        location = path.parents[2] / 'source/app/post_init.py'
        tree = ast.parse(location.read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'PostInit')
        create_admin = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_create_safe_admin')
        run = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
        final_log = next(n for n in ast.walk(run) if isinstance(n, ast.If) and ast.unparse(n.test) == 'pwd is not None')
        user = SimpleNamespace(id=1, user='administrator')
        model = MagicMock(return_value=user)
        model.query.filter.return_value.first.return_value = None
        bcrypt = MagicMock()
        bcrypt.generate_password_hash.return_value = b'hashed-password'
        subject = SimpleNamespace(_logger=MagicMock(), _configuration={'IRIS_ADM_PASSWORD': 'fixture-password'})
        namespace = {'User': model, 'bc': bcrypt, 'or_': MagicMock(),
                     'db': SimpleNamespace(session=MagicMock()), 'add_user_to_group': MagicMock(),
                     'add_user_to_organisation': MagicMock()}
        exec(compile(ast.Module(body=[create_admin], type_ignores=[]), str(location), 'exec'), namespace)
        namespace['_create_safe_admin'](subject, SimpleNamespace(org_id=1), SimpleNamespace(group_id=1),
                                        'administrator', 'admin@example.org', 'fixture-password', 'fixture-key')
        exec(compile(ast.Module(body=[final_log], type_ignores=[]), str(location), 'exec'),
             {'self': subject, 'pwd': 'fixture-password', 'admin': user})
        self.assertNotIn('fixture-password', str(subject._logger.mock_calls))

    def test_first_start_creates_secrets_and_restarts_retain_them(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bootstrap.initialize(root, 'https://iris.example:18545')
            original = (root / 'iris.env').read_bytes()
            certificate = (root / 'iris-cert.pem').read_bytes()
            values = dict(line.split('=', 1) for line in original.decode().splitlines())
            self.assertEqual(values['POSTGRES_PASSWORD'], values['POSTGRES_ADMIN_PASSWORD'])
            self.assertEqual(len(values['IRIS_SECRET_KEY']), 64)
            self.assertIn(values['RABBITMQ_DEFAULT_PASS'], values['CELERY_BROKER'])
            bootstrap.initialize(root, 'https://iris.example:18545')
            self.assertEqual((root / 'iris.env').read_bytes(), original)
            self.assertEqual((root / 'iris-cert.pem').read_bytes(), certificate)
            names = subprocess.check_output(['openssl', 'x509', '-in', str(root / 'iris-cert.pem'),
                                             '-noout', '-ext', 'subjectAltName'], text=True)
            self.assertIn('DNS:iris.example', names)

    def test_new_public_host_changes_tls_without_rotating_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bootstrap.initialize(root, 'https://localhost:18545')
            original = (root / 'iris.env').read_bytes()
            bootstrap.initialize(root, 'https://192.0.2.10:18545')
            self.assertEqual((root / 'iris.env').read_bytes(), original)
            names = subprocess.check_output(['openssl', 'x509', '-in', str(root / 'iris-cert.pem'),
                                             '-noout', '-ext', 'subjectAltName'], text=True)
            self.assertIn('IP Address:192.0.2.10', names)

    def test_incomplete_credentials_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'iris.env').write_text('POSTGRES_PASSWORD=existing\n')
            with self.assertRaises(RuntimeError):
                bootstrap.initialize(root, 'https://localhost:18545')
            self.assertEqual((root / 'iris.env').read_text(), 'POSTGRES_PASSWORD=existing\n')

    def test_invalid_origin_is_rejected_before_writing(self):
        for origin in ('http://localhost', 'https://user:password@example.org',
                       'https://example.org/path', 'https://example.org/?query=value'):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                bootstrap.public_hostname(origin)
