"""pybind11 omni.usd bindings"""
import omni.usd._usd
import typing
import UsdContextInitialLoadSet
import carb._carb
import carb.events._events

__all__ = [
    "AudioManager",
    "PickingMode",
    "Selection",
    "StageEventType",
    "StageRenderingEventType",
    "StageState",
    "UsdContext",
    "UsdContextInitialLoadSet",
    "WRITABLE_USD_FILE_EXTS_STR",
    "add_hydra_engine",
    "attach_all_hydra_engines",
    "create_context",
    "destroy_context",
    "get_context",
    "get_context_from_stage_id",
    "merge_layers",
    "merge_prim_spec",
    "release_all_hydra_engines",
    "resolve_paths",
    "resolve_prim_path_references",
    "shutdown_usd"
]


class AudioManager():
    pass
class PickingMode():
    """
    Members:

      NONE

      RESET_AND_SELECT

      MERGE_SELECTION

      INVERT_SELECTION

      TRACK
    """
    def __init__(self, arg0: int) -> None: ...
    def __int__(self) -> int: ...
    @property
    def name(self) -> str:
        """
        (self: handle) -> str

        :type: str
        """
    INVERT_SELECTION: omni.usd._usd.PickingMode # value = PickingMode.INVERT_SELECTION
    MERGE_SELECTION: omni.usd._usd.PickingMode # value = PickingMode.MERGE_SELECTION
    NONE: omni.usd._usd.PickingMode # value = PickingMode.NONE
    RESET_AND_SELECT: omni.usd._usd.PickingMode # value = PickingMode.RESET_AND_SELECT
    TRACK: omni.usd._usd.PickingMode # value = PickingMode.TRACK
    __members__: dict # value = {'NONE': PickingMode.NONE, 'RESET_AND_SELECT': PickingMode.RESET_AND_SELECT, 'MERGE_SELECTION': PickingMode.MERGE_SELECTION, 'INVERT_SELECTION': PickingMode.INVERT_SELECTION, 'TRACK': PickingMode.TRACK}
    pass
class Selection():
    def clear_selected_prim_paths(self) -> bool: ...
    def get_selected_prim_paths(self) -> typing.List[str]: ...
    def is_prim_path_selected(self, arg0: str) -> bool: ...
    def select_all_prims(self, type_names: object = None) -> None: 
        """
        Select all prims with specific types.
        """
    def select_inverted_prims(self) -> None: ...
    def set_prim_path_selected(self, arg0: str, arg1: bool, arg2: bool, arg3: bool, arg4: bool) -> bool: ...
    def set_selected_prim_paths(self, arg0: typing.List[str], arg1: bool) -> bool: ...
    pass
class StageEventType():
    """
            Stage operation results.
            

    Members:

      SAVED

      SAVE_FAILED

      OPENING

      OPENED

      OPEN_FAILED

      CLOSING

      CLOSED

      SELECTION_CHANGED

      ASSETS_LOADED

      ASSETS_LOAD_ABORTED

      GIZMO_TRACKING_CHANGED

      MDL_PARAM_LOADED

      SETTINGS_LOADED

      SETTINGS_SAVING

      OMNIGRAPH_START_PLAY

      OMNIGRAPH_STOP_PLAY

      SIMULATION_START_PLAY

      SIMULATION_STOP_PLAY

      ANIMATION_START_PLAY

      ANIMATION_STOP_PLAY

      DIRTY_STATE_CHANGED

      ASSETS_LOADING

      HYDRA_GEOSTREAMING_STARTED

      HYDRA_GEOSTREAMING_STOPPED

      HYDRA_GEOSTREAMING_STOPPED_NOT_ENOUGH_MEM

      HYDRA_GEOSTREAMING_STOPPED_AT_LIMIT
    """
    def __init__(self, arg0: int) -> None: ...
    def __int__(self) -> int: ...
    @property
    def name(self) -> str:
        """
        (self: handle) -> str

        :type: str
        """
    ANIMATION_START_PLAY: omni.usd._usd.StageEventType # value = StageEventType.ANIMATION_START_PLAY
    ANIMATION_STOP_PLAY: omni.usd._usd.StageEventType # value = StageEventType.ANIMATION_STOP_PLAY
    ASSETS_LOADED: omni.usd._usd.StageEventType # value = StageEventType.ASSETS_LOADED
    ASSETS_LOADING: omni.usd._usd.StageEventType # value = StageEventType.ASSETS_LOADING
    ASSETS_LOAD_ABORTED: omni.usd._usd.StageEventType # value = StageEventType.ASSETS_LOAD_ABORTED
    CLOSED: omni.usd._usd.StageEventType # value = StageEventType.CLOSED
    CLOSING: omni.usd._usd.StageEventType # value = StageEventType.CLOSING
    DIRTY_STATE_CHANGED: omni.usd._usd.StageEventType # value = StageEventType.DIRTY_STATE_CHANGED
    GIZMO_TRACKING_CHANGED: omni.usd._usd.StageEventType # value = StageEventType.GIZMO_TRACKING_CHANGED
    HYDRA_GEOSTREAMING_STARTED: omni.usd._usd.StageEventType # value = StageEventType.HYDRA_GEOSTREAMING_STARTED
    HYDRA_GEOSTREAMING_STOPPED: omni.usd._usd.StageEventType # value = StageEventType.HYDRA_GEOSTREAMING_STOPPED
    HYDRA_GEOSTREAMING_STOPPED_AT_LIMIT: omni.usd._usd.StageEventType # value = StageEventType.HYDRA_GEOSTREAMING_STOPPED_AT_LIMIT
    HYDRA_GEOSTREAMING_STOPPED_NOT_ENOUGH_MEM: omni.usd._usd.StageEventType # value = StageEventType.HYDRA_GEOSTREAMING_STOPPED_NOT_ENOUGH_MEM
    MDL_PARAM_LOADED: omni.usd._usd.StageEventType # value = StageEventType.MDL_PARAM_LOADED
    OMNIGRAPH_START_PLAY: omni.usd._usd.StageEventType # value = StageEventType.OMNIGRAPH_START_PLAY
    OMNIGRAPH_STOP_PLAY: omni.usd._usd.StageEventType # value = StageEventType.OMNIGRAPH_STOP_PLAY
    OPENED: omni.usd._usd.StageEventType # value = StageEventType.OPENED
    OPENING: omni.usd._usd.StageEventType # value = StageEventType.OPENING
    OPEN_FAILED: omni.usd._usd.StageEventType # value = StageEventType.OPEN_FAILED
    SAVED: omni.usd._usd.StageEventType # value = StageEventType.SAVED
    SAVE_FAILED: omni.usd._usd.StageEventType # value = StageEventType.SAVE_FAILED
    SELECTION_CHANGED: omni.usd._usd.StageEventType # value = StageEventType.SELECTION_CHANGED
    SETTINGS_LOADED: omni.usd._usd.StageEventType # value = StageEventType.SETTINGS_LOADED
    SETTINGS_SAVING: omni.usd._usd.StageEventType # value = StageEventType.SETTINGS_SAVING
    SIMULATION_START_PLAY: omni.usd._usd.StageEventType # value = StageEventType.SIMULATION_START_PLAY
    SIMULATION_STOP_PLAY: omni.usd._usd.StageEventType # value = StageEventType.SIMULATION_STOP_PLAY
    __members__: dict # value = {'SAVED': StageEventType.SAVED, 'SAVE_FAILED': StageEventType.SAVE_FAILED, 'OPENING': StageEventType.OPENING, 'OPENED': StageEventType.OPENED, 'OPEN_FAILED': StageEventType.OPEN_FAILED, 'CLOSING': StageEventType.CLOSING, 'CLOSED': StageEventType.CLOSED, 'SELECTION_CHANGED': StageEventType.SELECTION_CHANGED, 'ASSETS_LOADED': StageEventType.ASSETS_LOADED, 'ASSETS_LOAD_ABORTED': StageEventType.ASSETS_LOAD_ABORTED, 'GIZMO_TRACKING_CHANGED': StageEventType.GIZMO_TRACKING_CHANGED, 'MDL_PARAM_LOADED': StageEventType.MDL_PARAM_LOADED, 'SETTINGS_LOADED': StageEventType.SETTINGS_LOADED, 'SETTINGS_SAVING': StageEventType.SETTINGS_SAVING, 'OMNIGRAPH_START_PLAY': StageEventType.OMNIGRAPH_START_PLAY, 'OMNIGRAPH_STOP_PLAY': StageEventType.OMNIGRAPH_STOP_PLAY, 'SIMULATION_START_PLAY': StageEventType.SIMULATION_START_PLAY, 'SIMULATION_STOP_PLAY': StageEventType.SIMULATION_STOP_PLAY, 'ANIMATION_START_PLAY': StageEventType.ANIMATION_START_PLAY, 'ANIMATION_STOP_PLAY': StageEventType.ANIMATION_STOP_PLAY, 'DIRTY_STATE_CHANGED': StageEventType.DIRTY_STATE_CHANGED, 'ASSETS_LOADING': StageEventType.ASSETS_LOADING, 'HYDRA_GEOSTREAMING_STARTED': StageEventType.HYDRA_GEOSTREAMING_STARTED, 'HYDRA_GEOSTREAMING_STOPPED': StageEventType.HYDRA_GEOSTREAMING_STOPPED, 'HYDRA_GEOSTREAMING_STOPPED_NOT_ENOUGH_MEM': StageEventType.HYDRA_GEOSTREAMING_STOPPED_NOT_ENOUGH_MEM, 'HYDRA_GEOSTREAMING_STOPPED_AT_LIMIT': StageEventType.HYDRA_GEOSTREAMING_STOPPED_AT_LIMIT}
    pass
class StageRenderingEventType():
    """
            Rendering Events.
            

    Members:

      NEW_FRAME
    """
    def __init__(self, arg0: int) -> None: ...
    def __int__(self) -> int: ...
    @property
    def name(self) -> str:
        """
        (self: handle) -> str

        :type: str
        """
    NEW_FRAME: omni.usd._usd.StageRenderingEventType # value = StageRenderingEventType.NEW_FRAME
    __members__: dict # value = {'NEW_FRAME': StageRenderingEventType.NEW_FRAME}
    pass
class StageState():
    """
            Stage states.
            

    Members:

      CLOSED

      CLOSING

      OPENING

      OPENED
    """
    def __init__(self, arg0: int) -> None: ...
    def __int__(self) -> int: ...
    @property
    def name(self) -> str:
        """
        (self: handle) -> str

        :type: str
        """
    CLOSED: omni.usd._usd.StageState # value = StageState.CLOSED
    CLOSING: omni.usd._usd.StageState # value = StageState.CLOSING
    OPENED: omni.usd._usd.StageState # value = StageState.OPENED
    OPENING: omni.usd._usd.StageState # value = StageState.OPENING
    __members__: dict # value = {'CLOSED': StageState.CLOSED, 'CLOSING': StageState.CLOSING, 'OPENING': StageState.OPENING, 'OPENED': StageState.OPENED}
    pass
class UsdContext():
    def add_to_pending_creating_mdl_paths(self, path: str = '', recreate: bool = False, loadInputs: bool = True) -> bool: ...
    def attach_stage_with_callback(self, stage_id: int, on_finish_fn: typing.Callable[[bool, str], None] = None) -> bool: ...
    def can_close_stage(self) -> bool: ...
    def can_open_stage(self) -> bool: ...
    def can_save_stage(self) -> bool: ...
    def close_stage(self, on_finish_fn: typing.Callable[[bool, str], None] = None) -> bool: ...
    def close_stage_with_callback(self, on_finish_fn: typing.Callable[[bool, str], None]) -> bool: ...
    def compute_path_world_bounding_box(self, arg0: str) -> typing.Tuple[carb._carb.Double3, carb._carb.Double3]: ...
    def compute_path_world_transform(self, arg0: str) -> typing.List[float[16]]: ...
    def disable_save_to_recent_files(self) -> None: ...
    def enable_save_to_recent_files(self) -> None: ...
    def export_as_stage(self, url: str, on_finish_fn: typing.Callable[[bool, str], None] = None) -> bool: 
        """
        Export stage with all prims flattened, and it will include contents from session layer also.
        """
    def export_as_stage_with_callback(self, url: str, on_finish_fn: typing.Callable[[bool, str], None]) -> bool: ...
    def get_attached_hydra_engine_names(self) -> typing.List[str]: ...
    def get_rendering_event_stream(self) -> carb.events._events.IEventStream: ...
    @staticmethod
    def get_selection(*args, **kwargs) -> typing.Any: ...
    def get_stage_audio_manager(self) -> AudioManager: ...
    def get_stage_event_stream(self) -> carb.events._events.IEventStream: ...
    def get_stage_id(self) -> int: ...
    def get_stage_loading_status(self) -> typing.Tuple[str, int, int]: ...
    def get_stage_state(self) -> StageState: ...
    def get_stage_url(self) -> str: ...
    def has_pending_edit(self) -> bool: ...
    def is_new_stage(self) -> bool: ...
    def is_omni_stage(self) -> bool: ...
    def is_writable(self) -> bool: ...
    def load_render_settings_from_stage(self, arg0: int) -> None: ...
    def open_stage(self, url: str, on_finish_fn: typing.Callable[[bool, str], None] = None, load_set: UsdContextInitialLoadSet = UsdContextInitialLoadSet.LOAD_ALL) -> bool: ...
    def open_stage_with_callback(self, url: str, on_finish_fn: typing.Callable[[bool, str], None], load_set: UsdContextInitialLoadSet = UsdContextInitialLoadSet.LOAD_ALL) -> bool: ...
    def register_selection_group(self) -> int: ...
    def remove_all_hydra_engines(self) -> None: ...
    def reopen_stage(self, on_finish_fn: typing.Callable[[bool, str], None] = None, load_set: UsdContextInitialLoadSet = UsdContextInitialLoadSet.LOAD_ALL) -> bool: ...
    def reopen_stage_with_callback(self, on_finish_fn: typing.Callable[[bool, str], None], load_set: UsdContextInitialLoadSet = UsdContextInitialLoadSet.LOAD_ALL) -> bool: ...
    def save_as_stage(self, url: str, on_finish_fn: typing.Callable[[bool, str, typing.List[str]], None] = None) -> bool: ...
    def save_as_stage_with_callback(self, url: str, on_finish_fn: typing.Callable[[bool, str, typing.List[str]], None]) -> bool: ...
    def save_layers(self, new_root_layer_path: str, layer_identifiers: typing.List[str], on_finish_fn: typing.Callable[[bool, str, typing.List[str]], None] = None) -> bool: ...
    def save_layers_with_callback(self, new_root_layer_path: str, layer_identifiers: typing.List[str], on_finish_fn: typing.Callable[[bool, str, typing.List[str]], None]) -> bool: ...
    def save_render_settings_to_current_stage(self) -> None: ...
    def save_stage(self, on_finish_fn: typing.Callable[[bool, str, typing.List[str]], None] = None) -> bool: ...
    def save_stage_with_callback(self, on_finish_fn: typing.Callable[[bool, str, typing.List[str]], None]) -> bool: ...
    def set_pending_edit(self, arg0: bool) -> None: ...
    def set_pickable(self, arg0: str, arg1: bool) -> None: ...
    def set_selection_group(self, groupId: int, path: str) -> None: ...
    def set_selection_group_outline_color(self, groupId: int, color: carb._carb.Float4) -> None: ...
    def set_selection_group_shade_color(self, groupId: int, color: carb._carb.Float4) -> None: ...
    pass
class UsdContextInitialLoadSet():
    """
            Specifies the initial set of prims to load when opening a UsdStage.
            

    Members:

      LOAD_ALL

      LOAD_NONE
    """
    def __init__(self, arg0: int) -> None: ...
    def __int__(self) -> int: ...
    @property
    def name(self) -> str:
        """
        (self: handle) -> str

        :type: str
        """
    LOAD_ALL: omni.usd._usd.UsdContextInitialLoadSet # value = UsdContextInitialLoadSet.LOAD_ALL
    LOAD_NONE: omni.usd._usd.UsdContextInitialLoadSet # value = UsdContextInitialLoadSet.LOAD_NONE
    __members__: dict # value = {'LOAD_ALL': UsdContextInitialLoadSet.LOAD_ALL, 'LOAD_NONE': UsdContextInitialLoadSet.LOAD_NONE}
    pass
def add_hydra_engine(name: str, context: UsdContext) -> None:
    pass
def attach_all_hydra_engines(context: UsdContext) -> None:
    pass
def create_context(name: str = '') -> UsdContext:
    pass
def destroy_context(name: str = '') -> bool:
    pass
def get_context(name: str = '') -> UsdContext:
    pass
def get_context_from_stage_id(stage_id: int) -> UsdContext:
    pass
def merge_layers(arg0: str, arg1: str, arg2: bool) -> None:
    pass
def merge_prim_spec(dst_layer_identifier: str, src_layer_identifier: str, prim_spec_path: str, dst_is_stronger_than_src: bool = True, target_prim_path: str = '') -> None:
    """
    Merge prim specs between layers.
    """
def release_all_hydra_engines(context: UsdContext = None) -> None:
    pass
def resolve_paths(src_layer_identifier: str, dst_layer_identifier: str, store_relative_path: bool = True, relative_to_src_layer: bool = False, copy_sublayer_offsets: bool = False) -> None:
    """
    Resolve external paths in dst layer against base layer specified by src_layer_identifier.
    """
def resolve_prim_path_references(layer: str, old_prim_path: str, new_prim_path: str) -> None:
    """
                Resolve all prim path reference to use new path. This is mainly used to remapping
                prim path reference after structure change of original prim.

                Args:
                    layer (Sdf.Layer): Layer to resolve.
                    old_prim_path (str): Old prim path.
                    new_prim_path (str): New prim path that all old prim path references will be replaced to.
            
    """
def shutdown_usd() -> None:
    pass
WRITABLE_USD_FILE_EXTS_STR = 'usd|usda|usdc|live'
