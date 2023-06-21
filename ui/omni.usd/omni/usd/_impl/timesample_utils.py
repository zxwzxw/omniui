import typing
import omni.usd
from enum import Enum
from pxr import Usd, Tf, Sdf, Gf, UsdShade, UsdGeom, UsdLux


class Value_On_Layer(Enum):
    No_Value = 0
    ON_CURRENT_LAYER = 0
    ON_STRONGER_LAYER = 1
    ON_WEAKER_LAYER = 2


def get_frame_time_code(time, fps):
    if fps <= 0:
        fps = 24
    return round(time * fps)


def get_frame_time(time_code, fps):
    if fps <= 0:
        fps = 24
    return round(time_code) / fps


def attr_has_timesample_on_key(attr: Usd.Attribute, time_code: Usd.TimeCode):
    if time_code.IsDefault() or not attr:
        return False
    time_samples = attr.GetTimeSamples()
    time_code_value = time_code.GetValue()
    if round(time_code_value) != time_code_value:
        log_warn(f"Error: TimeSample Value {time_code_value} should be without decimal part.")
        return False
    return time_code_value in time_samples


def get_attribute_effective_timesample_layer_info(stage, attr: Usd.Attribute):
    if attr.GetNumTimeSamples() == 0:
        return Value_On_Layer.No_Value, None
    attr_layers = attr.GetResolveInfo().GetNode().layerStack.layers
    authoring_layer = stage.GetEditTarget().GetLayer()
    isOnStrongerLayer = True
    for layer in attr_layers:
        attr_spec = layer.GetAttributeAtPath(attr.GetPath())
        if attr_spec and len(attr_spec.GetInfo("timeSamples")) > 0:
            if layer == authoring_layer:
                return Value_On_Layer.ON_CURRENT_LAYER, layer
            elif isOnStrongerLayer:
                return Value_On_Layer.ON_STRONGER_LAYER, layer
            else:
                return Value_On_Layer.ON_WEAKER_LAYER, layer
        else:  # no attrSpec or no timesample
            if layer == authoring_layer:
                isOnStrongerLayer = False

    return Value_On_Layer.No_Value, None


def get_attribute_effective_defaultvalue_layer_info(stage, attr: Usd.Attribute):
    # if an attribute doesn't have any authoring value, GetNode() assert out
    # guard it with this HasAuthoredValue() to prevent from crashing
    if not attr or not attr.HasAuthoredValue():
        return Value_On_Layer.No_Value, None
    attr_layers = attr.GetResolveInfo().GetNode().layerStack.layers
    authoring_layer = stage.GetEditTarget().GetLayer()
    isOnStrongerLayer = True
    for layer in attr_layers:
        attr_spec = layer.GetAttributeAtPath(attr.GetPath())
        if attr_spec and attr_spec.GetInfo("default"):
            if layer == authoring_layer:
                return Value_On_Layer.ON_CURRENT_LAYER, layer
            elif isOnStrongerLayer:
                return Value_On_Layer.ON_STRONGER_LAYER, layer
            else:
                return Value_On_Layer.ON_WEAKER_LAYER, layer
        else:  # no attrSpec or no timesample
            if layer == authoring_layer:
                isOnStrongerLayer = False

    return Value_On_Layer.No_Value, None


def copy_timesamples_from_weaker_layer(stage, attr: Usd.Attribute):
    layer_info, layer = get_attribute_effective_timesample_layer_info(stage, attr)
    if layer_info == Value_On_Layer.ON_WEAKER_LAYER:
        time_samples = attr.GetMetadata("timeSamples")
        for key, value in time_samples.items():
            attr.Set(value, key)


def get_timesamples_count_in_authoring_layer(stage, attr_path: Sdf.Path):
    authoring_layer = stage.GetEditTarget().GetLayer()
    if authoring_layer == stage.GetSessionLayer():
        return 0
    attr_spec = authoring_layer.GetAttributeAtPath(attr_path) if authoring_layer else None
    new_key_count = len(attr_spec.GetInfo("timeSamples")) if attr_spec else 0
    return new_key_count
