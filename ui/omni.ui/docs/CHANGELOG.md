# Changelog

The Omniverse UI Framework.

`omni.ui` provides the basic types necessary to create rich extensions with a
fluid and dynamic user interface in the Omniverse applications.

## [2.14.4] - 2023-02-14
### Fixed
- Fix crash with mipmapped single channel image

## [2.14.3] - 2023-01-30
### Fixed
- Fixed mouse_released_fn for right click.

## [2.14.2] - 2023-02-01
### Changed
- Fixed multiple tests that weren't working in random order.
- Fixed golden img comparison diff image to have good alpha values.

## [2.13.7] - 2022-01-23
### Fixed
- Blurry text in ui.CanvasFrame

## [2.13.6] - 2022-01-19
### Fixed
- ui.Menu: Fix calling shown and torn callbacks when shown_changed_fn used with torn-off menu.

## [2.13.5] - 2022-01-18
### Fixed
- ui.Menu: Fix for incorrect behavior of shown_changed_fn in torn off menu

## [2.13.4] - 2022-01-16
### Added
- ui.Plot: ability to draw xy graphs

## [2.13.3] - 2023-01-10
### Fixed
- Tooltip position for omni.ui cache on mode near the boundary of the current canvasFrame

## [2.13.2] - 2023-01-04
### Changed
- Upload SVG data to texture without going to an on-disk image when possible.

## [2.12.26] - 2022-01-05
### Fixed
- Remove early exit from ui.Placer when child size is less than or equal ot zero.

## [2.12.25] - 2022-11-28
### Added
- The ability to rasterize ui.Frame and ui.Window to speed up the run loop.
  `ui.Frame(raster_policy=ui.RasterPolicy.AUTO)`. `ui.Placer` also supports it.
- A new method for rendering the ui.CanvasFrame that does not alter the
  position of the child widgets. This method involves rasterizing the entire
  canvas area and skipping the iteration of the child widgets during zoom, which
  can improve performance.

## [2.12.24] - 2022-12-14
### Fixed
- Regression with clipping of ui.Frame(separate_window=1) inside ScrollingFrame

## [2.12.23] - 2022-12-05
### Fixed
- Frame using separate_window flag was growing constantly during drag & drop

## [2.12.22] - 2022-12-04
### Fixed
- Grid crash due to trying to access an array element greater than its size

## [2.12.21] - 2022-12-02
### Add
- Add Multi-GPU upload support to DynamicTextureProvider
- Add set_bytes_data_from_gpu to ByteImageProvider for cuda/warp integration

## [2.12.20] - 2022-12-01
### Fixed
- Layout change crashes due to _restore_workspace_asyncs is called simultaneously

## [2.12.19] - 2022-10-20
### Changed
- TreeView behaviour in CanvasFrame

## [2.12.18] - 2022-11-20
### Fixed
- Disable mgpu in tests

## [2.12.17] - 2022-11-15
### Added
- Add DynamicTextureProvider

## [2.12.16] - 2022-11-03
### Changed
- Added additional validity checks and move some internal asserts to carb-errors.
- Fix a few possible lifetime issues by keeping local shared_ptr alive.
- Avoid some unnecessary copies into containers.

## [2.12.15] - 2022-11-11
### Fixed
- Removed experimental code from ui.Frame

## [2.12.14] - 2022-11-08
### Changed
- On Treeview multiselect, scroll to the most recently selected item.

## [2.12.13] - 2022-11-07
### Fixed
- Invalid assert on displaying large doubles

## [2.12.12] - 2022-10-25
### Added
- Overview page for omni.ui docs

## [2.12.11] - 2022-10-20
### Fixed
- Removed warning in `ui.VectorImageProvider`. Instead, it waits whaen the
  widget resolution is more than 0.

## [2.12.10] - 2022-10-11
### Fixed
- Memory leak in `ui.ImageWithProvider`

## [2.12.9] - 2022-10-03
### Fixed
- Fixed unexpected call of `mouse_released_fn`

## [2.12.8] - 2022-10-07
### Added
- Changed overflow warning to only report once

## [2.12.7] - 2022-10-06
### Fixed
- Size caching of MultiFloatField

## [2.12.6] - 2022-10-04
### Fixed
- Size caching of menu bar of MainWindow

## [2.12.5] - 2022-04-21
### Fixed
- `ui.Window.deferred_dock_in` prevented normal work of the layout

## [2.12.4] - 2022-09-30
### Fixed
- Reset size caching of Grid

## [2.12.3] - 2022-08-31
### Fixed
- mouse_wheel_fn is not called in a container widget like Frame
### Added
- Property elidedTextStr for Label, so that user can customize the elided_text_str instead of "..."

## [2.12.2] - 2022-09-30
### Fixed
- Reset size caching when visibility changes

## [2.12.1] - 2022-09-29
### Fixed
- Placer size caching

### Changed
## [2.12.0] - 2022-09-22
### Changed
- Aggressive caching of sizes of all the widgets
- Stack.send_mouse_events_to_back is true by default to make the behavior like
  in ImGui

## [2.11.5] - 2022-09-19
### Added
- `ui.Window.app_window` accessor.

## [2.1
### Added
- `ui.MainWindow` is able to hide all the windows with the property
  `ui.MainWindow.show_foreground`

## [2.11.3] - 2022-09-06
### Fixed
- Fix the workspace remove_window_visibility_changed_callback remove all the callback function at once.

## [2.11.2] - 2022-08-29
### Fixed
- Skip Placer draw if the child is 0-size

## [2.11.1] - 2022-08-02
### Fixed
- ui.MenuItem was disabled when changing visibility with delay

## [2.11.0] - 2022-08-23
### Added
- 'sendMouseEventsToBack' property to Stack widget
### Changed
- In Z-based stacks mouse events will go the front-most widget, unless 'sendMouseEventsToBack' is true.

## [2.10.9] - 2022-08-15
### Changed
- mouse_wheel_fn is not called if another window covers the widget
### Added
- Property to be able to scroll unfocused window.

## [2.10.8] - 2022-08-10
### Fixed
- Fixed TreeView's computed content height when root node is hidden.

## [2.10.7] - 2022-08-01
### Fixed
- Regenerate Menu when it's enabled.
- Make sure the menu is always on top.
- Middle click outside of the menu closes the menu
- Drag of menu bar doesn't produce detached menu

## [2.10.6] - 2022-07-28
### Added
- Add a interface to remove window's visibility changed callback function in omni.ui.Workspace.

## [2.10.5] - 2022-07-25
### Fixed
- Menu 2.0 in full screen mode
- User needs to drag the menu for 5 pixels for tearing off

## [2.10.4] - 2022-07-21
### Added
- Menu 2.0 title bar line

## [2.10.3] - 2022-07-19
### Fixed
- Drop down menu disappears when mousing between the gap

## [2.10.2] - 2022-07-18
### Added
- Add callback function in omni.ui.Workspace to notify the listener when any window's visibility changed.

## [2.10.1] - 2022-07-13
### Fixed
- Menu 2.0: SubMenu position

## [2.10.0] - 2022-07-07
### Added
- Precision property for FloatSlider, FloatDrag and FloatField.

## [2.9.12] - 2022-07-06
### Fixed
- ui.ImageWithProvider carsh when the style or image_url is not defined (OM-45414)

## [2.9.11] - 2022-06-21
### Added
- Ability to use clickable buttons in Menu 2.0

## [2.9.10] - 2022-06-15
### Fixed
- Padding of Slider and Field
### Added
- Support of border_color in ComboBox
- Support of fonts in TextEditor
### Changed
- No necessary to keep ImageProvider in python var anymore

## [2.9.9] - 2022-06-01
### Added
- Supports for fonts through the style "font"

## [2.9.8] - 2022-05-25
### Fixed
- Rounding of ui.FloatSlider

## [2.9.7] - 2022-05-12
### Fixed
- Crash when creating and destroying ui.Image

## [2.9.6] - 2022-05-02
### Removed
- Dependency on pip

## [2.9.5] - 2022-05-06
### Added
- Add style to change modal window dim background color

## [2.9.4] - 2022-05-02
### Added
- ui.Workspace API to inspect parent docking node id and docking node size:
  - get_parent_dock_id
  - get_dock_id_width
  - get_dock_id_height
  - set_dock_id_width
  - set_dock_id_height

## [2.9.3] - 2022-04-22
### Fixed
- Image blurring when it's placed to fractional position (like x=0.5, y=0.5)

## [2.9.2] - 2022-04-08
### Fixed
- Change the CanvasFrame zoom max from constant 10 to float max
- Make the CanvasFrame zoom near the zoom min and zoom max smooth

## [2.9.1] - 2022-04-06
### Fixed
- The workspace should hide the explicitly invisible windows even if the flag
keep_windows_open is set.

## [2.9.0] - 2022-04-06
### Fixed
- Message "Failed to acquire interface while unloading all plugins" related to
  Button, Image and ImageWithProvider

## [2.8.2] - 2022-04-05
### Added
- setZoomKeyShortcut api for ui.CanvasFrame to allow user to set alternative shortcut for graph zoom in adition to middle
  mouse scroll

## [2.8.1] - 2022-04-01
### Fixed
- Used `getAmendedProjection` to transform to/from NDC space.

## [2.8.0] - 2022-03-21
### Changed
- ui.CollapsableFrame marks both its header and body for rebuilding on a rebuild call

## [2.7.9] - 2022-02-22
### Changed
- Updated `capture_and_compare` with use_log parameter
- Updated `docked_test_window` for omni.kit.window compatibility

## [2.7.8] - 2022-03-25
### Fixed
- Compensate dpiScale for the menu bar

## [2.7.7] - 2022-03-24
### Fixed
- Fixed the "Hide Tab" window title menu item
- Polishing `ui.Menu`

## [2.7.5] - 2022-03-17
### Fixed
- Fixed `/app/window/hideUi` mode when only viewport is visible

## [2.7.4] - 2022-03-14
### Fixed
- Checking ImGui visibility when creating new window

## [2.7.3] - 2022-03-10
### Fixed
- Fixed the size of `ui.ToolBar`. Before it was always 600x400 and it's the
  reason why the saves workspace proportions were wrong. So the workspace
  proportions are fixed.
- Fixed the visibility of windows in `ui.Workspace.restore_workspace`.

## [2.7.2] - 2022-03-08
### Fixed
- Treeview column reorder issue of wrong column width

## [2.7.1] - 2022-02-18
### Fixed
- OM-36695: Drag and drop of multiple items
- OM-43762: Freezing of ui.FreeBezierCurve when end_tangent_height is extreamly big
- "Move to External Window" menu should only appear when clicking the title

## [2.7.0] - 2022-02-18
### Added
- ui.CanvasFrame.set_pan_x_changed_fn for tracking how user navigates
- ui.MenuItemCollection that behaves like a radio box
- Property ui.Widget.tooltip so it's possible to query it
- Ability to create right-aligned horizontal menu

## Fixed
- The menu automatically updates when changing the `checked` property
- Horizontal ui.Menu doesn't open windows on hover
- ui.MenuHelper checks if the user clicked in another window

## [2.6.1] - 2022-02-14
### Fixed
- OM-44806: `ui.Widget.checked_changed_fn`

## [2.6.0] - 2022-02-02
### Changed
- Full refactor of ui.Menu. Fully compatible with the old menu.

## [2.5.19] - 2022-01-28
### Changed
- set TreeView header's height and width to 0 instead of computedHeight and computedWidth

## [2.5.18] - 2022-01-26
### Added
- Arg in `Workspace.restore_workspace` to keep the windows open

## [2.5.17] - 2022-01-19
### Changed
- Fix issue for OM-40734: once TreeView is scrolled, the header is not clickable

## [2.5.16] - 2022-01-19
### Changed
- Delay tooltip when hovering is larger than 0.5 second

## [2.5.15] - 2022-01-18
### Added
- Add scroll_x_max and scroll_y_max for ScrollingFrame

## [2.5.14] - 2022-01-11
### Changed
- The way to add a shade to named color:
  `cl.test_named_shade_append = cl.shade(cl("#000000"), red=cl("#FF0000"))`
  `cl.test_named_shade_append.add_shade(blue=cl("#0000FF"))`

## [2.5.12] - 2022-01-07
### Changed
- Override previously submitted tooltip (only one tooltip is allowed)

## [2.5.11] - 2022-01-06
### Changed
- `cl.shade` appends palette to existing shade

## [2.5.10] - 2021-12-16
### Fixed
- Crash when specifying `columns_resizable=True` on a treeview but forgetting to set `column_widths`

## [2.5.9] - 2021-12-13
### Added
- ImageWithProvider.prepare_draw to force the image loading

## [2.5.8] - 2021-12-09
### Added
- The ability to move ui.Window to the virtual OS window. See
  `ui.Window.move_to_app_window`

## [2.5.7] - 2021-12-08
### Added
- Warning message when restoring the layout of tab bar of the window that
doesn't exist

## [2.5.6] - 2021-12-02
### Fixed
- Crash when ui.Image attempts loading a broken svg the second time

## [2.5.5] - 2021-11-17
### Added
- ui.Separator supports title parameter for fancy menu headers

## [2.5.4] - 2021-11-06
### Fixed
- Crash ui.TreeView when getting children right after constructor

## [2.5.3] - 2021-11-02
### Added
- ui.Menu.shown is a property that is True if the menu is shown on the screen
- Static ui.Menu.get_current() that returns currently shown menu
- ui.Inspector can get children of ui.TreeView, ui.Grid and ui.Frame
- The ability to use FontHelper with non-widgets

## [2.5.2] - 2021-09-20
### Added
- Added missing `text` binding to omni.ui.Menu

## [2.5.1] - 2021-09-07
### Added
- The ability to add third-party modules to namespace omni.ui

## [2.5.0] - 2021-08-17
### Fixed
- TreeView crash when AbstractItem is removed in Python

## [2.4.0] - 2021-07-22
### Added
- OffsetLine draws the line stuck to the bounds of other widgets

## [2.3.2] - 2021-06-21
### Fixed
- [OM-29853] Fixed crash in WindowHandle::isSelectedInDock

## [2.3.1] - 2021-06-15
### Changed
- When `dock_tab_bar_visible` is false, tab bar has a triangle and doesn't
  have tabs
### Added
- Added a menu that sets `dock_tab_bar_visible` for a tab if it's a single
  tab in tab bar
- Added `dock_tab_bar_enabled` to disable tab bar completely
- Serialization of `dock_tab_bar_visible` and `dock_tab_bar_enabled` in quick
  layout

## [2.3.0] - 2021-06-04
### Added
- The ability to use style shades for floats and URLs in style properties

## [2.2.0] - 2021-05-31
### Added
- `ui.Widget.set_computed_content_size_changed_fn` will be called when the
  computed size of the widget is changed.

## [2.1.8] - 2021-05-14
### Fixed
- Tooltip on ui.Line
- ui.StringField size in ui.CanvasFrame

## [2.1.7] - 2021-05-11
### Added
- Added WINDOW_FLAGS_NO_SCROLL_WITH_MOUSE that locks scroll
### Fixed
- Fixed pan over a backdrop in Material Editor

## [2.1.6] - 2021-05-07
### Fixed
- Don't block hovering state when popup window is on the screen

## [2.1.5] - 2021-04-08
### Fixed
- position_x/position_y of undocked window
### Changed
- Those methods are not abstract anymore:
  a. AbstractItemDelegate::buildBranch
  b. AbstractItemDelegate::buildHeader
  c. AbstractItemModel::appendChildItem
  d. AbstractItemModel::removeItem

## [2.1.4] - 2021-04-06
### Added
- ui.Widget.FLAG_WANT_CAPTURE_KEYBOARD: The flag passed to `key_pressed`
  callback that indicated omni.ui is using the keyboard input exclusively

## [2.1.3] - 2021-03-18
## Added
- Default style can be applied to `omni.ui.style.default`
- CSS color names
- Named colors
- Shades

## [2.1.2] - 2021-02-17
### Added
- Added docked_test_window function to OmniUiTest

## [2.1.1] - 2021-02-08
### Added
- ui.Workspace.set_show_window_fn
- ui.Workspace.show_window

## [2.1.0] - 2021-01-12
### Changed
- Documentation
- Shapes API to have free and non-free widgets. `Shape` is abstract class, all
  the derived classes should implement `_drawShape`.

### Added
- Widget.style property
- FreeLine, FreeRectangle, FreeCircle, FreeTriangle

## [2.0.1] - 2020-11-16
### Added
- Started changelog
- Keyboard callback for `ui.Window`
- Ability to grab the keyboard for the exclusive use of `ui.Window`
