
# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

__all__ = ["WrapExtension"]

import omni.ext
import carb
import carb.settings

from pxr import UsdGeom, Usd

from omni.kit.notification_manager import post_notification, NotificationStatus
from omni.kit.async_engine import run_coroutine
from .shrink_utils import shrink_wrap
import omni.kit.commands


class WrapExtension(omni.ext.IExt):

    def on_startup(self):
        app = omni.kit.app.get_app_interface()
        ext_manager = app.get_extension_manager()
        self._menu = None
        self._notification = None
        self._extension_toggle_sub = ext_manager.subscribe_to_extension_enable(
            on_enable_fn=lambda _: self._register_menu(),
            on_disable_fn=lambda _: self._unregister_menu()
        )
        self._prims = []
        self._pending_task = None

    def _get_nested(self, objects):
        """Check for nested prim selection"""
        for prim in objects.get("prim_list", []):
            all_children = prim.GetAllChildren()
            for check_prim in objects.get("prim_list", []):
                if prim != check_prim and check_prim in all_children:
                    self._notify(f"Nested selection: {check_prim.GetName()}")
                    return check_prim

    def _cant_copy(self, objects):
        for prim in objects.get("prim_list", []):
            if not omni.usd.can_be_copied(prim):
                return prim

    # Checks
    def _not_referenced(self, objects):
        if not self._cm.has_reference(objects):
            return True

    def _not_payload(self, objects):
        if not self._cm.has_payload(objects):
            return True

    def _is_xform(self, objects):
        if self._cm.prim_is_type(objects, UsdGeom.Xform):
            return True

    def _not_pending(self, objects):
        return not self._pending_task

    def _not_payload_or_reference(self, objects):
        if not self._cm.has_payload_or_reference(objects):
            return True

    # Actions
    def _shrink_wrap(self, objects: dict):
        # do something
        shrink_wrap(objects)

    def _register_menu(self):
        """Called when extension is loaded"""
        # Add context menu to omni.kit.widget.stage
        if omni.kit.context_menu:
            self._cm = omni.kit.context_menu.get_instance()

        if self._cm:
            sub_menu = [
                {
                    "name": "Convex Wrap",
                    "glyph": "menu_insert_sublayer.svg",
                    "enabled_fn": [self._is_xform],
                    "onclick_fn": self._shrink_wrap,
                }
            ]
            menu = {
                "name":
                    {
                        'Wrap Tool': [sub_menu]
                    },
                "glyph": "menu_insert_sublayer.svg",
                "appear_after": "Save Selected",
            }
            self._menu = omni.kit.context_menu.add_menu(menu, "MENU", "omni.kit.widget.stage")

    def _notify(self, message, type: str = "warn", silent: bool = False):
        if self._notification:
            self._notification.dismiss()
        if type in ["info"]:
            if not silent:
                self._notification = post_notification(text=message, duration=6, status=NotificationStatus.INFO)
            carb.log_info(message)
        elif type in ["warn"]:
            if not silent:
                self._notification = post_notification(text=message, duration=6, status=NotificationStatus.WARNING)
            carb.log_warn(message)
        elif type in ["error"]:
            carb.log_error(message)

    def _unregister_menu(self):
        if self._menu:
            self._menu.release()
        self._menu = None
        self._cm = None

    def on_shutdown(self):
        self._extension_toggle_sub = None
        self._prims = None
        if self._notification:
            self._notification.dismiss()
        self._notification = None
        if self._pending_task:
            self._pending_task.cancel()
        self._pending_task = None
        self._unregister_menu()
