from enum import Enum
from functools import lru_cache
import typing
import carb
import omni.kit.app


from pxr import Usd, Tf, Sdf, Gf, Trace


class EventType(Enum):
    CHANGE_INFO_ONLY = 0
    RESYNC = 1


class EventDispatcher:
    def __init__(self):
        self._path_to_callbacks = {}
        self._dispatch_set = set()

    def subscribe_on_change(self, path, on_change: typing.Callable) -> carb.Subscription:
        key = Sdf.Path(path)
        callbacks = self._path_to_callbacks.setdefault(key, set())
        callbacks.add(on_change)

        def unsub_fn():
            callbacks.discard(on_change)

        return carb.Subscription(unsub_fn)

    def on_changes(self, paths):
        self._dispatch_set.update(paths)

    def pump(self):
        for path in self._dispatch_set:
            self._dispatch_changed(path)
        self._dispatch_set.clear()

    def _send_callbacks(self, cb_path, changed_path):
        if cb_path in self._path_to_callbacks:
            cb = self._path_to_callbacks[cb_path]
            for f in cb:
                f(changed_path)

    def _dispatch_changed(self, path):
        # Send callback for property path. Notify the property path subscription.
        self._send_callbacks(cb_path=path, changed_path=path)

        prim_path = path.GetPrimPath()
        if prim_path != path:
            # Send callback for property's prim path. Notify the prim path subscription for any property change.
            # Still pass 'path' not 'prim_path' as changed_path here
            self._send_callbacks(cb_path=prim_path, changed_path=path)


class UsdWatcher:
    def __init__(self):
        self._update_sub = (
            omni.kit.app.get_app_interface()
            .get_update_event_stream()
            .create_subscription_to_pop(lambda evt: self._pump(), name="[ext: omni.usd] UsdWatcher")
        )
        self._change_info_only_dispatcher = EventDispatcher()
        self._resync_dispatcher = EventDispatcher()
        self._objects_changed = Tf.Notice.Register(Usd.Notice.ObjectsChanged, self._on_prim_change, None)

    def destroy(self):
        self._update_sub = None

    @Trace.TraceFunction
    def _on_prim_change(self, notice, stage):
        self._get_dispatcher(EventType.RESYNC).on_changes(notice.GetResyncedPaths())
        self._get_dispatcher(EventType.CHANGE_INFO_ONLY).on_changes(notice.GetChangedInfoOnlyPaths())

    def subscribe_to_resync_path(self, path, on_change: typing.Callable) -> carb.Subscription:
        return self._get_dispatcher(EventType.RESYNC).subscribe_on_change(path, on_change)

    def subscribe_to_change_info_path(self, path, on_change: typing.Callable) -> carb.Subscription:
        return self._get_dispatcher(EventType.CHANGE_INFO_ONLY).subscribe_on_change(path, on_change)

    def _pump(self):
        for t in EventType:
            self._get_dispatcher(t).pump()

    def _get_dispatcher(self, event_type: EventType):
        if event_type == EventType.RESYNC:
            return self._resync_dispatcher
        else:
            return self._change_info_only_dispatcher


# USD Prim Watcher singleton getter
@lru_cache()
def get_watcher():
    return UsdWatcher()
