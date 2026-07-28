#!/usr/bin/env python3
#
#  IRIS OpenCTI Module Source Code
#  contact@dfir-iris.org
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 3 of the License, or (at your option) any later version.

import iris_interface.IrisInterfaceStatus as InterfaceStatus
from iris_interface.IrisModuleInterface import IrisModuleInterface
from iris_interface.IrisModuleInterface import IrisModuleTypes

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

    def _sync_hook(self, module_id, enabled, iris_hook_name, manual_hook_name=None):
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
        else:
            self.deregister_from_hook(module_id=self.module_id, iris_hook_name=iris_hook_name)

    def register_hooks(self, module_id: int):
        """
        Registers all OpenCTI hooks.
        """
        self.module_id = module_id
        module_conf = self.module_dict_conf

        self._sync_hook(
            module_id,
            module_conf.get("opencti_on_ioc_create_hook_enabled"),
            "on_postload_ioc_create",
        )
        self._sync_hook(
            module_id,
            module_conf.get("opencti_on_ioc_update_hook_enabled"),
            "on_postload_ioc_update",
        )
        self._sync_hook(
            module_id,
            module_conf.get("opencti_on_alert_create_hook_enabled"),
            "on_postload_alert_create",
        )
        self._sync_hook(
            module_id,
            module_conf.get("opencti_on_alert_update_hook_enabled"),
            "on_postload_alert_update",
        )
        self._sync_hook(
            module_id,
            module_conf.get("opencti_on_case_update_hook_enabled"),
            "on_postload_case_update",
        )
        self._sync_hook(
            module_id,
            module_conf.get("opencti_manual_ioc_hook_enabled"),
            "on_manual_trigger_ioc",
            "Get OpenCTI insight",
        )
        self._sync_hook(
            module_id,
            module_conf.get("opencti_manual_alert_hook_enabled"),
            "on_manual_trigger_alert",
            "Enrich alert with OpenCTI",
        )
        self._sync_hook(
            module_id,
            module_conf.get("opencti_manual_case_hook_enabled"),
            "on_manual_trigger_case",
            "Enrich case with OpenCTI",
        )

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

        if hook_name in ["on_postload_ioc_create", "on_postload_ioc_update", "on_manual_trigger_ioc"]:
            status = opencti_handler.safe_handle(opencti_handler.handle_iocs, data)
        elif hook_name in ["on_postload_alert_create", "on_postload_alert_update", "on_manual_trigger_alert"]:
            status = opencti_handler.safe_handle(opencti_handler.handle_alerts, data)
        elif hook_name in ["on_postload_case_update", "on_manual_trigger_case"]:
            status = opencti_handler.safe_handle(opencti_handler.handle_cases, data)
        else:
            self.log.critical(f"Received unsupported hook {hook_name}")
            return InterfaceStatus.I2Error(data=data, logs=list(self.message_queue))

        if status.is_failure():
            self.log.error(f"Encountered error processing hook {hook_name}")
            return InterfaceStatus.I2Error(data=data, logs=list(self.message_queue))

        self.log.info(f"Successfully processed hook {hook_name}")
        return InterfaceStatus.I2Success(data=data, logs=list(self.message_queue))
