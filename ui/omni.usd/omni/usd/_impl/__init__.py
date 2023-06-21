from .._usd import *
from .api import *
from .utils import *
from .layer_utils import *
from .timesample_utils import *
from .watcher import UsdWatcher, get_watcher
from .transform_helper import TransformHelper
from .layer_legacy import LayerEditMode, SublayerChangeType, Layers
from .layer_legacy import  _get_layers, reload_layer_async, is_layer_globally_muted, active_authoring_layer_context

import carb.events
import asyncio
import carb
import omni.ext
import omni.kit.app

# omni.usd.editor
from . import editor

stage_event_sub = None

# Watcher is singleton. Call destroy explicitly to clean up subscriptions.
class UsdExtension(omni.ext.IExt):
    # from kit/source/python/extensions-bundled/omni/kit/builtin/init.py
    @staticmethod
    async def init_stage_event(fast_mode: int, settings: carb.settings.ISettings):
        import omni.kit.app

        def clear_history():
            import omni.kit.undo

            omni.kit.undo.clear_history()
            omni.kit.undo.clear_stack()

        def on_stage_event(event):
            if event.type == int(omni.usd.StageEventType.OPENED) or event.type == int(omni.usd.StageEventType.CLOSING):
                clear_history()

        await omni.kit.app.get_app().next_update_async()

        global stage_event_sub
        stage_event_sub = (
            omni.usd.get_context()
            .get_stage_event_stream()
            .create_subscription_to_pop(on_stage_event, name="init stage event")
        )

        if omni.usd.get_context().get_stage():
            clear_history()

        if fast_mode:
            return

        if settings.get("/app/content/emptyStageOnStart"):
            if omni.usd.get_context().get_stage_state() == omni.usd.StageState.CLOSED:
                extensions = [ext["id"] for ext in omni.kit.app.get_app().get_extension_manager().get_extensions() if ext["enabled"]]
                if any(item.startswith("omni.kit.stage_templates") for item in extensions):
                    import omni.kit.stage_templates

                    omni.kit.stage_templates.new_stage(template=None)
                else:
                    omni.usd.get_context().new_stage()


    def on_startup(self):
        # delay init_stage_event as it shouldn't trigger before tests and around "app started"
        settings = carb.settings.get_settings()
        fast_mode = settings.get("/app/startup/fast/mode")
        if fast_mode:
            omni.usd.create_context()
            omni.usd.get_context().new_stage()

        asyncio.ensure_future(UsdExtension.init_stage_event(fast_mode, settings))

    def on_shutdown(self):
        global stage_event_sub
        stage_event_sub = None

        get_watcher().destroy()

        omni.usd.shutdown_usd()


def _get_stage(self):
    """Returns current :class:`pxr.Usd.Stage`"""

    # This function connects `omni.usd.UsdContext` pybind11 python bindings with Pixar's Usd bindings.
    # The UsdStage object is stored by C++ code inside of Usd Utils cache under some id.
    # We get the id from `omni.usd.UsdContext` interface and use it to retrieve UsdStage from Usd Utils.
    from pxr import Usd, UsdUtils

    id = self.get_stage_id()
    cache = UsdUtils.StageCache.Get()
    return cache.Find(Usd.StageCache.Id.FromLongInt(id))


async def _next_frame_async(self, inViewportId=0) -> None:
    """Wait for frame complete event from Kit for specific viewport. """
    import omni.kit.app
    order = omni.kit.app.EVENT_ORDER_DEFAULT

    f = asyncio.Future()

    def on_event(e: carb.events.IEvent):
        viewId = e.payload["viewport_handle"]
        if viewId == inViewportId and not f.done():
            f.set_result(None)

    sub = self.get_rendering_event_stream().create_subscription_to_push_by_type(
        int(omni.usd.StageRenderingEventType.NEW_FRAME),
        on_event, name="omni.usd._next_frame_async", order=order
    )
    return await f

UsdContext.next_usd_async = _next_frame_async
UsdContext.next_frame_async = _next_frame_async

UsdContext.get_stage = _get_stage

UsdContext.get_layers = _get_layers
