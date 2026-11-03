"""Turning an object's axes (the origin's rotation) while its mesh stays where it is.

An object whose rotation was applied keeps its tilted mesh but gets world-aligned
axes. This module finds the directions the mesh really has (from its flat faces,
the Edit Mode selection, ...) and turns the object's axes back onto them: the
object gets the rotation, the mesh the inverse turn, and nothing moves on screen.
"""

import itertools
import math
from collections import defaultdict

import bmesh
import bpy
import numpy as np
from mathutils import Matrix

from . import core

_SAME_DIR = math.cos(math.radians(4.0))     # normals this close count as one direction
_RIGHT_ANGLE = math.sin(math.radians(4.0))  # ... and this close to 90 degrees as perpendicular
_FLAT_SHARE = 0.08    # the main face direction must hold this much of the face area
_SPREAD_SHARE = 0.2   # a side direction holding less than this is only a curved surface
_CLEAR_SPREAD = 0.05  # relative difference of point spreads needed to call a direction clear


def _unit(v):
    if v is None:
        return None
    v = np.asarray(v, dtype=np.float64)
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-9 else None


def _in_plane(direction, normal):
    """``direction`` made exactly perpendicular to ``normal`` (None if it was parallel)."""
    if direction is None:
        return None
    return _unit(direction - normal * float(direction @ normal))


def _canonical(normals):
    """Flip each normal so its largest component is positive (n and -n then share a bin)."""
    idx = np.abs(normals).argmax(axis=1)
    sign = np.sign(normals[np.arange(len(normals)), idx])
    sign[sign == 0] = 1.0
    return normals * sign[:, None]


def _dominant_direction(normals, areas):
    """Area-weighted main direction of a set of normals (sign ignored) and its share of the area."""
    total = float(areas.sum()) if len(areas) else 0.0
    if total <= 0.0:
        return None, 0.0
    canon = _canonical(normals)
    keys = np.round(canon / 0.05).astype(np.int64)
    _unique, inverse = np.unique(keys, axis=0, return_inverse=True)
    inverse = np.asarray(inverse).reshape(-1)
    best = int(np.bincount(inverse, weights=areas).argmax())
    pick = inverse == best
    seed = _unit((canon[pick] * areas[pick, None]).sum(axis=0))
    if seed is None:
        return None, 0.0
    dots = normals @ seed
    near = np.abs(dots) > _SAME_DIR
    d = _unit((normals[near] * np.sign(dots[near])[:, None] * areas[near, None]).sum(axis=0))
    return d, float(areas[near].sum()) / total


def _principal_axes(points):
    """Directions of the point spread, widest first, with their variances."""
    c = points - points.mean(axis=0)
    var, vec = np.linalg.eigh(c.T @ c / max(len(points), 1))
    order = var.argsort()[::-1]
    return vec[:, order], var[order]


def _clear(var, i):
    """Is spread direction ``i`` clearly wider than the next one?"""
    return var[0] > 1e-12 and (var[i] - var[i + 1]) / var[0] >= _CLEAR_SPREAD


def _perpendicular_from(current, d):
    """The current axis most at right angles to ``d``, made exactly perpendicular."""
    best = None
    for k in range(3):
        axis = current[:, k]
        p = axis - d * float(axis @ d)
        if best is None or np.linalg.norm(p) > np.linalg.norm(best):
            best = p
    return _unit(best)


def current_rotation(obj):
    """The object's world rotation (scale, also a mirroring one, left out) as a 3x3 array."""
    return np.array(obj.matrix_world.to_quaternion().to_matrix())


def _edge_direction(mesh, points, normal):
    """Main direction of the edges lying across ``normal`` (length-weighted, modulo 90 degrees).

    A square plate has no side faces and spreads the same way in every direction,
    but its edges still say where its sides run. Directions are folded four times
    around the circle so edges at right angles agree; None when no direction stands
    out (a disc).
    """
    count = len(mesh.edges)
    if not count:
        return None
    pairs = np.empty(count * 2, dtype=np.int64)
    mesh.edges.foreach_get("vertices", pairs)
    pairs = pairs.reshape(count, 2)
    vec = points[pairs[:, 1]] - points[pairs[:, 0]]
    length = np.linalg.norm(vec, axis=1)
    keep = length > 1e-9
    vec, length = vec[keep], length[keep]
    across = np.abs((vec / length[:, None]) @ normal) < _RIGHT_ANGLE
    if not across.any():
        return None
    vec, length = vec[across], length[across]
    u = _perpendicular_from(np.eye(3), normal)
    w = np.cross(normal, u)
    angle = np.arctan2(vec @ w, vec @ u)
    c, s = float((length * np.cos(4 * angle)).sum()), float((length * np.sin(4 * angle)).sum())
    if math.hypot(c, s) < 0.3 * float(length.sum()):
        return None
    a = math.atan2(s, c) / 4.0
    return _unit(u * math.cos(a) + w * math.sin(a))


def _world_normals(mesh, matrix_world):
    n = len(mesh.polygons)
    normals = np.empty(n * 3, dtype=np.float64)
    mesh.polygons.foreach_get("normal", normals)
    areas = np.empty(n, dtype=np.float64)
    mesh.polygons.foreach_get("area", areas)
    m3 = np.array(matrix_world.to_3x3())
    # Normals follow the inverse transpose (as row vectors: n @ M^-1).
    normals = normals.reshape(n, 3) @ np.linalg.inv(m3)
    length = np.linalg.norm(normals, axis=1)
    keep = length > 1e-12
    return normals[keep] / length[keep, None], areas[keep]


# -- where the axes should point ---------------------------------------------------------

def shape_frame(obj):
    """Main directions of the object's own mesh in world space: (primary, secondary) or None.

    Hard-surface shapes are read from their flat faces: the direction holding the
    most face area, then the largest one at right angles to it, or, without side
    faces, the way its edges run. A shape without flat faces falls back to the
    directions in which its points spread the most.
    secondary may be None when only one direction is clear (a cylinder's axis).
    """
    mesh = obj.data
    points = core._transform(core._mesh_coords(mesh), obj.matrix_world)
    if len(mesh.polygons):
        normals, areas = _world_normals(mesh, obj.matrix_world)
        d1, share = _dominant_direction(normals, areas)
        if d1 is not None and share >= _FLAT_SHARE:
            d2 = None
            side = np.abs(normals @ d1) < _RIGHT_ANGLE
            if side.any():
                d, share2 = _dominant_direction(normals[side], areas[side])
                if d is not None and share2 >= _SPREAD_SHARE:
                    d2 = _in_plane(d, d1)
            if d2 is None:  # no side faces (a plate): the edges show where the sides run
                d2 = _in_plane(_edge_direction(mesh, points, d1), d1)
            if d2 is None and len(points) >= 3:
                flat = points - np.outer(points @ d1, d1)
                axes, var = _principal_axes(flat)
                if _clear(var, 0):
                    d2 = _in_plane(axes[:, 0], d1)
            return d1, d2
    if len(points) < 3:
        return None
    axes, var = _principal_axes(points)
    if not _clear(var, 0):
        return None
    return axes[:, 0], (axes[:, 1] if _clear(var, 1) else None)


def _vec(v):
    return np.array((v[0], v[1], v[2]), dtype=np.float64)


def selection_frame(obj):
    """Directions given by the (stored) Edit Mode selection, in world space, or None.

    Faces: their normal, and the longest edge of the active (or largest) face.
    Edges: the plane of the active edge and the edge most at right angles to it, or
    the active edge and the faces along it. Vertices: the plane through them, and the
    line from the first to the second one picked.
    """
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bm.transform(obj.matrix_world)
        bm.normal_update()
        active = bm.select_history.active
        faces = [f for f in bm.faces if f.select]
        if faces:
            areas = np.array([f.calc_area() for f in faces])
            normals = np.array([_vec(f.normal) for f in faces])
            mean = (normals * areas[:, None]).sum(axis=0)
            if np.linalg.norm(mean) >= 0.5 * areas.sum():
                normal = _unit(mean)
            else:  # faces facing many ways (a closed part): take their main direction
                normal = _dominant_direction(normals, areas)[0]
            if normal is None:
                return None
            ref = active if isinstance(active, bmesh.types.BMFace) and active.select \
                else faces[int(areas.argmax())]
            edge = max(ref.edges, key=lambda e: e.calc_length())
            return normal, _in_plane(_vec(edge.verts[1].co - edge.verts[0].co), normal)

        edges = [e for e in bm.edges if e.select]
        if edges:
            first = active if isinstance(active, bmesh.types.BMEdge) and active.select \
                else max(edges, key=lambda e: e.calc_length())
            d = _unit(_vec(first.verts[1].co - first.verts[0].co))
            if d is None:
                return None
            best, best_sin = None, 0.0
            for e in edges:
                other = _unit(_vec(e.verts[1].co - e.verts[0].co))
                if e is first or other is None:
                    continue
                sin = float(np.linalg.norm(np.cross(d, other)))
                if sin > best_sin:
                    best, best_sin = other, sin
            if best is not None and best_sin > _RIGHT_ANGLE:
                normal = _unit(np.cross(d, best))
                facing = sum((_vec(f.normal) for f in first.link_faces), np.zeros(3))
                if float(normal @ facing) < 0.0:
                    normal = -normal
                return normal, d
            linked = [_vec(f.normal) for f in first.link_faces]
            normal = _in_plane(_unit(sum(linked, np.zeros(3))) if linked else None, d)
            return (normal, d) if normal is not None else (d, None)

        verts = [v for v in bm.verts if v.select]
        if len(verts) < 2:
            return None
        points = np.array([_vec(v.co) for v in verts])
        history = [v for v in bm.select_history if isinstance(v, bmesh.types.BMVert) and v.select]
        if len(history) >= 2:
            d = _unit(_vec(history[1].co - history[0].co))
        else:
            d = _principal_axes(points)[0][:, 0]
        if len(verts) >= 3:
            axes, var = _principal_axes(points)
            if var[1] > 1e-12 and (var[1] - var[2]) / var[1] >= _CLEAR_SPREAD:
                normal = axes[:, 2]
                facing = sum((_vec(v.normal) for v in verts), np.zeros(3))
                if float(normal @ facing) < 0.0:
                    normal = -normal
                return normal, _in_plane(d, normal)
        return (d, None) if d is not None else None
    finally:
        bm.free()


def _signed_permutations():
    mats = []
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product((1.0, -1.0), repeat=3):
            p = np.zeros((3, 3))
            for col, row in enumerate(perm):
                p[row, col] = signs[col]
            if np.linalg.det(p) > 0:
                mats.append(p)
    return mats


_TURNS = _signed_permutations()  # the 24 ways to lay three axes on three directions


def frame_rotation(primary, secondary, current, axis='NEAREST', long_axis='ANY', points=None):
    """World rotation (3x3 Matrix) built on the found directions.

    'NEAREST' picks, of the 24 ways to lay the object's axes on these directions,
    the one closest to the current axes: an object whose rotation was applied gets
    its old rotation values back instead of a quarter turn. A box looks the same
    from several sides, so past 45 degrees that guess can swap two axes; long_axis
    ('X', 'Y' or 'Z') then settles it by putting that axis along the longest side
    of ``points`` (world space). 'X', 'Y' or 'Z' as ``axis`` instead puts that axis
    on the primary direction (a face normal) exactly as it points.
    """
    a = _unit(primary)
    b = _in_plane(secondary, a)
    if b is None:
        b = _perpendicular_from(current, a)
    if axis == 'NEAREST':
        frame = np.column_stack((a, b, np.cross(a, b)))
        turns = [frame @ p for p in _TURNS]
        if long_axis != 'ANY' and points is not None and len(points):
            spans = [float(np.ptp(points @ frame[:, i])) for i in range(3)]
            longest = frame[:, int(np.argmax(spans))]
            k = "XYZ".index(long_axis)
            turns = [r for r in turns if abs(float(r[:, k] @ longest)) > 0.999]
        rot = max(turns, key=lambda r: float(np.trace(current.T @ r)))
    else:
        k = "XYZ".index(axis)
        if float(b @ current[:, (k + 1) % 3]) < 0.0:
            b = -b
        rot = np.zeros((3, 3))
        rot[:, k] = a
        rot[:, (k + 1) % 3] = b
        rot[:, (k + 2) % 3] = np.cross(a, b)
    return Matrix(rot.tolist())


def rotation_animated(obj):
    paths = {"rotation_euler", "rotation_quaternion", "rotation_axis_angle"}
    if any(fc.data_path in paths for fc in core._action_fcurves(obj)):
        return True
    anim = obj.animation_data
    return anim is not None and any(d.data_path in paths for d in anim.drivers)


def has_partial_selection(objects):
    """True when some object has part (neither all nor none) of its mesh selected."""
    for obj in objects:
        mesh = obj.data
        count = len(mesh.vertices)
        sel = np.empty(count, dtype=bool)
        mesh.vertices.foreach_get("select", sel)
        if 0 < int(sel.sum()) < count:
            return True
    return False


# -- applying ---------------------------------------------------------------------------

def _flip_faces(mesh):
    """Turn the faces outward again after a mirroring transform (Mesh.transform leaves them inside out)."""
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
        bm.to_mesh(mesh)
    finally:
        bm.free()


def transform_data(mesh, matrix):
    mesh.transform(matrix, shape_keys=True)
    if matrix.determinant() < 0.0:
        _flip_faces(mesh)
    mesh.update()


def data_users(objects):
    """{mesh: [every local object using it]} for the meshes of ``objects``."""
    data = {o.data for o in objects}
    users = defaultdict(list)
    for obj in bpy.data.objects:
        if obj.data in data and obj.library is None:
            users[obj.data].append(obj)
    return users


def _is_identity(m):
    return all(abs(m[i][j] - (1.0 if i == j else 0.0)) < 1e-9 for i in range(4) for j in range(4))


def set_rotations(context, rotations, outcome):
    """Turn each object's axes to the world rotation in ``rotations`` ({obj: 3x3}).

    The mesh gets the inverse turn, so nothing moves on screen. A uniform scale is
    kept; a non-uniform (or mirroring) one cannot stay on turned axes without
    shearing the shape, so it goes into the mesh and is reported. Children and other
    objects that share the mesh stay where they are. Returns the objects changed.
    """
    shots = core.snapshot_sensitive_shapes(context, rotations)
    users = data_users(rotations)
    handled, changed = set(), []
    for obj, rot in rotations.items():
        if obj.data in handled:
            continue
        handled.add(obj.data)
        old = obj.matrix_world.copy()
        m3 = old.to_3x3()
        sizes = [c.length for c in m3.col]
        if max(sizes) - min(sizes) <= 1e-6 * max(sizes) and m3.determinant() > 0.0:
            size = sum(sizes) / 3.0
        else:
            size = 1.0
            outcome.scale_applied.append(obj)
        new = Matrix.Translation(old.translation) @ rot.to_4x4() @ Matrix.Scale(size, 4)
        delta = new.inverted_safe() @ old
        if _is_identity(delta):
            continue
        sharing = users[obj.data]
        kids = {c: c.matrix_world.copy() for u in sharing for c in u.children}
        transform_data(obj.data, delta)
        back = delta.inverted_safe()
        for other in sharing:
            other.matrix_world = new if other is obj else other.matrix_world @ back
        context.view_layer.update()
        for child, matrix in kids.items():
            child.matrix_world = matrix
        context.view_layer.update()
        changed.append(obj)
    core.compare_shapes(context, shots, outcome)
    return changed
