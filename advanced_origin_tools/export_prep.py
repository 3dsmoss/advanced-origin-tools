"""Getting objects ready for a game engine: the export check and its fixes."""

import numpy as np
from mathutils import Matrix

from . import core, orient

ISSUES = ('SCALE', 'NEGATIVE', 'ORIGIN')
ISSUE_LABELS = {'SCALE': "Scale not applied", 'NEGATIVE': "Negative scale", 'ORIGIN': "Origin far from the mesh"}
ISSUE_FIX = {'SCALE': 'SCALE', 'NEGATIVE': 'SCALE', 'ORIGIN': 'ORIGIN'}  # issue -> fix_export issue
_ORIGIN_MARGIN = 0.5  # origin further than this (times the object's size) from its box


def issues(objects):
    """{issue: [objects]} for the mesh objects among ``objects``.

    SCALE: scale not applied. NEGATIVE: mirroring scale (faces come out inside out
    in most engines). ORIGIN: the origin is far from the object's own box, so its
    pivot in the engine sits out in empty space.
    """
    found = {key: [] for key in ISSUES}
    for obj in objects:
        if obj.type != 'MESH':
            continue
        if any(c < 0.0 for c in obj.scale):
            found['NEGATIVE'].append(obj)
        elif any(abs(c - 1.0) > 1e-4 for c in obj.scale):
            found['SCALE'].append(obj)
        corners = np.array([tuple(c) for c in obj.bound_box])
        lo, hi = corners.min(axis=0), corners.max(axis=0)
        size = float((hi - lo).max())
        if size > 1e-6:
            margin = _ORIGIN_MARGIN * size
            if (lo - margin > 0.0).any() or (hi + margin < 0.0).any():
                found['ORIGIN'].append(obj)
    return found


def scale_animated(obj):
    paths = {"scale", "delta_scale"}
    if any(fc.data_path in paths for fc in core._action_fcurves(obj)):
        return True
    anim = obj.animation_data
    return anim is not None and any(d.data_path in paths for d in anim.drivers)


def apply_scale(context, objects, outcome):
    """Move each object's scale into its mesh (scale becomes 1); children stay in place.

    Meshes shared with other objects are skipped (the other users would change
    size). A mirroring scale also turns the faces outward again. Returns the
    objects changed.
    """
    users = orient.data_users(objects)
    done = []
    for obj in objects:
        if len(users[obj.data]) > 1:
            outcome.shared_skipped.append(obj)
            continue
        matrix = Matrix.Diagonal(tuple(obj.scale)).to_4x4()
        kids = {c: c.matrix_world.copy() for c in obj.children}
        orient.transform_data(obj.data, matrix)
        obj.scale = (1.0, 1.0, 1.0)
        context.view_layer.update()
        for child, m in kids.items():
            child.matrix_world = m
        context.view_layer.update()
        done.append(obj)
    return done
