import bpy

SELECTION_OP = "object.aot_origin_to_selection"
PIE_OP = "wm.call_menu_pie"
PIE_MENU = "VIEW3D_MT_aot_origin_pie"
TRANSFORM_MENU_OP = "view3d.aot_transform_menu"  # cards drawn around the cursor
NO_QUIT_OP = "wm.aot_no_quit"  # Ctrl Q outside the 3D View: never close Blender by accident

addon_keymaps = []


def register():
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:  # background mode
        return
    # "3D View Generic" is checked before "3D View", and add-on items go to the head of
    # their keymap, so these win over leftovers in an imported key configuration (for
    # example a pie of an add-on that is not installed, which would swallow the key).
    km = kc.keymaps.new(name='3D View Generic', space_type='VIEW_3D')
    # Over the 3D View Ctrl Q is Origin to Selection instead of Quit.
    kmi = km.keymap_items.new(SELECTION_OP, 'Q', 'PRESS', ctrl=True)
    addon_keymaps.append((km, kmi))
    # Shift Alt Q: one hand, next to Ctrl Q. Free in Blender's keymap outside Grease Pencil edit modes
    # (Ctrl Alt Q would take Quad View).
    kmi = km.keymap_items.new(PIE_OP, 'Q', 'PRESS', shift=True, alt=True)
    kmi.properties.name = PIE_MENU
    addon_keymaps.append((km, kmi))
    # Orientation + Pivot Point + Snapping as cards around the cursor. Ctrl Shift Q is free
    # in Blender's keymap (Ctrl Alt Q is Quad View); Shift Mouse 4 stays as a second key
    # for mice that have the button (Mouse 4 alone is View Selected).
    kmi = km.keymap_items.new(TRANSFORM_MENU_OP, 'Q', 'PRESS', ctrl=True, shift=True)
    addon_keymaps.append((km, kmi))
    kmi = km.keymap_items.new(TRANSFORM_MENU_OP, 'BUTTON4MOUSE', 'PRESS', shift=True)
    addon_keymaps.append((km, kmi))
    # Everywhere else Ctrl Q does nothing (a note in the status bar) instead of closing
    # Blender: the same keys must not quit just because the pointer left the 3D View.
    # It can be switched off in the add-on preferences like any shortcut.
    km = kc.keymaps.new(name='Window', space_type='EMPTY')
    kmi = km.keymap_items.new(NO_QUIT_OP, 'Q', 'PRESS', ctrl=True)
    addon_keymaps.append((km, kmi))


def unregister():
    for km, kmi in addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except (ReferenceError, RuntimeError):
            pass
    addon_keymaps.clear()


def _target_name(kmi):
    """Menu name of a wm.call_menu_pie item (None otherwise)."""
    props = kmi.properties
    return getattr(props, "name", None) if props is not None else None


def user_items():
    """The user-keyconfig copies of the addon shortcuts (edits there are saved)."""
    kc = bpy.context.window_manager.keyconfigs.user
    if kc is None:
        return []
    found = []
    seen = {}  # (keymap, operator, menu) -> how many add-on items of it came before
    for km_addon, kmi_addon in addon_keymaps:
        km = kc.keymaps.get(km_addon.name)
        if km is None:
            continue
        wanted = _target_name(kmi_addon)
        key = (km_addon.name, kmi_addon.idname, wanted)
        nth = seen.get(key, 0)
        seen[key] = nth + 1
        # Two shortcuts for one operator (Ctrl Shift Q and Shift Mouse 4): pair them in order.
        matches = [kmi for kmi in km.keymap_items
                   if kmi.idname == kmi_addon.idname and (wanted is None or _target_name(kmi) == wanted)]
        if nth < len(matches):
            found.append((km, matches[nth]))
    return found


_KEY_NAMES = {'BUTTON4MOUSE': "Mouse 4", 'BUTTON5MOUSE': "Mouse 5", 'LEFTMOUSE': "LMB", 'RIGHTMOUSE': "RMB",
              'MIDDLEMOUSE': "MMB", 'SPACE': "Space", 'TAB': "Tab", 'RET': "Enter", 'ESC': "Esc"}


def _shown_item(idname, target):
    """The shortcut to show for an operator: a keyboard one before a mouse button."""
    items = [kmi for _km, kmi in user_items()
             if kmi.idname == idname and (target is None or _target_name(kmi) == target)]
    active = [kmi for kmi in items if kmi.active]
    if not active:
        return items[0] if items else None
    return min(active, key=lambda kmi: kmi.type.endswith("MOUSE"))


def shortcut_keys(idname, target=None):
    """The shortcut as separate key caps, e.g. ['Shift', 'Alt', 'Q'] ([] when unset)."""
    kmi = _shown_item(idname, target)
    if kmi is None or not kmi.active:
        return []
    keys = [name for flag, name in ((kmi.ctrl, "Ctrl"), (kmi.shift, "Shift"), (kmi.alt, "Alt"),
                                    (kmi.oskey, "Cmd")) if flag]
    keys.append(_KEY_NAMES.get(kmi.type, kmi.type.replace("_", " ").title() if len(kmi.type) > 1 else kmi.type))
    return keys


def shortcut_text(idname, target=None):
    kmi = _shown_item(idname, target)
    return kmi.to_string() if kmi is not None and kmi.active else ""
