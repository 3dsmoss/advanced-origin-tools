"""Geometry helpers: gathering targets, computing origin points and moving origins.

Origins are moved with ``bpy.ops.object.origin_set`` (restricted to the given
objects through ``context.temp_override``). Blender's own operator already keeps
children, shape keys and shared mesh data consistent, so this module only decides
*where* the origin goes.
"""

from collections import defaultdict

import bmesh
import bpy
import numpy as np
from mathutils import Vector

# Object types whose geometry can be measured and whose origin can be moved.
GEOMETRY_TYPES = {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'}

# Sculpt and paint undo steps do not restore object transforms, so Ctrl+Z after an
# origin change there would leave the geometry shifted. Only these modes are safe.
SUPPORTED_MODES = {'OBJECT', 'EDIT_MESH'}

AXIS_FACTORS = {'MIN': 0.0, 'MID': 0.5, 'MAX': 1.0}

# Tolerance used to decide whether an origin ended up where it was asked to go.
_EPSILON = 1e-4


def is_editable(obj):
    return obj.library is None and obj.data is not None and obj.data.library is None


def gather_targets(context, *, mesh_only=False):
    """Objects the tools act on in the current mode."""
    types = {'MESH'} if mesh_only else GEOMETRY_TYPES
    mode = context.mode
    if mode == 'EDIT_MESH':
        objects = context.objects_in_mode or []
    elif mode == 'OBJECT':
        objects = context.selected_editable_objects or []
    else:
        objects = []
    return [o for o in objects if o.type in types and is_editable(o)]


def reference_object(context, objects):
    """Object whose axes are used for combined, local-space bounds."""
    active = context.active_object
    return active if active in objects else objects[0]


# --------------------------------------------------------------------------
# Point gathering (all coordinates are in the object's local space)
# --------------------------------------------------------------------------

def _mesh_coords(mesh, selected_only=False):
    count = len(mesh.vertices)
    co = np.empty(count * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(count, 3).astype(np.float64)
    if selected_only:
        sel = np.empty(count, dtype=bool)
        mesh.vertices.foreach_get("select", sel)
        co = co[sel]
    return co


def local_points(obj, depsgraph, *, evaluated=True, selected_only=False):
    """Vertex positions of ``obj`` in local space as an (N, 3) array.

    Selection only exists on the original mesh, so ``selected_only`` always reads
    the base mesh. Non-mesh objects are always measured after evaluation.
    """
    if obj.type == 'MESH' and (selected_only or not evaluated):
        return _mesh_coords(obj.data, selected_only)

    obj_eval = obj.evaluated_get(depsgraph)
    try:
        mesh = obj_eval.to_mesh()
    except RuntimeError:
        mesh = None
    if mesh is None:
        return np.empty((0, 3))
    try:
        return _mesh_coords(mesh)
    finally:
        obj_eval.to_mesh_clear()


def _element_center(elem):
    if isinstance(elem, bmesh.types.BMVert):
        return elem.co.copy()
    if isinstance(elem, bmesh.types.BMEdge):
        return (elem.verts[0].co + elem.verts[1].co) / 2.0
    if isinstance(elem, bmesh.types.BMFace):
        return elem.calc_center_median()
    return None


def active_element_center(obj):
    """Local center of the last selected vertex/edge/face, or None."""
    mesh = obj.data
    if obj.mode == 'EDIT':
        bm = bmesh.from_edit_mesh(mesh)
        return _element_center(bm.select_history.active)
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        return _element_center(bm.select_history.active)
    finally:
        bm.free()


# --------------------------------------------------------------------------
# Target computation
# --------------------------------------------------------------------------

def _transform(points, matrix):
    m = np.array(matrix, dtype=np.float64)
    return points @ m[:3, :3].T + m[:3, 3]


def _box_point(points, factors):
    lo = points.min(axis=0)
    hi = points.max(axis=0)
    return Vector(lo + (hi - lo) * factors)


def bbox_targets(point_sets, factors, *, space, combined, reference):
    """World-space origin target for every object in ``point_sets``.

    point_sets: {obj: (N, 3) local points}, all non-empty.
    factors: (fx, fy, fz) in 0..1, where 0 is the min side and 1 the max side.
    """
    factors = np.asarray(factors, dtype=np.float64)

    if not combined:
        targets = {}
        for obj, points in point_sets.items():
            mw = obj.matrix_world
            if space == 'LOCAL':
                targets[obj] = mw @ _box_point(points, factors)
            else:
                targets[obj] = _box_point(_transform(points, mw), factors)
        return targets

    if space == 'LOCAL':
        ref_mw = reference.matrix_world
        ref_inv = ref_mw.inverted_safe()
        merged = np.concatenate([_transform(p, ref_inv @ o.matrix_world) for o, p in point_sets.items()])
        point = ref_mw @ _box_point(merged, factors)
    else:
        merged = np.concatenate([_transform(p, o.matrix_world) for o, p in point_sets.items()])
        point = _box_point(merged, factors)
    return {obj: point.copy() for obj in point_sets}


def median_targets(point_sets, *, combined):
    """World-space median of the points of each object (or of all of them)."""
    if not combined:
        return {o: o.matrix_world @ Vector(p.mean(axis=0)) for o, p in point_sets.items()}
    merged = np.concatenate([_transform(p, o.matrix_world) for o, p in point_sets.items()])
    point = Vector(merged.mean(axis=0))
    return {obj: point.copy() for obj in point_sets}


# --------------------------------------------------------------------------
# Applying origins
# --------------------------------------------------------------------------

class Outcome:
    """What happened besides the origins moving, for the operator's report."""

    def __init__(self):
        self.missed = []          # origin not exactly on target (shared data, 2D curve / text Z)
        self.mirror_kept = []     # target pulled back onto a Mirror modifier plane
        self.shape_changed = []   # (object, modifier names): final shape depends on the origin
        self.anim_motion = []     # rotation / scale animated: motion now pivots differently
        self.anim_unshifted = []  # location driven by NLA or drivers: keys could not be shifted
        self.scale_applied = []   # non-uniform or mirroring scale moved into the mesh to keep the shape
        self.shared_skipped = []  # mesh shared with other objects: left alone


# Mirror modifiers without a mirror object reflect around the object's own origin.

def mirror_plane_axes(obj):
    axes = set()
    for mod in obj.modifiers:
        if mod.type == 'MIRROR' and mod.mirror_object is None and mod.show_viewport:
            axes.update(i for i in range(3) if mod.use_axis[i])
    return axes


def keep_on_mirror_planes(targets, outcome):
    """Pull each target back onto its object's mirror planes (local coordinate 0)."""
    for obj, point in targets.items():
        axes = mirror_plane_axes(obj)
        if not axes:
            continue
        local = obj.matrix_world.inverted_safe() @ point
        if all(abs(local[i]) < 1e-9 for i in axes):
            continue
        for i in axes:
            local[i] = 0.0
        targets[obj] = obj.matrix_world @ local
        outcome.mirror_kept.append(obj)


# Modifiers whose result does not depend on where the origin is. Anything else is
# checked after the change by comparing the final shape.
_ORIGIN_SAFE_MODIFIERS = {
    'ARMATURE', 'BEVEL', 'BOOLEAN', 'CORRECTIVE_SMOOTH', 'DATA_TRANSFER', 'DECIMATE', 'EDGE_SPLIT',
    'LAPLACIANSMOOTH', 'LATTICE', 'MASK', 'MULTIRES', 'REMESH', 'SHRINKWRAP', 'SKIN', 'SMOOTH',
    'SOLIDIFY', 'SUBSURF', 'TRIANGULATE', 'VERTEX_WEIGHT_EDIT', 'VERTEX_WEIGHT_MIX',
    'VERTEX_WEIGHT_PROXIMITY', 'WELD', 'WEIGHTED_NORMAL', 'WIREFRAME',
}


def _origin_sensitive_modifiers(obj):
    names = []
    for mod in obj.modifiers:
        if not mod.show_viewport or mod.type in _ORIGIN_SAFE_MODIFIERS:
            continue
        if mod.type == 'MIRROR' and mod.mirror_object is not None:
            continue
        if mod.type == 'ARRAY' and not mod.use_object_offset:
            continue
        names.append(mod.name)
    return names


def _final_shape(obj, depsgraph):
    obj_eval = obj.evaluated_get(depsgraph)
    try:
        mesh = obj_eval.to_mesh()
    except RuntimeError:
        return None
    if mesh is None:
        return None
    try:
        return _transform(_mesh_coords(mesh), obj_eval.matrix_world)
    finally:
        obj_eval.to_mesh_clear()


def snapshot_sensitive_shapes(context, objects):
    """Final world-space shape of every object that has origin-dependent modifiers."""
    depsgraph = context.evaluated_depsgraph_get()
    shots = {}
    for obj in objects:
        names = _origin_sensitive_modifiers(obj)
        if names:
            shape = _final_shape(obj, depsgraph)
            if shape is not None:
                shots[obj] = (names, shape)
    return shots


def compare_shapes(context, shots, outcome):
    depsgraph = context.evaluated_depsgraph_get()
    for obj, (names, before) in shots.items():
        after = _final_shape(obj, depsgraph)
        if after is None:
            continue
        size = float(np.ptp(before, axis=0).max()) if len(before) else 1.0
        if after.shape != before.shape or float(np.abs(after - before).max()) > 1e-5 * max(1.0, size):
            outcome.shape_changed.append((obj, names))


# Location animation: keys are shifted with the origin so the motion stays the same.

_ROT_SCALE_PATHS = {"rotation_euler", "rotation_quaternion", "rotation_axis_angle", "scale",
                    "delta_rotation_euler", "delta_rotation_quaternion", "delta_scale"}


def _action_fcurves(obj):
    anim = obj.animation_data
    if anim is None or anim.action is None:
        return []
    action = anim.action
    slot = getattr(anim, "action_slot", None)
    if slot is not None:  # Blender 4.4+: layered actions
        from bpy_extras import anim_utils
        getter = getattr(anim_utils, "action_get_channelbag_for_slot", None)
        if getter is not None:
            bag = getter(action, slot)
            return list(bag.fcurves) if bag is not None else []
    return list(getattr(action, "fcurves", []))


def _shift_location_keys(obj, delta, outcome):
    anim = obj.animation_data
    if anim is None or delta.length < 1e-12:
        return
    if (any(d.data_path == "location" for d in anim.drivers)
            or any(track.strips for track in anim.nla_tracks)) and obj not in outcome.anim_unshifted:
        outcome.anim_unshifted.append(obj)
    for fc in _action_fcurves(obj):
        if fc.data_path != "location" or abs(delta[fc.array_index]) < 1e-12:
            continue
        d = delta[fc.array_index]
        for key in fc.keyframe_points:
            key.co.y += d
            key.handle_left.y += d
            key.handle_right.y += d
        fc.update()


def _note_rotation_animation(objects, outcome):
    for obj in objects:
        if any(fc.data_path in _ROT_SCALE_PATHS for fc in _action_fcurves(obj)):
            outcome.anim_motion.append(obj)


def _point_key(point):
    return tuple(round(c, 7) for c in point)


def set_origins(context, targets, outcome):
    """Move the origin of each object in ``targets`` ({obj: world point}).

    Other objects that use the same data (linked duplicates) are compensated so
    their geometry stays where it is, and location keyframes move along with the
    location. Problems are collected in ``outcome``.
    """
    target_data = {obj.data for obj in targets}
    users = defaultdict(list)
    for obj in bpy.data.objects:
        if obj.data in target_data and obj.library is None:
            users[obj.data].append(obj)

    # One origin_set call per distinct point; each data block is handled once.
    groups = {}
    handled = set()
    for obj, point in targets.items():
        if obj.data in handled:
            continue
        handled.add(obj.data)
        groups.setdefault(_point_key(point), (point, []))[1].append(obj)

    shots = snapshot_sensitive_shapes(context, targets)
    cursor = context.scene.cursor
    saved_cursor = cursor.location.copy()
    touched = []
    try:
        for point, objects in groups.values():
            scope = list(objects)
            for obj in objects:
                scope.extend(u for u in users[obj.data] if u not in scope)
            before = {o: o.location.copy() for o in scope}
            cursor.location = point
            with context.temp_override(selected_editable_objects=scope,
                                       active_object=objects[0], object=objects[0]):
                bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
            for obj in scope:
                _shift_location_keys(obj, obj.location - before[obj], outcome)
            touched.extend(scope)
    finally:
        cursor.location = saved_cursor

    context.view_layer.update()
    outcome.missed = [obj for obj, point in targets.items()
                      if (obj.matrix_world.translation - point).length > _EPSILON * max(1.0, point.length)]
    compare_shapes(context, shots, outcome)
    _note_rotation_animation(touched, outcome)


def _ancestors(obj):
    parent = obj.parent
    while parent is not None:
        yield parent
        parent = parent.parent


def _translate_world(obj, delta, outcome):
    # Express the world-space offset in the space ``location`` lives in
    # (parent, parent inverse, delta transforms and constraints included).
    parent_space = obj.matrix_world @ obj.matrix_basis.inverted_safe()
    local_delta = parent_space.to_3x3().inverted_safe() @ delta
    obj.location += local_delta
    _shift_location_keys(obj, local_delta, outcome)


def _lowest_z(obj, depsgraph, evaluated):
    points = local_points(obj, depsgraph, evaluated=evaluated)
    if not len(points):
        return obj.matrix_world.translation.z
    return float(_transform(points, obj.matrix_world)[:, 2].min())


def move_objects(context, objects, how, outcome, *, combined=False, shared_point=None, evaluated=True):
    """Drop objects to the floor or move their new origin to the world origin.

    'FLOOR' moves each object so its lowest point rests on Z = 0 (in combined mode
    the whole group moves together). 'WORLD' moves the origin onto the world
    origin. Objects whose parent also moves are skipped: they follow their parent.
    """
    moving = set(objects)
    roots = [o for o in objects if not any(p in moving for p in _ancestors(o))]
    depsgraph = context.evaluated_depsgraph_get()
    if how == 'FLOOR':
        lows = {o: _lowest_z(o, depsgraph, evaluated) for o in objects}
        group_low = min(lows.values())
        deltas = {o: Vector((0.0, 0.0, -(group_low if combined else lows[o]))) for o in roots}
    else:
        deltas = {o: -(shared_point if combined and shared_point is not None
                       else o.matrix_world.translation) for o in roots}
    for obj in roots:
        _translate_world(obj, deltas[obj], outcome)
    context.view_layer.update()
    return roots
