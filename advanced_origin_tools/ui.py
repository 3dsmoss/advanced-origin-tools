import bpy
from bpy.app.translations import pgettext_iface as iface_
from bpy.props import BoolProperty, EnumProperty, PointerProperty

from . import core, export_prep, keymaps, operators, origin_card

DEFAULT_CATEGORY = origin_card.DEFAULT_TAB

SELECTION_OP = operators.OBJECT_OT_aot_origin_to_selection.bl_idname
BBOX_OP = operators.OBJECT_OT_aot_origin_to_bbox.bl_idname
PIE_MENU = keymaps.PIE_MENU
CTX = operators.I18N_CTX


def _(text):
    return iface_(text, CTX)

# (x, z) -> arrow and long name used by the grid and the pie.
GRID = {
    ('MIN', 'MAX'): ("↖", "Top Left"), ('MID', 'MAX'): ("↑", "Top"), ('MAX', 'MAX'): ("↗", "Top Right"),
    ('MIN', 'MID'): ("←", "Left"), ('MID', 'MID'): ("●", "Center"), ('MAX', 'MID'): ("→", "Right"),
    ('MIN', 'MIN'): ("↙", "Bottom Left"), ('MID', 'MIN'): ("↓", "Bottom"), ('MAX', 'MIN'): ("↘", "Bottom Right"),
}


class AOT_Settings(bpy.types.PropertyGroup):
    """Sidebar choices, passed to the operators by the panel and pie buttons."""
    center: EnumProperty(name="Center", items=operators.CENTER_ITEMS, default='MEDIAN', translation_context=CTX)
    depth: EnumProperty(name="Depth", items=operators.Y_ITEMS, default='MID', translation_context=CTX,
                        description="Which side along Y the grid buttons use")
    scope: EnumProperty(name="Multiple Objects", items=operators.SCOPE_ITEMS, default='EACH',
                        translation_context=CTX)
    space: EnumProperty(name="Space", items=operators.SPACE_ITEMS, default='LOCAL', translation_context=CTX)
    source: EnumProperty(name="Measure", items=operators.SOURCE_ITEMS, default='EVALUATED',
                         translation_context=CTX)
    use_selection: BoolProperty(
        name="Edit Mode Selection", translation_context=CTX,
        description="In Edit Mode, use only the selected vertices (the whole mesh when nothing is selected)",
        default=True)
    keep_mirror: BoolProperty(name="Keep Mirror Plane", description=operators.KEEP_MIRROR_DESC,
                              default=True, translation_context=CTX)
    orient_source: EnumProperty(name="Align To", translation_context=CTX, default='AUTO',
                                items=[i for i in operators.ORIENT_ITEMS if i[0] in operators.ORIENT_CARD])


ORIENT_OP = operators.OBJECT_OT_aot_orient_origin.bl_idname
FIX_OP = operators.OBJECT_OT_aot_fix_export.bl_idname

def _orient_button(layout, settings, *, text, icon='NONE'):
    # Run in the 3D View itself, so the preview opens there (also from the sidebar).
    layout = layout.row(align=True)
    layout.operator_context = 'INVOKE_REGION_WIN'
    op = layout.operator(ORIENT_OP, text=_(text), icon=icon, translate=False)
    op.source = settings.orient_source
    return op


def _bbox_button(layout, settings, x, z, *, y=None, space=None, text=None, icon='NONE', move='NONE'):
    op = layout.operator(BBOX_OP, text=text if text is not None else GRID[(x, z)][0],
                         icon=icon, translate=False)
    op.x = x
    op.y = y or settings.depth
    op.z = z
    op.scope = settings.scope
    op.space = space or settings.space
    op.source = settings.source
    op.use_selection = settings.use_selection
    op.keep_mirror = settings.keep_mirror
    op.move = move
    return op


def _selection_button(layout, settings, *, text, icon='NONE'):
    op = layout.operator(SELECTION_OP, text=_(text), icon=icon, translate=False)
    op.center = settings.center
    op.scope = settings.scope
    op.space = settings.space
    op.keep_mirror = settings.keep_mirror
    return op


def _hint(layout, template, text):
    if text:
        row = layout.row()
        row.alignment = 'RIGHT'
        row.enabled = False
        row.label(text=_(template) % text, translate=False)


class VIEW3D_PT_aot_origin_tab(bpy.types.Panel):
    """Holds the sidebar tab open; the card (origin_card.py) paints this space itself."""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = DEFAULT_CATEGORY
    bl_label = "Origin Tools"
    bl_translation_context = CTX
    bl_options = {'HIDE_HEADER'}

    @classmethod
    def poll(cls, context):
        return origin_card.card_enabled()

    def draw(self, context):
        pass


class VIEW3D_PT_aot_origin(bpy.types.Panel):
    """The classic panel: used when the card is off or the tab is shared."""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = DEFAULT_CATEGORY
    bl_label = "Origin Tools"
    bl_translation_context = CTX

    @classmethod
    def poll(cls, context):
        return not origin_card.card_enabled()

    def draw(self, context):
        settings = context.scene.aot_settings
        layout = self.layout

        col = layout.column(align=True)
        col.label(text=_("Selection Center"), icon='RESTRICT_SELECT_OFF', translate=False)
        col.row(align=True).prop(settings, "center", expand=True)
        row = col.row(align=True)
        row.scale_y = 1.3
        _selection_button(row, settings, text="Origin to Selection")
        _hint(layout, "Shortcut: %s", keymaps.shortcut_text(SELECTION_OP))

        layout.separator()

        col = layout.column(align=True)
        col.label(text=_("Bounding Box"), icon='SHADING_BBOX', translate=False)
        col.row(align=True).prop(settings, "depth", expand=True)
        grid = col.column(align=True)
        grid.scale_y = 1.3
        for z in ('MAX', 'MID', 'MIN'):
            row = grid.row(align=True)
            for x in ('MIN', 'MID', 'MAX'):
                _bbox_button(row, settings, x, z)

        row = layout.row(align=True)
        # The origin goes on the object's own bottom (Space setting); the floor uses the lowest point.
        _bbox_button(row, settings, 'MID', 'MIN', y='MID', text=_("Drop to Floor"),
                     icon='ANCHOR_BOTTOM', move='FLOOR')
        _bbox_button(row, settings, 'MID', 'MIN', y='MID', text=_("To World Origin"),
                     icon='WORLD', move='WORLD')

        layout.separator()
        col = layout.column(align=True)
        col.label(text=_("Orientation"), icon='ORIENTATION_GIMBAL', translate=False)
        col.row(align=True).prop(settings, "orient_source", expand=True)
        row = col.row(align=True)
        row.scale_y = 1.2
        _orient_button(row, settings, text="Orient Origin")

        layout.separator()
        col = layout.column(align=True)
        col.label(text=_("Export"), icon='EXPORT', translate=False)
        objects = core.gather_targets(context, mesh_only=True)
        if objects:
            found = export_prep.issues(objects)
            box = layout.box().column(align=True)
            problems = False
            for issue in export_prep.ISSUES:
                if found[issue]:
                    problems = True
                    row = box.row(align=True)
                    row.label(text=f"{_(export_prep.ISSUE_LABELS[issue])} · {len(found[issue])}", icon='ERROR',
                              translate=False)
                    row.operator(FIX_OP, text=_("Fix"), translate=False).issue = export_prep.ISSUE_FIX[issue]
            if not problems:
                box.label(text=_("Ready for export"), icon='CHECKMARK', translate=False)

        _hint(layout, "Pie menu: %s", keymaps.shortcut_text("wm.call_menu_pie", PIE_MENU))
        _hint(layout, "Transform menus: %s", keymaps.shortcut_text(keymaps.TRANSFORM_MENU_OP))


class VIEW3D_PT_aot_origin_options(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = DEFAULT_CATEGORY
    bl_label = "Options"
    bl_translation_context = CTX
    bl_parent_id = "VIEW3D_PT_aot_origin"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        settings = context.scene.aot_settings
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(settings, "scope")
        layout.prop(settings, "space")
        layout.prop(settings, "source")
        layout.prop(settings, "use_selection")
        layout.prop(settings, "keep_mirror")


class VIEW3D_MT_aot_origin_pie(bpy.types.Menu):
    bl_idname = PIE_MENU
    bl_label = "Origin"
    bl_translation_context = CTX

    def draw(self, context):
        settings = context.scene.aot_settings
        pie = self.layout.menu_pie()

        def grid_item(layout, x, z):
            arrow, name = GRID[(x, z)]
            _bbox_button(layout, settings, x, z, text=f"{arrow}  {_(name)}")

        # Pie order: West, East, South, North, North-West, North-East, South-West, South-East.
        grid_item(pie, 'MIN', 'MID')
        grid_item(pie, 'MAX', 'MID')

        south = pie.column()
        grid_item(south, 'MID', 'MIN')
        box = south.box().column(align=True)
        grid_item(box, 'MID', 'MID')
        _selection_button(box, settings, text="Origin to Selection", icon='RESTRICT_SELECT_OFF')
        _bbox_button(box, settings, 'MID', 'MIN', y='MID', text=_("Drop to Floor"),
                     icon='ANCHOR_BOTTOM', move='FLOOR')
        _orient_button(box, settings, text="Orient Origin", icon='ORIENTATION_GIMBAL')
        depth_name = dict((k, n) for k, n, _d in operators.Y_ITEMS)[settings.depth]
        box.label(text=_("Depth: %s") % _(depth_name), translate=False)

        grid_item(pie, 'MID', 'MAX')
        grid_item(pie, 'MIN', 'MAX')
        grid_item(pie, 'MAX', 'MAX')
        grid_item(pie, 'MIN', 'MIN')
        grid_item(pie, 'MAX', 'MIN')


PANELS = (VIEW3D_PT_aot_origin_tab, VIEW3D_PT_aot_origin, VIEW3D_PT_aot_origin_options)
MENUS = (VIEW3D_MT_aot_origin_pie,)


def set_category(name):
    """Move the panels to another sidebar tab (re-registration is required)."""
    name = (name or "").strip() or DEFAULT_CATEGORY
    for cls in reversed(PANELS):
        if cls.is_registered:
            bpy.utils.unregister_class(cls)
    for cls in PANELS:
        cls.bl_category = name
        bpy.utils.register_class(cls)


def register(category=DEFAULT_CATEGORY):
    bpy.utils.register_class(AOT_Settings)
    bpy.types.Scene.aot_settings = PointerProperty(type=AOT_Settings)
    for cls in MENUS:
        bpy.utils.register_class(cls)
    set_category(category)


def unregister():
    for cls in reversed(PANELS):
        if cls.is_registered:
            bpy.utils.unregister_class(cls)
    for cls in reversed(MENUS):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.aot_settings
    bpy.utils.unregister_class(AOT_Settings)
