# Blender 4.2+ reads blender_manifest.toml; bl_info is kept for older versions.
bl_info = {
    "name": "Advanced Origin Tools",
    "author": "Moss3D",
    "version": (1, 5, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar (N) > Origin  |  Ctrl Q, Shift Alt Q (pie), Ctrl Shift Q (transform menu)",
    "description": "Set origins to the selection or to any of the 27 bounding box points, "
                   "turn their axes with an on-object preview, and check objects for export",
    "category": "3D View",
}

if "bpy" in locals():
    import importlib
    for _module in (core, orient, export_prep, draw_kit, orient_preview, operators, keymaps,  # noqa: F821
                    origin_card, ui, transform_menu, preferences, translations):  # noqa: F821
        importlib.reload(_module)

import bpy

from . import (core, draw_kit, export_prep, keymaps, operators, orient, orient_preview,  # noqa: F401
               origin_card, preferences, transform_menu, translations, ui)


def register():
    preferences.register()
    for cls in operators.classes:
        bpy.utils.register_class(cls)
    ui.register(preferences.category())
    transform_menu.register()
    origin_card.register()
    keymaps.register()
    translations.register(__package__)


def unregister():
    translations.unregister(__package__)
    keymaps.unregister()
    origin_card.unregister()
    transform_menu.unregister()
    ui.unregister()
    for cls in reversed(operators.classes):
        bpy.utils.unregister_class(cls)
    preferences.unregister()
    draw_kit.unload_fonts()
