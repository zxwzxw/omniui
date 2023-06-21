from ._stageupdate import *

# Cached editor instance pointer
def get_stage_update_interface() -> IStageUpdate:
    """Returns cached :class:`omni.usd.IStageUpdate` interface"""

    if not hasattr(get_stage_update_interface, "iface"):
        get_stage_update_interface.iface = acquire_stage_update_interface()
    return get_stage_update_interface.iface
