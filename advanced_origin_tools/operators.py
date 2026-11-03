import math
import time

import bpy
import numpy as np
from bpy.app.translations import pgettext_iface as iface_
from bpy.app.translations import pgettext_tip as tip_
from bpy.props import BoolProperty, EnumProperty, StringProperty
from mathutils import Matrix

from . import core, export_prep, orient, orient_preview

# The open Orient Origin preview (one at a time) and a request to apply it.
_PREVIEW = {"op": None, "apply": False, "beat": 0.0}

# Events the Orient Origin preview lets through, so the view can be turned while it is open.
_NAVIGATION = {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'TRACKPADPAN', 'TRACKPADZOOM',
               'MOUSEROTATE', 'MOUSESMARTZOOM', 'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}

# --------------------------------------------------------------------------
# Shared enum items (also used by the scene settings in ui.py)
# --------------------------------------------------------------------------

X_ITEMS = [
    ('MIN', "Left", "Negative X side"),
    ('MID', "Center", "Middle of the X range"),
    ('MAX', "Right", "Positive X side"),
]
Y_ITEMS = [
    ('MIN', "Front", "Negative Y side (the side seen from the Front view)"),
    ('MID', "Middle", "Middle of the Y range"),
    ('MAX', "Back", "Positive Y side"),
]
# Blender's own catalogs translate common words differently ("Back" as "go back",
# "Space" as whitespace), so this add-on's interface uses its own context.
I18N_CTX = "AdvancedOriginTools"
Z_ITEMS = [
    ('MIN', "Bottom", "Negative Z side"),
    ('MID', "Center", "Middle of the Z range"),
    ('MAX', "Top", "Positive Z side"),
]
SCOPE_ITEMS = [
    ('EACH', "Each Object", "Every object gets its own origin from its own geometry"),
    ('COMBINED', "Combined", "All objects get the same origin, computed from all of them together"),
]
SPACE_ITEMS = [
    ('LOCAL', "Local", "Use the object's own axes (follows rotation)"),
    ('WORLD', "World", "Use the world axes"),
]
SOURCE_ITEMS = [
    ('EVALUATED', "With Modifiers", "Measure the final shape, including modifiers such as Mirror or Array"),
    ('BASE', "Base Mesh", "Measure the mesh without modifiers"),
]
CENTER_ITEMS = [
    ('MEDIAN', "Median", "Average position of the selected vertices", 'PIVOT_MEDIAN', 0),
    ('BOUNDS', "Bounds", "Center of the box around the selected vertices", 'PIVOT_BOUNDBOX', 1),
    ('ACTIVE', "Active", "The last selected vertex, edge or face", 'PIVOT_ACTIVE', 2),
]
MOVE_ITEMS = [
    ('NONE', "Keep Position", "Only move the origin"),
    ('FLOOR', "Drop to Floor", "Then move the object so its lowest point rests on Z = 0"),
    ('WORLD', "To World Origin", "Then move the object so the new origin sits at the world origin"),
]

ORIENT_ITEMS = [
    ('AUTO', "Auto", "Edit Mode: the selected faces, edges or vertices. Object Mode: the object's own flat faces"),
    ('SHAPE', "Shape", "The object's own flat faces (or the way its shape spreads)"),
    ('SELECTION', "Selection", "The selected faces, edges or vertices (in Object Mode, the stored Edit Mode selection)"),
    ('ACTIVE', "Active", "The axes of the active object (select the others, then the active one last)"),
    ('VIEW', "View", "The current view: X to the right, Y up, Z toward you"),
    ('CURSOR', "3D Cursor", "The rotation of the 3D cursor"),
    ('WORLD', "World", "The world axes: straightens the object's axes"),
]
ORIENT_CARD = ('AUTO', 'ACTIVE', 'WORLD')
AXIS_ITEMS = [
    ('NEAREST', "Nearest", "Lay the axes on the found directions the way closest to the current axes, "
                           "so the rotation values stay small"),
    ('Z', "Z", "The face normal (main direction) becomes the Z axis"),
    ('Y', "Y", "The face normal (main direction) becomes the Y axis"),
    ('X', "X", "The face normal (main direction) becomes the X axis"),
]
LONG_ITEMS = [
    ('ANY', "Any", "No preference: the turn closest to the current axes"),
    ('X', "X", "The longest side lies along X"),
    ('Y', "Y", "The longest side lies along Y"),
    ('Z', "Z", "The longest side lies along Z"),
]
FIX_ITEMS = [
    ('SCALE', "Apply Scale", "Move the scale into the mesh so the scale is 1 (also turns mirrored faces outward)"),
    ('ORIGIN', "Origin to Bottom Center", "Put the origin on the bottom center of the object's own box"),
]

KEEP_MIRROR_DESC = ("Objects with a Mirror modifier keep their origin on the mirror plane, "
                    "so the mirrored result does not change")

_X_NAMES = {'MIN': "Left", 'MID': "Center", 'MAX': "Right"}
_Y_NAMES = {'MIN': "Front", 'MID': "Middle", 'MAX': "Back"}
_Z_NAMES = {'MIN': "Bottom", 'MID': "Center", 'MAX': "Top"}

_SETTINGS_SKIP = {'SKIP_SAVE'}


def _enum(**kwargs):
    return EnumProperty(translation_context=I18N_CTX, **kwargs)


def _keep_mirror_prop():
    return BoolProperty(name="Keep Mirror Plane", description=KEEP_MIRROR_DESC, default=True,
                        options=_SETTINGS_SKIP, translation_context=I18N_CTX)


def _settings(context):
    return getattr(context.scene, "aot_settings", None)


def _names(objects):
    names = [o.name for o in objects[:3]]
    return ", ".join(names) + (" ..." if len(objects) > 3 else "")


def _restore_mode(context, mode):
    """Return to the mode the user started in.

    In the UI this happens on the next event-loop tick, so the operator itself
    finishes in Object Mode and Blender records a full undo step. An Edit Mode undo
    step stores only the mesh: Ctrl+Z would then put the vertices back without
    moving the object, and the geometry would jump.
    """
    if bpy.app.background or context.window is None:
        bpy.ops.object.mode_set(mode=mode)
        return

    # Keep only the window's address: a stored Python reference could point to freed
    # memory if the window were closed (or the file reloaded) before the timer runs.
    window_ptr = context.window.as_pointer()

    def reenter():
        window = next((w for w in bpy.context.window_manager.windows if w.as_pointer() == window_ptr), None)
        if window is None:
            return None
        try:
            with bpy.context.temp_override(window=window):
                active = bpy.context.view_layer.objects.active
                if active is not None and active.mode == 'OBJECT':
                    bpy.ops.object.mode_set(mode=mode)
        except (ReferenceError, RuntimeError, TypeError):
            pass  # object gone or not editable any more
        return None

    bpy.app.timers.register(reenter, first_interval=0.0)


def _fill_unset_from_settings(op, context, names):
    """Shortcut / search calls take their options from the sidebar settings."""
    settings = _settings(context)
    if settings is None:
        return
    for name in names:
        if not op.properties.is_property_set(name):
            setattr(op, name, getattr(settings, name))


class _OriginOperator:
    """Mode handling and reporting shared by both operators."""

    def _run(self, context, compute):
        objects = self.gather(context)
        if not objects:
            self.report({'WARNING'}, tip_("No suitable object to work on"))
            return {'CANCELLED'}

        was_edit = context.mode == 'EDIT_MESH'
        if was_edit:
            bpy.ops.object.mode_set(mode='OBJECT')
        outcome = core.Outcome()
        try:
            result = compute(context, objects, was_edit)
            if result is None:
                return {'CANCELLED'}
            targets, notes = result
            shared = next(iter(targets.values())).copy() if self.scope == 'COMBINED' else None
            if self.keep_mirror:
                core.keep_on_mirror_planes(targets, outcome)
            core.set_origins(context, targets, outcome)
            moved = self.after_origins(context, targets, outcome, shared)
        finally:
            if was_edit:
                _restore_mode(context, 'EDIT')

        self._report_result(targets, outcome, notes, moved)
        return {'FINISHED'}

    def after_origins(self, context, targets, outcome, shared):
        return None

    def _report_result(self, targets, outcome, notes, moved):
        warnings = list(notes)
        if outcome.missed:
            warnings.append(tip_("Origin could not be placed exactly on: %s "
                                 "(shared mesh data, or a 2D curve / text keeps its Z)") % _names(outcome.missed))
        if outcome.mirror_kept:
            warnings.append(tip_("Origin kept on the mirror plane (Mirror modifier): %s")
                            % _names(outcome.mirror_kept))
        if outcome.anim_unshifted:
            warnings.append(tip_("Location is driven by NLA strips or drivers and was not adjusted: %s")
                            % _names(outcome.anim_unshifted))
        if outcome.anim_motion:
            warnings.append(tip_("Rotation or scale is animated, the motion now turns around the new origin: %s")
                            % _names(outcome.anim_motion))
        if outcome.shape_changed:
            parts = [f"{obj.name} ({', '.join(mods)})" for obj, mods in outcome.shape_changed[:3]]
            warnings.append(tip_("Final shape changed, these modifiers depend on the origin: %s. "
                                 "Ctrl+Z undoes it") % "; ".join(parts))
        for text in warnings:
            self.report({'WARNING'}, text)
        if warnings:
            return
        if len(targets) == 1:
            msg = tip_("Origin set")
        else:
            msg = tip_("Origin set on %d objects") % len(targets)
        if moved:
            msg += " · " + (tip_("object moved") if len(moved) == 1
                            else tip_("%d objects moved") % len(moved))
        self.report({'INFO'}, msg)


class OBJECT_OT_aot_origin_to_selection(_OriginOperator, bpy.types.Operator):
    """Move the origin to the selected vertices, edges or faces (works in Object Mode too, using the stored Edit Mode selection)"""
    bl_idname = "object.aot_origin_to_selection"
    bl_label = "Origin to Selection"
    bl_options = {'REGISTER', 'UNDO'}
    bl_translation_context = I18N_CTX

    center: _enum(name="Center", items=CENTER_ITEMS, default='MEDIAN', options=_SETTINGS_SKIP)
    scope: _enum(name="Multiple Objects", items=SCOPE_ITEMS, default='EACH', options=_SETTINGS_SKIP)
    space: _enum(name="Bounds Space", items=SPACE_ITEMS, default='LOCAL', options=_SETTINGS_SKIP,
                 description="Axes used when the center is the bounds of the selection")
    keep_mirror: _keep_mirror_prop()

    @classmethod
    def poll(cls, context):
        if context.mode not in core.SUPPORTED_MODES:
            cls.poll_message_set(tip_("Works in Object Mode and mesh Edit Mode"))
            return False
        if not core.gather_targets(context, mesh_only=True):
            cls.poll_message_set(tip_("Select a mesh object"))
            return False
        return True

    def gather(self, context):
        return core.gather_targets(context, mesh_only=True)

    def invoke(self, context, event):
        _fill_unset_from_settings(self, context, ("center", "scope", "space", "keep_mirror"))
        return self.execute(context)

    def execute(self, context):
        return self._run(context, self._compute)

    def _compute(self, context, objects, was_edit):
        combined = self.scope == 'COMBINED'
        notes = []

        if self.center == 'ACTIVE':
            centers = {}
            for obj in objects:
                local = core.active_element_center(obj)
                if local is not None:
                    centers[obj] = obj.matrix_world @ local
            if not centers:
                self.report({'WARNING'}, tip_("No active element: select a vertex, edge or face last"))
                return None
            if combined:
                ref = core.reference_object(context, list(centers))
                point = centers[ref]
                return {o: point.copy() for o in objects}, notes
            skipped = [o for o in objects if o not in centers]
            if skipped:
                notes.append(tip_("Skipped %d objects without an active element") % len(skipped))
            return centers, notes

        point_sets = {}
        for obj in objects:
            points = core.local_points(obj, None, selected_only=True)
            if len(points):
                point_sets[obj] = points
        if not point_sets:
            self.report({'WARNING'}, tip_("Nothing selected: select vertices, edges or faces in Edit Mode first"))
            return None
        skipped = len(objects) - len(point_sets)
        if skipped and not was_edit:
            notes.append(tip_("Skipped %d objects without a stored selection") % skipped)

        if self.center == 'MEDIAN':
            targets = core.median_targets(point_sets, combined=combined)
        else:
            targets = core.bbox_targets(point_sets, (0.5, 0.5, 0.5), space=self.space, combined=combined,
                                        reference=core.reference_object(context, list(point_sets)))
        if combined:
            # Every object takes the shared point, including the ones without a selection.
            point = next(iter(targets.values()))
            targets = {o: point.copy() for o in objects}
        return targets, notes

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.row().prop(self, "center", expand=True)
        layout.prop(self, "scope")
        sub = layout.column()
        sub.active = self.center == 'BOUNDS'
        sub.prop(self, "space")
        layout.prop(self, "keep_mirror")


class OBJECT_OT_aot_origin_to_bbox(_OriginOperator, bpy.types.Operator):
    """Move the origin to a point of the bounding box"""
    bl_idname = "object.aot_origin_to_bbox"
    bl_label = "Origin to Bounding Box"
    bl_options = {'REGISTER', 'UNDO'}
    bl_translation_context = I18N_CTX

    x: _enum(name="X", items=X_ITEMS, default='MID')
    y: _enum(name="Y", items=Y_ITEMS, default='MID')
    z: _enum(name="Z", items=Z_ITEMS, default='MID')
    scope: _enum(name="Multiple Objects", items=SCOPE_ITEMS, default='EACH', options=_SETTINGS_SKIP)
    space: _enum(name="Space", items=SPACE_ITEMS, default='LOCAL', options=_SETTINGS_SKIP)
    source: _enum(name="Measure", items=SOURCE_ITEMS, default='EVALUATED', options=_SETTINGS_SKIP)
    use_selection: BoolProperty(
        name="Edit Mode Selection", translation_context=I18N_CTX,
        description="In Edit Mode, use only the selected vertices (the whole mesh when nothing is selected)",
        default=True, options=_SETTINGS_SKIP)
    keep_mirror: _keep_mirror_prop()
    move: _enum(name="Then", items=MOVE_ITEMS, default='NONE', options=_SETTINGS_SKIP)

    @classmethod
    def poll(cls, context):
        if context.mode not in core.SUPPORTED_MODES:
            cls.poll_message_set(tip_("Works in Object Mode and mesh Edit Mode"))
            return False
        if not core.gather_targets(context):
            cls.poll_message_set(tip_("Select a mesh, curve, surface, text or metaball object"))
            return False
        return True

    @classmethod
    def description(cls, context, props):
        if props.move == 'FLOOR':
            return tip_("Put the origin on the chosen point and drop the object to the floor (Z = 0)")
        if props.move == 'WORLD':
            return tip_("Put the origin on the chosen point and move the object to the world origin")
        parts = [iface_(_Y_NAMES[props.y], I18N_CTX), iface_(_Z_NAMES[props.z], I18N_CTX),
                 iface_(_X_NAMES[props.x], I18N_CTX)]
        return tip_("Move the origin to this bounding box point: %s") % " / ".join(parts)

    def gather(self, context):
        return core.gather_targets(context)

    def invoke(self, context, event):
        _fill_unset_from_settings(self, context, ("scope", "space", "source", "use_selection", "keep_mirror"))
        return self.execute(context)

    def execute(self, context):
        return self._run(context, self._compute)

    def _compute(self, context, objects, was_edit):
        depsgraph = context.evaluated_depsgraph_get()
        evaluated = self.source == 'EVALUATED'
        notes = []

        point_sets = {}
        if was_edit and self.use_selection:
            for obj in objects:
                points = core.local_points(obj, depsgraph, selected_only=True)
                if len(points):
                    point_sets[obj] = points
        if not point_sets:
            for obj in objects:
                points = core.local_points(obj, depsgraph, evaluated=evaluated)
                if len(points):
                    point_sets[obj] = points
        if not point_sets:
            self.report({'WARNING'}, tip_("The selected objects have no geometry"))
            return None
        empty = len(objects) - len(point_sets)
        if empty and not (was_edit and self.use_selection):
            notes.append(tip_("Skipped %d objects without geometry") % empty)

        factors = (core.AXIS_FACTORS[self.x], core.AXIS_FACTORS[self.y], core.AXIS_FACTORS[self.z])
        combined = self.scope == 'COMBINED'
        targets = core.bbox_targets(point_sets, factors, space=self.space, combined=combined,
                                    reference=core.reference_object(context, list(point_sets)))
        if combined:
            # In Edit Mode, objects without a selection still join the shared origin.
            point = next(iter(targets.values()))
            targets = {o: point.copy() for o in objects}
        return targets, notes

    def after_origins(self, context, targets, outcome, shared):
        if self.move == 'NONE':
            return None
        return core.move_objects(context, list(targets), self.move, outcome,
                                 combined=self.scope == 'COMBINED', shared_point=shared,
                                 evaluated=self.source == 'EVALUATED')

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.row(align=True).prop(self, "x", expand=True)
        col.row(align=True).prop(self, "y", expand=True)
        col.row(align=True).prop(self, "z", expand=True)
        layout.separator()
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(self, "move")
        layout.prop(self, "scope")
        layout.prop(self, "space")
        layout.prop(self, "source")
        if context.mode == 'EDIT_MESH':
            layout.prop(self, "use_selection")
        layout.prop(self, "keep_mirror")


def _mode_ok(cls, context, *, mesh_only):
    if context.mode not in core.SUPPORTED_MODES:
        cls.poll_message_set(tip_("Works in Object Mode and mesh Edit Mode"))
        return False
    if not core.gather_targets(context, mesh_only=mesh_only):
        cls.poll_message_set(tip_("Select a mesh object") if mesh_only
                             else tip_("Select a mesh, curve, surface, text or metaball object"))
        return False
    return True


def _report_warnings(op, outcome, notes):
    warnings = list(notes)
    if outcome.scale_applied:
        warnings.append(tip_("Non-uniform or mirrored scale was moved into the mesh to keep the shape: %s")
                        % _names(outcome.scale_applied))
    if outcome.shared_skipped:
        warnings.append(tip_("Mesh shared with other objects, skipped: %s") % _names(outcome.shared_skipped))
    if outcome.shape_changed:
        parts = [f"{obj.name} ({', '.join(mods)})" for obj, mods in outcome.shape_changed[:3]]
        warnings.append(tip_("Final shape changed, these modifiers depend on the origin: %s. "
                             "Ctrl+Z undoes it") % "; ".join(parts))
    for text in warnings:
        op.report({'WARNING'}, text)
    return bool(warnings)


class OBJECT_OT_aot_orient_origin(bpy.types.Operator):
    """Turn the object's axes (the origin's rotation) to the geometry, another object or the world. The mesh stays where it is"""
    bl_idname = "object.aot_orient_origin"
    bl_label = "Orient Origin"
    bl_options = {'REGISTER', 'UNDO'}
    bl_translation_context = I18N_CTX

    source: _enum(name="Align To", items=ORIENT_ITEMS, default='AUTO', options=_SETTINGS_SKIP)
    axis: _enum(name="Main Axis", items=AXIS_ITEMS, default='NEAREST',
                description="Which object axis follows the face normal (Auto, Shape and Selection)")
    long_axis: _enum(name="Long Side", items=LONG_ITEMS, default='ANY',
                     description="Which axis runs along the object's longest side (with Main Axis on Nearest). "
                                 "Settles it when a box turned past 45 degrees gets two axes swapped")

    @classmethod
    def poll(cls, context):
        return _mode_ok(cls, context, mesh_only=True)

    turns: StringProperty(name="Quarter Turns", options={'HIDDEN'},
                          description="Quarter turns picked in the preview, around the new X, Y or Z axis")

    # -- interactive preview -------------------------------------------------------------

    def invoke(self, context, event):
        running = _PREVIEW.get("op")
        if running is not None and time.monotonic() - _PREVIEW.get("beat", 0.0) < 1.0:
            # Pressed again while the preview is open: apply that one, never open a second.
            _PREVIEW["apply"] = True
            return {'CANCELLED'}
        settings = _settings(context)
        if settings is not None and not self.properties.is_property_set("source"):
            self.source = settings.orient_source
        region = context.region
        if (bpy.app.background or context.area is None or context.area.type != 'VIEW_3D'
                or region is None or region.type != 'WINDOW'):
            return self.execute(context)
        objects = core.gather_targets(context, mesh_only=True)
        if not objects:
            self.report({'WARNING'}, tip_("No suitable object to work on"))
            return {'CANCELLED'}
        if context.mode == 'EDIT_MESH':
            for obj in objects:
                obj.update_from_editmode()  # the preview reads the mesh and its selection
        self._objects = objects
        self._area = context.area
        self._edit = context.mode == 'EDIT_MESH'
        self._saved_turns = {}
        self._base, self._error = self._preview_base(context)
        if self._base is None:
            self.report({'WARNING'}, self._error)
            return {'CANCELLED'}
        self._seen = settings.orient_source if settings is not None else None
        self._points = {o: orient_preview.sample_points(core._transform(core._mesh_coords(o.data), o.matrix_world))
                        for o in objects}
        self._state = {"region": region.as_pointer(), "items": [], "hints": []}
        self._refresh()
        self._handle = bpy.types.SpaceView3D.draw_handler_add(orient_preview.draw, (self._state,),
                                                              'WINDOW', 'POST_PIXEL')
        # A slow tick so a request from the card (apply, other mode) is seen without waiting for input.
        self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
        _PREVIEW.update(op=self, apply=False, beat=time.monotonic())
        context.window_manager.modal_handler_add(self)
        self._area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _preview_base(self, context):
        """(rotations, None) for the current source, or (None, reason)."""
        self._resolved = self._resolve(self._objects, self._edit)
        rotations, _notes, error = self._compute(context, self._objects, self._resolved)
        return (None, error) if error else (rotations, None)

    def _refresh(self):
        items = []
        for obj, rot in (self._base or {}).items():
            items.append({"origin": obj.matrix_world.translation.copy(), "old": orient.current_rotation(obj),
                          "new": np.array(self._turned(rot)), "points": self._points[obj]})
        name = iface_(dict((k, n) for k, n, _d in ORIENT_ITEMS)[self.source], I18N_CTX)
        if self.source == 'AUTO':
            # Say what Auto read: a leftover Edit Mode selection otherwise turns it silently.
            used = "from the selection" if self._resolved == 'SELECTION' else "from the shape"
            name += " (" + iface_(used, I18N_CTX) + ")"
        mode = iface_("Mode: %s", I18N_CTX) % name
        if self._error:  # this mode cannot work here (Active with one object): say why
            mode += " · " + self._error
        self._state["items"] = items
        self._state["hints"] = [(["X", "Y", "Z"], iface_("Turn 90°", I18N_CTX)), (["Tab"], mode),
                                (["Enter"], iface_("Apply", I18N_CTX)), (["Esc"], iface_("Cancel", I18N_CTX))]

    def _end_preview(self, context):
        if getattr(self, "_handle", None) is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
            self._handle = None
        if getattr(self, "_timer", None) is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        if _PREVIEW.get("op") is self:
            _PREVIEW.update(op=None, apply=False)
        try:
            self._area.tag_redraw()
        except (ReferenceError, AttributeError):
            pass

    def _finish(self, context):
        self._end_preview(context)
        if self._base is None:
            self.report({'WARNING'}, self._error)
            return {'CANCELLED'}
        return self.execute(context)

    def modal(self, context, event):
        try:
            return self._modal(context, event)
        except Exception:
            self._end_preview(context)  # never leave the preview drawn over the view
            raise

    def _over_view(self, event):
        """Is the pointer over the 3D View itself (not its sidebar, toolbar or header)?"""
        area = self._area
        mx, my = event.mouse_x, event.mouse_y
        if not (area.x <= mx < area.x + area.width and area.y <= my < area.y + area.height):
            return False
        for r in area.regions:
            if r.type != 'WINDOW' and r.width > 1 and r.x <= mx < r.x + r.width and r.y <= my < r.y + r.height:
                return False
        return True

    def _modal(self, context, event):
        _PREVIEW["beat"] = time.monotonic()  # alive: a stale entry (file reloaded) is ignored
        if _PREVIEW.get("apply"):
            return self._finish(context)
        settings = _settings(context)
        if settings is not None and settings.orient_source != self._seen:
            self._seen = settings.orient_source  # picked on the card: show that mode
            self._switch(context, settings.orient_source)
        kind = event.type
        if kind == 'TIMER':
            return {'PASS_THROUGH'}
        if kind in _NAVIGATION or kind.startswith("NDOF") or (kind.startswith("NUMPAD_") and kind != 'NUMPAD_ENTER'):
            return {'PASS_THROUGH'}  # orbit, pan and zoom to look at the preview
        if kind in {'LEFTMOUSE', 'RIGHTMOUSE'} and not self._over_view(event):
            return {'PASS_THROUGH'}  # the card, sidebar or header: let them have the click
        if event.value != 'PRESS':
            return {'RUNNING_MODAL'}
        if kind in {'X', 'Y', 'Z'}:
            self.turns = (self.turns + kind)[-12:]
        elif kind == 'BACK_SPACE':
            self.turns = ""
        elif kind == 'TAB':
            order = list(ORIENT_CARD)
            nxt = order[(order.index(self.source) + 1) % len(order)] if self.source in order else order[0]
            self._switch(context, nxt)
            if settings is not None:
                settings.orient_source = self._seen = nxt
        elif kind in {'RET', 'NUMPAD_ENTER', 'SPACE', 'LEFTMOUSE'}:
            return self._finish(context)
        elif kind in {'ESC', 'RIGHTMOUSE'}:
            self._end_preview(context)
            return {'CANCELLED'}
        else:
            return {'RUNNING_MODAL'}
        self._refresh()
        self._area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _switch(self, context, source):
        """Show another mode; each mode keeps its own quarter turns."""
        if source == self.source:
            return
        self._saved_turns[self.source] = self.turns
        self.source = source
        self.turns = self._saved_turns.get(source, "")
        self._base, self._error = self._preview_base(context)
        self._refresh()
        self._area.tag_redraw()

    # -- applying ------------------------------------------------------------------------

    def _turned(self, rot):
        m = rot.copy()
        for axis in self.turns:
            m = m @ Matrix.Rotation(math.pi / 2, 3, axis)
        return m

    def _resolve(self, objects, edit):
        """Auto: the selection when Edit Mode has part of the mesh selected, else the shape."""
        if self.source != 'AUTO':
            return self.source
        return 'SELECTION' if edit and orient.has_partial_selection(objects) else 'SHAPE'

    def execute(self, context):
        objects = core.gather_targets(context, mesh_only=True)
        if not objects:
            self.report({'WARNING'}, tip_("No suitable object to work on"))
            return {'CANCELLED'}
        was_edit = context.mode == 'EDIT_MESH'
        if was_edit:
            bpy.ops.object.mode_set(mode='OBJECT')
        outcome = core.Outcome()
        try:
            rotations, notes, error = self._compute(context, objects, self._resolve(objects, was_edit))
            if error:
                self.report({'WARNING'}, error)
                return {'CANCELLED'}
            rotations = {o: self._turned(r) for o, r in rotations.items()}
            changed = orient.set_rotations(context, rotations, outcome)
        finally:
            if was_edit:
                _restore_mode(context, 'EDIT')
        if not _report_warnings(self, outcome, notes):
            if not changed:
                self.report({'INFO'}, tip_("The axes already point that way"))
            elif len(changed) == 1:
                self.report({'INFO'}, tip_("Origin axes aligned"))
            else:
                self.report({'INFO'}, tip_("Origin axes aligned on %d objects") % len(changed))
        return {'FINISHED'}

    def _compute(self, context, objects, source):
        """({obj: world rotation}, notes, error): no reports, so the preview can try sources quietly."""
        animated = [o for o in objects if orient.rotation_animated(o)]
        objects = [o for o in objects if o not in animated]
        notes = []
        if animated:
            notes.append(tip_("Rotation is animated, skipped: %s") % _names(animated))

        if source in {'SHAPE', 'SELECTION'}:
            rotations, unclear = {}, []
            for obj in objects:
                frame = orient.selection_frame(obj) if source == 'SELECTION' else orient.shape_frame(obj)
                if frame is None:
                    unclear.append(obj)
                    continue
                points = core._transform(core._mesh_coords(obj.data), obj.matrix_world) \
                    if self.long_axis != 'ANY' else None
                rotations[obj] = orient.frame_rotation(frame[0], frame[1], orient.current_rotation(obj), self.axis,
                                                       self.long_axis, points)
            if unclear:
                notes.append((tip_("Nothing selected on: %s") if source == 'SELECTION'
                              else tip_("No clear direction in the shape of: %s")) % _names(unclear))
            if not rotations:
                return None, notes, notes[-1] if notes else tip_("No suitable object to work on")
            return rotations, notes, None

        copy_hint = tip_("Select the objects to turn, then the one to copy last (active)")
        if source == 'ACTIVE':
            ref = context.active_object
            if ref is None or not ref.select_get():
                return None, notes, copy_hint
            rot = ref.matrix_world.to_quaternion().to_matrix()
            rotations = {o: rot.copy() for o in objects if o is not ref}
            return (rotations, notes, None) if rotations else (None, notes, copy_hint)

        if source == 'VIEW':
            rv3d = context.region_data
            if rv3d is None or not hasattr(rv3d, "view_rotation"):
                return None, notes, tip_("Run it from a 3D View to use the view")
            rot = rv3d.view_rotation.to_matrix()
        elif source == 'CURSOR':
            rot = context.scene.cursor.matrix.to_quaternion().to_matrix()
        else:
            rot = Matrix.Identity(3)
        if not objects:
            return None, notes, notes[-1]
        return {o: rot.copy() for o in objects}, notes, None

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(self, "source")
        found = self.source in {'AUTO', 'SHAPE', 'SELECTION'}
        sub = layout.row()
        sub.active = found
        sub.prop(self, "axis", expand=True)
        sub = layout.row()
        sub.active = found and self.axis == 'NEAREST'
        sub.prop(self, "long_axis", expand=True)


class OBJECT_OT_aot_fix_export(_OriginOperator, bpy.types.Operator):
    """Fix this export problem on the selected objects that have it"""
    bl_idname = "object.aot_fix_export"
    bl_label = "Fix for Export"
    bl_options = {'REGISTER', 'UNDO'}
    bl_translation_context = I18N_CTX

    issue: _enum(name="Fix", items=FIX_ITEMS, default='SCALE')
    keep_mirror: _keep_mirror_prop()
    scope = 'EACH'

    @classmethod
    def poll(cls, context):
        return _mode_ok(cls, context, mesh_only=True)

    @classmethod
    def description(cls, context, props):
        return tip_(dict((k, d) for k, _n, d in FIX_ITEMS)[props.issue])

    def gather(self, context):
        found = export_prep.issues(core.gather_targets(context, mesh_only=True))
        if self.issue == 'SCALE':
            return found['SCALE'] + found['NEGATIVE']
        return found['ORIGIN']

    def execute(self, context):
        if self.issue == 'ORIGIN':
            return self._run(context, self._compute)
        objects = self.gather(context)
        if not objects:
            self.report({'INFO'}, tip_("Nothing to fix"))
            return {'CANCELLED'}
        animated = [o for o in objects if export_prep.scale_animated(o)]
        objects = [o for o in objects if o not in animated]
        notes = [tip_("Scale is animated, skipped: %s") % _names(animated)] if animated else []
        was_edit = context.mode == 'EDIT_MESH'
        if was_edit:
            bpy.ops.object.mode_set(mode='OBJECT')
        outcome = core.Outcome()
        try:
            done = export_prep.apply_scale(context, objects, outcome)
        finally:
            if was_edit:
                _restore_mode(context, 'EDIT')
        if not _report_warnings(self, outcome, notes):
            self.report({'INFO'}, tip_("Scale applied on %d objects") % len(done))
        return {'FINISHED'}

    def _compute(self, context, objects, was_edit):
        depsgraph = context.evaluated_depsgraph_get()
        point_sets = {}
        for obj in objects:
            points = core.local_points(obj, depsgraph)
            if len(points):
                point_sets[obj] = points
        if not point_sets:
            self.report({'INFO'}, tip_("Nothing to fix"))
            return None
        return core.bbox_targets(point_sets, (0.5, 0.5, 0.0), space='LOCAL', combined=False,
                                 reference=None), []


class WM_OT_aot_no_quit(bpy.types.Operator):
    """Ctrl Q is Origin to Selection over the 3D View. Elsewhere it does nothing, so Blender is never closed by accident (quit with File > Quit; this shortcut can be switched off in the add-on preferences)"""
    bl_idname = "wm.aot_no_quit"
    bl_label = "Ctrl Q Does Not Quit"
    bl_options = {'REGISTER'}  # listed in the Info log, so it is clear what the key did
    bl_translation_context = I18N_CTX

    def execute(self, context):
        self.report({'INFO'}, tip_("Ctrl+Q does not quit Blender (Origin Tools). Use File > Quit"))
        return {'FINISHED'}


classes = (
    WM_OT_aot_no_quit,
    OBJECT_OT_aot_origin_to_selection,
    OBJECT_OT_aot_origin_to_bbox,
    OBJECT_OT_aot_orient_origin,
    OBJECT_OT_aot_fix_export,
)
