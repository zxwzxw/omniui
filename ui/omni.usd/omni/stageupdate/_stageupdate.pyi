import omni.stageupdate._stageupdate
import typing
import carb._carb

__all__ = [
    "IStageUpdate",
    "StageUpdateNode",
    "acquire_stage_update_interface"
]


class IStageUpdate():
    def create_stage_update_node(self, display_name: str, on_attach_fn: typing.Callable[[int, float], None] = None, on_detach_fn: typing.Callable[[], None] = None, on_update_fn: typing.Callable[[float, float], None] = None, on_prim_add_fn: typing.Callable[[str], None] = None, on_prim_or_property_change_fn: typing.Callable[[str], None] = None, on_prim_remove_fn: typing.Callable[[str], None] = None, on_raycast_fn: typing.Callable[[carb._carb.Float3, carb._carb.Float3, bool], None] = None) -> StageUpdateNode: ...
    def get_stage_update_nodes(self) -> tuple: ...
    def set_stage_update_node_enabled(self, index: int, enabled: bool) -> None: 
        """
                    Toggle Simulation Node enable/disable.

                    Args:
                        index (int): Simulation Node index in tuple, returned by `get_stage_update_nodes`.
                        enabled(bool): Enable/disable toggle. 
                    
        """
    def set_stage_update_node_order(self, index: int, enabled: int) -> None: 
        """
                    Change Simulation Node order.

                    Args:
                        index (int): Simulation Node index in tuple, returned by `get_stage_update_nodes`.
                        order(int): Order to sort on. 
                    
        """
    def subscribe_to_stage_update_node_change_events(self, fn: typing.Callable[[], None]) -> carb._carb.Subscription: 
        """
                    Subscribes to Simulation Node(s) change events.

                    Event is triggered when nodes are added, removed, toggled.

                    See :class:`.Subscription` for more information on subscribing mechanism.

                    Args:
                        fn: The callback to be called on change.

                    Returns:
                        The subscription holder.
        """
    pass
class StageUpdateNode():
    pass
def acquire_stage_update_interface(plugin_name: str = None, library_path: str = None) -> IStageUpdate:
    pass
