"""The design's icons, drawn with draw_kit's smooth strokes.

Each icon is the design's 16x16 SVG (y pointing down) written out as simple parts:
    ('l', [(x, y), ...])            open polyline
    ('z', [(x, y), ...])            closed polyline
    ('c', cx, cy, r)                circle outline
    ('C', cx, cy, r)                filled circle
    ('d', cx, cy, r, on, off)       dashed circle
    ('e', cx, cy, rx, ry)           ellipse outline
    ('r', x, y, w, h, rx)           rectangle outline
    ('R', x, y, w, h)               filled rectangle
    ('q', x, y, w, h, rx, on, off)  dashed rectangle
    ('p', [(x, y), ...], alpha)     filled polygon (light tint)
"""

import math

import gpu
from gpu_extras.batch import batch_for_shader

from . import draw_kit as dk

_UP = [('l', [(8, 13), (8, 3)]), ('l', [(4.5, 6.5), (8, 3), (11.5, 6.5)])]
_CURSOR = [('d', 8, 8, 4.5, 2.4, 1.6), ('l', [(8, 1), (8, 4)]), ('l', [(8, 12), (8, 15)]),
           ('l', [(1, 8), (4, 8)]), ('l', [(12, 8), (15, 8)])]
_HEX = [(8, 2), (13.5, 5), (13.5, 11), (8, 14), (2.5, 11), (2.5, 5)]
# Orient Origin: two axes and a quarter-turn arrow between them.
_TURN = [(2.5 + 9 * math.cos(math.radians(a)), 13.5 - 9 * math.sin(math.radians(a))) for a in range(16, 75, 6)]

ICONS = {
    # panel
    "badge": [('c', 8, 8, 4.5), ('C', 8, 8, 1.3), ('l', [(8, 1), (8, 3.5)]), ('l', [(8, 12.5), (8, 15)]),
              ('l', [(1, 8), (3.5, 8)]), ('l', [(12.5, 8), (15, 8)])],
    "to_selection": [('c', 8, 8, 2), ('l', [(8, 1.5), (8, 4.5)]), ('l', [(8, 11.5), (8, 14.5)]),
                     ('l', [(1.5, 8), (4.5, 8)]), ('l', [(11.5, 8), (14.5, 8)])],
    "info": [('c', 8, 8, 6.5), ('l', [(8, 7.5), (8, 11.5)]), ('C', 8, 4.85, 0.8)],
    "arrow": _UP,
    "center": [('c', 8, 8, 5), ('C', 8, 8, 1.8)],
    "drop": [('l', [(8, 2), (8, 10)]), ('l', [(5, 7), (8, 10), (11, 7)]), ('l', [(2.5, 13.5), (13.5, 13.5)])],
    "world": [('l', [(3, 13), (13.5, 13)]), ('l', [(3, 13), (3, 2.5)]), ('l', [(3, 13), (9.5, 6.5)]),
              ('C', 3, 13, 1.3)],
    "chevron": [('l', [(6, 3.5), (10.5, 8), (6, 12.5)])],
    "plus": [('l', [(8, 3), (8, 13)]), ('l', [(3, 8), (13, 8)])],
    "check": [('l', [(3.5, 8.5), (6.5, 11.5), (12.5, 4.5)])],
    "orient": [('l', [(2.5, 13.5), (14, 13.5)]), ('l', [(2.5, 13.5), (2.5, 2)]), ('l', _TURN),
               ('l', [(_TURN[-1][0] + 3.0, _TURN[-1][1] - 0.9), _TURN[-1],
                      (_TURN[-1][0] + 1.9, _TURN[-1][1] + 2.5)])],
    "warn": [('z', [(8, 2), (14.5, 13.5), (1.5, 13.5)]), ('l', [(8, 6.5), (8, 9.5)]), ('C', 8, 11.7, 0.8)],
    "ok": [('c', 8, 8, 6.5), ('l', [(5, 8.3), (7.2, 10.5), (11, 5.8)])],
    # pivot point
    "BOUNDING_BOX_CENTER": [('q', 2.5, 2.5, 11, 11, 1, 2.5, 1.8), ('C', 8, 8, 1.4)],
    "CURSOR": _CURSOR,
    "INDIVIDUAL_ORIGINS": [('c', 4, 5, 2), ('c', 12, 5, 2), ('c', 8, 12, 2)],
    "MEDIAN_POINT": [('c', 3.5, 4, 1.3), ('c', 12.5, 4, 1.3), ('c', 8, 13, 1.3), ('C', 8, 7, 1.7)],
    "ACTIVE_ELEMENT": [('c', 8, 8, 5.5), ('C', 8, 8, 2.3)],
    # orientation
    "GLOBAL": [('c', 8, 8, 6), ('e', 8, 8, 2.6, 6), ('l', [(2, 8), (14, 8)])],
    "LOCAL": [('z', _HEX), ('l', [(2.5, 5), (8, 8), (13.5, 5)]), ('l', [(8, 8), (8, 14)])],
    "NORMAL": [('l', [(2, 13), (14, 13)]), ('l', [(8, 13), (8, 3)]), ('l', [(5.5, 5.5), (8, 3), (10.5, 5.5)])],
    "GIMBAL": [('c', 8, 8, 6), ('e', 8, 8, 6, 2.4), ('e', 8, 8, 2.4, 6)],
    "VIEW": [('eye',), ('c', 8, 8, 2)],
    "ORIENT_CURSOR": _CURSOR,
    "PARENT": [('r', 5.5, 1.5, 5, 4, 1), ('l', [(8, 5.5), (8, 8.5)]), ('l', [(4, 11), (4, 8.5), (12, 8.5), (12, 11)]),
               ('c', 4, 12.5, 1.5), ('c', 12, 12.5, 1.5)],
    "CUSTOM": [('c', 8, 8, 5.5), ('l', [(8, 5), (8, 11)]), ('l', [(5, 8), (11, 8)])],
    # snapping
    "INCREMENT": [('l', [(2, 12), (14, 12)]), ('l', [(4, 12), (4, 9)]), ('l', [(8, 12), (8, 6)]),
                  ('l', [(12, 12), (12, 9)])],
    "GRID": [('l', [(2, 5.5), (14, 5.5)]), ('l', [(2, 10.5), (14, 10.5)]), ('l', [(5.5, 2), (5.5, 14)]),
             ('l', [(10.5, 2), (10.5, 14)])],
    "VERTEX": [('l', [(2, 14), (8, 4), (14, 14)]), ('R', 6.5, 2.5, 3, 3)],
    "EDGE": [('l', [(3.5, 12.5), (12.5, 3.5)]), ('c', 2.8, 13.2, 1.3), ('c', 13.2, 2.8, 1.3)],
    "FACE": [('p', [(3, 4), (12, 2.5), (13.5, 11.5), (4.5, 13)], 0.25), ('z', [(3, 4), (12, 2.5), (13.5, 11.5), (4.5, 13)])],
    "VOLUME": [('z', _HEX), ('C', 8, 8.5, 1.5)],
    "EDGE_MIDPOINT": [('l', [(2, 12), (14, 4)]), ('C', 8, 8, 1.9)],
    "EDGE_PERPENDICULAR": [('l', [(2, 11), (14, 3)]), ('l', [(6.5, 8), (9.5, 12.5)])],
    "FACE_MIDPOINT": [('r', 2.5, 2.5, 11, 11, 1.5), ('C', 8, 8, 1.9)],
}
ICONS["FACE_CENTER"] = ICONS["FACE_MIDPOINT"]

# CSS rotate() for the anchor arrows, clockwise in degrees.
ANCHOR_ROTATION = {
    ('MIN', 'MAX'): -45, ('MID', 'MAX'): 0, ('MAX', 'MAX'): 45,
    ('MIN', 'MID'): -90, ('MAX', 'MID'): 90,
    ('MIN', 'MIN'): -135, ('MID', 'MIN'): 180, ('MAX', 'MIN'): 135,
}


def _eye():
    """The design's eye: two arcs from (1.5, 8) to (14.5, 8) through (8, 3.5) and (8, 12.5)."""
    top = [(1.5 + 13 * t / 16, 8 - 4.5 * math.sin(math.pi * t / 16) ** 0.85) for t in range(17)]
    bottom = [(1.5 + 13 * t / 16, 8 + 4.5 * math.sin(math.pi * t / 16) ** 0.85) for t in range(17)]
    return top + bottom[::-1][1:]


def _arc_points(cx, cy, rx, ry, steps=40):
    return [(cx + rx * math.cos(i / steps * math.tau), cy + ry * math.sin(i / steps * math.tau))
            for i in range(steps)]


def _dashes(points, closed, on, off):
    """Split a polyline into dash pieces of length `on`, gaps `off` (16-unit space)."""
    pts = points + points[:1] if closed else points
    pieces, current, drawing, left = [], [pts[0]], True, on
    for a, b in zip(pts, pts[1:]):
        seg = math.dist(a, b)
        pos = 0.0
        while seg - pos > left:
            t = (pos + left) / seg
            p = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            if drawing:
                current.append(p)
                pieces.append(current)
            current = [p]
            pos += left
            drawing = not drawing
            left = on if drawing else off
        left -= seg - pos
        if drawing:
            current.append(b)
        else:
            current = [b]
    if drawing and len(current) > 1:
        pieces.append(current)
    return pieces


def _rect_points(x, y, w, h, r):
    pts = []
    r = min(r, w / 2, h / 2)
    for cx, cy, a0 in ((x + w - r, y + r, -90), (x + w - r, y + h - r, 0), (x + r, y + h - r, 90),
                       (x + r, y + r, 180)):
        for i in range(5):
            a = math.radians(a0 + 90 * i / 4)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def draw(name, x, y, size, color, width=1.4, rotation=0.0):
    """Draw icon `name` with its bottom-left corner at (x, y), `size` pixels square."""
    parts = ICONS.get(name)
    if parts is None:
        return
    k = size / 16.0
    # Whole-pixel corner, plus half a pixel: the design's strokes sit on whole units, so
    # this puts straight strokes on pixel centers (one crisp pixel, not two faint halves).
    x, y = round(x) + 0.5, round(y) + 0.5
    cx, cy = x + size / 2, y + size / 2
    ang = math.radians(rotation)
    ca, sa = math.cos(ang), math.sin(ang)
    # Slightly under the SVG width: a 1 px anti-aliased edge reads heavier than a browser's.
    stroke = width * k * 0.85

    def to_screen(u, v):
        du, dv = u - 8.0, v - 8.0
        ru, rv = du * ca - dv * sa, du * sa + dv * ca   # clockwise on screen, as CSS rotate()
        return cx + ru * k, cy - rv * k

    def poly(points, closed=False):
        dk.outline([to_screen(u, v) for u, v in points], stroke, color, closed=closed)

    for part in parts:
        kind = part[0]
        if kind == 'l':
            poly(part[1])
        elif kind == 'z':
            poly(part[1], closed=True)
        elif kind == 'c':
            px, py = to_screen(part[1], part[2])
            dk.ring(px, py, part[3] * k, stroke, color)
        elif kind == 'C':
            px, py = to_screen(part[1], part[2])
            r = part[3] * k
            dk.fill(px - r, py - r, 2 * r, 2 * r, r, color, snap=False)
        elif kind == 'd':
            for piece in _dashes(_arc_points(part[1], part[2], part[3], part[3], 48), True, part[4], part[5]):
                poly(piece)
        elif kind == 'e':
            poly(_arc_points(part[1], part[2], part[3], part[4]), closed=True)
        elif kind == 'eye':
            poly(_eye(), closed=True)
        elif kind == 'r':
            poly(_rect_points(*part[1:6]), closed=True)
        elif kind == 'q':
            for piece in _dashes(_rect_points(*part[1:6]), True, part[6], part[7]):
                poly(piece)
        elif kind == 'R':
            u, v, w, h = part[1:5]
            x0, y0 = to_screen(u, v + h)
            dk.fill(x0, y0, w * k, h * k, 0.0, color, snap=False)
        elif kind == 'p':
            pts = [to_screen(u, v) for u, v in part[1]]
            tris = []
            for i in range(1, len(pts) - 1):
                tris += [pts[0], pts[i], pts[i + 1]]
            sh = dk.shader('UNIFORM_COLOR')
            batch = batch_for_shader(sh, 'TRIS', {"pos": tris})
            gpu.state.blend_set('ALPHA')
            sh.bind()
            sh.uniform_float("color", (color[0], color[1], color[2], color[3] * part[2]))
            batch.draw(sh)
    gpu.state.blend_set('ALPHA')
