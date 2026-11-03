import bpy
import rna_keymap_ui
from bpy.props import BoolProperty, StringProperty

from . import keymaps, operators, ui


def _update_category(self, context):
    ui.set_category(self.category)


def _redraw_all(self, context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


class AOT_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    category: StringProperty(
        name="Sidebar Tab",
        translation_context=operators.I18N_CTX,
        description="Name of the sidebar (N panel) tab that shows the tools",
        default=ui.DEFAULT_CATEGORY,
        update=_update_category,
    )
    card_style: BoolProperty(
        name="Card Style Sidebar",
        translation_context=operators.I18N_CTX,
        description=("Draw Origin Tools as a card in its own sidebar tab. Off, or when the tab is shared "
                     "with other tools (Tool, Item, View), the classic panel is used"),
        default=True,
        update=_redraw_all,
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "category")
        row = layout.row()
        row.prop(self, "card_style")
        if self.card_style and self.category.strip() in {"Tool", "Item", "View"}:
            row.label(text="Shared tab: classic panel", text_ctxt=operators.I18N_CTX, icon='INFO')

        box = layout.box()
        box.label(text="Shortcuts", text_ctxt=operators.I18N_CTX, icon='KEYINGSET')
        kc = context.window_manager.keyconfigs.user
        for km, kmi in keymaps.user_items():
            col = box.column()
            col.context_pointer_set("keymap", km)
            rna_keymap_ui.draw_kmi([], kc, km, kmi, col, 0)


def category():
    addon = bpy.context.preferences.addons.get(__package__)
    if addon is not None and addon.preferences is not None:
        return addon.preferences.category
    return ui.DEFAULT_CATEGORY


def register():
    bpy.utils.register_class(AOT_Preferences)


def unregister():
    bpy.utils.unregister_class(AOT_Preferences)
