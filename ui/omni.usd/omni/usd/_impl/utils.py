import carb.profiler
import carb.settings
import typing
import asyncio
import functools
import re
import os
import asyncio
import carb
import omni.usd
from .._usd import WRITABLE_USD_FILE_EXTS_STR, get_context_from_stage_id
import weakref
from enum import Enum
from pxr import Usd, Tf, Sdf, Gf, UsdShade, UsdGeom, UsdLux, Trace, UsdUtils
from typing import Callable, Union, Tuple, List


_writable_usd_file_exts = tuple(WRITABLE_USD_FILE_EXTS_STR.split('|'))
_writable_usd_dotted_file_exts = tuple('.' + x for x in _writable_usd_file_exts)
_writable_usd_files_desc = 'USD Files ({})'.format(
    ';'.join('*' + x for x in _writable_usd_dotted_file_exts)
)
_writable_usd_re = re.compile(
    rf"^[^?]*\.({WRITABLE_USD_FILE_EXTS_STR})(\?.*)?$",
    re.IGNORECASE)


_readable_usd_file_exts_str = None
_readable_usd_file_exts = None
_readable_usd_dotted_file_exts = None
_readable_usd_files_desc = None
_readable_usd_re = None


# Note - the writableUsd* members are functions just for symmetry with the
#        readableUsd* members
def writable_usd_file_exts_str():
    return WRITABLE_USD_FILE_EXTS_STR


def writable_usd_file_exts():
    return _writable_usd_file_exts


def writable_usd_dotted_file_exts():
    return _writable_usd_dotted_file_exts


def writable_usd_files_desc():
    return _writable_usd_files_desc


def writable_usd_re():
    return _writable_usd_re


# These need to be functions so that querying of FileFormatRegistry is delayed -
# currently, it is baked on first use, so we want to give omniverse extensions
# a chance to load

def _bake_readable_usd_file_info():
    global _readable_usd_file_exts_str
    global _readable_usd_file_exts
    global _readable_usd_dotted_file_exts
    global _readable_usd_files_desc
    global _readable_usd_re

    if _readable_usd_file_exts is not None:
        return

    # restrict to file formats whose target is "usd", since that's what
    # Usd.Stage.IsSupportedFile uses
    _readable_usd_file_exts = tuple(
        ext for ext in Sdf.FileFormat.FindAllFileFormatExtensions()
        if Sdf.FileFormat.FindByExtension(ext, "usd"))
    _readable_usd_file_exts_str = '|'.join(_readable_usd_file_exts)
    _readable_usd_dotted_file_exts = tuple('.' + x for x in _readable_usd_file_exts)
    _readable_usd_files_desc = 'USD Readable Files ({})'.format(
        ';'.join('*' + x for x in _readable_usd_dotted_file_exts)
    )
    _readable_usd_re = re.compile(
        rf"^[^?]*\.({_readable_usd_file_exts_str})(\?.*)?$",
        re.IGNORECASE)


def readable_usd_file_exts_str():
    _bake_readable_usd_file_info()
    return _readable_usd_file_exts_str


def readable_usd_file_exts():
    _bake_readable_usd_file_info()
    return _readable_usd_file_exts


def readable_usd_dotted_file_exts():
    _bake_readable_usd_file_info()
    return _readable_usd_dotted_file_exts


def readable_usd_files_desc():
    _bake_readable_usd_file_info()
    return _readable_usd_files_desc


def readable_usd_re():
    _bake_readable_usd_file_info()
    return _readable_usd_re


def is_usd_writable_filetype(filepath: str) -> bool:
    if not filepath:
        return False

    return bool(writable_usd_re().match(filepath))


def is_usd_readable_filetype(filepath: str):
    if not filepath:
        return False

    url = omni.client.break_url(filepath)
    if not url or not url.path:
        return False

    return Usd.Stage.IsSupportedFile(url.path)


def __get_stage(usd_context_or_stage: Union[str, Usd.Stage] = ""):
    if isinstance(usd_context_or_stage, omni.usd.UsdContext):
        stage = usd_context_or_stage.GetStage()
    elif isinstance(usd_context_or_stage, Usd.Stage):
        stage = usd_context_or_stage
    else:
        if not usd_context_or_stage:
            usd_context_or_stage = ""
        stage = omni.usd.get_context(usd_context_or_stage).get_stage()
    
    return stage


def get_prim_at_path(path: Sdf.Path, usd_context_name: Union[str, Usd.Stage] = "") -> Usd.Prim:
    stage = __get_stage(usd_context_name)
    if stage:
        return stage.GetPrimAtPath(path.GetPrimPath())
    return None


def get_prop_at_path(path: Sdf.Path, usd_context_name: Union[str, Usd.Stage] = "") -> Usd.Property:
    prim = get_prim_at_path(path, usd_context_name)
    if prim:
        return prim.GetProperty(path.name)
    return None


@carb.profiler.profile
def find_spec_on_session_or_its_sublayers(
    stage: Usd.Stage, path: Sdf.Path, predicate: Callable[[Sdf.Spec], bool] = None
):
    def get_spec(layer: Sdf.Layer, path: Sdf.Path):
        spec = layer.GetObjectAtPath(path)
        if spec and (predicate is None or predicate(spec)):
            return spec
        
        return None

    session_layer = stage.GetSessionLayer()
    spec = get_spec(session_layer, path)
    if spec:
        return session_layer, spec

    # Iterating using index is MUCH faster than doing "for path in session_layer.subLayerPaths:"
    # 0.02ms vs 2ms!
    sub_layer_paths = session_layer.subLayerPaths
    for i in range(len(sub_layer_paths)):
        layer = Sdf.Layer.Find(sub_layer_paths[i])
        if layer:
            spec = get_spec(layer, path)
            if spec:
                return layer, spec

    return None, None


def set_prop_val(prop: Usd.Property, val: typing.Any, time_code=Usd.TimeCode.Default(), auto_target_layer: bool = True):
    stage = prop.GetStage()

    if auto_target_layer:
        # if the property exists on session layer, switch EditTarget to session layer instead
        session_layer, property_spec = find_spec_on_session_or_its_sublayers(stage, prop.GetPath())

        if property_spec:
            with Usd.EditContext(stage, session_layer):
                _set_prop_val(prop, val, time_code)
        else:
            new_target = stage.GetEditTargetForLocalLayer(stage.GetEditTarget().GetLayer())
            with Usd.EditContext(stage, new_target):
                _set_prop_val(prop, val, time_code)
    else:
        _set_prop_val(prop, val, time_code)


def set_attr_val(
    attr: Usd.Attribute, val: typing.Any, time_code=Usd.TimeCode.Default(), auto_target_layer: bool = True
):
    """
    `set_prop_val` is misnamed. It should be set_attr_val. But had to keep it for backward comp
    """
    set_prop_val(attr, val, time_code, auto_target_layer)


def clear_attr_val_at_time(attr: Usd.Attribute, time_code=Usd.TimeCode.Default(), auto_target_layer: bool = True):
    stage = attr.GetStage()

    if auto_target_layer:
        # if the property exists on session layer, switch EditTarget to session layer instead
        session_layer, attr_spec = find_spec_on_session_or_its_sublayers(stage, attr.GetPath())
        if attr_spec:
            with Usd.EditContext(stage, session_layer):
                attr.ClearAtTime(time_code)
        else:
            new_target = stage.GetEditTargetForLocalLayer(stage.GetEditTarget().GetLayer())
            with Usd.EditContext(stage, new_target):
                attr.ClearAtTime(time_code)
    else:
        attr.ClearAtTime(time_code)


def is_path_valid(path: Sdf.Path):
    return (
        bool(omni.usd.get_context().get_stage().GetPrimAtPath(path))
        if path.GetPrimPath() == path
        else bool(omni.usd.get_prop_at_path(path))
    )


@Trace.TraceFunction
def is_hidden_type(prim):
    while not prim.IsPseudoRoot():
        if prim.GetMetadata("hide_in_stage_window"):
            return True
        prim = prim.GetParent()
    return False


@Trace.TraceFunction
def is_child_type(prim, type):
    for child in prim.GetAllChildren():
        if child.IsA(type):
            return True
        if omni.usd.is_child_type(child, type):
            return True

    return False


@Trace.TraceFunction
def is_ancestor_prim_type(stage: Usd.Stage, prim_path: Sdf.Path, prim_type: Usd.SchemaBase):
    # are any parent prims in prim_path type prim_type?
    parent_path = prim_path.GetParentPath()
    while parent_path and parent_path != Sdf.Path.absoluteRootPath:
        parent_prim = stage.GetPrimAtPath(parent_path)
        if parent_prim and parent_prim.IsA(prim_type):
            return True
        parent_path = parent_path.GetParentPath()
    return False


def is_prim_material_supported(prim):
    if not prim:
        return False

    # DomeLights in the RTX Renderer support baking to texture.
    if prim.IsA(UsdLux.DomeLight):
        return True

    # don't allow materials on light/camera or materials
    if prim.IsA(UsdLux.Light) or prim.IsA(UsdGeom.Camera) or prim.IsA(UsdShade.Material):
        return False

    # only Imageable or Subset types
    return prim.IsA(UsdGeom.Gprim) or prim.IsA(UsdGeom.Xform) or prim.IsA(UsdGeom.Subset)


def can_prim_have_children(stage: Usd.Stage, new_path: Sdf.Path, prim: Usd.Prim):
    # if prim is UsdGeom.Gprim and any parent prims are also UsdGeom.Gprim then return False
    if prim.IsA(UsdGeom.Gprim) and is_ancestor_prim_type(stage, new_path, UsdGeom.Gprim):
        return False

    return True


def _set_prop_val(prop: Usd.Property, val: typing.Any, time_code=Usd.TimeCode.Default()):
    # Add support to set Gf.Matrix4X, Gf.QuatX using python tuple
    prop_type = prop.GetTypeName()
    if prop_type == Sdf.ValueTypeNames.Matrix4d and isinstance(val, tuple):
        prop.Set(Gf.Matrix4d(*val), time_code)
    elif prop_type == Sdf.ValueTypeNames.Quath and isinstance(val, tuple):
        prop.Set(Gf.Quath(*val), time_code)
    elif prop_type == Sdf.ValueTypeNames.Quatf and isinstance(val, tuple):
        prop.Set(Gf.Quatf(*val), time_code)
    elif prop_type == Sdf.ValueTypeNames.Quatd and isinstance(val, tuple):
        prop.Set(Gf.Quatd(*val), time_code)
    elif prop_type == Sdf.ValueTypeNames.Int2 and isinstance(val, tuple):
        prop.Set(Gf.Vec2i(int(val[0]), int(val[1])), time_code)
    else:
        prop.Set(val, time_code)


def remove_property(prim_path: Sdf.Path, property_name: Sdf.Path, usd_context_or_stage: Union[str, Usd.Stage] = ""):
    stage = __get_stage(usd_context_or_stage)

    with Sdf.ChangeBlock():
        for layer in stage.GetLayerStack():
            prim_spec = layer.GetPrimAtPath(prim_path)
            if prim_spec:
                property_spec = layer.GetPropertyAtPath(prim_path.AppendProperty(property_name))
                if property_spec:
                    prim_spec.RemoveProperty(property_spec)


def get_shader_from_material(prim, get_prim=False):
    material = UsdShade.Material(prim)
    shader = material.ComputeSurfaceSource("mdl")[0] if material else None
    if shader and get_prim:
        return shader.GetPrim()
    return shader


async def get_subidentifier_from_material(prim: Usd.Prim, on_complete_fn: typing.Callable = None):
    carb.log_warn(f"omni.usd.get_subidentifier_from_material is depreciated. Use omni.kit.material.library.get_subidentifier_from_material instead")
    if not on_complete_fn or not prim:
        return

    shader = UsdShade.Shader(prim)
    asset = shader.GetSourceAsset("mdl") if shader else None
    mdl_file = asset.resolvedPath if asset else None
    if not mdl_file:
        on_complete_fn(None)
        return
    await get_subidentifier_from_mdl(mdl_file, on_complete_fn)


async def get_subidentifier_from_mdl(mdl_file: str, on_complete_fn: typing.Callable = None):
    carb.log_warn(f"omni.usd.get_subidentifier_from_mdl is depreciated. Use omni.kit.material.library.get_subidentifier_from_mdl instead")
    if not mdl_file:
        carb.log_error(f"get_subidentifier_from_mdl: Failed to read file {mdl_file}")
        if on_complete_fn:
            on_complete_fn(None)
        return

    result, _, content = await omni.client.read_file_async(mdl_file)
    if result != omni.client.Result.OK:
        carb.log_error(f"get_subidentifier_from_material: Failed to read file {mdl_file}")
        on_complete_fn(None)
        return

    re_material_in_mdl = re.compile(r"export\s+material\s+([^\s]+)\s*\(")
    mtl_list = []
    for line in memoryview(content).tobytes().decode("utf-8").splitlines():
        # get material names from MDL file
        for match in re.finditer(re_material_in_mdl, line):
            mtl_list.append(match.group(1))

    if on_complete_fn:
        on_complete_fn(mtl_list)
    return mtl_list


def create_material_input(
    prim, name, value, vtype, def_value=None, min_value=None, max_value=None, display_name=None, display_group=None, color_space=None
):
    shader = omni.usd.get_shader_from_material(prim)
    if shader:
        existing_input = shader.GetInput(name)
        if existing_input and existing_input.GetTypeName() != vtype:
            omni.usd.remove_property(shader.GetPrim().GetPath(), existing_input.GetFullName())

        surfaceInput = shader.CreateInput(name, vtype)
        surfaceInput.Set(value)
        attr = surfaceInput.GetAttr()

        if def_value is not None:
            attr.SetCustomDataByKey("default", def_value)
        if min_value is not None:
            attr.SetCustomDataByKey("range:min", min_value)
        if max_value is not None:
            attr.SetCustomDataByKey("range:max", max_value)
        if display_name is not None:
            attr.SetDisplayName(display_name)
        if display_group is not None:
            attr.SetDisplayGroup(display_group)
        if color_space is not None:
            attr.SetColorSpace(color_space)

        return attr


def get_local_transform_matrix(prim: Usd.Prim, time_code: Usd.TimeCode = Usd.TimeCode.Default()):
    xformable = UsdGeom.Xformable(prim)
    # todo GetResetXformStack (also not supported in C++ counterpart in Kit's UsdUtils.h)
    return xformable.GetLocalTransformation(time_code)


def get_world_transform_matrix(prim: Usd.Prim, time_code: Usd.TimeCode = Usd.TimeCode.Default()):
    xformable = UsdGeom.Xformable(prim)
    return xformable.ComputeLocalToWorldTransform(time_code)


def get_sdf_layer(prim):
    if prim is None:
        return None

    arcs = Usd.PrimCompositionQuery(prim).GetCompositionArcs()
    for arc in arcs:
        arc_layer = arc.GetIntroducingLayer()
        arc_prim = arc.GetIntroducingPrimPath()
        if arc_layer is None or arc_prim is None:
            continue
        if arc_prim == prim.GetPath():
            return arc_layer

    return prim.GetStage().GetRootLayer()


def get_authored_prim(prim):
    while not prim.IsPseudoRoot():
        if prim.HasAuthoredReferences():
            return prim
        prim = prim.GetParent()
    return None


def get_introducing_layer(prim: Usd.Prim) -> Tuple[Sdf.Layer, Sdf.Path]:
    """
    This function will find the introducing layer and prim path of this prim.
    An introducting layer is where the prim is firstly defined.

    Args:
        prim (Usd.Prim): Prim handle

    Returns:
        Tuple[Sdf.Layer, Sdf.Path]: Introducing layer and its introducing prim path.
    """

    introducing_layer = None
    introducing_prim_path = None
    prim_stack = prim.GetPrimStack()
    for prim_spec in prim_stack:
        if prim_spec.specifier == Sdf.SpecifierDef:
            introducing_layer = prim_spec.layer
            introducing_prim_path = prim_spec.path
            break

    if not introducing_layer:
        return None, None

    query = Usd.PrimCompositionQuery(prim)
    qFilter = Usd.PrimCompositionQuery.Filter()
    qFilter.arcTypeFilter = Usd.PrimCompositionQuery.ArcTypeFilter.ReferenceOrPayload
    qFilter.arcIntroducedFilter = Usd.PrimCompositionQuery.ArcIntroducedFilter.IntroducedInRootLayerStack
    query.filter = qFilter
    arcs = query.GetCompositionArcs()
    for arc in arcs:
        layer = arc.GetIntroducingLayer()
        (_, ref) = arc.GetIntroducingListEditor()
        asset_path = layer.ComputeAbsolutePath(ref.assetPath)
        if os.path.normpath(introducing_layer.identifier) == os.path.normpath(asset_path):
            introducing_layer = layer
            introducing_prim_path = arc.GetIntroducingPrimPath()
            break

    return introducing_layer, introducing_prim_path


def find_path_in_nodes(node, set_fn):
    def find_in_sublayers(node, layerTree, set_fn, sublayer=False):
        layer = layerTree.layer
        spec = layer.GetObjectAtPath(node.path)
        if spec:
            set_fn(layer.identifier)
        if layerTree.childTrees:
            find_in_sublayers(node, layerTree.childTrees[-1], set_fn, True)

    find_in_sublayers(node, node.layerStack.layerTree, set_fn, False)
    if node.children:
        omni.usd.find_path_in_nodes(node.children[-1], set_fn)


def get_url_from_prim(prim):
    """
    Returns url of Prim when authored reference or None
    """
    url_path = None
    external_refs = omni.usd.get_composed_references_from_prim(prim)
    if not external_refs:
        external_refs = omni.usd.get_composed_payloads_from_prim(prim)

    if external_refs:
        # Show the first ref path
        ref, layer = external_refs[0]
        url_path = layer.ComputeAbsolutePath(ref.assetPath)
    else:
        authored_prim = omni.usd.get_authored_prim(prim)
        if authored_prim and authored_prim != prim:
            index = prim.GetPrimIndex()
            if index.IsValid():

                def set_url(url):
                    nonlocal url_path
                    url_path = url

                omni.usd.find_path_in_nodes(index.rootNode, set_url)

    return url_path


def get_composed_payloads_from_prim(prim: Usd.Prim) -> List[Tuple[Sdf.Payload, Sdf.Layer]]:
    """Gets composed payload list from prim.

    Args:
        prim (Usd.Prim): Handle of Usd.Prim.

    Returns:
        List of payload items. Each item is a tuple that includes payload handle, and
        the layer it's from.
    """

    def _make_payloads_absolute(info_map, layer, payloads):
        ret_payloads = []
        for payload in payloads:
            authored_asset_path = payload.assetPath
            asset_path = (
                authored_asset_path
                if len(authored_asset_path) == 0 or layer.anonymous
                else layer.ComputeAbsolutePath(authored_asset_path)
            )
            # make a copy as Reference is immutable
            ref_new = Sdf.Payload(
                assetPath=asset_path,
                primPath=payload.primPath,
                layerOffset=payload.layerOffset,
            )

            ret_payloads.append(ref_new)
            info_map.append((ref_new, layer, payload.layerOffset, payload.assetPath))

        return ret_payloads

    # Poor man's version of _GetListOpMetadataImpl and _PcpComposeSiteReferencesOrPayloads without discarding invalid reference
    payload_and_layers = []
    stack = prim.GetPrimStack()
    info_map = []  # cannot use dict, have to use equal compare. Equal reference may not have same hash
    list_ops = []
    for prim_spec in stack:
        if prim_spec.HasInfo(Sdf.PrimSpec.PayloadKey):
            op = prim_spec.GetInfo(Sdf.PrimSpec.PayloadKey)
            # Reference assetPath needs to be converted to absolute path so composed list properly adds and removes refs
            # that may have different relative paths but actually resolve to the same absolute path.
            if op.isExplicit:
                op.explicitItems = _make_payloads_absolute(info_map, prim_spec.layer, op.explicitItems)
            else:
                op.addedItems = _make_payloads_absolute(info_map, prim_spec.layer, op.addedItems)
                op.prependedItems = _make_payloads_absolute(info_map, prim_spec.layer, op.prependedItems)
                op.appendedItems = _make_payloads_absolute(info_map, prim_spec.layer, op.appendedItems)
                op.deletedItems = _make_payloads_absolute(info_map, prim_spec.layer, op.deletedItems)
                op.orderedItems = _make_payloads_absolute(info_map, prim_spec.layer, op.orderedItems)
            list_ops.append(op)

    items = []
    list_ops.reverse()
    for op in list_ops:
        items = op.ApplyOperations(items)

    for item in items:
        info = next((x for x in info_map if x[0] == item), None)
        if info:
            restored_payload = Sdf.Payload(
                assetPath=info[3],
                primPath=info[0].primPath,
                layerOffset=info[2],
            )
            payload_and_layers.append((restored_payload, info[1]))
        else:
            carb.log_error("Cannot found payload in info map! It might be a bug in the widget code.")
    return payload_and_layers


def get_composed_references_from_prim(prim: Usd.Prim, fix_slashes: bool=True) -> List[Tuple[Sdf.Reference, Sdf.Layer]]:
    """Gets composed reference list from prim.

    Args:
        prim (Usd.Prim): Handle of Usd.Prim.

    Returns:
        List of reference items. Each item is a tuple that includes reference handle, and
        the layer it's from.
    """

    def _make_refs_absolute(info_map, layer, refs):
        ret_refs = []
        for ref in refs:
            authored_asset_path = ref.assetPath
            asset_path = (
                authored_asset_path
                if len(authored_asset_path) == 0 or layer.anonymous
                else layer.ComputeAbsolutePath(authored_asset_path)
            )
            # make a copy as Reference is immutable
            ref_new = Sdf.Reference(
                assetPath=asset_path.replace("\\", "/") if fix_slashes else asset_path,
                primPath=ref.primPath,
                layerOffset=ref.layerOffset,
                customData=ref.customData,
            )

            ret_refs.append(ref_new)
            info_map.append((ref_new, layer, ref.layerOffset, ref.assetPath))

        return ret_refs

    # Poor man's version of _GetListOpMetadataImpl and _PcpComposeSiteReferencesOrPayloads without discarding invalid reference
    ref_and_layers = []
    stack = prim.GetPrimStack()
    info_map = []  # cannot use dict, have to use equal compare. Equal reference may not have same hash
    list_ops = []
    for prim_spec in stack:
        if prim_spec.HasInfo(Sdf.PrimSpec.ReferencesKey):
            op = prim_spec.GetInfo(Sdf.PrimSpec.ReferencesKey)
            # Reference assetPath needs to be converted to absolute path so composed list properly adds and removes refs
            # that may have different relative paths but actually resolve to the same absolute path.
            if op.isExplicit:
                op.explicitItems = _make_refs_absolute(info_map, prim_spec.layer, op.explicitItems)
            else:
                op.addedItems = _make_refs_absolute(info_map, prim_spec.layer, op.addedItems)
                op.prependedItems = _make_refs_absolute(info_map, prim_spec.layer, op.prependedItems)
                op.appendedItems = _make_refs_absolute(info_map, prim_spec.layer, op.appendedItems)
                op.deletedItems = _make_refs_absolute(info_map, prim_spec.layer, op.deletedItems)
                op.orderedItems = _make_refs_absolute(info_map, prim_spec.layer, op.orderedItems)
            list_ops.append(op)

    items = []
    list_ops.reverse()
    for op in list_ops:
        items = op.ApplyOperations(items)

    for item in items:
        info = next((x for x in info_map if x[0] == item), None)
        if info:
            restored_ref = Sdf.Reference(
                assetPath=info[3].replace("\\", "/") if fix_slashes else info[3],
                primPath=info[0].primPath,
                layerOffset=info[2],
                customData=info[0].customData,
            )
            ref_and_layers.append((restored_ref, info[1]))
        else:
            carb.log_error("Cannot found reference in info map! It might be a bug in the widget code.")

    return ref_and_layers


def get_composed_payloads_from_prim(prim: Usd.Prim, fix_slashes: bool=True) -> List[Tuple[Sdf.Payload, Sdf.Layer]]:
    """Gets composed payload list from prim.

    Args:
        prim (Usd.Prim): Handle of Usd.Prim.

    Returns:
        List of payload items. Each item is a tuple that includes payload handle, and
        the layer it's from.
    """

    def _make_refs_absolute(info_map, layer, refs):
        ret_refs = []
        for ref in refs:
            authored_asset_path = ref.assetPath
            asset_path = (
                authored_asset_path
                if len(authored_asset_path) == 0 or layer.anonymous
                else layer.ComputeAbsolutePath(authored_asset_path)
            )
            # make a copy as Payload is immutable
            ref_new = Sdf.Payload(
                assetPath=asset_path.replace("\\", "/") if fix_slashes else asset_path,
                primPath=ref.primPath,
                layerOffset=ref.layerOffset,
            )

            ret_refs.append(ref_new)
            info_map.append((ref_new, layer, ref.layerOffset, ref.assetPath))

        return ret_refs

    # Poor man's version of _GetListOpMetadataImpl and _PcpComposeSiteReferencesOrPayloads without discarding invalid payload
    ref_and_layers = []
    stack = prim.GetPrimStack()
    info_map = []  # cannot use dict, have to use equal compare. Equal payload may not have same hash
    list_ops = []
    for prim_spec in stack:
        if prim_spec.HasInfo(Sdf.PrimSpec.PayloadKey):
            op = prim_spec.GetInfo(Sdf.PrimSpec.PayloadKey)
            # Payload assetPath needs to be converted to absolute path so composed list properly adds and removes refs
            # that may have different relative paths but actually resolve to the same absolute path.
            if op.isExplicit:
                op.explicitItems = _make_refs_absolute(info_map, prim_spec.layer, op.explicitItems)
            else:
                op.addedItems = _make_refs_absolute(info_map, prim_spec.layer, op.addedItems)
                op.prependedItems = _make_refs_absolute(info_map, prim_spec.layer, op.prependedItems)
                op.appendedItems = _make_refs_absolute(info_map, prim_spec.layer, op.appendedItems)
                op.deletedItems = _make_refs_absolute(info_map, prim_spec.layer, op.deletedItems)
                op.orderedItems = _make_refs_absolute(info_map, prim_spec.layer, op.orderedItems)
            list_ops.append(op)

    items = []
    list_ops.reverse()
    for op in list_ops:
        items = op.ApplyOperations(items)

    for item in items:
        info = next((x for x in info_map if x[0] == item), None)
        if info:
            restored_ref = Sdf.Payload(
                assetPath=info[3].replace("\\", "/") if fix_slashes else info[3],
                primPath=info[0].primPath,
                layerOffset=info[2],
            )
            ref_and_layers.append((restored_ref, info[1]))
        else:
            carb.log_error("Cannot found payload in info map! It might be a bug in the widget code.")

    return ref_and_layers


# Check if prim is brought into composition by its ancestor.
def check_ancestral(prim):
    def check_ancestral_node(node):
        # Check if any of the node is ancestral
        is_ancestral = node.IsDueToAncestor()
        if not is_ancestral:
            for child in node.children:
                is_ancestral = check_ancestral_node(child) or is_ancestral
                if is_ancestral:
                    break
        return is_ancestral

    return check_ancestral_node(prim.GetPrimIndex().rootNode)


def can_be_copied(prim):
    stage = prim.GetStage()
    for layer in stage.GetLayerStack():
        old_prim_spec = layer.GetPrimAtPath(prim.GetPath().pathString)
        if old_prim_spec is not None:
            return True

    return False


def handle_exception(func):
    """
    Decorator to print exception in async functions
    """
    import traceback

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except asyncio.CancelledError:
            # We always cancel the task. It's not a problem.
            pass
        except Exception as e:
            carb.log_error(f"Exception when async '{func}'")
            carb.log_error(f"{e}")
            carb.log_error(f"{traceback.format_exc()}")

    return wrapper


# Python equivalent of UsdUtils::getLocalTransformSRT
def get_local_transform_SRT(prim, time=Usd.TimeCode.Default()) -> Tuple[Gf.Vec3d, Gf.Vec3d, Gf.Vec3i, Gf.Vec3d]:
    """
    Return a tuple of [scale, rotation, rotation_order, translate] for given prim.

    """

    xform = UsdGeom.Xformable(prim)

    ordered_xform_ops = xform.GetOrderedXformOps() or []

    seen_scale = False
    seen_rotation = 0  # use a counter here, because euler angle can show up as individual xform_op.
    seen_axes = [False, False, False]
    seen_translation = False

    # default values
    scale = Gf.Vec3d(1.0, 1.0, 1.0)
    rotation = Gf.Vec3d(0.0, 0.0, 0.0)
    rotation_order = Gf.Vec3i(-1, -1, -1)  # placeholder
    translation = Gf.Vec3d(0.0, 0.0, 0.0)

    type_enums_to_int = {
        UsdGeom.XformOp.TypeInvalid: 0,
        UsdGeom.XformOp.TypeTranslate: 1,
        UsdGeom.XformOp.TypeScale: 2,
        UsdGeom.XformOp.TypeRotateX: 3,
        UsdGeom.XformOp.TypeRotateY: 4,
        UsdGeom.XformOp.TypeRotateZ: 5,
        UsdGeom.XformOp.TypeRotateXYZ: 6,
        UsdGeom.XformOp.TypeRotateXZY: 7,
        UsdGeom.XformOp.TypeRotateYXZ: 8,
        UsdGeom.XformOp.TypeRotateYZX: 9,
        UsdGeom.XformOp.TypeRotateZXY: 10,
        UsdGeom.XformOp.TypeRotateZYX: 11,
        UsdGeom.XformOp.TypeOrient: 12,
        UsdGeom.XformOp.TypeTransform: 13,
    }

    ordered_xform_ops.reverse()
    for xform_op in ordered_xform_ops:

        if xform_op.IsInverseOp():
            continue

        op_type = xform_op.GetOpType()

        if op_type == UsdGeom.XformOp.TypeTransform:
            seen_scale = True
            seen_rotation = 3
            seen_translation = True
            mtx = xform_op.GetOpTransform(time)

            rot_mat = Gf.Matrix4d(1.0)
            _, _, scale, rot_mat, translation, _ = mtx.Factor()

            # By default decompose as XYZ order (make it an option?)
            decomp_rot = rot_mat.ExtractRotation().Decompose(Gf.Vec3d.ZAxis(), Gf.Vec3d.YAxis(), Gf.Vec3d.XAxis())
            rotation = Gf.Vec3d(decomp_rot[2], decomp_rot[1], decomp_rot[0])
            rotation_order = Gf.Vec3i(0, 1, 2)

            break

        if not seen_scale:
            if op_type == UsdGeom.XformOp.TypeScale:
                if seen_rotation or seen_translation:
                    carb.log_warn("Incompatible xformOpOrder, rotation or translation applied before scale.")

                seen_scale = True
                scale = xform_op.Get(time) or (1.0, 1.0, 1.0)

        if seen_rotation != 3:
            if (
                type_enums_to_int[op_type] >= type_enums_to_int[UsdGeom.XformOp.TypeRotateXYZ]
                and type_enums_to_int[op_type] <= type_enums_to_int[UsdGeom.XformOp.TypeRotateZYX]
            ):
                if seen_translation or seen_rotation != 0:
                    carb.log_warn(
                        "Incompatible xformOpOrder, translation applied before rotation or too many rotation ops."
                    )

                seen_rotation = 3
                rotation = xform_op.Get(time) or (0.0, 0.0, 0.0)

                rotation_orders = [
                    Gf.Vec3i(0, 1, 2),  # XYZ
                    Gf.Vec3i(0, 2, 1),  # XZY
                    Gf.Vec3i(1, 0, 2),  # YXZ
                    Gf.Vec3i(1, 2, 0),  # YZX
                    Gf.Vec3i(2, 0, 1),  # ZXY
                    Gf.Vec3i(2, 1, 0),  # ZYX
                ]

                rotation_order = rotation_orders[
                    type_enums_to_int[op_type] - type_enums_to_int[UsdGeom.XformOp.TypeRotateXYZ]
                ]

            elif op_type >= UsdGeom.XformOp.TypeRotateX and op_type <= UsdGeom.XformOp.TypeRotateZ:
                if seen_translation or seen_rotation > 3:
                    carb.log_warn("Incompatible xformOpOrder, too many single axis rotation ops.")

                # Set rotation order based on individual axis order
                rotation_order[seen_rotation] = type_enums_to_int[op_type] - type_enums_to_int[UsdGeom.XformOp.TypeRotateX]
                seen_rotation += 1
                seen_axes[type_enums_to_int[op_type] - type_enums_to_int[UsdGeom.XformOp.TypeRotateX]] = True

                angle = xform_op.Get(time) or 0.0

                rotation[type_enums_to_int[op_type] - type_enums_to_int[UsdGeom.XformOp.TypeRotateX]] = angle
            elif op_type == UsdGeom.XformOp.TypeOrient:
                if seen_translation or seen_rotation != 0:
                    carb.log_warn(
                        "Incompatible xformOpOrder, translation applied before rotation or too many rotation ops."
                    )

                seen_rotation = 3
                rot = Gf.Rotation()
                quat = xform_op.Get(time)
                if quat is not None:
                    rot.SetQuat(quat)

                # By default decompose as XYZ order (make it an option?)
                decomp_rot = rot.Decompose(Gf.Vec3d.ZAxis(), Gf.Vec3d.YAxis(), Gf.Vec3d.XAxis())
                rotation = Gf.Vec3d(decomp_rot[2], decomp_rot[1], decomp_rot[0])
                rotation_order = Gf.Vec3i(0, 1, 2)

        if not seen_translation:
            # Do not get translation from pivot
            if op_type == UsdGeom.XformOp.TypeTranslate and "pivot" not in xform_op.SplitName():
                seen_translation = True
                translation = xform_op.Get(time) or (0.0, 0.0, 0.0)

    if seen_rotation == 0:
        # If we did not see any rotation op, get it from the preferences
        order_map = {
            "XYZ": Gf.Vec3i(0, 1, 2),
            "XZY": Gf.Vec3i(0, 2, 1),
            "YXZ": Gf.Vec3i(1, 0, 2),
            "YZX": Gf.Vec3i(1, 2, 0),
            "ZXY": Gf.Vec3i(2, 0, 1),
            "ZYX": Gf.Vec3i(2, 1, 0),
        }
        settings = carb.settings.get_settings()
        if prim.IsA(UsdGeom.Camera):
            order_str = settings.get("/persistent/app/primCreation/DefaultCameraRotationOrder")
        else:
            order_str = settings.get("/persistent/app/primCreation/DefaultRotationOrder")
        rotation_order = order_map.get(order_str, Gf.Vec3i(0, 1, 2))
        seen_rotation = 3
    else:
        # Assign rotation order to missing rotation ops after existing rotation ops
        for i in range(0, 3):
            if rotation_order[i] == -1:
                for j in range(0, 3):
                    if not seen_axes[j]:
                        rotation_order[i] = j
                        seen_axes[j] = True
                        break
    return scale, rotation, rotation_order, translation


def get_stage_next_free_path(stage: Usd.Stage, path: Union[str, Sdf.Path], prepend_default_prim: bool):
    if isinstance(path, str) and not Sdf.Path.IsValidPathString(path):
        raise ValueError(f"{path} is not a valid path")

    path = Sdf.Path(path)
    # If path is missing leading slash, it's still ValidPathString but may crash in other USD api. Correct it here and issue a warning.
    corrected_path = path.MakeAbsolutePath(Sdf.Path.absoluteRootPath)
    if path != corrected_path:
        carb.log_warn(f"Path {path} is auto-corrected to {corrected_path}. Please verify your path format.")
        path = corrected_path

    if prepend_default_prim and stage.HasDefaultPrim():
        defaultPrim = stage.GetDefaultPrim()
        if defaultPrim and not (path.HasPrefix(defaultPrim.GetPath()) and path != defaultPrim.GetPath()):
            path = path.ReplacePrefix(Sdf.Path.absoluteRootPath, defaultPrim.GetPath())

    def increment_path(path):
        match = re.search("_(\d+)$", path)
        if match:
            new_num = int(match.group(1)) + 1
            ret = re.sub("_(\d+)$", str.format("_{:02d}", new_num), path)
        else:
            ret = path + "_01"
        return ret

    path_string = path.pathString
    while stage.GetPrimAtPath(path_string):
        path_string = increment_path(path_string)

    return path_string


def get_prim_descendents(root_prim):
    descendents = []
    for prim in Usd.PrimRange(root_prim):
        if prim.IsA(UsdGeom.Subset) or prim.IsA(UsdGeom.Gprim) or prim.IsA(UsdGeom.Xform):
            descendents.append(prim)

    return descendents


class PrimCaching:
    def __init__(self, usd_type, stage, on_changed=None):
        self._notice_listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, self._on_usd_changed, stage)
        self._stage = weakref.ref(stage) if stage else None
        self._usd_type = usd_type
        self._on_changed = on_changed
        self._usd_cache_state = False
        self._usd_property_changes = set()
        self.__prim_changed_task = None
        self._stage_event_sub = (
            omni.usd.get_context()
            .get_stage_event_stream()
            .create_subscription_to_pop(self._on_stage_event, name="PrimCaching stage update")
        )

    def __del__(self):
        if self._notice_listener:
            carb.log_error(f"PrimCaching leak. destroy has not been called")
            self.destroy()

    def destroy(self):
        if self._notice_listener:
            self._notice_listener.Revoke()
        self._notice_listener = None
        self._stage = None
        self._usd_type = None
        self._usd_property_changes = None
        self.__prim_changed_task = None
        self._stage_event_sub = None

    @Trace.TraceFunction
    def _on_usd_changed(self, notice, stage):
        if not self._stage or not self._stage():
            return

        if stage != self._stage():
            return

        for p in notice.GetResyncedPaths():
            self._usd_property_changes.add(p.GetPrimPath() if p.IsPropertyPath() else p)

        for p in notice.GetChangedInfoOnlyPaths():
            self._usd_property_changes.add(p.GetPrimPath() if p.IsPropertyPath() else p)

        # Update in the next frame. We need it because we want to accumulate the affected prims
        if self.__prim_changed_task is None or self.__prim_changed_task.done():
            self.__prim_changed_task = asyncio.ensure_future(self._update_usd_cache_state())

    @handle_exception
    async def _update_usd_cache_state(self):
        await omni.kit.app.get_app().next_update_async()
        if not self._stage or not self._stage():
            return
        stage = self._stage()
        for path in self._usd_property_changes:
            prim = stage.GetPrimAtPath(path)
            # if prim is deleted or is a material, clear cache
            if not prim:
                carb.log_verbose(f"prim {path.GetPrimPath()} deleted/renamed - cleared cache")
                self.set_cache_state(False)
                if self._on_changed:
                    self._on_changed()
                break
            if prim.IsA(self._usd_type):
                carb.log_verbose(f"prim {prim} changed - cleared cache")
                self.set_cache_state(False)
                if self._on_changed:
                    self._on_changed()
                break
        self._usd_property_changes = set()

    def _on_stage_event(self, event: carb.events.IEvent):
        if event.type == int(omni.usd.StageEventType.CLOSING):
            carb.log_verbose(f"stage closed - cleared cache & reset stage")
            if self._notice_listener:
                self._notice_listener.Revoke()
            self._notice_listener = None
            self._stage = None
            self.set_cache_state(False)
            if self._on_changed:
                self._on_changed()
        elif event.type == int(omni.usd.StageEventType.OPENED):
            stage = omni.usd.get_context().get_stage()
            carb.log_verbose(f"new stage - cleared cache & initalized new stage")
            if stage:
                self._stage = weakref.ref(stage)
                self._notice_listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, self._on_usd_changed, stage)
            self.set_cache_state(False)
            if self._on_changed:
                self._on_changed()

    def get_cache_state(self):
        return self._usd_cache_state

    def set_cache_state(self, state):
        self._usd_cache_state = state

    def get_stage(self):
        if self._stage:
            return self._stage()
        return None


def duplicate_prim(
    stage: Usd.Stage, prim_path: Union[str, Sdf.Path],
    path_to: Union[str, Sdf.Path], duplicate_layers: bool = True
):
    """
    Duplicate prim. This will duplicate prim specs in all sublayers with the same prim path.
    
    Args:
        stage (Usd.Stage): Stage handle.

        prim_path (Union[str, Sdf.Path]): Prim path.

        path_to (Union[str, Sdf.Path]): Copy to path.

        duplicate_layers (bool): True if it's to duplicate this prim in all layers.
            False if it's to duplicate this prim in the current edit target only.
            If you want to collapse all overrides inside all layers of this prim,
            see omni.usd.stitch_prim_specs for reference.

    Return:
        True if successful, or false otherwise.
    """

    sdf_from_path = Sdf.Path(prim_path)
    sdf_to_path = Sdf.Path(path_to)
    usd_prim = stage.GetPrimAtPath(sdf_from_path)
    if not usd_prim or sdf_from_path == Sdf.Path.absoluteRootPath:
        carb.log_warn(f"Cannot duplicate prim {prim_path} since it's not existed.")
        return False
    
    introducing_layer, intro_prim_path = omni.usd.get_introducing_layer(usd_prim)
    from_reference_or_payload = False
    prim_spec_in_def_layer = None
    for prim_spec in usd_prim.GetPrimStack():
        if prim_spec.specifier == Sdf.SpecifierDef:
            if introducing_layer != prim_spec.layer and intro_prim_path != prim_path:
                from_reference_or_payload = True
                prim_spec_in_def_layer = prim_spec
                break

    with Sdf.ChangeBlock():
        for old_prim_spec in usd_prim.GetPrimStack():
            layer = old_prim_spec.layer
            dst_layer = layer
            if not duplicate_layers:
                dst_layer = stage.GetEditTarget().GetLayer()
            elif from_reference_or_payload and prim_spec_in_def_layer == old_prim_spec:
                dst_layer = introducing_layer

            if (
                duplicate_layers
                or (not duplicate_layers and (old_prim_spec.hasReferences or old_prim_spec.hasPayloads))
                or old_prim_spec.specifier == Sdf.SpecifierDef
            ):
                if layer != dst_layer:
                    # Copy def prim from reference or payload into temp layer
                    temp_layer = Sdf.Layer.CreateAnonymous()
                    Sdf.CreatePrimInLayer(temp_layer, sdf_from_path)
                    Sdf.CopySpec(layer, old_prim_spec.path, temp_layer, sdf_from_path)

                    # Converts all external references inside temp_layer to absolute path.
                    # All paths will be resolved against layer.identifier.
                    omni.usd.resolve_paths(layer.identifier, temp_layer.identifier, False)

                    # Converts all external references inside temp_layer to relative path.
                    # And the relative path is compuated against dst_layer.identifier.
                    omni.usd.resolve_paths(dst_layer.identifier, temp_layer.identifier, True, True)

                    # If prim is not inside the sublayer list but in reference or payload,
                    # it needs to resolve the prim path since all its referenced relationships
                    # needs to be remapped to new paths against the introducing path.
                    if not stage.HasLocalLayer(layer) and from_reference_or_payload:
                        root_prim_path = old_prim_spec.path.GetPrefixes()[0]
                        omni.usd.resolve_prim_path_references(
                            temp_layer.identifier, str(root_prim_path), str(intro_prim_path)
                        )
                    
                    if from_reference_or_payload and prim_spec_in_def_layer == old_prim_spec:
                        # It's possible that there are overrides in the intro layer, it
                        # needs to merge all those overrides.
                        omni.usd.merge_prim_spec(
                            temp_layer.identifier, introducing_layer.identifier,
                            str(sdf_from_path), False
                        )

                    # It's possible that the prim is defined inside reference or payload,
                    # and it has overrides inside the target layer. It needs to
                    # copy all those overrides also.
                    if dst_layer.GetPrimAtPath(sdf_from_path):
                        omni.usd.merge_prim_spec(temp_layer.identifier, dst_layer.identifier, str(sdf_from_path), False)

                    src_layer = temp_layer
                    src_prim_path = sdf_from_path
                else:
                    src_layer = layer
                    src_prim_path = old_prim_spec.path

                Sdf.CreatePrimInLayer(dst_layer, sdf_to_path)
                Sdf.CopySpec(src_layer, src_prim_path, dst_layer, sdf_to_path)

                if not duplicate_layers:
                    break
    
    return True


def make_path_relative_to_current_edit_target(url_path, stage=None):
    if not url_path:
        return url_path

    path_method = carb.settings.get_settings().get("/persistent/app/material/dragDropMaterialPath") or "relative"
    if not stage:
        stage = omni.usd.get_context().get_stage()
        if not stage:
            carb.log_verbose('make_path_relative_to_current_edit_target: Failed due to no stage')
            return url_path

    if path_method.lower() == "relative":
        # XXX: PyBind omni::usd::UsdUtils::makePathRelativeToLayer
        url = url_path
        stage_layer = stage.GetEditTarget().GetLayer()
        if not stage_layer.anonymous and not Sdf.Layer.IsAnonymousLayerIdentifier(url):
            stage_layer_path = stage_layer.realPath
            if stage_layer_path.replace('\\', '/') == url:
                carb.log_verbose(f'make_path_relative_to_current_edit_target: Failed as cannot reference {url} onto itself')
                return url_path
            relative_url = omni.client.make_relative_url(stage_layer_path, url)
            if relative_url:
                return relative_url
        else:
            carb.log_verbose('make_path_relative_to_current_edit_target: Failed as stage is anonymous')

    return url_path


def get_context_from_stage(stage: Usd.Stage):
    """Gets corresponding UsdContext of the stage if it's found."""

    cache = UsdUtils.StageCache.Get()
    stage_id = cache.GetId(stage)
    if not stage_id.IsValid():
        return None

    return get_context_from_stage_id(stage_id.ToLongInt())


def correct_filename_case(file: str) -> str:
    try:
        import platform, glob, re

        if platform.system().lower() == "windows":
            # get correct case filename
            ondisk = glob.glob(re.sub(r'([^:/\\])(?=[/\\]|$)|\[', r'[\g<0>]', file))[0].replace("\\", "/")
            # correct drive letter case
            if ondisk[0].islower() and ondisk[1] == ":":
                ondisk = ondisk[0].upper() + ondisk[1:]
            # has only case changed
            if ondisk.lower() == file.lower():
                return ondisk
    except Exception as exc:
        pass
    return file
