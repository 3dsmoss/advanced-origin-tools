"""The sidebar's Origin Tools as a card, in the add-on's own look.

Blender draws sidebar panels only with its own widgets. To give Origin Tools the
same look as the Shift Mouse 4 cards, the panel registered under the add-on's tab
draws nothing, and this module paints a card over the sidebar while that tab is the
one on top. A modal listener handles clicks on the card while it is on screen;
every other event goes on to Blender untouched.

Living with Blender:
* The listener runs only while a card is visible. Blender postpones autosave while
  any modal operator runs, so every STEP_ASIDE seconds, when the pointer is not on
  the card, the listener leaves and the keep-alive starts it again a moment later.
* One listener per window: a token makes an older copy leave on its next event.
* The card is drawn in the sidebar region itself, so switching tabs or closing the
  sidebar repaints that region and the card simply is not drawn any more.
"""

import sys
import time
import traceback

import bpy
import gpu
from bpy.app.translations import pgettext_iface as iface_

from . import core, draw_kit as dk, export_prep, icons, keymaps, operators

CTX = operators.I18N_CTX
DEFAULT_TAB = "Origin"
SHARED_TABS = {"Tool", "Item", "View"}  # tabs other panels live in: no card there

# -- sizes at 1x (from the design: Origin Tools UI / Specs) ------------------------------

MARGIN = 6            # from the sidebar's edges
TAB_STRIP = 26        # the sidebar's tab column on its right edge
PAD = 12              # panel padding
GAP = 10              # between sections, and between rows in a section
CARD_R = 10
SECTION_PAD = 12
SECTION_R = 10
LABEL_H = 14
WELL_H = 36           # 28 px segments in a 3 px well with a 1 px line
WELL_R = 7
SEG_R = 5
PRIMARY_H = 34
HINT_H = 16
ROW_LABEL_W = 40
CELL_H = 40
CELL_GAP = 4
ANCHOR_PAD = 6
ACTION_H = 32
ACTION_GAP = 6
FOLD_H = 42
OPT_WELL_H = 32
SWITCH_ROW_H = 30
SWITCH_W = 30
SWITCH_H = 18
KEY_ROW_H = 20
CHECK_H = 26          # export check rows
FIX_W = 46            # their Fix button
SCROLL_STEP = 40
STEP_ASIDE = 20.0     # seconds between autosave openings
BEAT_TIMEOUT = 3.0    # a listener silent this long is considered gone
CAPS_SPACING = 0.09   # letter-spacing of the caps labels, in em
# -- module state -----------------------------------------------------------------------

_state = {
    "enabled": False,
    "handle": None,
    "failed": False,
    "options_open": False,
    "last_anchor": None,   # (x, z) of the grid point used last: drawn as active
    "layouts": {},        # sidebar region pointer -> (controls, card rect)
    "scroll": {},         # sidebar region pointer -> scroll offset in pixels
    "hover": (0, None),   # (region pointer, ctl_key of the control under the pointer)
    "listeners": {},      # window pointer -> token
    "beats": {},          # window pointer -> last time its listener heard an event
    "token": 0,
}


def _addon_prefs():
    addon = bpy.context.preferences.addons.get(__package__)
    return addon.preferences if addon is not None else None


def tab_name():
    prefs = _addon_prefs()
    name = (getattr(prefs, "category", "") or "").strip() if prefs is not None else ""
    return name or DEFAULT_TAB


def card_enabled():
    prefs = _addon_prefs()
    style = getattr(prefs, "card_style", True) if prefs is not None else True
    return bool(style) and tab_name() not in SHARED_TABS and not _state["failed"]


def sidebar(area):
    for region in area.regions:
        if region.type == 'UI':
            return region
    return None


def card_visible(area):
    if area is None or area.type != 'VIEW_3D' or not card_enabled():
        return False
    if not getattr(area.spaces.active, "show_region_ui", False):
        return False
    region = sidebar(area)
    # A sidebar dragged shut still says it is shown; its width tells the truth.
    return (region is not None and region.width >= 60
            and getattr(region, "active_panel_category", "") == tab_name())


# -- what the card shows ----------------------------------------------------------------------

def _(text):
    return iface_(text, CTX)


def _items(items):
    return [(key, _(name)) for key, name, *_rest in items]


_ORIENT_HINTS = {
    ('AUTO', True): "Uses the selected faces",
    ('AUTO', False): "Uses the flat faces",
    ('ACTIVE', False): "Copies the active object",
    ('WORLD', False): "Straight to world axes",
}


def _orient_state(context, settings, meshes):
    """(enabled, hint) of the Orient Origin button."""
    source = settings.orient_source
    edit = context.mode == 'EDIT_MESH'
    hint = _(_ORIENT_HINTS.get((source, edit and source == 'AUTO'), ""))
    if source != 'ACTIVE':
        return bool(meshes), hint
    active = context.active_object
    ok = active is not None and active.select_get() and any(o is not active for o in meshes)
    return ok, hint if ok else _("Select the others, then the one to copy")


def card_info(context):
    settings = context.scene.aot_settings
    mode_ok = context.mode in core.SUPPORTED_MODES
    meshes = core.gather_targets(context, mesh_only=True) if mode_ok else []
    sel_ok = bool(meshes)
    bbox_ok = mode_ok and bool(core.gather_targets(context))
    if not mode_ok:
        reason = iface_("Works in Object Mode and mesh Edit Mode")
    elif not sel_ok:
        reason = iface_("Select a mesh object")
    else:
        reason = ""
    orient_ok, orient_hint = _orient_state(context, settings, meshes)
    found = export_prep.issues(meshes) if meshes else {}
    pkg = sys.modules.get(__package__)
    version = ".".join(str(v) for v in getattr(pkg, "bl_info", {}).get("version", ()))
    return {
        "s": settings,
        "sel_ok": sel_ok,
        "bbox_ok": bbox_ok,
        "reason": reason,
        "orient_ok": orient_ok,
        "orient_hint": orient_hint,
        "checked": len(meshes),
        "checks": [(issue, len(found[issue])) for issue in export_prep.ISSUES if found.get(issue)],
        "mode": iface_("Edit Mode") if context.mode == 'EDIT_MESH' else iface_("Object Mode"),
        "keys": [(_("Origin to Selection"), keymaps.shortcut_keys(keymaps.SELECTION_OP)),
                 (_("Pie menu"), keymaps.shortcut_keys(keymaps.PIE_OP, keymaps.PIE_MENU)),
                 (_("Transform menus"), keymaps.shortcut_keys(keymaps.TRANSFORM_MENU_OP))],
        "version": version,
        "last_anchor": _state["last_anchor"],
    }


# -- layout ----------------------------------------------------------------------------------

class Ctl:
    __slots__ = ("kind", "x", "y", "w", "h", "label", "action", "on", "enabled", "glyph", "style")

    def __init__(self, kind, x, y, w, h, label="", action=None, on=False, enabled=True, glyph=None, style=None):
        self.kind, self.label, self.action = kind, label, action
        self.on, self.enabled, self.glyph, self.style = on, enabled, glyph, style
        self.x, self.y, self.w, self.h = x, y, w, h

    def contains(self, mx, my):
        return self.x <= mx <= self.x + self.w and self.y <= my <= self.y + self.h


def build(info, region_w, region_h, scale, points=11.0, scroll=0.0, options_open=False):
    """Controls of the card, top-down, in sidebar-region pixels. Returns (controls, card, content height).

    Laid out like the design's Main board: header, Selection Center, Bounding Box,
    Options (folding), shortcut keys at the bottom. `points` is kept for callers."""
    s = scale
    st = info["s"]
    ctls = []
    x0 = MARGIN * s
    card_w = max(60 * s, region_w - (TAB_STRIP + 2 * MARGIN) * s)
    top = region_h - MARGIN * s + scroll
    ix, iw = x0 + PAD * s, card_w - 2 * PAD * s
    y = top - PAD * s

    def add(kind, x, h, w, **kw):
        nonlocal y
        ctls.append(Ctl(kind, x, y - h * s, w, h * s, **kw))
        return ctls[-1]

    # Header: badge, title, subtitle.
    y -= 6 * s
    add('header', ix + 4 * s, 36, iw - 8 * s, label=_("Origin Tools"),
        style=_("Set origin from selection or bounds"))
    y -= (36 + 8 + GAP) * s

    def section(body):
        nonlocal y
        top_y = y
        box = Ctl('section', ix, 0, iw, 0)
        ctls.append(box)
        y -= SECTION_PAD * s
        body(ix + SECTION_PAD * s, iw - 2 * SECTION_PAD * s)
        y -= SECTION_PAD * s
        box.y, box.h = y, top_y - y
        y -= GAP * s

    def segmented(cx, cw, prop, items, height=WELL_H):
        nonlocal y
        add('well', cx, height, cw)
        n = len(items)
        inner = cw - 8 * s
        w = (inner - 2 * s * (n - 1)) / n
        current = getattr(st, prop)
        sy = y - height * s + 4 * s
        for i, (key, label) in enumerate(items):
            ctls.append(Ctl('seg', cx + 4 * s + i * (w + 2 * s), sy, w, (height - 8) * s, label,
                            action=('set', prop, key), on=(current == key)))
        y -= height * s

    def selection(cx, cw):
        nonlocal y
        add('label', cx, LABEL_H, cw, label=_("Selection Center"), style=info["mode"])
        y -= (LABEL_H + GAP) * s
        segmented(cx, cw, "center", _items(operators.CENTER_ITEMS))
        y -= GAP * s
        add('button', cx, PRIMARY_H, cw, label=_("Origin to Selection"), action=('select',),
            enabled=info["sel_ok"], glyph="to_selection")
        y -= PRIMARY_H * s
        if info["reason"]:
            y -= GAP * s
            add('hint', cx, HINT_H, cw, label=info["reason"])
            y -= HINT_H * s

    def labeled(cx, cw, title, prop, items):
        """A segmented row with its label beside it as in the design; above it when narrow."""
        nonlocal y
        beside = cw - (ROW_LABEL_W + 10) * s >= 150 * s
        lw = (ROW_LABEL_W + 10) * s if beside else 0.0
        if beside:
            add('rowlabel', cx, WELL_H, ROW_LABEL_W * s, label=title)
        else:
            add('rowlabel', cx, LABEL_H, cw, label=title)
            y -= (LABEL_H + 6) * s
        segmented(cx + lw, cw - lw, prop, items)
        return beside, lw

    def bounding_box(cx, cw):
        nonlocal y
        add('label', cx, LABEL_H, cw, label=_("Bounding Box"))
        y -= (LABEL_H + GAP) * s
        beside, lw = labeled(cx, cw, _("Depth"), "depth", _items(operators.Y_ITEMS))
        y -= GAP * s
        well_h = ANCHOR_PAD * 2 + CELL_H * 3 + CELL_GAP * 2 + 2
        if beside:
            ctls.append(Ctl('rowlabel', cx, y - (12 + LABEL_H) * s, ROW_LABEL_W * s, LABEL_H * s, _("Anchor")))
        else:
            add('rowlabel', cx, LABEL_H, cw, label=_("Anchor"))
            y -= (LABEL_H + 6) * s
        add('well', cx + lw, well_h, cw - lw, style='anchor')
        gx = cx + lw + (ANCHOR_PAD + 1) * s
        gw = cw - lw - 2 * (ANCHOR_PAD + 1) * s
        cell_w = (gw - 2 * CELL_GAP * s) / 3
        gy = y - (ANCHOR_PAD + 1) * s
        for z in ('MAX', 'MID', 'MIN'):
            for i, x in enumerate(('MIN', 'MID', 'MAX')):
                ctls.append(Ctl('cell', gx + i * (cell_w + CELL_GAP * s), gy - CELL_H * s, cell_w, CELL_H * s,
                                action=('bbox', x, z, 'NONE'), enabled=info["bbox_ok"], glyph=(x, z),
                                on=(info["last_anchor"] == (x, z))))
            gy -= (CELL_H + CELL_GAP) * s
        y -= well_h * s
        y -= (GAP + 2) * s
        add('divider', cx, 1, cw)
        y -= (1 + 2 + GAP) * s
        half = (cw - ACTION_GAP * s) / 2
        floor_label, world_label = _("Drop to Floor"), _("World Origin")
        # Side by side when both labels fit whole; a narrow sidebar stacks them instead.
        if max(dk.text_width(t, 12 * s) for t in (floor_label, world_label)) <= half - 34 * s:
            ctls.append(Ctl('action', cx, y - ACTION_H * s, half, ACTION_H * s, floor_label,
                            action=('bbox', 'MID', 'MIN', 'FLOOR'), enabled=info["bbox_ok"], glyph="drop"))
            ctls.append(Ctl('action', cx + half + ACTION_GAP * s, y - ACTION_H * s, half, ACTION_H * s,
                            world_label, action=('bbox', 'MID', 'MIN', 'WORLD'), enabled=info["bbox_ok"],
                            glyph="world"))
            y -= ACTION_H * s
        else:
            ctls.append(Ctl('action', cx, y - ACTION_H * s, cw, ACTION_H * s, floor_label,
                            action=('bbox', 'MID', 'MIN', 'FLOOR'), enabled=info["bbox_ok"], glyph="drop"))
            y -= (ACTION_H + ACTION_GAP) * s
            ctls.append(Ctl('action', cx, y - ACTION_H * s, cw, ACTION_H * s, world_label,
                            action=('bbox', 'MID', 'MIN', 'WORLD'), enabled=info["bbox_ok"], glyph="world"))
            y -= ACTION_H * s

    def orientation(cx, cw):
        nonlocal y
        add('label', cx, LABEL_H, cw, label=_("Orientation"))
        y -= (LABEL_H + GAP) * s
        segmented(cx, cw, "orient_source",
                  _items([i for i in operators.ORIENT_ITEMS if i[0] in operators.ORIENT_CARD]))
        y -= GAP * s
        add('action', cx, ACTION_H, cw, label=_("Orient Origin"), action=('orient',),
            enabled=info["orient_ok"], glyph="orient")
        y -= ACTION_H * s
        if info["orient_hint"]:
            y -= GAP * s
            add('hint', cx, HINT_H, cw, label=info["orient_hint"])
            y -= HINT_H * s

    def export(cx, cw):
        nonlocal y
        add('label', cx, LABEL_H, cw, label=_("Export"))
        y -= (LABEL_H + GAP) * s
        if not info["checked"]:
            add('hint', cx, HINT_H, cw, label=_("Select objects to check them for export"))
            y -= HINT_H * s
            return
        if not info["checks"]:
            add('checkok', cx, CHECK_H, cw, label=_("Ready for export"))
            y -= CHECK_H * s
            return
        for i, (issue, count) in enumerate(info["checks"]):
            if i:
                y -= 4 * s
            add('check', cx, CHECK_H, cw - (FIX_W + 8) * s, label=_(export_prep.ISSUE_LABELS[issue]),
                style=count)
            add('fix', cx + cw - FIX_W * s, CHECK_H, FIX_W * s, label=_("Fix"), action=('fix', issue))
            y -= CHECK_H * s

    section(selection)
    section(bounding_box)
    section(orientation)
    section(export)

    # Options: the whole header row folds the section open and shut.
    top_y = y
    box = Ctl('section', ix, 0, iw, 0)
    ctls.append(box)
    add('fold', ix, FOLD_H, iw, label=_("Options"), action=('options',), on=options_open)
    y -= FOLD_H * s
    if options_open:
        cx, cw = ix + SECTION_PAD * s, iw - 2 * SECTION_PAD * s
        for prop, title, items in (("scope", "Multiple Objects", operators.SCOPE_ITEMS),
                                   ("space", "Space", operators.SPACE_ITEMS),
                                   ("source", "Measure", operators.SOURCE_ITEMS)):
            add('optlabel', cx, LABEL_H, cw, label=_(title))
            y -= (LABEL_H + 6) * s
            segmented(cx, cw, prop, _items(items), OPT_WELL_H)
            y -= 8 * s
        for prop, title in (("use_selection", "Edit Mode Selection"), ("keep_mirror", "Keep Mirror Plane")):
            add('switch_row', cx, SWITCH_ROW_H, cw, label=_(title), action=('toggle', prop),
                on=bool(getattr(st, prop)))
            y -= (SWITCH_ROW_H + 4) * s
        y -= 8 * s
    box.y, box.h = y, top_y - y
    y -= GAP * s

    # Shortcut keys.
    add('rule', ix, 1, iw)
    y -= (1 + 10) * s
    for label, keys in info["keys"]:
        if keys:
            add('keys', ix + 4 * s, KEY_ROW_H, iw - 8 * s, label=label, style=keys)
            y -= (KEY_ROW_H + 8) * s
    y -= (PAD - 4) * s

    card = Ctl('card', x0, y, card_w, top - y)
    ctls.insert(0, card)
    return ctls, card, top - y


def ctl_key(c):
    """Identity of a control that survives the rebuild on every redraw."""
    return None if c is None else (c.kind, c.action, c.label)


def hit(ctls, mx, my):
    for c in reversed(ctls):
        if c.action is not None and c.contains(mx, my):
            return c
    return None


def op_call(settings, action):
    """Operator and properties behind a card button (kept apart so it can be tested)."""
    if action[0] == 'select':
        return "aot_origin_to_selection", {
            "center": settings.center, "scope": settings.scope, "space": settings.space,
            "keep_mirror": settings.keep_mirror}
    if action[0] == 'orient':
        return "aot_orient_origin", {"source": settings.orient_source}
    if action[0] == 'fix':
        return "aot_fix_export", {"issue": export_prep.ISSUE_FIX[action[1]], "keep_mirror": settings.keep_mirror}
    _kind, x, z, move = action
    return "aot_origin_to_bbox", {
        "x": x, "y": 'MID' if move != 'NONE' else settings.depth, "z": z, "move": move,
        # The origin goes on the object's own bottom (Space setting); resting on the floor
        # uses the lowest point either way. A world box would put a tilted object's origin
        # out in empty space under it.
        "space": settings.space,
        "scope": settings.scope, "source": settings.source, "use_selection": settings.use_selection,
        "keep_mirror": settings.keep_mirror}


def perform(context, area, ctl):
    settings = context.scene.aot_settings
    action = ctl.action
    if action[0] == 'set':
        setattr(settings, action[1], action[2])
    elif action[0] == 'toggle':
        setattr(settings, action[1], not getattr(settings, action[1]))
    elif action[0] == 'options':
        _state["options_open"] = not _state["options_open"]
    elif action[0] in {'select', 'bbox', 'orient', 'fix'}:
        name, props = op_call(settings, action)
        region = next((r for r in area.regions if r.type == 'WINDOW'), None)
        # Orient Origin opens its preview on the object first; the others act at once.
        how = 'INVOKE_DEFAULT' if action[0] == 'orient' else 'EXEC_DEFAULT'
        with context.temp_override(window=context.window, area=area, region=region):
            getattr(bpy.ops.object, name)(how, True, **props)
        if action[0] == 'bbox' and action[3] == 'NONE':
            _state["last_anchor"] = (action[1], action[2])


# -- painting -----------------------------------------------------------------------------------

def _caps(c, s, color):
    size = 10.5 * s
    dk.text(c.label.upper(), c.x, c.y, c.h, size, color, face="semibold", spacing=CAPS_SPACING * size)


def paint(ctls, scale, points, hover):
    s = scale
    gpu.state.blend_set('ALPHA')
    for c in ctls:
        hot = hover is not None and c.enabled and c.action is not None and ctl_key(c) == hover
        k = c.kind
        if k == 'card':
            dk.shadow(c.x, c.y, c.w, c.h, CARD_R * s, s)
            dk.box(c.x, c.y, c.w, c.h, CARD_R * s, dk.PANEL, None, dk.SECTION_LINE, 1.0 * s)
        elif k == 'header':
            badge = 36 * s
            by = c.y + (c.h - badge) / 2
            dk.box(c.x, by, badge, badge, 9 * s, dk.ACCENT)
            icons.draw("badge", c.x + (badge - 20 * s) / 2, by + (badge - 20 * s) / 2, 20 * s, dk.WHITE)
            tx = c.x + badge + 12 * s
            dk.text(dk.fit(c.label, c.w - badge - 12 * s, 15 * s, "semibold"), tx, c.y + c.h / 2 - 1 * s,
                    c.h / 2, 15 * s, dk.TEXT_TITLE, face="semibold")
            dk.text(dk.fit(c.style, c.w - badge - 12 * s, 11.5 * s), tx, c.y + 2 * s, c.h / 2 - 2 * s, 11.5 * s,
                    dk.TEXT_MUTED)
        elif k == 'section':
            dk.box(c.x, c.y, c.w, c.h, SECTION_R * s, dk.SECTION, None, dk.SECTION_LINE, 1.0 * s)
        elif k == 'label':
            _caps(c, s, dk.TEXT_LABEL)
            if c.style:
                # The mode tag only when it clears the title (a narrow sidebar drops it).
                size = 10.5 * s
                title_w = dk.text_width(c.label.upper(), size, "semibold", CAPS_SPACING * size)
                if title_w + 10 * s + dk.text_width(c.style, size) <= c.w:
                    dk.text(c.style, c.x, c.y, c.h, size, dk.TEXT_FAINT, 'RIGHT', c.w)
        elif k == 'well':
            dk.box(c.x, c.y, c.w, c.h, (8 if c.style == 'anchor' else WELL_R) * s, dk.WELL, None, dk.WELL_LINE,
                   1.0 * s)
        elif k == 'seg':
            if c.on:
                dk.fill(c.x, c.y - 1 * s, c.w, c.h, SEG_R * s, (0.0, 0.0, 0.0, 0.35), soft=2 * s)
                dk.box(c.x, c.y, c.w, c.h, SEG_R * s, dk.ACCENT_HOVER if hot else dk.ACCENT)
            elif hot:
                dk.box(c.x, c.y, c.w, c.h, SEG_R * s, dk.mix(dk.WELL, dk.WHITE, 0.07))
            dk.text(dk.fit(c.label, c.w - 6 * s, 12 * s, "medium"), c.x, c.y, c.h, 12 * s,
                    dk.WHITE if c.on else (dk.TEXT if hot else dk.TEXT_SEG), 'CENTER', c.w, face="medium")
        elif k == 'button':
            if c.enabled:
                dk.box(c.x, c.y, c.w, c.h, 6 * s, dk.ACCENT_HOVER if hot else dk.ACCENT, None, dk.ACCENT, 1.0 * s)
                color = dk.WHITE
            else:
                dk.box(c.x, c.y, c.w, c.h, 6 * s, dk.DISABLED, None, dk.DISABLED_LINE, 1.0 * s)
                color = dk.DISABLED_TEXT
            size = 12.5 * s
            tw = dk.text_width(c.label, size, "medium")
            total = 14 * s + 8 * s + tw
            sx = c.x + (c.w - total) / 2
            icons.draw(c.glyph, sx, c.y + (c.h - 14 * s) / 2, 14 * s, color, 1.5)
            dk.text(c.label, sx + 22 * s, c.y, c.h, size, color, face="medium")
        elif k == 'hint':
            icons.draw("info", c.x, c.y + (c.h - 12 * s) / 2, 12 * s, dk.TEXT_HINT, 1.5)
            dk.text(dk.fit(c.label, c.w - 18 * s, 11 * s), c.x + 18 * s, c.y, c.h, 11 * s, dk.TEXT_HINT)
        elif k == 'rowlabel':
            dk.text(c.label, c.x, c.y, c.h, 11.5 * s, dk.TEXT_MUTED)
        elif k == 'cell':
            if not c.enabled:
                fillc, line, color = dk.DISABLED, dk.DISABLED_LINE, dk.DISABLED_TEXT
            elif c.on:
                fillc, line, color = (dk.ACCENT_HOVER if hot else dk.ACCENT), dk.ACCENT, dk.WHITE
            elif hot:
                fillc, line, color = dk.BUTTON_HOVER, dk.CELL_LINE, dk.TEXT
            else:
                fillc, line, color = dk.CELL, dk.CELL_LINE, dk.TEXT_ICON
            dk.box(c.x, c.y, c.w, c.h, 6 * s, fillc, None, line, 1.0 * s)
            ix, iy = c.x + (c.w - 16 * s) / 2, c.y + (c.h - 16 * s) / 2
            if c.glyph == ('MID', 'MID'):
                icons.draw("center", ix, iy, 16 * s, color, 1.5)
            else:
                icons.draw("arrow", ix, iy, 16 * s, color, 1.5, icons.ANCHOR_ROTATION[c.glyph])
        elif k == 'divider':
            dk.fill(c.x, c.y, c.w, max(1.0, c.h), 0.0, dk.DIVIDER)
        elif k == 'action':
            if not c.enabled:
                fillc, line, color = dk.DISABLED, dk.DISABLED_LINE, dk.DISABLED_TEXT
            elif hot:
                fillc, line, color = dk.BUTTON_HOVER, dk.ACTION_LINE, dk.TEXT_TITLE
            else:
                fillc, line, color = dk.ACTION, dk.ACTION_LINE, dk.TEXT_BUTTON
            dk.box(c.x, c.y, c.w, c.h, 6 * s, fillc, None, line, 1.0 * s)
            size = 12 * s
            label = dk.fit(c.label, c.w - 34 * s, size)
            total = 14 * s + 7 * s + dk.text_width(label, size)
            sx = c.x + (c.w - total) / 2
            icons.draw(c.glyph, sx, c.y + (c.h - 14 * s) / 2, 14 * s, color, 1.5)
            dk.text(label, sx + 21 * s, c.y, c.h, size, color)
        elif k == 'fold':
            color = dk.TEXT if hot else dk.TEXT_LABEL
            _caps(Ctl('l', c.x + 12 * s, c.y, c.w, c.h, c.label), s, color)
            icons.draw("chevron", c.x + c.w - 26 * s, c.y + (c.h - 14 * s) / 2, 14 * s, color, 1.6,
                       90 if c.on else 0)
        elif k == 'optlabel':
            dk.text(c.label, c.x, c.y, c.h, 11.5 * s, dk.TEXT_MUTED)
        elif k == 'switch_row':
            if hot:
                dk.box(c.x - 4 * s, c.y, c.w + 8 * s, c.h, 6 * s, dk.mix(dk.SECTION, dk.WHITE, 0.05))
            dk.text(dk.fit(c.label, c.w - (SWITCH_W + 12) * s, 12.5 * s), c.x, c.y, c.h, 12.5 * s, dk.TEXT_SOFT)
            dk.switch(c.x + c.w - SWITCH_W * s, c.y + (c.h - SWITCH_H * s) / 2, SWITCH_W * s, SWITCH_H * s,
                      c.on, s, hot)
        elif k == 'rule':
            dk.fill(c.x, c.y, c.w, max(1.0, c.h), 0.0, dk.FOOT_LINE)
        elif k == 'keys':
            dk.text(dk.fit(c.label, c.w * 0.45, 11 * s), c.x, c.y, c.h, 11 * s, dk.TEXT_HINT)
            _key_caps(c.style, c.x + c.w, c.y, c.h, s)
        elif k == 'check':
            icons.draw("warn", c.x, c.y + (c.h - 14 * s) / 2, 14 * s, dk.WARN, 1.5)
            count = f"{c.style}"
            cw = dk.text_width(count, 11 * s, "mono") + 10 * s
            dk.text(dk.fit(c.label, c.w - 22 * s - cw, 12 * s), c.x + 22 * s, c.y, c.h, 12 * s, dk.TEXT_SOFT)
            dk.box(c.x + c.w - cw, c.y + (c.h - 18 * s) / 2, cw, 18 * s, 9 * s, dk.WARN_FILL)
            dk.text(count, c.x + c.w - cw, c.y + (c.h - 18 * s) / 2, 18 * s, 11 * s, dk.WARN, 'CENTER', cw,
                    face="mono")
        elif k == 'fix':
            dk.box(c.x, c.y, c.w, c.h, 6 * s, dk.BUTTON_HOVER if hot else dk.ACTION, None, dk.ACTION_LINE, 1.0 * s)
            dk.text(c.label, c.x, c.y, c.h, 11.5 * s, dk.TEXT_TITLE if hot else dk.TEXT_BUTTON, 'CENTER', c.w,
                    face="medium")
        elif k == 'checkok':
            icons.draw("ok", c.x, c.y + (c.h - 14 * s) / 2, 14 * s, dk.OK, 1.5)
            dk.text(dk.fit(c.label, c.w - 22 * s, 12 * s), c.x + 22 * s, c.y, c.h, 12 * s, dk.TEXT_SOFT)
    gpu.state.blend_set('NONE')


def _key_caps(keys, right, y, h, s):
    """Keyboard key chips, right aligned: mono 10 px, 2/6 padding, 2 px bottom edge."""
    size = 10 * s
    widths = [dk.text_width(k, size, "mono") + 12 * s for k in keys]
    x = right - sum(widths) - 3 * s * (len(keys) - 1)
    ch = 18 * s
    cy = y + (h - ch) / 2
    for key, w in zip(keys, widths):
        dk.box(x, cy - 1 * s, w, ch + 1 * s, 4 * s, dk.KEY_LINE)          # the thicker bottom edge
        dk.box(x, cy + 1 * s, w, ch - 1 * s, 4 * s, dk.KEY, None, dk.KEY_LINE, 1.0 * s)
        dk.text(key, x, cy + 1 * s, ch - 1 * s, size, dk.KEY_TEXT, 'CENTER', w, face="mono")
        x += w + 3 * s

def _scale_points(context):
    prefs = context.preferences
    scale = prefs.system.ui_scale or 1.0
    points = prefs.ui_styles[0].widget.points if len(prefs.ui_styles) else 11.0
    return scale, points


def _draw():
    context = bpy.context
    region, area = context.region, context.area
    if region is None or region.type != 'UI' or not card_visible(area):
        return
    try:
        key = region.as_pointer()
        scale, points = _scale_points(context)
        info = card_info(context)
        scroll = _state["scroll"].get(key, 0.0)
        ctls, card, height = build(info, region.width, region.height, scale, points, scroll,
                                   _state["options_open"])
        room = region.height - 2 * MARGIN * scale
        limit = max(0.0, height - room)
        if scroll > limit:
            _state["scroll"][key] = scroll = limit
            ctls, card, height = build(info, region.width, region.height, scale, points, scroll,
                                       _state["options_open"])
        _state["layouts"][key] = (ctls, card)
        hover_region, hover = _state["hover"]
        paint(ctls, scale, points, hover if hover_region == key else None)  # hover is a ctl_key
    except Exception:  # noqa: BLE001 - a broken card must never break the sidebar
        traceback.print_exc()
        _state["failed"] = True


# -- the listener ----------------------------------------------------------------------------------

PASS = {'PASS_THROUGH'}


def _card_under(window, mx, my):
    for area in window.screen.areas:
        if area.type != 'VIEW_3D' or not card_visible(area):
            continue
        region = sidebar(area)
        if region.x <= mx < region.x + region.width and region.y <= my < region.y + region.height:
            laid = _state["layouts"].get(region.as_pointer())
            if laid is not None:
                return area, region, laid
    return None, None, None


def _redraw(region_ptr):
    wm = bpy.context.window_manager
    for window in wm.windows:
        for area in window.screen.areas:
            for region in area.regions:
                if region.as_pointer() == region_ptr:
                    region.tag_redraw()
                    return


class VIEW3D_OT_aot_card_listener(bpy.types.Operator):
    """Gives the Origin Tools card its clicks. Started by the add-on, never by hand"""
    bl_idname = "view3d.aot_card_listener"
    bl_label = "Origin Tools Card"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        window = context.window
        if window is None:
            return {'CANCELLED'}
        _state["token"] += 1
        self.token = _state["token"]
        self.window_ptr = window.as_pointer()
        _state["listeners"][self.window_ptr] = self.token
        _state["beats"][self.window_ptr] = time.monotonic()
        self.started = time.monotonic()
        self.last_on_card = 0.0
        self.timer = context.window_manager.event_timer_add(1.0, window=window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _leave(self, context):
        try:
            context.window_manager.event_timer_remove(self.timer)
        except (ReferenceError, ValueError, RuntimeError):
            pass
        if _state["listeners"].get(self.window_ptr) == self.token:
            del _state["listeners"][self.window_ptr]
        region_ptr, hover = _state["hover"]
        if hover is not None:
            _state["hover"] = (0, None)
            _redraw(region_ptr)
        return {'FINISHED', 'PASS_THROUGH'}

    def modal(self, context, event):
        if not _state["enabled"] or _state["listeners"].get(self.window_ptr) != self.token:
            return self._leave(context)
        _state["beats"][self.window_ptr] = time.monotonic()
        try:
            return self._event(context, event)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            return self._leave(context)

    def _event(self, context, event):
        now = time.monotonic()
        if event.type == 'TIMER':
            if not any(card_visible(a) for a in context.window.screen.areas):
                return self._leave(context)
            if now - self.started > STEP_ASIDE and now - self.last_on_card > 1.0:
                return self._leave(context)  # let a waiting autosave run; the keep-alive restarts us
            return PASS

        area, region, laid = _card_under(context.window, event.mouse_x, event.mouse_y)
        if region is None:
            region_ptr, hover = _state["hover"]
            if hover is not None:
                _state["hover"] = (0, None)
                _redraw(region_ptr)
            return PASS
        ctls, card = laid
        mx, my = event.mouse_x - region.x, event.mouse_y - region.y
        key = region.as_pointer()
        on_card = card.contains(mx, my)
        target = hit(ctls, mx, my) if on_card else None

        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            if on_card:
                self.last_on_card = now
            if _state["hover"] != (key, ctl_key(target)):
                old_ptr = _state["hover"][0]
                _state["hover"] = (key, ctl_key(target))
                region.tag_redraw()
                if old_ptr and old_ptr != key:
                    _redraw(old_ptr)
            return PASS
        if not on_card:
            return PASS
        self.last_on_card = now
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            scale = context.preferences.system.ui_scale or 1.0
            step = SCROLL_STEP * scale * (1 if event.type == 'WHEELDOWNMOUSE' else -1)
            _state["scroll"][key] = max(0.0, _state["scroll"].get(key, 0.0) + step)
            region.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS' and target is not None and target.enabled:
                perform(context, area, target)
                region.tag_redraw()
                for r in area.regions:
                    if r.type == 'WINDOW':
                        r.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'RIGHTMOUSE':
            return {'RUNNING_MODAL'}
        return PASS

    def cancel(self, context):
        if _state["listeners"].get(self.window_ptr) == self.token:
            del _state["listeners"][self.window_ptr]


def _keep_alive():
    """Start a listener in every window that shows a card and has none (or a silent one)."""
    if not _state["enabled"]:
        return None
    try:
        wm = bpy.context.window_manager
        now = time.monotonic()
        for window in (wm.windows if wm is not None else ()):
            ptr = window.as_pointer()
            if ptr in _state["listeners"] and now - _state["beats"].get(ptr, 0.0) < BEAT_TIMEOUT:
                continue
            area = next((a for a in window.screen.areas if card_visible(a)), None)
            if area is None:
                continue
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            with bpy.context.temp_override(window=window, area=area, region=region):
                bpy.ops.view3d.aot_card_listener('INVOKE_DEFAULT')
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    return 0.5


@bpy.app.handlers.persistent
def _after_load(_dummy):
    # Loading a file drops running modal operators: let the keep-alive start fresh ones.
    _state["listeners"].clear()
    _state["layouts"].clear()
    _state["hover"] = (0, None)


classes = (VIEW3D_OT_aot_card_listener,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    _state["enabled"] = True
    _state["failed"] = False
    _state["handle"] = bpy.types.SpaceView3D.draw_handler_add(_draw, (), 'UI', 'POST_PIXEL')
    bpy.app.handlers.load_post.append(_after_load)
    if not bpy.app.background:
        bpy.app.timers.register(_keep_alive, first_interval=0.5, persistent=True)


def unregister():
    _state["enabled"] = False  # running listeners leave on their next event
    if bpy.app.timers.is_registered(_keep_alive):
        bpy.app.timers.unregister(_keep_alive)
    if _after_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_after_load)
    if _state["handle"] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_state["handle"], 'UI')
        _state["handle"] = None
    _state["layouts"].clear()
    _state["listeners"].clear()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
