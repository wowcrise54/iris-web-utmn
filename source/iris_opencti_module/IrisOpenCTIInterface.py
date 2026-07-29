#!/usr/bin/env python3
#
#  IRIS OpenCTI Module Source Code
#  contact@dfir-iris.org
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 3 of the License, or (at your option) any later version.

import copy

import iris_interface.IrisInterfaceStatus as InterfaceStatus
from iris_interface.IrisModuleInterface import IrisModuleInterface
from iris_interface.IrisModuleInterface import IrisModuleTypes

from app import db
from app.models import IrisModule
import iris_opencti_module.IrisOpenCTIConfig as interface_conf
from iris_opencti_module.opencti_handler.opencti_handler import OpenCTIHandler


class IrisOpenCTIInterface(IrisModuleInterface):
    """
    Provide the interface between IRIS and OpenCTI.
    """
    name = "IrisOpenCTIInterface"
    module_id = -1
    _module_name = interface_conf.module_name
    _module_description = interface_conf.module_description
    _interface_version = interface_conf.interface_version
    _module_version = interface_conf.module_version
    _pipeline_support = interface_conf.pipeline_support
    _pipeline_info = interface_conf.pipeline_info
    _module_configuration = interface_conf.module_configuration
    _module_type = IrisModuleTypes.module_processor
    _DISABLED_HOOKS = (
        "on_postload_ioc_create",
        "on_postload_ioc_update",
        "on_postload_alert_create",
        "on_postload_alert_update",
        "on_postload_case_update",
        "on_manual_trigger_case",
    )

    def _sync_hook(self, module_id, enabled, iris_hook_name, manual_hook_name=None):
        # Re-register manual hooks so stale UI labels and legacy duplicate
        # registrations cannot remain after a module upgrade.
        self.deregister_from_hook(module_id=module_id, iris_hook_name=iris_hook_name)
        if enabled:
            status = self.register_to_hook(
                module_id,
                iris_hook_name=iris_hook_name,
                manual_hook_name=manual_hook_name,
            )
            if status.is_failure():
                self.log.error(status.get_message())
                self.log.error(status.get_data())
            else:
                self.log.info(f"Successfully registered {iris_hook_name} hook")

    def register_hooks(self, module_id: int):
        """
        Register manual-only OpenCTI hooks and remove every legacy automatic hook.
        """
        self.module_id = module_id
        module_conf = self.module_dict_conf

        for hook_name in self._DISABLED_HOOKS:
            self.deregister_from_hook(module_id=module_id, iris_hook_name=hook_name)

        self._sync_hook(
            module_id,
            module_conf.get("opencti_manual_ioc_hook_enabled"),
            "on_manual_trigger_ioc",
            "Получить данные из OpenCTI",
        )
        self._sync_hook(
            module_id,
            module_conf.get("opencti_manual_alert_hook_enabled"),
            "on_manual_trigger_alert",
            "Обогатить IOC алёрта через OpenCTI",
        )

        graph_hook_name = "on_manual_trigger_alert_opencti_graph"
        self._sync_hook(
            module_id,
            module_conf.get("opencti_manual_alert_hook_enabled"),
            graph_hook_name,
            "Построить граф OpenCTI",
        )

    @staticmethod
    def _merged_configuration(existing_configuration):
        existing_values = {
            parameter.get("param_name"): parameter.get("value", parameter.get("default"))
            for parameter in (existing_configuration or [])
        }
        merged = copy.deepcopy(interface_conf.module_configuration)
        for parameter in merged:
            parameter["value"] = existing_values.get(
                parameter["param_name"],
                parameter.get("default"),
            )
        return merged

    def upgrade_existing_registration(self):
        """
        Synchronize an already registered OpenCTI module during IRIS startup.
        """
        module = IrisModule.query.filter(
            IrisModule.module_name == "iris_opencti_module"
        ).first()
        if module is None:
            return False

        module.module_config = self._merged_configuration(module.module_config)
        module.module_description = interface_conf.module_description
        module.module_version = interface_conf.module_version
        module.interface_version = interface_conf.interface_version
        db.session.commit()

        self.register_hooks(module.id)
        return True

    def hooks_handler(self, hook_name: str, hook_ui_name: str, data: any):
        """
        Dispatch OpenCTI hooks to the correct handler.
        """
        self.log.info(f"Received {hook_name}")
        opencti_handler = OpenCTIHandler(
            mod_config=self.module_dict_conf,
            server_config=self.server_dict_conf,
            logger=self.log,
        )

        if hook_name == "on_manual_trigger_ioc":
            status = opencti_handler.safe_handle(opencti_handler.handle_iocs, data)
        elif hook_name == "on_manual_trigger_alert":
            status = opencti_handler.safe_handle(opencti_handler.handle_alerts, data)
        elif hook_name == "on_manual_trigger_alert_opencti_graph":
            status = opencti_handler.safe_handle(opencti_handler.handle_alert_graphs, data)
        else:
            self.log.critical(f"Received unsupported hook {hook_name}")
            return InterfaceStatus.I2Error(data=data, logs=list(self.message_queue))

        if status.is_failure():
            self.log.error(f"Encountered error processing hook {hook_name}")
            return InterfaceStatus.I2Error(data=data, logs=list(self.message_queue))

        self.log.info(f"Successfully processed hook {hook_name}")
        return InterfaceStatus.I2Success(data=data, logs=list(self.message_queue))
