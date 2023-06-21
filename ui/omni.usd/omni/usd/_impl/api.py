# Copyright (c) 2020, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#

import asyncio
import carb.events
import omni.kit.app
from .._usd import *
from functools import partial
from typing import Tuple, List, Dict, Any
from pxr import Usd, UsdUtils


# Save new_stage handles as it will be patched below.
__old_new_stage = UsdContext.new_stage
__old_new_stage_with_callback = UsdContext.new_stage_with_callback


def on_stage_result(result: bool, err_msg: str, future: asyncio.Future):
    if not future.done():
        future.set_result((result, err_msg))

def on_layers_saved_result(result: bool, err_msg: str, saved_layers: List[str], future: asyncio.Future):
    if not future.done():
        future.set_result((result, err_msg, saved_layers))

async def _next_stage_event_async(self) -> Tuple[StageEventType, Dict[Any, Any]]:
    """Wait for next stage event of omni.usd."""
    order = omni.kit.app.EVENT_ORDER_DEFAULT

    f = asyncio.Future()

    def on_event(e: carb.events.IEvent):
        if not f.done():
            f.set_result((e.type, e.payload.get_dict()))

    sub = self.get_stage_event_stream().create_subscription_to_pop(on_event, name="asyn stage update", order=order)
    return await f


async def _selection_changed_async(self) -> List[str]:
    """Wait for selection to be changed. Return a list of newly selected paths."""
    f = asyncio.Future()

    def on_event(e: carb.events.IEvent):
        if e.type == int(StageEventType.SELECTION_CHANGED) and not f.done():
            f.set_result(self.get_selection().get_selected_prim_paths())

    sub = self.get_stage_event_stream().create_subscription_to_pop(on_event, name="async selection changed")
    return await f


def _new_stage_python_wrapper(self, fn=None, load_set: UsdContextInitialLoadSet = UsdContextInitialLoadSet.LOAD_ALL):
    """Python version of omni.usd.get_context.new_stage() that supports to customize load set of new stage."""
    if not fn:
        success = __old_new_stage(self, fn)
        if success and load_set == UsdContextInitialLoadSet.LOAD_NONE:
            self.get_stage().SetLoadRules(Usd.StageLoadRules.LoadNone())
    else:
        def on_new_stage_callback(success, error_message):
            if success and load_set == UsdContextInitialLoadSet.LOAD_NONE:
                self.get_stage().SetLoadRules(Usd.StageLoadRules.LoadNone())
            
            fn(success, error_message)
        
        success = __old_new_stage_with_callback(self, on_new_stage_callback)
    
    return success


def _new_stage_sync(self, load_set: UsdContextInitialLoadSet = UsdContextInitialLoadSet.LOAD_ALL) -> bool:
    return _new_stage_python_wrapper(self, None, load_set)


async def _new_stage_async(self, load_set: UsdContextInitialLoadSet = UsdContextInitialLoadSet.LOAD_ALL) -> Tuple[bool, str]:
    """Asynchronous version of :func:`omni.usd.get_context().new_stage_with_callback`. Return a ``(result, error)`` tuple. Where error
    string is empty if ``result`` is ``False``."""
    f = asyncio.Future()
    _new_stage_python_wrapper(self, partial(on_stage_result, future=f), load_set)
    return await f


async def _attach_stage_async(self, stage) -> Tuple[bool, str]:
    """Asynchronous version of :func:`omni.usd.get_context().attach_stage_with_callback`. It's used to attach an existing opened
    stage. Return a ``(result, error)`` tuple. Where error string is empty if ``result`` is ``False``."""
    if not stage:
        return (False, "Failed to attach empty stage.")

    # Inserts stage into cache and passes it as stage id to usd context.
    cache = UsdUtils.StageCache.Get()
    stage_id = cache.Insert(stage).ToLongInt()

    f = asyncio.Future()
    self.attach_stage_with_callback(stage_id, partial(on_stage_result, future=f))
    return await f


async def _open_stage_async(
    self, url: str, load_set: UsdContextInitialLoadSet = UsdContextInitialLoadSet.LOAD_ALL
) -> Tuple[bool, str]:
    """Asynchronous version of :func:`omni.usd.get_context().open_stage_with_callback`. Return a ``(result, error)`` tuple. Where
    error string is empty if ``result`` is ``False``."""
    f = asyncio.Future()
    self.open_stage_with_callback(url, partial(on_stage_result, future=f), load_set)
    return await f


async def _reopen_stage_async(
    self, load_set: UsdContextInitialLoadSet = UsdContextInitialLoadSet.LOAD_ALL
) -> Tuple[bool, str]:
    """Asynchronous version of :func:`omni.usd.get_context().reopen_stage_with_callback`. Return a ``(result, error)`` tuple. Where
    error string is empty if ``result`` is ``False``."""
    f = asyncio.Future()
    self.reopen_stage_with_callback(partial(on_stage_result, future=f), load_set)
    return await f


async def _close_stage_async(self) -> Tuple[bool, str]:
    """Asynchronous version of :func:`omni.usd.get_context().close_stage_with_callback`. Return a ``(result, error)`` tuple. Where
    error string is empty if ``result`` is ``False``."""
    f = asyncio.Future()
    self.close_stage_with_callback(partial(on_stage_result, future=f))
    return await f


async def _save_stage_async(self) -> Tuple[bool, str]:
    """Asynchronous version of :func:`omni.usd.get_context().save_stage_with_callback`. Return a ``(result, error)`` tuple. Where
    error string is empty if ``result`` is ``False``."""
    f = asyncio.Future()
    self.save_stage_with_callback(partial(on_layers_saved_result, future=f))
    return await f


async def _save_as_stage_async(self, url: str) -> Tuple[bool, str]:
    """Asynchronous version of :func:`omni.usd.get_context().save_as_stage_with_callback`. Return a ``(result, error)`` tuple. Where
    error string is empty if ``result`` is ``False``."""
    f = asyncio.Future()
    self.save_as_stage_with_callback(url, partial(on_layers_saved_result, future=f))
    return await f


async def _save_layers_async(self, new_root_layer_path: str, layer_identifiers: List[str]) -> Tuple[bool, str]:
    """Asynchronous version of :func:`omni.usd.get_context().save_layers_with_callback`. Return a ``(result, error)`` tuple. Where
    error string is empty if ``result`` is ``False``."""
    f = asyncio.Future()
    self.save_layers_with_callback(new_root_layer_path, layer_identifiers, partial(on_layers_saved_result, future=f))
    return await f


async def _export_as_stage_async(self, url: str) -> Tuple[bool, str]:
    """Asynchronous version of :func:`omni.usd.get_context().export_as_stage_with_callback`. Return a ``(result, error)`` tuple.
    Where error string is empty if ``result`` is ``False``."""
    f = asyncio.Future()
    self.export_as_stage_with_callback(url, partial(on_stage_result, future=f))
    return await f


async def _load_mdl_parameters_for_prim_async(self, prim):
    path = prim.GetPath().pathString
    stage_future = asyncio.Future()

    if self.add_to_pending_creating_mdl_paths(path, False):

        def on_stage(stage_event):
            if (
                stage_event.type == int(StageEventType.MDL_PARAM_LOADED)
                and stage_event.payload["prim_path"] == path
                and not stage_future.done()
            ):
                stage_future.set_result(True)

        stage_sub = self.get_stage_event_stream().create_subscription_to_pop(
            on_stage, name="load_mdl_parameters_for_prim"
        )
        return await stage_future


# Deprecated live interfaces
class StageLiveModeType:
    ALWAYS_ON = 0
    TOGGLE_ON = 1
    TOGGLE_OFF = 2


def __not_functional(func):
    def inner(*args, **kwargs):
        carb.log_warn(f"omni.usd.UsdContext.{func.__name__} IS DEPRECATED AND NOT FUNCTIONAL ANYMORE!!! Please update to omni.kit.usd.layers.LiveSyncing for new live interfaces.")
        return func(*args, **kwargs)

    return inner


@__not_functional
def _set_layer_live(self, identifier: str, live: bool):
    pass


@__not_functional
def _is_layer_live(self, identifier: str):
    return False


@__not_functional
def _set_stage_live(self, mode: StageLiveModeType):
    return


def _is_stage_live(self):
    carb.log_warn(f"omni.usd.UsdContext.is_stage_live is DEPRECATED. Please update to omni.kit.usd.layers.LiveSyncing for new live interface.")
    try:
        import omni.kit.usd.layers as layers
        return layers.get_live_syncing(self).is_stage_in_live_session()
    except Exception:
        pass

    return False


def _get_stage_live_mode(self):
    carb.log_warn(f"omni.usd.UsdContext.get_stage_live_mode is DEPRECATED. Please update to omni.kit.usd.layers.LiveSyncing for new live interface.")
    try:
        import omni.kit.usd.layers as layers
        live = layers.get_live_syncing(self).is_stage_in_live_session()
        if live:
            return StageLiveModeType.ALWAYS_ON
        else:
            return StageLiveModeType.TOGGLE_OFF
    except Exception:
        pass

    return StageLiveModeType.TOGGLE_OFF


@__not_functional
def _subscribe_to_live_mode_update_events(self, fn):
    return None


UsdContext.next_stage_event_async = _next_stage_event_async
UsdContext.selection_changed_async = _selection_changed_async
UsdContext.new_stage_async = _new_stage_async
UsdContext.open_stage_async = _open_stage_async
UsdContext.attach_stage_async = _attach_stage_async
UsdContext.reopen_stage_async = _reopen_stage_async
UsdContext.close_stage_async = _close_stage_async
UsdContext.save_stage_async = _save_stage_async
UsdContext.save_as_stage_async = _save_as_stage_async
UsdContext.save_layers_async = _save_layers_async
UsdContext.export_as_stage_async = _export_as_stage_async
UsdContext.load_mdl_parameters_for_prim_async = _load_mdl_parameters_for_prim_async

# Deprecated APIs
UsdContext.set_layer_live = _set_layer_live
UsdContext.is_layer_live = _is_layer_live
UsdContext.set_stage_live = _set_stage_live
UsdContext.is_stage_live = _is_stage_live
UsdContext.get_stage_live_mode = _get_stage_live_mode
UsdContext.subscribe_to_live_mode_update_events = _subscribe_to_live_mode_update_events

# Patch new_stage and new_stage_with_callback to support loadset param.
# This is only done in python currently without touching UsdContext in cpp
# for ABI safety.
UsdContext.new_stage = _new_stage_sync
UsdContext.new_stage_with_callback = _new_stage_python_wrapper
