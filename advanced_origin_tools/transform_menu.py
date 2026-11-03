"""Shift Mouse 4: the header's Orientation, Pivot Point and Snapping menus as cards
around the cursor, in the add-on's own look.

Blender's menus can only be colored through the theme, so these cards are drawn by
the add-on itself: rounded shapes through `gpu`, text through `blf`, and a modal
operator that decides what every click means. Sizes are written at 1x and
multiplied by the interface scale; rectangles are given by their bottom-left corner,
as Blender's region coordinates are.

Using it works like a pie: press the shortcut, then either click an entry, or keep
the button held, move onto an entry and let go. Shift-click keeps the cards open
(for several snap targets). Esc, right click or a click outside closes them.
"""

import ast
import json
import math
import os

import bpy
import gpu
from bpy.app.translations import pgettext_iface as iface_

from . import draw_kit as dk, icons, keymaps, operators

CTX = operators.I18N_CTX

# -- sizes at 1x (from the design: Transform Menus overlay / Specs) ----------------------

PAD = 8
HEADER_H = 28
ROW_H = 30
ROW_GAP = 4
CARD_R = 12
ROW_R = 6
ICON = 15
MIN_W = 200
SIDE_GAP = 150    # cursor to the inner edge of the side cards
TOP_GAP = 72      # cursor to the bottom of the top card
FOOTER_GAP = 9    # divider with its margins above the Only Locations row
SWITCH_W = 30
SWITCH_H = 18
PLUS = 24
CHECK = 14
HINT_BAR = 50     # room kept at the bottom for the hint strip
MARGIN = 8        # keep the cards this far inside the 3D View
DRAG = 12         # moving this far with the button held turns a release into a pick
CAPS_SPACING = 0.09
LISTS = {'orient', 'pivot', 'snap'}
IGNORED = {'LEFT_SHIFT', 'RIGHT_SHIFT', 'LEFT_CTRL', 'RIGHT_CTRL', 'LEFT_ALT', 'RIGHT_ALT', 'OSKEY',
           'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}
PASSED = {'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'WHEELINMOUSE', 'WHEELOUTMOUSE', 'MIDDLEMOUSE',
          'TRACKPADPAN', 'TRACKPADZOOM', 'MOUSEROTATE', 'MOUSESMARTZOOM', 'TIMER', 'TIMER0', 'TIMER1',
          'TIMER2', 'TIMER_JOBS', 'TIMER_AUTOSAVE', 'TIMER_REPORT', 'TIMERREGION', 'NDOF_MOTION'}


# -- the data the cards show ------------------------------------------------------

def custom_orientations(slot):
    """Names of the user's custom orientations.

    Blender has no list for them, but assigning a value that does not exist makes
    it name every valid one in the error message (nothing is changed)."""
    builtin = [i.identifier for i in slot.bl_rna.properties["type"].enum_items]
    try:
        slot.type = "\u0001"
    except TypeError as ex:
        return parse_enum_error(str(ex), builtin)
    return []


def parse_enum_error(message, builtin):
    start = message.rfind("not found in (")
    if start < 0:
        return []
    try:
        names = ast.literal_eval(message[start + len("not found in "):].strip())
    except (ValueError, SyntaxError):
        return []
    if isinstance(names, str):
        names = (names,)
    return [n for n in names if n not in builtin]


def _enum(data, prop):
    return [(i.identifier, iface_(i.name)) for i in data.bl_rna.properties[prop].enum_items]


def menu_data(context):
    ts = context.tool_settings
    slot = context.scene.transform_orientation_slots[0]
    orients = _enum(slot, "type") + [(n, n) for n in custom_orientations(slot)]
    return {
        "orient": orients,
        "orient_value": {slot.type},
        "pivot": _enum(ts, "transform_pivot_point"),
        "pivot_value": {ts.transform_pivot_point},
        "snap": _enum(ts, "snap_elements_base"),
        "snap_value": set(ts.snap_elements_base),
        "use_snap": ts.use_snap,
        "align": ts.use_transform_pivot_point_align if context.mode in {'OBJECT', 'POSE', 'WEIGHT_PAINT'} else None,
        "align_label": iface_(ts.bl_rna.properties["use_transform_pivot_point_align"].name),
        "titles": (iface_("Orientation"), iface_("Pivot Point"), iface_("Snapping")),
    }


# -- layout -----------------------------------------------------------------------

class Hit:
    __slots__ = ("kind", "value", "label", "x", "y", "w", "h", "on")

    def __init__(self, kind, value, label, x, y, w, h, on=False):
        self.kind, self.value, self.label, self.on = kind, value, label, on
        self.x, self.y, self.w, self.h = x, y, w, h

    def contains(self, mx, my):
        return self.x <= mx <= self.x + self.w and self.y <= my <= self.y + self.h


class Card:
    __slots__ = ("title", "x", "y", "w", "h", "hits", "widget", "_entries")

    def __init__(self, title, w, h):
        self.title, self.w, self.h = title, w, h
        self.x = self.y = 0.0
        self.hits = []
        self.widget = None  # 'plus' or 'switch' in the header

    def contains(self, mx, my):
        return self.x <= mx <= self.x + self.w and self.y <= my <= self.y + self.h


text_width = dk.text_width


def build_cards(data, cx, cy, area_w, area_h, scale, points, insets=(0.0, 0.0, 0.0, 0.0)):
    """Card rectangles in region pixels around the cursor (cx, cy).

    insets: (left, bottom, right, top) taken by the toolbar, sidebar and header, which
    are drawn on top of the 3D View; the cards stay clear of them.
    """
    s = scale
    item_size = 12.5 * s
    title_size = 10.5 * s

    def card_for(title, kind, entries, values, widget=None, footer=None):
        widest = max(text_width(label, item_size) for _key, label in entries)
        widest += (10 + ICON + 10 + 10) * s + ((CHECK + 10) * s if kind == 'snap' else 0)
        head = text_width(title.upper(), title_size, "semibold", CAPS_SPACING * title_size) + (PLUS + 16) * s
        if footer is not None:
            widest = max(widest, text_width(footer[1], item_size) + (SWITCH_W + 26) * s)
        base = (MIN_W + (10 if kind == 'snap' else 0)) * s
        w = max(base, widest + 2 * PAD * s, head + 2 * PAD * s)
        rows = len(entries)
        h = (PAD + HEADER_H + rows * (ROW_H + ROW_GAP) - ROW_GAP + PAD) * s
        if footer is not None:
            h += (FOOTER_GAP + ROW_H) * s
        card = Card(title, w, h)
        card._entries = (kind, entries, values, widget, footer)  # noqa: SLF001 - filled in below
        return card

    titles = data["titles"]
    orient = card_for(titles[0], 'orient', data["orient"], data["orient_value"], widget='plus')
    pivot = card_for(titles[1], 'pivot', data["pivot"], data["pivot_value"],
                     footer=None if data["align"] is None else ('align_toggle', data["align_label"], data["align"]))
    snap = card_for(titles[2], 'snap', data["snap"], data["snap_value"], widget='switch')

    orient.x, orient.y = cx - SIDE_GAP * s - orient.w, cy - orient.h / 2
    snap.x, snap.y = cx + SIDE_GAP * s, cy - snap.h / 2
    pivot.x, pivot.y = cx - pivot.w / 2, cy + TOP_GAP * s
    cards = [orient, pivot, snap]

    # Keep everything inside the visible part of the 3D View.
    m = MARGIN * s
    lo_x, lo_y = insets[0] + m, insets[1] + m
    hi_x, hi_y = area_w - insets[2] - m, area_h - insets[3] - m

    def span(pos, size):
        return max(getattr(c, pos) + getattr(c, size) for c in cards) - min(getattr(c, pos) for c in cards)

    if span("x", "w") > hi_x - lo_x or span("y", "h") > hi_y - lo_y:
        # Too little room around the cursor (small view, large interface scale):
        # one row instead, tops aligned, centered on the cursor.
        gap = 16 * s
        tallest = max(c.h for c in cards)
        x = cx - (sum(c.w for c in cards) + gap * 2) / 2
        for c in cards:
            c.x, c.y = x, cy + tallest / 2 - c.h
            x += c.w + gap

    left = min(c.x for c in cards)
    right = max(c.x + c.w for c in cards)
    bottom = min(c.y for c in cards)
    top = max(c.y + c.h for c in cards)
    dx = (lo_x - left) if left < lo_x else min(0.0, hi_x - right)
    dy = (lo_y - bottom) if bottom < lo_y else min(0.0, hi_y - top)
    for c in cards:
        c.x += dx
        c.y += dy

    for c in cards:
        kind, entries, values, widget, footer = c._entries
        del c._entries
        row_top = c.y + c.h - (PAD + HEADER_H) * s
        for key, label in entries:
            y = row_top - ROW_H * s
            c.hits.append(Hit(kind, key, label, c.x + PAD * s, y, c.w - 2 * PAD * s, ROW_H * s, key in values))
            row_top = y - ROW_GAP * s
        header_mid = c.y + c.h - (PAD + HEADER_H / 2) * s
        if widget == 'plus':
            size = PLUS * s
            c.widget = Hit('add_orientation', None, "+", c.x + c.w - (PAD + 2) * s - size, header_mid - size / 2,
                           size, size)
        elif widget == 'switch':
            c.widget = Hit('snap_toggle', None, "", c.x + c.w - (PAD + 6) * s - SWITCH_W * s,
                           header_mid - SWITCH_H * s / 2, SWITCH_W * s, SWITCH_H * s, data["use_snap"])
        if footer is not None:
            y = c.y + PAD * s
            c.hits.append(Hit(footer[0], None, footer[1], c.x + PAD * s, y, c.w - 2 * PAD * s, ROW_H * s,
                              bool(footer[2])))
    return cards


def hit_at(cards, mx, my):
    for c in cards:
        if c.widget is not None and c.widget.contains(mx, my):
            return c.widget
        for h in c.hits:
            if h.contains(mx, my):
                return h
    return None


# -- applying a pick ------------------------------------------------------------------

def apply_hit(context, hit, add=False):
    """Change the setting behind ``hit``. Returns True when the cards should stay open."""
    ts = context.tool_settings
    if hit.kind == 'orient':
        context.scene.transform_orientation_slots[0].type = hit.value
        return add
    if hit.kind == 'pivot':
        ts.transform_pivot_point = hit.value
        return add
    if hit.kind == 'snap':
        current = set(ts.snap_elements_base)
        if add:
            current ^= {hit.value}
            ts.snap_elements_base = current or {hit.value}
            return True
        ts.snap_elements_base = {hit.value}
        return False
    if hit.kind == 'snap_toggle':
        ts.use_snap = not ts.use_snap
        return True
    if hit.kind == 'align_toggle':
        ts.use_transform_pivot_point_align = not ts.use_transform_pivot_point_align
        return True
    if hit.kind == 'add_orientation':
        try:
            bpy.ops.transform.create_orientation(use=True)
        except RuntimeError:
            pass  # nothing to build it from (no active object / selection)
        return True
    return True


# -- drawing ----------------------------------------------------------------------------

_ORIENT_ICON = {'CURSOR': "ORIENT_CURSOR"}


def _row_icon(kind, value):
    if kind == 'orient':
        name = _ORIENT_ICON.get(value, value)
        return name if name in icons.ICONS else "CUSTOM"
    return value


def _caps(text, x, y, h, size, color):
    dk.text(text.upper(), x, y, h, size, color, face="semibold", spacing=CAPS_SPACING * size)


def _hint_bar(st):
    groups = [(["Click"], _("Set")), (["Shift", "+", "Click"], _("Add snap element")), (["Esc"], _("Close"))]
    dk.hint_bar(groups, st.width / 2, st.hint_y, st.scale)


def draw_cards(st):
    s = st.scale
    item_size = 12.5 * s
    gpu.state.blend_set('ALPHA')

    # Where the menu was opened: a 28 px ring with a dot, as in the design.
    dk.ring(st.cx, st.cy, 13 * s, 2.0 * s, dk.FOCUS)
    dk.fill(st.cx - 2 * s, st.cy - 2 * s, 4 * s, 4 * s, 2 * s, dk.FOCUS)

    snapping_on = True
    for c in st.cards:
        if c.widget is not None and c.widget.kind == 'snap_toggle':
            snapping_on = c.widget.on

    for c in st.cards:
        dk.shadow(c.x, c.y, c.w, c.h, CARD_R * s, s)
        dk.box(c.x, c.y, c.w, c.h, CARD_R * s, dk.MENU_CARD, None, dk.MENU_LINE, 1.0 * s)

        head_y = c.y + c.h - (PAD + HEADER_H) * s
        _caps(c.title, c.x + (PAD + 6) * s, head_y, HEADER_H * s, 10.5 * s, dk.TEXT_LABEL)
        if c.widget is not None:
            w = c.widget
            hover = st.hover is w
            if w.kind == 'snap_toggle':
                dk.switch(w.x, w.y, w.w, w.h, w.on, s, hover)
            else:
                if hover:
                    dk.box(w.x, w.y, w.w, w.h, 6 * s, dk.BUTTON_HOVER)
                icons.draw("plus", w.x + (w.w - 14 * s) / 2, w.y + (w.h - 14 * s) / 2, 14 * s,
                           dk.WHITE if hover else dk.TEXT_SOFT, 1.6)

        for h in c.hits:
            hover = st.hover is h
            if h.kind == 'align_toggle':
                line_y = h.y + h.h + 4 * s
                dk.fill(h.x + 2 * s, line_y, h.w - 4 * s, 1.0 * s, 0.0, dk.MENU_DIVIDER)
                if hover:
                    dk.box(h.x, h.y, h.w, h.h, ROW_R * s, dk.BUTTON_HOVER)
                dk.text(dk.fit(h.label, h.w - (SWITCH_W + 26) * s, item_size), h.x + 10 * s, h.y, h.h, item_size,
                        dk.TEXT_SOFT)
                dk.switch(h.x + h.w - (SWITCH_W + 6) * s, h.y + (h.h - SWITCH_H * s) / 2, SWITCH_W * s,
                          SWITCH_H * s, h.on, s, hover)
                continue
            dim = h.kind == 'snap' and not snapping_on
            if h.on:
                fillc, line, color = (dk.ACCENT_HOVER if hover else dk.ACCENT), dk.ACCENT_LINE, dk.WHITE
            elif hover:
                fillc, line, color = dk.BUTTON_HOVER, None, dk.TEXT
            else:
                fillc, line, color = dk.BUTTON, None, dk.TEXT_ROW
            if dim:  # the design's opacity 0.5, as a blend so strokes never double up
                fillc, color = dk.mix(fillc, dk.MENU_CARD, 0.5), dk.mix(color, dk.MENU_CARD, 0.5)
                line = None
            dk.box(h.x, h.y, h.w, h.h, ROW_R * s, fillc, None, line, 1.0 * s)
            icons.draw(_row_icon(h.kind, h.value), h.x + 10 * s, h.y + (h.h - ICON * s) / 2, ICON * s, color, 1.4)
            room = h.w - (10 + ICON + 10 + 10) * s - ((CHECK + 10) * s if h.kind == 'snap' else 0)
            dk.text(dk.fit(h.label, room, item_size), h.x + (10 + ICON + 10) * s, h.y, h.h, item_size, color)
            if h.kind == 'snap':
                bx, by = h.x + h.w - (10 + CHECK) * s, h.y + (h.h - CHECK * s) / 2
                if h.on:
                    dk.box(bx, by, CHECK * s, CHECK * s, 4 * s, dk.mix(dk.WHITE, dk.MENU_CARD, 0.5) if dim else dk.WHITE)
                    icons.draw("check", bx + 2 * s, by + 2 * s, 10 * s, dk.ACCENT, 2.4)
                else:
                    dk.box(bx, by, CHECK * s, CHECK * s, 4 * s, (0, 0, 0, 0), None,
                           dk.mix(dk.CHECK_OFF, dk.MENU_CARD, 0.5) if dim else dk.CHECK_OFF, 1.0 * s)

    _hint_bar(st)
    gpu.state.blend_set('NONE')


def _(text):
    return iface_(text, CTX)

# -- the operator -------------------------------------------------------------------------

class _State:
    """Everything the draw callback needs; deliberately not the operator itself."""

    def __init__(self):
        self.region_ptr = 0
        self.region_x = self.region_y = 0
        self.cx = self.cy = 0.0
        self.scale = 1.0
        self.points = 11.0
        self.hint_y = 18.0
        self.width = self.height = 0
        self.cards = []
        self.hover = None
        self.handle = None
        self.launch = 'NONE'
        self.dragged = False


_active = None


def _draw(st):
    region = bpy.context.region
    if region is not None and region.as_pointer() == st.region_ptr:
        draw_cards(st)


overlap_insets = dk.overlap_insets


def _region_under(context):
    for region in context.area.regions:
        if region.type == 'WINDOW':
            return region
    return None


def _close():
    global _active
    st = _active
    _active = None
    if st is not None and st.handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(st.handle, 'WINDOW')
    wm = bpy.context.window_manager
    for window in (wm.windows if wm is not None else ()):
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


class VIEW3D_OT_aot_transform_menu(bpy.types.Operator):
    """Transform Orientation, Pivot Point and Snapping around the cursor"""
    bl_idname = keymaps.TRANSFORM_MENU_OP
    bl_label = "Transform Menu"
    bl_translation_context = CTX

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def _rebuild(self, context):
        st = _active
        st.cards = build_cards(menu_data(context), st.cx, st.cy, st.width, st.height, st.scale, st.points,
                               st.insets)

    def invoke(self, context, event):
        global _active
        if _active is not None:  # pressed again while open: close
            _close()
            return {'CANCELLED'}
        region = _region_under(context)
        if region is None:
            return {'CANCELLED'}
        prefs = context.preferences
        st = _State()
        st.region_ptr = region.as_pointer()
        st.region_x, st.region_y = region.x, region.y
        st.width, st.height = region.width, region.height
        left, bottom, right, top = overlap_insets(context.area, region)
        st.hint_y = bottom + 18 * (prefs.system.ui_scale or 1.0)
        st.insets = (left, bottom + HINT_BAR * (prefs.system.ui_scale or 1.0), right, top)
        st.cx, st.cy = event.mouse_x - region.x, event.mouse_y - region.y
        st.scale = prefs.system.ui_scale or 1.0
        st.points = prefs.ui_styles[0].widget.points if len(prefs.ui_styles) else 11.0
        st.launch = event.type
        st.press = (st.cx, st.cy)
        _active = st
        self._rebuild(context)
        st.handle = bpy.types.SpaceView3D.draw_handler_add(_draw, (st,), 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self)
        region.tag_redraw()
        return {'RUNNING_MODAL'}

    def _finish(self, context, passed=False):
        _close()
        return {'FINISHED', 'PASS_THROUGH'} if passed else {'FINISHED'}

    def _pick(self, context, hit, add):
        keep = apply_hit(context, hit, add)
        try:
            bpy.ops.ed.undo_push(message=hit.label or self.bl_label)
        except RuntimeError:
            pass
        if keep:
            self._rebuild(context)
            _active.hover = hit_at(_active.cards, hit.x + 1, hit.y + 1)
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        return self._finish(context)

    def modal(self, context, event):
        st = _active
        if st is None:
            return {'CANCELLED'}
        mx, my = event.mouse_x - st.region_x, event.mouse_y - st.region_y
        kind, value = event.type, event.value

        if kind in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            hover = hit_at(st.cards, mx, my)
            if hover is not st.hover:
                st.hover = hover
                context.area.tag_redraw()
            if not st.dragged and math.dist((mx, my), st.press) > DRAG * st.scale:
                st.dragged = True
            return {'RUNNING_MODAL'}

        if kind == st.launch:
            if value == 'PRESS' and getattr(event, "is_repeat", False):
                return {'RUNNING_MODAL'}  # a held keyboard key repeats: not a second press
            if value == 'RELEASE':
                if not st.dragged:
                    return {'RUNNING_MODAL'}  # quick press: stay open for a click
                hit = hit_at(st.cards, mx, my)
                if hit is not None and hit.kind in LISTS:
                    return self._pick(context, hit, add=False)
                return self._finish(context)
            if value == 'PRESS':
                return self._finish(context)  # the shortcut again closes the cards

        if kind == 'LEFTMOUSE':
            if value != 'PRESS':
                return {'RUNNING_MODAL'}
            hit = hit_at(st.cards, mx, my)
            if hit is None:
                return self._finish(context)
            return self._pick(context, hit, add=event.shift)

        if kind in {'RIGHTMOUSE', 'ESC'}:
            return self._finish(context) if value == 'PRESS' else {'RUNNING_MODAL'}
        if kind == 'WINDOW_DEACTIVATE':
            return self._finish(context)
        if kind in IGNORED:
            return {'RUNNING_MODAL'}
        if kind in PASSED or kind.startswith('TIMER') or kind.startswith('NDOF'):
            return {'PASS_THROUGH'}
        if value == 'PRESS':
            return self._finish(context, passed=True)  # any other key: close, then let it work
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        _close()


# -- the previous version changed theme colors while its pie was open ----------------------

def _recover_old_theme_backup():
    try:
        path = os.path.join(bpy.utils.extension_path_user(__package__, create=False), "aot_theme_backup.json")
    except Exception:  # noqa: BLE001 - not installed as an extension
        return
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        ui = bpy.context.preferences.themes[0].user_interface
        for widget, attr, color in saved:
            colors = getattr(ui, widget, None)
            if colors is not None and hasattr(colors, attr):
                setattr(colors, attr, tuple(color))
    except (OSError, ValueError, TypeError):
        pass
    try:
        os.remove(path)
    except OSError:
        pass


classes = (VIEW3D_OT_aot_transform_menu,)


def register():
    _recover_old_theme_backup()
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    _close()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
