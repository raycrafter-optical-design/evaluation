# Development log

What we had to change to make this work, and the choices behind it. Newest decisions are at the
end of each section. Where a number is given it was measured offscreen, not on a real display.

## 1. Architecture

- **Optiland is the engine, behind a Qt-free `model.py`.** The GUI never touches Optiland
  directly, except through the model's result objects (`SpotResult`, `FastTrace`, ...). The model
  rebuilds a small Optiland system from the state on every change (about 8 ms) instead of mutating
  a long-lived one, which is simpler and avoids stale surfaces after add/delete/flip.
- **matplotlib first, then pyqtgraph.** The first version drew with matplotlib. pyqtgraph won on
  speed (draw about 1 ms against about 6 ms; full update about 26 ms against about 65 ms) and
  because lenses and the image plane can be native draggable items. The matplotlib GUI
  (`gui.py`) has been deleted.
- **Updates are coalesced.** Mouse drags request an update through a zero-delay single-shot timer,
  so a burst of events costs one recompute.
- **Fast and slow paths.** The side view, spot, through-focus plot and status bar update on every
  change (about 17 ms of tracing). The MTF, ray fan and field curvature are redrawn 120 ms after
  the last change, and only for the visible tab.
- **One Optiland system per update.** `trace_fast` builds a single system with two fields (0 deg
  and the current angle) and traces both spots, the side-view fan and the paraxial summary from
  it. Building the system (about 8 ms) is the largest single cost, so it is done once rather than
  once per plot; adding the second field and the paraxial summary left the fast path at about
  17 ms.

## 2. Things that broke, and what fixed them

- **UTF-16 ZMX files.** Optiland's reader needs UTF-8, so each prescription is converted into a
  temporary file before loading.
- **`surfaces.add(material=None)` raises.** Air must be expressed by leaving `material` out.
- **Deprecation warnings** in Optiland 0.6.3. The new `optic.surfaces / fields / wavelengths` API
  is used where it exists; `surface_group` is still used to read per-surface ray positions for
  the side view.
- **Black box around a lens when hovering.** The invisible `LinearRegionItem` that makes a lens
  draggable has a transparent brush, and pyqtgraph derives the hover brush from it. The derived
  brush came out solid black. Both brushes are now set explicitly. (The hover brush was first a
  faint blue tint; that rectangle looked bad and is now fully transparent, see section 3.)
- **Many rays, one curve.** All side-view rays are joined into a single curve separated by NaN
  and drawn with `connect="finite"`; one item is much faster than one per ray.
- **Drop-down highlight unreadable on macOS.** The first fix (colouring the popup list in the
  stylesheet) did nothing, because macOS draws the default combo popup with the native style and
  ignores stylesheet selection colours, giving white text on a white highlight. Fix: give the
  combo a plain `QListView` popup, and style its `::item:hover` and `::item:selected` states.
  Checked by rendering the open popup and looking at it.
- **Tab titles too narrow to read.** The tab font size had been set on `QTabBar::tab`, so Qt sized the
  tabs from the 13 px default font but painted 11 px text, and on macOS the titles were cut short.
  Fix: set `font-size: 11px` on `QTabBar` itself (so sizing and painting agree), give each tab a
  90 px minimum width, and turn off title eliding and scroll arrows. Checked by comparing each tab's
  width with its text width.
- **Two overlapping grids on the side view.** `make_plot` turns pyqtgraph's grid on for every
  plot. When adding the hand-drawn square grid the line that switched the built-in one off for the
  side view was deleted by mistake, so both were drawn. Restored, with a comment explaining it.

- **Side view squeezed to a sliver.** A word-wrapped hint label in the control panel reported a
  large height-for-width size hint, which swelled the bottom row. Fixes: the label ignores its
  vertical hint (with a reserved minimum height so it still shows), the side view has a 240 px
  minimum, and the side view and the three tab widgets ignore their own preferred heights so the
  2:3 stretch alone shares the height (342 / 512 px at 900 px tall).
- **Image label bounced while dragging.** `InfiniteLine`'s built-in label re-anchors itself on
  every move. Replaced by a `TextItem` at a fixed height, moved with the line.
- **"image" label kept the green bar over its text.** The caption is now white on a green box
  with a higher z-value than the line.
- **Combo-box arrow had dark right and bottom edges** (the native macOS arrow). A style sheet can
  only replace it with an image, so a flat chevron PNG is drawn at start-up and written to the
  temp folder; a light grey divider sits at its left.
- **Name tag lost its top corners.** The tag was a child of the view box, which clips its children
  to the data area; a tall lens near the top edge sliced the tag square. It is now a child of the
  plot item and positioned in screen pixels (clamped to stay inside the plot).
- **Timing text wrapped onto many lines.** `idealWidth()` came out a little too narrow. Wrapping
  is switched off and 12 px of slack added.
- **Near-duplicate rule ignored negative lenses** (the tolerance was multiplied by a negative focal
  length) and would have dropped one of the two -50 mm lenses of different sizes. It now compares
  magnitudes and only within one lens size.

## 3. Choices in the plots

- **Square grid on the side view.** The axes span 450 mm by 64 mm, so a grid in data units would
  be rectangles. The grid is drawn by hand: spacing is chosen per axis so each cell is 40 screen
  pixels square, anchored at the origin, and redrawn when the plot is resized. It is a faint
  grey and sits behind everything.
- **Hover feedback instead of selection.** There is no selected (red) state any more. The lens
  under the pointer turns a darker blue (darker purple for a Plossl pair, and the whole pair
  darkens together); that lens is the target of the right-click menu and the F / Delete keys. The
  hit test is `lens_index_at`. A widget `Leave` event clears it, because no mouse-move arrives when
  the pointer exits. The left/right arrow cursor shows over lenses and over the image line.
- **Lens name tag.** White text, 10% smaller than the default, on a solid rounded box a shade
  darker than the lens colour, centred 3 px above the lens. The box is drawn 2 px inside the text
  item at top and bottom, because the text item has more vertical margin than horizontal.
- **Beam vergence.** Modelled in Optiland as a finite object distance of -1000 / V mm: a real
  point source for diverging beams and a negative distance (a virtual object behind the lens) for
  converging ones. The beam diameter is still measured at the first lens. The slider spans +/-1
  dioptre, the vergence of an f = 1000 mm lens. In the side view each incoming ray is drawn back
  with slope = tilt - V * height. "Reset beam" restores 0 vergence, 0 angle and 10 mm.
- **Spot diagram overlay.** Each field is centred on its own centroid so shapes and sizes are
  comparable. Orange is 0 deg, blue is the current angle; the title carries both RMS radii in
  those colours, which saves a legend. The 0 deg spot is hidden when the angle is 0.
- **Airy disk.** Radius 0.61 lambda / NA, with NA taken from the traced rays (largest angle from
  the mean ray direction), so it is right for any vergence and for tilted beams, and zero for a
  parallel beam (no circle). The spot view is widened to include the circle, but never by more than
  3x the spot size, so a huge Airy disk cannot shrink the spots to a dot.
- **Through-focus.** No extra ray tracing: the rays at the image plane are straight lines, so the
  RMS radius at any other plane is a vectorised calculation (under 1 ms). The window is 4 depths
  of focus (lambda / NA^2) either side, extended to include the best focus if the image plane is
  far from it, and cannot reach back into the last lens. The same function drives autofocus.
- **Ray fan.** Two fans of 41 rays (along y and along x); the error is each ray's image-plane
  position minus the chief ray's (the middle ray). The y range is symmetric about zero so a
  perfect system is a flat line.
- **Tabs kept small.** Three `QTabWidget`s with a flat style: 11 px grey text, transparent
  background, a 2 px blue underline on the selected tab, left aligned, no frame. Field curvature
  has a one-tab widget so the three plots line up. Only the visible MTF or ray-fan tab is computed.
- **Readouts in the status bar.** EFL, BFL, f-number (EFL / beam diameter) and the Airy radius,
  next to the image plane z and RMS radius. EFL and BFL come from Optiland's paraxial properties;
  Optiland reports the back focal point relative to the image surface, so BFL is measured from the
  last lens vertex using the image plane position. With no lenses these are omitted.
- **Timings moved to the side view.** The trace and draw times are small grey text in its top-right
  corner, in 2/3 of the size of the axis numbers (read from the viewport font after the style sheet
  is applied, so it follows if that size changes). The "n lens(es)" text was removed.

## 4. Decisions worth remembering

- A collimated beam is an object at infinity, so moving a lens is the same as moving the image
  plane the other way. Only the lens-to-image distance changes the spot.
- Field curvature is estimated from ray fans with a closed-form least-squares focus
  (-cov(position, slope) / var(slope)) rather than Optiland's `FieldCurvature` class.
- The catalog is the A-coated 2" positive achromats (`AC508` / `ACT508`) plus the A-coated negative
  ones (`ACN127` / `ACN254`); near-duplicate focal lengths of one size are collapsed to the rounder one.

## 5. Known gaps

- Rays are not clipped by lens apertures or mounts (a beam wider than a small negative lens still passes).
- Single wavelength (555 nm); no chromatic focal shift or polychromatic spot.
- No undo/redo or saving of a setup (only the ZMX export and the HTML report).
- Everything was checked offscreen with code-driven events and screenshots; mouse behaviour on a
  real display has not been tried.

## 6. Later additions

- **Controls.** Reset beam and Save ZMX share a row; Generate report and a Lock focus checkbox sit
  below, and a grey hint at the foot of the panel points to the right-click menu. The panel is a
  framed card and each plot has a thin grey border. Each plot has a 5 px gap under its x label
  (the border stays put), and the side view has an 8 px gap at the top.
- **Lock focus** (off by default). On every update it runs autofocus, and keeps the result only if
  the focus lies between the last lens (+1 mm) and 5 mm inside the right edge of the side view;
  otherwise the image plane stays where it was (a negative lens has no real focus). While locked
  the green line cannot be dragged, has no hover highlight and no arrow cursor.
- **Image line** is dashed green and turns solid green on hover (pyqtgraph's default hover colour is
  red).
- **Negative achromats.** The drop-down now also has the eight A-coated ACN127 / ACN254 lenses
  (Thorlabs makes no 2" negative ones), listed after the positive ones. Negative lenses cannot
  form a Plossl pair. Beams are not clipped to the smaller apertures.
- **Per-lens actions in a right-click menu**: Flip (F), Delete (Del or Backspace) and Make / Split
  Plossl, replacing the Flip, Delete, Make Plossl and Split Plossl buttons. The keys act on the
  lens under the pointer. While "Make Plossl" is highlighted, a dashed red rectangle outlines the
  two lenses that would be paired.
- **Reordering lenses by dragging.** Moving a lens (or pair) so its centre passes the centre of a
  neighbour swaps the two in the list. The pair keeps the same overall span and the air gap between
  them, so nothing downstream moves. `move_lens` returns the new order so the GUI reorders its
  per-lens graphics, otherwise the item under the mouse would end up drawing the wrong lens.
- **HTML report** (`report.py`). The ray diagram across the top, then spot, through-focus and MTF,
  then ray fan and field curvature, as inline matplotlib SVG in the GUI colours, with a row of
  summary tiles. Each plot except the ray diagram has a "?" button that opens a non-modal note
  beside the card (right, left, below or above, whichever has room), with the card outlined. No
  blur or dimming, so the text can be read next to the plot. The file is self-contained and is
  written to the temp folder and opened in the default browser.
- **App icon.** A lens with converging rays, drawn in code, replaces the Python rocket in the Dock.
  If macOS still shows the rocket at launch, a small `.app` bundle with an `.icns` would be needed.

## 7. Clean-up

- Removed: selection state and the click-to-select handler, the four per-lens buttons and their
  enable/disable logic, the red selection colour, the hover rectangle brush, the `InfiniteLine`
  label, and one unused variable in the swap code. Imports tidied and `json` moved to the top of
  `report.py`. A scan for unused imports, constants, functions and locals found nothing else.
