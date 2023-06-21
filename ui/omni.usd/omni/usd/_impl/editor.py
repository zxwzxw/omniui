from pxr import Sdf, Tf, Usd, UsdGeom

## C++ counterpart at include/omni/kit/EditorUsd.h

## Metadata should match whatever defined in source/plugins/omni.kit/usd/omniKit/resources
HIDE_IN_STAGE_WINDOW = "hide_in_stage_window"
NO_DELETE = "no_delete"
ALWAYS_PICK_MODEL = "always_pick_model"

# New meta that obeys naming convention
# UI can use this meta to decide if it should be displayed.
HIDE_IN_UI = "omni:kit:hideInUI"


def set_hide_in_stage_window(prim, hide):
    prim.SetMetadata(HIDE_IN_STAGE_WINDOW, hide)


def is_hide_in_stage_window(prim):
    return prim.GetMetadata(HIDE_IN_STAGE_WINDOW)


def set_no_delete(prim, no_delete):
    prim.SetMetadata(NO_DELETE, no_delete)


def is_no_delete(prim):
    return prim.GetMetadata(NO_DELETE)


def set_always_pick_model(prim, pick_model):
    prim.SetMetadata(ALWAYS_PICK_MODEL, pick_model)


def is_always_pick_model(prim):
    return prim.GetMetadata(ALWAYS_PICK_MODEL)


def set_hide_in_ui(prim, value):
    prim.SetMetadata(HIDE_IN_UI, value)


def is_hide_in_ui(prim):
    return prim.GetMetadata(HIDE_IN_UI)
