"""Exercise the shipped browser runtime and password controls in Node."""
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest
import app.i18n as i18n

ROOT = Path(__file__).resolve().parents[2] / "source" / "app"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node is required for client checks")


def run_node(script):
    result = subprocess.run([NODE], input=script, capture_output=True, text=True, encoding="utf-8", timeout=15)
    assert result.returncode == 0, result.stderr


def test_client_catalog_fallback_placeholders_plurals_and_table_defaults():
    payload = json.dumps(i18n.js_catalog("ru"), ensure_ascii=False)
    runtime = json.dumps(str(ROOT / "static/assets/js/iris/i18n.js"))
    run_node(f"""
const vm = require('vm'), fs = require('fs'), assert = require('assert');
const jq = {{fn: {{dataTable: {{defaults: {{}}}}, selectpicker: {{defaults: {{}}}}}},
  extend: (...args) => Object.assign(...args.filter(v => typeof v === 'object'))}};
const window = {{IRIS_I18N: {payload}, jQuery: jq}};
vm.runInNewContext(fs.readFileSync({runtime}, 'utf8'), {{window}});
assert.equal(window.IRIS_I18N.t('Save'), 'Сохранить');
assert.equal(window.IRIS_I18N.t('Customer Name:'), 'Название заказчика:');
assert.equal(window.IRIS_I18N.t('user supplied <value>'), 'user supplied <value>');
assert.equal(window.IRIS_I18N.t('Hello {{name}}', {{name: 'Dashboard'}}), 'Hello Dashboard');
assert.deepEqual([1, 2, 5, 11, 21].map(n => window.ngettext('task', 'tasks', n)),
 ['задача', 'задачи', 'задач', 'задач', 'задача']);
assert.equal(jq.fn.dataTable.defaults.language.lengthMenu, 'Показать _MENU_ записей');
assert.equal(jq.fn.dataTable.defaults.language.paginate.next, 'Следующая');
assert.equal(jq.fn.selectpicker.defaults.noneResultsText, 'Нет результатов для {{0}}');
const enWindow = {{IRIS_I18N: {{locale: 'en'}}}};
vm.runInNewContext(fs.readFileSync({runtime}, 'utf8'), {{window: enWindow}});
assert.equal(enWindow.t('Save'), 'Save');
""")


def test_login_password_visibility_can_be_toggled_back_without_i18n():
    html = (ROOT / "blueprints/login/templates/login.html").read_text(encoding="utf-8")
    script = next(s for s in re.findall(r"<script[^>]*>(.*?)</script>", html, re.S)
                  if "togglePassword.addEventListener" in s)
    run_node(f"""
const vm = require('vm'), assert = require('assert');
let click;
const password = {{type: 'password', getAttribute() {{return this.type;}},
 setAttribute(key, value) {{this.type = value;}}}};
const toggle = {{addEventListener(event, callback) {{click = callback;}},
 classList: {{toggle() {{}}}}}};
vm.runInNewContext({json.dumps(script)}, {{document: {{querySelector:
 selector => selector === '#password' ? password : toggle}}}});
click.call(toggle, {{}}); assert.equal(password.type, 'text');
click.call(toggle, {{}}); assert.equal(password.type, 'password');
""")
