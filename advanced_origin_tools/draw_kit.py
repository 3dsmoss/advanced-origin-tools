"""Shared look and drawing helpers for the add-on's own cards (gpu + blf).

Rectangles are given by their bottom-left corner in region pixels, as Blender's
regions are. Sizes passed in are already multiplied by the interface scale.
"""

import math
import os

import blf
import gpu
from gpu_extras.batch import batch_for_shader

# -- colors -----------------------------------------------------------------------
# From the "Origin Tools UI" design (Specs board): values at 1.0 interface scale.


def rgb(hex_color, alpha=1.0):
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0, alpha)


def mix(a, b, t):
    """a blended toward b by t (used instead of transparency, so strokes never double up)."""
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(4))


PANEL = rgb("#1E1E20")
SECTION = rgb("#2A2A2D")
SECTION_LINE = rgb("#37373B")
WELL = rgb("#1D1D1F")
WELL_LINE = rgb("#333337")
BUTTON = rgb("#353539")
BUTTON_HOVER = rgb("#404045")
ACTION = rgb("#343438")
ACTION_LINE = rgb("#3F3F44")
CELL = rgb("#303034")
CELL_LINE = rgb("#3C3C41")
ACCENT = rgb("#3D6FB6")
ACCENT_HOVER = rgb("#4A7CC2")
ACCENT_LINE = (1.0, 1.0, 1.0, 0.18)
FOCUS = rgb("#8FB4EF")
TEXT = rgb("#DCDCE0")
TEXT_ROW = rgb("#D2D2D7")
TEXT_BUTTON = rgb("#D6D6DB")
TEXT_SEG = rgb("#B8B8BE")
TEXT_ICON = rgb("#A9A9B0")
TEXT_TITLE = rgb("#F0F0F3")
TEXT_LABEL = rgb("#9D9DA4")
TEXT_MUTED = rgb("#93939A")
TEXT_HINT = rgb("#8A8A91")
TEXT_FAINT = rgb("#75757C")
TEXT_SOFT = rgb("#C4C4CA")
WHITE = (1.0, 1.0, 1.0, 1.0)
DISABLED = rgb("#2F2F33")
DISABLED_LINE = rgb("#38383C")
DISABLED_TEXT = rgb("#6C6C73")
TRACK_OFF = rgb("#4A4A50")
DIVIDER = rgb("#353539")
FOOT_LINE = rgb("#2E2E32")
KEY = rgb("#2C2C30")
KEY_LINE = rgb("#424248")
KEY_TEXT = rgb("#CFCFD4")
MENU_CARD = rgb("#29292C")
MENU_LINE = rgb("#3E3E43")
MENU_DIVIDER = rgb("#3A3A3F")
CHECK_OFF = rgb("#66666D")
WARN = rgb("#D9A54C")             # export check: problem
WARN_FILL = rgb("#D9A54C", 0.14)
OK = rgb("#6FB58C")               # export check: all good
HINT_BAR = rgb("#1A1A1C", 0.92)
SHADOW = (0.0, 0.0, 0.0, 1.0)

# -- fonts ------------------------------------------------------------------------
# IBM Plex Sans and JetBrains Mono (SIL Open Font License, see fonts/OFL-*.txt).

_FONT_FILES = {
    "regular": "IBMPlexSans-Regular.ttf",
    "medium": "IBMPlexSans-Medium.ttf",
    "semibold": "IBMPlexSans-SemiBold.ttf",
    "mono": "JetBrainsMono-Medium.ttf",
}
_FONTS = {}


def font(name="regular"):
    """blf font id of one of the add-on's fonts (Blender's own font if it cannot load)."""
    if name not in _FONTS:
        path = os.path.join(os.path.dirname(__file__), "fonts", _FONT_FILES.get(name, ""))
        fid = blf.load(path) if os.path.isfile(path) else -1
        _FONTS[name] = fid if fid != -1 else 0
    return _FONTS[name]


def unload_fonts():
    for name in list(_FONTS):
        if _FONTS[name] != 0:
            try:
                blf.unload(os.path.join(os.path.dirname(__file__), "fonts", _FONT_FILES[name]))
            except (RuntimeError, ValueError, KeyError):
                pass
    _FONTS.clear()

# -- primitives -----------------------------------------------------------------------
#
# Shapes are drawn by a small signed-distance shader: every pixel works out how far
# it is from the shape's edge and takes its coverage from that, so rounded corners,
# frames, circles and strokes come out smooth, the way Blender's own widgets do.
# Triangles and plain lines are only the fallback if that shader cannot be built.

_SDF_VERT = """
void main()
{
  p = pos;
  gl_Position = vec4(pos * view.xy + view.zw, 0.0, 1.0);
}
"""

_SDF_FRAG = """
float sd_box(vec2 q, vec2 half_size, float r)
{
  vec2 d = abs(q) - half_size + vec2(r);
  return min(max(d.x, d.y), 0.0) + length(max(d, vec2(0.0))) - r;
}

float sd_segment(vec2 q, vec2 a, vec2 b)
{
  vec2 qa = q - a;
  vec2 ba = b - a;
  float h = clamp(dot(qa, ba) / max(dot(ba, ba), 1e-6), 0.0, 1.0);
  return length(qa - ba * h);
}

vec3 srgb_to_linear(vec3 c)
{
  return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(vec3(0.04045), c));
}

void main()
{
  float radius = params.x;
  float soft = max(params.y, 0.75);
  float border = params.z;
  float d;
  if (params.w < 0.5) {
    d = sd_box(p - (rect.xy + rect.zw * 0.5), rect.zw * 0.5, radius);
  }
  else {
    d = sd_segment(p, rect.xy, rect.zw) - radius;
  }
  float cover = clamp(0.5 - d / soft, 0.0, 1.0);
  float inner = (border > 0.0) ? clamp(0.5 - (d + border) / soft, 0.0, 1.0) : cover;
  float t = (params.w < 0.5) ? clamp((p.y - rect.y) / max(rect.w, 1.0), 0.0, 1.0) : 0.5;
  vec4 fill = mix(colorBottom, colorTop, t);
  float fa = fill.a * inner;
  float ea = edgeColor.a * (cover - inner);
  float a = fa + ea;
  if (a <= 0.0) {
    discard;
  }
  vec3 rgb = (fill.rgb * fa + edgeColor.rgb * ea) / a;
  // The colors are display (sRGB) values. When Blender draws into a linear target that
  // it converts on output, hand it linear values, as its own shaders do.
  if (srgbTarget) {
    rgb = srgb_to_linear(rgb);
  }
  FragColor = vec4(rgb, a);
}
"""

_SHADERS = {}
_SDF = {"shader": None, "tried": False}


def shader(name):
    if name not in _SHADERS:
        _SHADERS[name] = gpu.shader.from_builtin(name)
    return _SHADERS[name]


def _sdf_shader():
    if not _SDF["tried"]:
        _SDF["tried"] = True
        try:
            iface = gpu.types.GPUStageInterfaceInfo("aot_sdf_iface")
            iface.smooth('VEC2', "p")
            info = gpu.types.GPUShaderCreateInfo()
            info.push_constant('VEC4', "view")
            info.push_constant('VEC4', "rect")
            info.push_constant('VEC4', "params")
            info.push_constant('VEC4', "colorTop")
            info.push_constant('VEC4', "colorBottom")
            info.push_constant('VEC4', "edgeColor")
            # Filled in by Blender itself on bind, as for its built-in shaders.
            info.push_constant('BOOL', "srgbTarget")
            info.vertex_in(0, 'VEC2', "pos")
            info.vertex_out(iface)
            info.fragment_out(0, 'VEC4', "FragColor")
            info.vertex_source(_SDF_VERT)
            info.fragment_source(_SDF_FRAG)
            _SDF["shader"] = gpu.shader.create_from_info(info)
            _SDF["iface"] = iface  # keep alive with the shader
        except Exception:  # noqa: BLE001 - fall back to triangles and lines
            _SDF["shader"] = None
    return _SDF["shader"]


_CLEAR = (0.0, 0.0, 0.0, 0.0)


def _sdf(quad, rect, radius, soft, border, mode, top, bottom, edge):
    sh = _sdf_shader()
    # Region pixels to clip space, taken from the matrices Blender set up for this region
    # (the same ones its own shaders use), not from the viewport size.
    mvp = gpu.matrix.get_projection_matrix() @ gpu.matrix.get_model_view_matrix()
    x0, y0, x1, y1 = quad
    verts = [(x0, y0), (x1, y0), (x1, y1), (x0, y0), (x1, y1), (x0, y1)]
    batch = batch_for_shader(sh, 'TRIS', {"pos": verts})
    # Every shape, not once per paint: blf switches blending off after each text it
    # draws. Unblended, the soft edge pixels would overwrite what is below with the edge
    # color at a low alpha, and when Blender lays the sidebar over the viewport those
    # pixels light up as a stray line above each frame and bright specks on its corners.
    gpu.state.blend_set('ALPHA')
    sh.bind()
    sh.uniform_float("view", (mvp[0][0], mvp[1][1], mvp[0][3], mvp[1][3]))
    sh.uniform_float("rect", rect)
    sh.uniform_float("params", (radius, soft, border, mode))
    sh.uniform_float("colorTop", top)
    sh.uniform_float("colorBottom", bottom)
    sh.uniform_float("edgeColor", edge)
    batch.draw(sh)


def round_rect(x, y, w, h, r, steps=None):
    r = max(0.0, min(r, w / 2, h / 2))
    steps = steps or max(4, int(r * 0.8))
    pts = []
    for cx, cy, start in ((x + w - r, y + h - r, 0), (x + r, y + h - r, 90),
                          (x + r, y + r, 180), (x + w - r, y + r, 270)):
        for i in range(steps + 1):
            a = math.radians(start + 90.0 * i / steps)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _tri_fill(x, y, w, h, r, top, bottom):
    pts = round_rect(x, y, w, h, r)
    center = (x + w / 2, y + h / 2)
    tris = []
    for i in range(len(pts)):
        tris += [center, pts[i], pts[(i + 1) % len(pts)]]
    if bottom == top:
        sh = shader('UNIFORM_COLOR')
        batch = batch_for_shader(sh, 'TRIS', {"pos": tris})
        sh.bind()
        sh.uniform_float("color", top)
    else:
        def color(p):
            t = (p[1] - y) / h if h else 0.0
            return tuple(bottom[k] + (top[k] - bottom[k]) * t for k in range(4))
        sh = shader('SMOOTH_COLOR')
        batch = batch_for_shader(sh, 'TRIS', {"pos": tris, "color": [color(p) for p in tris]})
        sh.bind()
    gpu.state.blend_set('ALPHA')  # blf turns it off after each text
    batch.draw(sh)


def _polyline(points, width, color):
    sh = shader('POLYLINE_UNIFORM_COLOR')
    batch = batch_for_shader(sh, 'LINE_STRIP', {"pos": points})
    gpu.state.blend_set('ALPHA')  # blf turns it off after each text
    sh.bind()
    sh.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
    sh.uniform_float("lineWidth", width)
    try:
        sh.uniform_bool("lineSmooth", True)
    except (ValueError, TypeError):
        pass
    sh.uniform_float("color", color)
    batch.draw(sh)


def _snap(x, y, w, h):
    """Put the rectangle's edges on whole pixels, as Blender's own widgets are.

    Layout math gives fractions (a third of a width, a scaled gap); an edge between two
    pixel rows splits a 1 px frame into two faint half lines, which reads as a broken,
    blurry outline, brighter on one side than the other.
    """
    x0, y0 = round(x), round(y)
    return x0, y0, max(1, round(x + w) - x0), max(1, round(y + h) - y0)


def fill(x, y, w, h, r, top, bottom=None, soft=1.0, snap=True):
    """Rounded rectangle, flat or with a vertical gradient. soft > 1 blurs the edge (shadows).

    snap=False keeps sub-pixel placement (small dots inside icons).
    """
    bottom = bottom or top
    if snap:
        x, y, w, h = _snap(x, y, w, h)
    if _sdf_shader() is None:
        _tri_fill(x, y, w, h, r, top, bottom)
        return
    grow = soft + 1.0
    _sdf((x - grow, y - grow, x + w + grow, y + h + grow), (x, y, w, h), min(r, w / 2, h / 2), soft, 0.0,
         0.0, top, bottom, _CLEAR)


def box(x, y, w, h, r, top, bottom=None, edge=None, edge_w=1.0, snap=True):
    """Rounded rectangle with an optional frame of edge_w pixels inside its edge."""
    bottom = bottom or top
    if snap:
        x, y, w, h = _snap(x, y, w, h)
    if _sdf_shader() is None:
        _tri_fill(x, y, w, h, r, top, bottom)
        _polyline(round_rect(x, y, w, h, r) + round_rect(x, y, w, h, r)[:1], edge_w, edge or bottom)
        return
    _sdf((x - 2.0, y - 2.0, x + w + 2.0, y + h + 2.0), (x, y, w, h), min(r, w / 2, h / 2), 1.0,
         edge_w if edge else 0.0, 0.0, top, bottom, edge or _CLEAR)


def line(a, b, width, color):
    """A stroke with round ends."""
    if _sdf_shader() is None:
        _polyline([a, b], width, color)
        return
    half = width / 2
    grow = half + 2.0
    _sdf((min(a[0], b[0]) - grow, min(a[1], b[1]) - grow, max(a[0], b[0]) + grow, max(a[1], b[1]) + grow),
         (a[0], a[1], b[0], b[1]), half, 1.0, 0.0, 1.0, color, color, _CLEAR)


def outline(points, width, color, closed=True):
    """Polyline as round-ended strokes (each segment one stroke)."""
    pts = points + [points[0]] if closed else points
    for a, b in zip(pts, pts[1:]):
        line(a, b, width, color)


def ring(cx, cy, r, width, color, steps=24):
    if _sdf_shader() is None:
        pts = [(cx + r * math.cos(a / steps * math.tau), cy + r * math.sin(a / steps * math.tau))
               for a in range(steps)]
        _polyline(pts + pts[:1], width, color)
        return
    outer = r + width / 2
    box(cx - outer, cy - outer, 2 * outer, 2 * outer, outer, _CLEAR, _CLEAR, color, width, snap=False)


def text_width(s, size, face="regular", spacing=0.0):
    fid = font(face)
    blf.size(fid, size)
    if not spacing:
        return blf.dimensions(fid, s)[0]
    return sum(blf.dimensions(fid, ch)[0] for ch in s) + spacing * max(0, len(s) - 1)


def text(s, x, y, h, size, color, align='LEFT', w=0.0, face="regular", spacing=0.0):
    """Text vertically centered in the band (y, h); centered or right aligned in w if asked.

    spacing: extra pixels between letters (the design's letter-spacing on caps labels)."""
    fid = font(face)
    blf.size(fid, size)
    blf.color(fid, *color)
    cap = blf.dimensions(fid, "X")[1]
    if align != 'LEFT':
        tw = text_width(s, size, face, spacing)
        x = x + (w - tw) / 2 if align == 'CENTER' else x + w - tw
    ty = round(y + (h - cap) / 2)
    if not spacing:
        blf.position(fid, round(x), ty, 0)
        blf.draw(fid, s)
        return
    for ch in s:
        blf.position(fid, round(x), ty, 0)
        blf.draw(fid, ch)
        x += blf.dimensions(fid, ch)[0] + spacing


def fit(s, room, size, face="regular"):
    fid = font(face)
    blf.size(fid, size)
    if blf.dimensions(fid, s)[0] <= room:
        return s
    while s and blf.dimensions(fid, s + "…")[0] > room:
        s = s[:-1]
    return s + "…"


def shadow(x, y, w, h, r, scale):
    """The design's card shadow: 0 12px 32px rgba(0,0,0,.45) and 0 2px 6px rgba(0,0,0,.3)."""
    # Shrunk by half the blur so the soft edge ends near the card instead of a hard band below it.
    blur = 30 * scale
    fill(x + blur / 2, y - 10 * scale + blur / 2, w - blur, h - blur, r, (0.0, 0.0, 0.0, 0.32), soft=blur)
    fill(x + 1 * scale, y - 2 * scale + 1 * scale, w - 2 * scale, h - 2 * scale, r, (0.0, 0.0, 0.0, 0.22), soft=4 * scale)

def switch(x, y, w, h, on, scale, hover=False):
    """Design switch: 30x18 track (accent when on), 14 px white knob."""
    track = (ACCENT_HOVER if hover else ACCENT) if on else (mix(TRACK_OFF, WHITE, 0.08) if hover else TRACK_OFF)
    box(x, y, w, h, h / 2, track)
    knob = h - 4 * scale
    kx = x + w - 2 * scale - knob if on else x + 2 * scale
    fill(kx, y + 2 * scale, knob, knob, knob / 2, WHITE)

def arrow(cx, cy, dx, dy, size, width, color):
    """A small arrow pointing along (dx, dy); (0, 0) draws a dot."""
    if dx == 0 and dy == 0:
        r = size * 0.32
        fill(cx - r, cy - r, 2 * r, 2 * r, r, color)
        return
    n = math.hypot(dx, dy)
    ux, uy = dx / n, dy / n
    tip = (cx + ux * size * 0.5, cy + uy * size * 0.5)
    tail = (cx - ux * size * 0.5, cy - uy * size * 0.5)
    line(tail, tip, width, color)
    head = size * 0.34
    for side in (1, -1):
        hx = tip[0] - ux * head + side * -uy * head * 0.8
        hy = tip[1] - uy * head + side * ux * head * 0.8
        line((hx, hy), tip, width, color)


def key_cap(key, x, y, s):
    """One keyboard chip (mono 10 px), bottom-left at (x, y). Returns its width."""
    size = 10 * s
    w = text_width(key, size, "mono") + 12 * s
    h = 17 * s
    box(x, y - 1 * s, w, h + 1 * s, 4 * s, KEY_LINE)
    box(x, y + 1 * s, w, h - 1 * s, 4 * s, KEY, None, KEY_LINE, 1.0 * s)
    text(key, x, y + 1 * s, h - 1 * s, size, KEY_TEXT, 'CENTER', w, face="mono")
    return w


def hint_bar(groups, center_x, y, s):
    """Key chips with labels on a dark strip, centered on center_x: [(keys, label), ...]."""
    size = 11 * s
    label_color = rgb("#A3A3AA")

    def group_width(keys, label):
        w = 0.0
        for key in keys:
            w += (text_width(key, size) if key == "+" else text_width(key, 10 * s, "mono") + 12 * s) + 6 * s
        return w + text_width(label, size)

    inner = sum(group_width(k, lab) for k, lab in groups) + 14 * s * (len(groups) - 1)
    w, h = inner + 28 * s, 32 * s
    x = center_x - w / 2
    box(x, y, w, h, 8 * s, HINT_BAR, None, MENU_DIVIDER, 1.0 * s)
    cx = x + 14 * s
    for keys, label in groups:
        for key in keys:
            if key == "+":
                text("+", cx, y, h, size, label_color)
                cx += text_width("+", size) + 6 * s
            else:
                cx += key_cap(key, cx, y + (h - 17 * s) / 2, s) + 6 * s
        text(label, cx, y, h, size, label_color)
        cx += text_width(label, size) + 14 * s


def overlap_insets(area, region):
    """Space taken by the regions drawn on top of the 3D View (toolbar, sidebar, header)."""
    left = bottom = right = top = 0.0
    for r in area.regions:
        if r.type == 'WINDOW' or r.width <= 1 or r.height <= 1:
            continue
        if (r.x + r.width <= region.x or r.x >= region.x + region.width
                or r.y + r.height <= region.y or r.y >= region.y + region.height):
            continue  # beside the 3D View, not over it
        if r.type == 'TOOLS':
            left = max(left, r.x + r.width - region.x)
        elif r.type == 'UI':
            right = max(right, region.x + region.width - r.x)
        elif r.type in {'HEADER', 'TOOL_HEADER'}:
            if r.y > region.y + region.height / 2:
                top = max(top, region.y + region.height - r.y)
            else:
                bottom = max(bottom, r.y + r.height - region.y)
    return left, bottom, right, top


def chevron(cx, cy, size, open_, width, color):
    if open_:
        pts = [(cx - size, cy + size * 0.5), (cx, cy - size * 0.5), (cx + size, cy + size * 0.5)]
    else:
        pts = [(cx - size * 0.5, cy + size), (cx + size * 0.5, cy), (cx - size * 0.5, cy - size)]
    outline(pts, width, color, closed=False)