"""
WARNING: The following interfaces are for legacy ones, which will be removed later.
"""

import carb
import omni.usd
import weakref

from pxr import Sdf, Usd
from typing import Callable, List


class LayerEditMode:
    NORMAL = 0
    AUTO_AUTHORING = 1
    SPEC_LINKING = 2


class SublayerChangeType:
    ADD = 0
    REMOVE = 1
    OFFSET = 2


class Layers:
    def __init__(self, usd_context) -> None:
        self._usd_context = usd_context
    
    def destroy(self):
        self._usd_context = None

    def __get_layers_interface(self):
        carb.log_warn(f"omni.usd.Layers is DEPRECATED. Please update to omni.kit.usd.layers for new layers interface.")
        try:
            import omni.kit.usd.layers as layers
            layers_interface = layers.get_layers(self._usd_context)
        except:
            layers_interface = None
        
        return layers_interface
    
    def __to_layers_edit_mode(self, edit_mode: LayerEditMode):
        try:
            import omni.kit.usd.layers as layers
            if edit_mode == LayerEditMode.NORMAL:
                return layers.LayerEditMode.NORMAL
            elif edit_mode == LayerEditMode.AUTO_AUTHORING:
                return layers.LayerEditMode.AUTO_AUTHORING
            elif edit_mode == LayerEditMode.SPEC_LINKING:
                return layers.LayerEditMode.SPECS_LINKING
        except:
            pass
        
        return None
    
    def __to_omni_usd_edit_mode(self, edit_mode):
        try:
            import omni.kit.usd.layers as layers
            if edit_mode == layers.LayerEditMode.NORMAL:
                return LayerEditMode.NORMAL
            elif edit_mode == layers.LayerEditMode.AUTO_AUTHORING:
                return LayerEditMode.AUTO_AUTHORING
            elif edit_mode == layers.LayerEditMode.SPECS_LINKING:
                return LayerEditMode.SPEC_LINKING
        except:
            pass
        
        return LayerEditMode.NORMAL
    
    def get_layer_name(self, layer_identifier: bool):
        layers = self.__get_layers_interface()
        if layers: 
            name = layers.get_layers_state().get_layer_name(layer_identifier)
        else:
            name = None
        
        if not name:
            name = Sdf.Layer.GetDisplayNameFromIdentifier(layer_identifier)
        
        return name
    
    def set_layer_muteness_scope(self, global_scope: bool):
        layers = self.__get_layers_interface()
        if layers: 
            layers.get_layers_state().set_muteness_scope(global_scope)
    
    def is_layer_muteness_global(self):
        layers = self.__get_layers_interface()
        if layers: 
            return layers.get_layers_state().is_muteness_global()
        
        return False
    
    def is_layer_locally_muted(self, layer_identifier: str):
        layers = self.__get_layers_interface()
        if layers: 
            return layers.get_layers_state().is_layer_locally_muted(layer_identifier)
        
        return False
    
    def is_layer_globally_muted(self, layer_identifier: str):
        layers = self.__get_layers_interface()
        if layers: 
            return layers.get_layers_state().is_layer_globally_muted(layer_identifier)
        
        return False
    
    def set_layer_edit_mode(self, edit_mode: LayerEditMode):
        layers = self.__get_layers_interface()
        if layers:
            layers_edit_mode = self.__to_layers_edit_mode(edit_mode)
            layers.set_edit_mode(layers_edit_mode)

    def get_layer_edit_mode(self):
        layers = self.__get_layers_interface()
        if layers:
            layers_edit_mode = layers.get_edit_mode() 
            return self.__to_omni_usd_edit_mode(layers_edit_mode)
        
        return LayerEditMode.NORMAL
    
    def is_layer_locked(self, layer_identifier: str):
        layers = self.__get_layers_interface()
        if layers: 
            return layers.get_layers_state().is_layer_locked(layer_identifier)
        
        return False
    
    def is_layer_locked_by_other(self, layer_identifier: str):
        return False
    
    def set_layer_lock_state(self, layer_identifier: str, locked: bool):
        layers = self.__get_layers_interface()
        if layers: 
            layers.get_layers_state().set_layer_lock_state(layer_identifier, locked)
        
    def get_layer_lock_user_name(self, layer_identifier):
        return ""
    
    def is_layer_writable(self, layer_identifier: str):
        layers = self.__get_layers_interface()
        if layers: 
            return layers.get_layers_state().is_layer_writable(layer_identifier)
        
        return True
    
    def is_layer_savable(self, layer_identifier: str):
        layers = self.__get_layers_interface()
        if layers: 
            return layers.get_layers_state().is_layer_savable(layer_identifier)
        
        return True
    
    def get_used_sublayers(self):
        layers = self.__get_layers_interface()
        if layers: 
            return layers.get_layers_state().get_local_layer_identifiers(False, True, False)
        
        return omni.usd.get_all_sublayers(self._usd_context.get_stage())

    def get_dirty_sublayers(self):
        layers = self.__get_layers_interface()
        if layers: 
            return layers.get_layers_state().get_dirty_layer_identifiers()
        
        return omni.usd.get_dirty_layers(self._usd_context.get_stage(), True)

    def set_default_edit_layer_identifier(self, layer_identifier: str):
        layers = self.__get_layers_interface()
        if layers: 
            layers.get_auto_authoring().set_default_layer(layer_identifier)

    def get_default_edit_layer_identifier(self):
        layers = self.__get_layers_interface()
        if layers: 
            return layers.get_auto_authoring().get_default_layer()
        
        return ""
    
    def is_auto_authoring_layer(self, layer_identifier: str):
        layers = self.__get_layers_interface()
        if layers: 
            return layers.get_auto_authoring().is_auto_authoring_layer(layer_identifier)

        return False

    def merge_prim_spec(self, target_layer_identifier: str, src_layer_identifier: str, prim_path: str, dst_is_stronger_than_src: bool):
        carb.log_warn(f"omni.usd.Layers.merge_prim_spec is DEPRECATED. Please use omni.usd.merge_prim_spec instead.")
        omni.usd.merge_prim_spec(target_layer_identifier, src_layer_identifier, prim_path, dst_is_stronger_than_src)
    
    def merge_layers(self, target_layer_identifier: str, src_layer_identifier: str, dst_is_stronger_than_src: bool):
        carb.log_warn(f"omni.usd.Layers.merge_layers is DEPRECATED. Please use omni.usd.merge_layers instead.")
        omni.usd.merge_layers(target_layer_identifier, src_layer_identifier, dst_is_stronger_than_src)

    def __not_functional(func):
        def inner(*args, **kwargs):
            carb.log_warn(f"omni.usd.Layers.{func.__name__} IS DEPRECATED AND NOT FUNCTIONAL ANYMORE!!! Please update to omni.kit.usd.layers for new layers interface.")
            return func(*args, **kwargs)

        return inner

    @__not_functional
    def subscribe_to_default_edit_layer_events(self, callback):
        return

    @__not_functional
    def subscribe_to_lock_events(self, callback):
        return None

    @__not_functional
    def subscribe_to_layer_muteness_events(self, callback):
        return None

    @__not_functional
    def subscribe_to_layer_muteness_scope_events(self, callback):
        return None

    @__not_functional
    def subscribe_to_layer_metadata_events(self, callback):
        return None

    @__not_functional
    def subscribe_to_layer_edit_mode_events(self, callback):
        return None

    @__not_functional
    def subscribe_to_sublayer_events(self, callback):
        return None

    @__not_functional
    def subscribe_to_prim_spec_events(self, callback):
        return None


def _get_layers(usd_context):
    return Layers(usd_context)


def active_authoring_layer_context(usd_context):
    carb.log_warn("omni.usd.active_authoring_layer_context is DEPRECATED, please switch to omni.kit.usd.layers.active_authoring_layer_context")
    try:
        import omni.kit.usd.layers as layers
        return layers.active_authoring_layer_context(usd_context)
    except:
        pass

    stage = usd_context.get_stage()
    edit_target = stage.GetEditTarget()
    return Usd.EditContext(stage, edit_target.GetLayer())


def is_layer_globally_muted(usd_context, layer_identifier: str) -> bool:
    carb.log_warn(f"omni.usd.is_layer_globally_muted is DEPRECATED. Please update to omni.kit.usd.layers for new layers interface.")
    try:
        import omni.kit.usd.layers as layers
        layers_interface = layers.get_layers(usd_context)
    except:
        layers_interface = None
    
    if layers_interface:
        return layers_interface.get_layers_state().is_layer_globally_muted(layer_identifier)
    
    return False


async def reload_layer_async(layer_identifier: str):
    layer = Sdf.Find(layer_identifier)
    if not layer:
        return

    layer.Reload()



