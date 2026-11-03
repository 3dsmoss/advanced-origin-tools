# Advanced Origin Tools – Changelog

## 1.5.0

### Fixed
- Shift+Mouse 4 cards looked washed out (light grey cards, pale accent): the 3D View draws into an sRGB buffer, and the custom shader now converts its colors the way Blender's own shaders do.
- Stray light lines above card frames and bright specks on their corners: blf switches blending off after each text, so later shapes wrote their soft edge pixels unblended; every shape now turns blending on itself.
- Orient Origin on a plate (no side faces, e.g. a square plane turned on three axes): the second axis now follows its edges; before, it was borrowed from the world and the box sat on the diagonal, far bigger than the plate.
- Drop to Floor / To World Origin put the origin on the object's own bottom (Space setting) instead of the bottom of a world-aligned box, which left a tilted object's origin in empty space; the object still rests on its lowest point.
- The Orient Origin preview says what Auto read ("from the selection" / "from the shape"), so a leftover Edit Mode selection no longer turns the axes unnoticed.
- Shortcuts: the transform menu also opens with Ctrl+Shift+Q (free in Blender's keymap; not every mouse has a Mouse 4 button, Shift+Mouse 4 stays as a second key). Ctrl+Q outside the 3D View no longer quits Blender (a note in the status bar instead; can be switched off in the preferences). A held keyboard key no longer closes the transform menu through key repeat.
- Card frames and icons snap to whole pixels: fractional layout positions split 1 px frames into two faint half lines (broken-looking corners, one side brighter than the other).
- Narrow sidebar: Drop to Floor / World Origin stack instead of being cut off, and the mode tag hides instead of overlapping the section title.
- Bounding box buttons no longer fail in Edit Mode (`mode_set(mode='EDIT_MESH')` raised a TypeError and left you in Object Mode).
- "Origin to Selection" with nothing selected no longer moves the origin to the 3D cursor; it reports a warning and does nothing.
- With several objects selected, every object no longer gets the active object's point.
- The "corner" buttons reached only the front-view (X/Z) plane with Y fixed to the middle; all 27 points of the box are reachable now.
- The result no longer depends on the Pivot Point setting.
- Undo in Edit Mode: Ctrl+Z restored the vertices but not the object position, so the mesh jumped. The tools now finish with a full undo step and return to Edit Mode right after.
- Linked duplicates (shared mesh) stay in place when one of them gets a new origin.
- Mirror modifier (half models): the origin stays on the mirror plane by default ("Keep Mirror Plane"), so the mirrored half no longer jumps.
- Drop to Floor: rotated objects now really rest on the floor (lowest point on Z = 0); the buttons measure in world space.
- Animated objects: location keyframes move together with the origin, so the object no longer jumps on other frames.

### Added
- Depth row (Front / Middle / Back) for the 3×3 grid: 27 bounding box points.
- Selection center modes: Median, Bounds, Active (last selected vertex, edge or face).
- Multiple objects: each object uses its own geometry, or all share one combined origin.
- Local or world-space bounds; bounds with or without modifiers.
- In Edit Mode the grid uses the selected vertices (whole mesh when nothing is selected).
- Drop to Floor and To World Origin buttons.
- Origin to Selection on Ctrl Q (over the 3D View; elsewhere Ctrl Q still quits Blender).
- Pie menu (Shift Alt Q).
- Transform menu (Shift Mouse 4): Transform Orientations, Pivot Point and Snap Target as dark, half-transparent cards around the cursor, drawn by the add-on (gpu/blf) with TexBridge's blue accent (#3b8fe5): rounded buttons, blue frame and dark blue fill on the current choice, switches for Snap and Only Locations, "+" for a custom orientation. Click to pick, or hold, move and release like a pie; Shift-click keeps it open for several snap targets; Esc, right click or a click outside closes it. Stays clear of the toolbar, sidebar and header, and falls back to a single row when there is little room. Plain Mouse 4 keeps Blender's View Selected.
- Adjust Last Operation (F9) for every option.
- Card style sidebar: in its own "Origin" tab the tools are drawn as a card in the add-on's look (header badge, Selection Center / Bounding Box / Options sections, segmented choices, 3x3 arrow grid, switches, hover and disabled states, scroll). A listener runs only while the card is on screen and steps aside regularly so Blender's autosave is not held back. "Card Style Sidebar" in Preferences switches back to the classic panel, which is also used when the tab is shared (Tool, Item, View).
- Orient Origin: turns an object's axes (the origin's rotation) while the mesh stays where it is. Auto reads the direction from the object's flat faces (Object Mode) or from the selected faces, edges or vertices (Edit Mode); also Active object, View, 3D Cursor and World. An object whose rotation was applied gets its old rotation values back. From the 3D View, the card, the panel or the pie it first shows a preview on the object (current axes faint, new axes as X / Y / Z arrows, the box the object gets on them): X / Y / Z turn the new axes a quarter turn (settles a box that looks the same from several sides), Tab or the card's Auto / Active / World switches the preview to that mode (each mode keeps its own turns; a mode that cannot work says why), clicks on the card or sidebar go to them, pressing Orient Origin again applies the open preview instead of opening a second one, Backspace undoes the turns, Enter, Space or a click applies, Esc or right click cancels; the view can be turned meanwhile, and the turns are kept for F9. F9: Main Axis (which axis follows the face normal) and Long Side (which axis runs along the longest side, for boxes turned past 45° where two axes could swap). Keeps children and linked duplicates in place; a non-uniform or mirrored scale goes into the mesh so the shape cannot shear. Skips objects with animated rotation.
- Export section: an export check for the selected meshes (scale not applied, negative scale, origin far from the mesh), each with a Fix button (apply scale with children kept and mirrored faces turned outward; origin to the bottom center). Shared meshes and animated scale are left alone.
- Preferences: sidebar tab name, editable shortcuts.
- Curves, surfaces, text and metaballs are supported by the bounding box tools.
- Warning when the final shape changes because a modifier depends on the origin (Displace with local coordinates, Hook, Simple Deform, ...), and when rotation or scale is animated.
- Turkish translation.
- Blender 4.2+ extension package (`blender_manifest.toml`).

### Changed
- The tools are disabled in Sculpt and Paint modes: their undo steps do not restore object transforms.
- Operator ids now have the `aot_` prefix to avoid clashes with other add-ons.
- Shortcuts live in the "3D View Generic" keymap, which Blender checks first, so leftovers in an imported key configuration (e.g. a pie of an add-on that is not installed) cannot swallow them.
