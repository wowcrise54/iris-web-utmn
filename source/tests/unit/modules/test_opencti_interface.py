from unittest import TestCase
from unittest.mock import MagicMock
from unittest.mock import PropertyMock
from unittest.mock import call
from unittest.mock import patch

import iris_interface.IrisInterfaceStatus as InterfaceStatus
from iris_opencti_module.IrisOpenCTIConfig import module_configuration
from iris_opencti_module.IrisOpenCTIInterface import IrisOpenCTIInterface


class TestOpenCTIInterface(TestCase):
    def test_configuration_exposes_only_manual_ioc_and_alert_triggers(self):
        parameter_names = {
            parameter["param_name"]
            for parameter in module_configuration
        }

        self.assertIn("opencti_manual_ioc_hook_enabled", parameter_names)
        self.assertIn("opencti_manual_alert_hook_enabled", parameter_names)
        self.assertNotIn("opencti_manual_case_hook_enabled", parameter_names)
        self.assertFalse(any(name.startswith("opencti_on_") for name in parameter_names))
        self.assertNotIn("opencti_add_matching_iocs", parameter_names)

    def test_configuration_upgrade_preserves_known_values_and_drops_removed_parameters(self):
        existing = [
            {"param_name": "opencti_url", "default": "", "value": "http://opencti:8080"},
            {"param_name": "opencti_token", "default": "", "value": "secret-token"},
            {"param_name": "opencti_on_ioc_create_hook_enabled", "default": False, "value": True},
        ]

        merged = IrisOpenCTIInterface._merged_configuration(existing)
        merged_values = {
            parameter["param_name"]: parameter["value"]
            for parameter in merged
        }

        self.assertEqual(merged_values["opencti_url"], "http://opencti:8080")
        self.assertEqual(merged_values["opencti_token"], "secret-token")
        self.assertEqual(merged_values["opencti_public_url"], "")
        self.assertEqual(merged_values["opencti_manual_alert_max_iocs"], 100)
        self.assertNotIn("opencti_on_ioc_create_hook_enabled", merged_values)

    def test_register_hooks_removes_legacy_hooks_and_registers_manual_actions(self):
        interface = IrisOpenCTIInterface.__new__(IrisOpenCTIInterface)
        interface.log = MagicMock()
        interface.deregister_from_hook = MagicMock()
        interface.register_to_hook = MagicMock(
            return_value=InterfaceStatus.I2Success(),
        )
        configuration = {
            "opencti_manual_ioc_hook_enabled": True,
            "opencti_manual_alert_hook_enabled": True,
        }

        with patch.object(
            IrisOpenCTIInterface,
            "module_dict_conf",
            new_callable=PropertyMock,
            return_value=configuration,
        ):
            interface.register_hooks(module_id=6)

        disabled_calls = [
            call(module_id=6, iris_hook_name=hook_name)
            for hook_name in IrisOpenCTIInterface._DISABLED_HOOKS
        ]
        for expected_call in disabled_calls:
            self.assertIn(expected_call, interface.deregister_from_hook.call_args_list)

        interface.register_to_hook.assert_has_calls([
            call(
                6,
                iris_hook_name="on_manual_trigger_ioc",
                manual_hook_name="Получить данные из OpenCTI",
            ),
            call(
                6,
                iris_hook_name="on_manual_trigger_alert",
                manual_hook_name="Обогатить IOC алёрта через OpenCTI",
            ),
            call(
                6,
                iris_hook_name="on_manual_trigger_alert_opencti_graph",
                manual_hook_name="Построить граф OpenCTI",
            ),
        ])
