"""On-object preview of Orient Origin: the axes now, the axes after, and the box they give.

Drawn in the 3D View while the operator waits for the user: faint thin lines for the
current axes, bold arrows with X / Y / Z tags for the new ones, the bounding box the
object would get on the new axes, and a strip with the keys at the bottom.
"""

import math

import bpy
import numpy as np
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

from . import draw_kit as dk

AXIS_COLORS = (dk.rgb("#F0485A"), dk.rgb("#7CC23A"), dk.rgb("#3D8BF2"))  # as Blender's gizmo
BOX_COLOR = (1.0, 1.0, 1.0, 0.38)
MAX_POINTS = 4000


def sample_points(points):
    """At most MAX_POINTS evenly spread points (enough for a bounding box preview)."""
    if len(points) <= MAX_POINTS:
        return points
    return points[:: int(math.ceil(len(points) / MAX_POINTS))]


def _arrow(a, b, width, color, s):
    """Line a -> b in screen space with an open arrow head at b."""
    dk.line(a, b, width, color)
    d = Vector(b) - Vector(a)
    if d.length < 1e-3:
        return
    d.normalize()
    size = 10 * s
    for angle in (math.radians(28), -math.radians(28)):
        ca, sa = math.cos(angle), math.sin(angle)
        back = Vector((-d.x * ca + d.y * sa, -d.x * sa - d.y * ca))
        dk.line(b, (b[0] + back.x * size, b[1] + back.y * size), width, color)


def _tag(p, d, letter, color, s):
    """Round tag with the axis letter just past the arrow tip."""
    r = 8.5 * s
    c = (p[0] + d.x * (r + 5 * s), p[1] + d.y * (r + 5 * s))
    dk.fill(c[0] - r, c[1] - r, 2 * r, 2 * r, r, color, snap=False)
    dk.text(letter, c[0] - r, c[1] - r, 2 * r, 11 * s, dk.WHITE, 'CENTER', 2 * r, face="semibold")


def draw(state):
    """POST_PIXEL handler. state: {"items": [...], "hints": [(keys, label)], "region": pointer}."""
    context = bpy.context
    region, rv3d = context.region, context.region_data
    if region is None or rv3d is None or region.as_pointer() != state.get("region"):
        return
    s = context.preferences.system.ui_scale or 1.0
    try:
        for item in state["items"]:
            _draw_item(region, rv3d, item, s)
        left, bottom, right, _top = dk.overlap_insets(context.area, region)
        dk.hint_bar(state["hints"], left + (region.width - left - right) / 2, bottom + 16 * s, s)
    except (ReferenceError, KeyError):  # an object went away under the preview
        pass


def _draw_item(region, rv3d, item, s):
    origin = Vector(item["origin"])
    rot = np.array(item["new"])
    points = item["points"]

    def screen(p):
        return location_3d_to_region_2d(region, rv3d, Vector(p))

    # The box the object gets on the new axes.
    if len(points):
        local = (points - np.array(origin)) @ rot
        lo, hi = local.min(axis=0), local.max(axis=0)
    else:
        lo = hi = np.zeros(3)
    size = float(max((hi - lo).max(), 1e-3))
    corners = [np.array(origin) + rot @ np.array((x, y, z)) for x in (lo[0], hi[0])
               for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
    projected = [screen(c) for c in corners]
    for i in range(8):
        for bit in (1, 2, 4):
            j = i ^ bit
            if i < j and projected[i] is not None and projected[j] is not None:
                dk.line(projected[i], projected[j], 1.2 * s, BOX_COLOR)

    base = screen(origin)
    if base is None:
        return
    # Current axes: thin and faint, so the change reads at a glance.
    old = np.array(item["old"])
    for k in range(3):
        tip = screen(np.array(origin) + old[:, k] * size * 0.45)
        if tip is not None:
            color = AXIS_COLORS[k]
            dk.line(base, tip, 1.5 * s, (color[0], color[1], color[2], 0.45))
    # New axes: bold arrows reaching just past the box, with a tag.
    for k in range(3):
        reach = max(float(hi[k]), 0.0) + size * 0.18
        reach = max(reach, size * 0.35)
        tip = screen(np.array(origin) + rot[:, k] * reach)
        if tip is None:
            continue
        d = Vector(tip) - Vector(base)
        if d.length < 1e-3:
            continue
        d.normalize()
        _arrow(base, tip, 3 * s, AXIS_COLORS[k], s)
        _tag(tip, d, "XYZ"[k], AXIS_COLORS[k], s)
    dk.fill(base[0] - 4 * s, base[1] - 4 * s, 8 * s, 8 * s, 4 * s, dk.WHITE, snap=False)
