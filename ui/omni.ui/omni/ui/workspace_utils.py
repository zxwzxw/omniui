# Copyright (c) 2018-2020, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#
"""The utilities to capture and restore layout"""
from . import _ui as ui
from typing import Any, Tuple
from typing import Dict
from typing import List
from typing import Optional
import asyncio
import carb
import functools
import omni.kit.app
import traceback

ROOT_WINDOW_NAME = "DockSpace"
SAME = "SAME"
LEFT = "LEFT"
RIGHT = "RIGHT"
TOP = "TOP"
BOTTOM = "BOTTOM"
EXCLUDE_WINDOWS = [
    ROOT_WINDOW_NAME,
    "Debug##Default",
    "Status Bar",
    "Select File to Save Layout",
    "Select File to Load Layout",
]

# Used to prevent _restore_workspace_async from execution simultaneously
restore_workspace_task_global = None


def handle_exception(func):
    """
    Decorator to print exception in async functions
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            carb.log_error(f"Exception when async '{func}'")
            carb.log_error(f"{e}")
            carb.log_error(f"{traceback.format_exc()}")

    return wrapper


def _dump_window(window: ui.WindowHandle, window_list: List[str]):
    """Convert WindowHandle to the window description as a dict."""
    window_title = window.title
    window_list.append(window_title)
    selected_in_dock = window.is_selected_in_dock()
    result = {
        "title": window_title,
        "width": window.width,
        "height": window.height,
        "position_x": window.position_x,
        "position_y": window.position_y,
        "dock_id": window.dock_id,
        "visible": window.visible,
        "selected_in_dock": selected_in_dock,
    }

    if selected_in_dock:
        result["dock_tab_bar_visible"] = window.dock_tab_bar_visible
        result["dock_tab_bar_enabled"] = window.dock_tab_bar_enabled

    return result


def _dump_dock_node(dock_id: int, window_list: List[str]):
    """Convert dock id to the node description as a dict."""
    result: Dict[str, Any] = {"dock_id": dock_id}
    children_docks = ui.Workspace.get_dock_children_id(dock_id)
    position = ui.Workspace.get_dock_position(dock_id)

    if position != ui.DockPosition.SAME:
        result["position"] = position.name

    if children_docks:
        # Children are docking nodes. Add them recursively.
        result["children"] = [
            _dump_dock_node(children_docks[0], window_list),
            _dump_dock_node(children_docks[1], window_list),
        ]
    else:
        # All the children are windows
        docked_windows = ui.Workspace.get_docked_windows(dock_id)
        children_windows = [_dump_window(window, window_list) for window in docked_windows]

        # The size of the unselected window is the size the window was visible.
        # We need to get the size of the selected window and set it to all the
        # siblings.
        selected = [window["selected_in_dock"] for window in children_windows]
        try:
            selected_id = selected.index(True)
        except ValueError:
            selected_id = None
        if selected_id is not None:
            width = children_windows[selected_id]["width"]
            height = children_windows[selected_id]["height"]
            # Found width/height of selected window. Set it to all children.
            for child in children_windows:
                child["width"] = width
                child["height"] = height

        result["children"] = children_windows

    return result


def _dock_in(target: dict, source: dict, position: str, ratio: float):
    """
    Docks windows together. The difference with ui.WindowHandle.dock_in is that, it takes window descriptions as dicts.

    Args:
        target: the dictionary with the description of the window it's necessary to dock to source.
        source: the dictionary with the description of the window to dock in.
        position: "SAME", "LEFT", "RIGHT", "TOP", "BOTTOM".
        ratio: when docking side by side, specifies where there will be the border.
    """
    # Convert string to DockPosition
    # TODO: DockPosition is pybind11 enum and it probably has this conversion
    if position == SAME:
        dock_position = ui.DockPosition.SAME
    elif position == LEFT:
        dock_position = ui.DockPosition.LEFT
    elif position == RIGHT:
        dock_position = ui.DockPosition.RIGHT
    elif position == TOP:
        dock_position = ui.DockPosition.TOP
    elif position == BOTTOM:
        dock_position = ui.DockPosition.BOTTOM
    else:
        raise ValueError(f"{position} is not member of ui.DockPosition")

    target_window = ui.Workspace.get_window(target["title"])
    source_window = ui.Workspace.get_window(source["title"])

    carb.log_verbose(f"Docking window '{target_window}'.dock_in('{source_window}', {dock_position}, {ratio})")
    try:
        target_window.dock_in(source_window, dock_position, ratio)
    except AttributeError:
        carb.log_warn(
            f"Can't restore {target['title']}. A window with this title could not be found. Make sure that auto-load has been enabled for this extension."
        )

    # Stop deferred docking
    if isinstance(target_window, ui.Window):
        target_window.deferred_dock_in("")


def _dock_order(target: dict, order: int):
    """Set the position of the window in the dock."""
    window = ui.Workspace.get_window(target["title"])
    try:
        window.dock_order = order
        if target.get("selected_in_dock", None):
            window.focus()
    except AttributeError:
        carb.log_warn(
            f"Can't set dock order for {target['title']}. A window with this title could not be found. Make sure that auto-load has been enabled for this extension."
        )


def _restore_tab_bar(target: dict):
    """Restore dock_tab_bar_visible and dock_tab_bar_enabled"""
    window = ui.Workspace.get_window(target["title"])
    dock_tab_bar_visible = target.get("dock_tab_bar_visible", None)
    if dock_tab_bar_visible is not None:
        if window:
            window.dock_tab_bar_visible = dock_tab_bar_visible
        else:
            carb.log_warn(
                f"Can't set tab bar visibility for {target['title']}. A window "
                "with this title could not be found. Make sure that auto-load "
                "has been enabled for this extension."
            )
            return
    dock_tab_bar_enabled = target.get("dock_tab_bar_enabled", None)
    if dock_tab_bar_enabled is not None:
        if window:
            window.dock_tab_bar_enabled = dock_tab_bar_enabled
        else:
            carb.log_warn(
                f"Can't enable tab bar for {target['title']}. A window with "
                "this title could not be found. Make sure that auto-load has "
                "been enabled for this extension."
            )


def _is_dock_node(node: dict):
    """Return True if the dict is a dock node description"""
    return isinstance(node, dict) and "children" in node


def _is_window(window: dict):
    """Return True if the dict is a window description"""
    return isinstance(window, dict) and "title" in window


def _is_all_windows(windows: list):
    """Return true if all the items of the given list are window descriptions"""
    for w in windows:
        if not _is_window(w):
            return False
    return True


def _is_all_docks(children: list):
    """Return true if all the provided children are docking nodes"""
    return len(children) == 2 and _is_dock_node(children[0]) and _is_dock_node(children[1])


def _has_children(workspace_description: dict):
    """Return true if the item has valin nonempty children"""
    if not _is_dock_node(workspace_description):
        # Windows don't have children
        return False

    for c in workspace_description["children"]:
        if _is_window(c) or _has_children(c):
            return True

    return False


def _get_children(workspace_description: dict):
    """Return nonempty children"""
    children = workspace_description["children"]
    children = [c for c in children if _is_window(c) or _has_children(c)]
    if len(children) == 1 and _is_dock_node(children[0]):
        return _get_children(children[0])
    return children


def _target(workspace_description: dict):
    """Recursively find the first available window in the dock node"""
    children = _get_children(workspace_description)
    first = children[0]
    if _is_window(first):
        return first

    return _target(first)


def _restore_workspace(
    workspace_description: dict,
    root: dict,
    dock_order: List[Tuple[Any, int]],
    windows_to_set_dock_visibility: List[Dict],
):
    """
    Dock all the windows according to the workspace description.

    Args:
        workspace_description: the given workspace description.
        root: the root node to dock everything into.
        dock_order: output list of windows to adjust docking order.
        windows_to_set_dock_visibility: list of windows that have the info about dock_tab_bar
    """
    children = _get_children(workspace_description)

    if _is_all_docks(children):
        # Children are dock nodes
        first = _target(children[0])
        second = _target(children[1])

        if children[1]["position"] == RIGHT:
            first_width = _get_width(children[0])
            second_width = _get_width(children[1])
            ratio = second_width / (first_width + second_width)
        else:
            first_height = _get_height(children[0])
            second_height = _get_height(children[1])
            ratio = second_height / (first_height + second_height)

        # Dock the second window to the root
        _dock_in(second, root, children[1]["position"], ratio)

        # Recursively dock children
        _restore_workspace(children[0], first, dock_order, windows_to_set_dock_visibility)
        _restore_workspace(children[1], second, dock_order, windows_to_set_dock_visibility)

    elif _is_all_windows(children):
        # Children are windows. Dock everything to the first window in the list
        first = None
        children_count = len(children)
        for i, w in enumerate(children):
            # Save docking order
            if children_count > 1:
                dock_order.append((w, i))

            if w.get("selected_in_dock", None):
                windows_to_set_dock_visibility.append(w)

            if not first:
                first = w
            else:
                _dock_in(w, first, "SAME", 0.5)


def _get_visible_windows(workspace_description: dict, visible: bool):
    result = []
    if _is_dock_node(workspace_description):
        for w in _get_children(workspace_description):
            result += _get_visible_windows(w, visible)

    elif _is_window(workspace_description):
        visible_flag = workspace_description.get("visible", None)
        if visible:
            if visible_flag is None or visible_flag:
                result.append(workspace_description["title"])
        else:  # visible == False
            # Separate branch because we don't want to add the window with no
            # "visible" flag
            if not visible_flag:
                result.append(workspace_description["title"])

    return result


def _restore_window(window_description: dict):
    """Set the position and the size of the window"""
    # Skip invisible windows
    visible = window_description.get("visible", None)
    if visible is False:
        return

    # Skip the window that doesn't exist
    window = ui.Workspace.get_window(window_description["title"])
    if not window:
        return
    window.position_x = window_description["position_x"]
    window.position_y = window_description["position_y"]
    window.width = window_description["width"]
    window.height = window_description["height"]


def _get_width(node: dict):
    """Compute width of the given dock. It recursively checks the child windows."""
    children = _get_children(node)
    if _is_all_docks(children):
        if children[1]["position"] == BOTTOM or children[1]["position"] == TOP:
            return _get_width(children[0])
        elif children[1]["position"] == RIGHT or children[1]["position"] == LEFT:
            return _get_width(children[0]) + _get_width(children[1])
    elif _is_all_windows(children):
        return children[0]["width"]


def _get_height(node: dict):
    """Compute height of the given dock. It recursively checks the child windows."""
    children = _get_children(node)
    if _is_all_docks(children):
        if children[1]["position"] == BOTTOM or children[1]["position"] == TOP:
            return _get_height(children[0]) + _get_height(children[1])
        elif children[1]["position"] == RIGHT or children[1]["position"] == LEFT:
            return _get_height(children[0])
    elif _is_all_windows(children):
        return children[0]["height"]


@handle_exception
async def _restore_workspace_async(
    workspace_dump: List[Any],
    visible_titles: List[str],
    keep_windows_open: bool,
    wait_for: Optional[asyncio.Task] = None,
):
    """Dock the windows according to the workspace description"""
    if wait_for is not None:
        # Wait for another _restore_workspace_async task
        await wait_for

    ui.Workspace.clear()

    visible_titles_set = set(visible_titles)
    workspace_visible_windows = set()
    workspace_hidden_windows = set()

    already_visible = True
    for workspace_description in workspace_dump:
        visible_windows = _get_visible_windows(workspace_description, True)
        hidden_windows = _get_visible_windows(workspace_description, False)
        workspace_visible_windows = workspace_visible_windows.union(visible_windows)
        workspace_hidden_windows = workspace_hidden_windows.union(hidden_windows)

        for window_title in visible_windows:
            already_visible = ui.Workspace.show_window(window_title) and already_visible

    # The rest of the windows should be closed
    if keep_windows_open:
        # Close the widows with flag "visible=False". Don't close the windows
        # that don't have this flag.
        for window_title in visible_titles_set.intersection(workspace_hidden_windows):
            ui.Workspace.show_window(window_title, False)
    else:
        # Close all the widows that don't have flag "visible=True"
        for window_title in visible_titles_set - workspace_visible_windows:
            ui.Workspace.show_window(window_title, False)

    if not already_visible:
        # One of the windows is just created. ImGui needs to initialize it
        # to dock it. Wait one frame.
        await omni.kit.app.get_app().next_update_async()
    else:
        # Otherwise: RuntimeWarning: coroutine '_restore_workspace_async' was never awaited
        await asyncio.sleep(0)

    dock_order: List[Tuple[Any, int]] = []
    windows_to_set_dock_visibility: List[Dict] = []
    for i, workspace_description in enumerate(workspace_dump):
        if i == 0:
            # The first window in the dump is the root window
            root_window_dump = workspace_dump[0]
            if not _has_children(root_window_dump):
                continue
            first_root = _target(root_window_dump)
            _dock_in(first_root, {"title": ROOT_WINDOW_NAME}, "SAME", 0.5)

            _restore_workspace(root_window_dump, first_root, dock_order, windows_to_set_dock_visibility)
        elif _is_window(workspace_description):
            # Floating window
            _restore_window(workspace_description)
        # TODO: Floating window that is docked to another floating window

    if dock_order or windows_to_set_dock_visibility:
        # Wait one frame to dock everything
        await omni.kit.app.get_app().next_update_async()

    if dock_order:
        # Restore docking order
        for window, position in dock_order:
            _dock_order(window, position)

    if windows_to_set_dock_visibility:
        # Restore dock_tab_bar_visible and dock_tab_bar_enabled
        for window in windows_to_set_dock_visibility:
            _restore_tab_bar(window)

    # Let ImGui finish all the layout
    await omni.kit.app.get_app().next_update_async()


def dump_workspace():
    """
    Capture current workspace and return the dict with the description of the
    docking state and window size.
    """
    dumped_windows: List[str] = []
    workspace_dump: List[Any] = []

    # Dump the root window
    dock_space = ui.Workspace.get_window(ROOT_WINDOW_NAME)
    if dock_space:
        workspace_dump.append(_dump_dock_node(dock_space.dock_id, dumped_windows))

    # Dump the rest
    for window in ui.Workspace.get_windows():
        title = window.title
        if title not in EXCLUDE_WINDOWS and title not in dumped_windows:
            workspace_dump.append(_dump_window(window, dumped_windows))

    return workspace_dump


def restore_workspace(workspace_dump: List[Any], keep_windows_open=False):
    """
    Dock the windows according to the workspace description.

    ### Arguments

        `workspace_dump : List[Any]`
            The dictionary with the description of the layout. It's the dict
            received from `dump_workspace`.

        `keep_windows_open : bool`
            Determines if it's necessary to hide the already opened windows that
            are not present in `workspace_dump`.
    """
    global restore_workspace_task_global

    # Visible titles
    # `WindowHandle.visible` is different when it's called from `ensure_future`
    # because it's called outside of ImGui::Begin/ImGui::End. As result, the
    # `Console` window is not in the list of visible windows and it's not
    # closed. That's why it's called here and passed to
    # `_restore_workspace_async`.
    workspace_windows = ui.Workspace.get_windows()
    visible_titles = [w.title for w in workspace_windows if w.visible and w.title not in EXCLUDE_WINDOWS]
    restore_workspace_task_global = asyncio.ensure_future(
        _restore_workspace_async(workspace_dump, visible_titles, keep_windows_open)
    )
