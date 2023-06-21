"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""

import math
import os
import weakref
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

import carb
import carb.profiler
import carb.settings
import omni.kit.commands
import omni.timeline
import omni.usd
import omni.client
import omni.client.utils as clientutils

from pxr import AudioSchema, Gf, Kind, Sdf, Trace, Usd, UsdGeom, UsdLux, UsdShade

from .stage_helper import UsdStageHelper


def post_notification(message: str, info: bool = False, duration: int = 3):
    try:
        import omni.kit.notification_manager as nm

        if info:
            type = nm.NotificationStatus.INFO
        else:
            type = nm.NotificationStatus.WARNING

        nm.post_notification(message, status=type, duration=duration)
    except:
        pass


def active_edit_context(usd_context):
    try:
        import omni.kit.usd.layers as layers

        return layers.active_authoring_layer_context(usd_context)
    except:
        pass

    stage = usd_context.get_stage()
    edit_target = stage.GetEditTarget()
    return Usd.EditContext(stage, edit_target.GetLayer())


def remove_prim_spec(layer: Sdf.Layer, prim_spec_path: str):
    """Removes prim spec from layer."""

    prim_spec = layer.GetPrimAtPath(prim_spec_path)
    if not prim_spec:
        return False

    if prim_spec.nameParent:
        name_parent = prim_spec.nameParent
    else:
        name_parent = layer.pseudoRoot

    if not name_parent:
        return False

    name = prim_spec.name
    if name in name_parent.nameChildren:
        del name_parent.nameChildren[name]

    return True


def prim_can_be_removed_without_destruction(usd_context, prim_path):
    """
    A destructive remove is one that will not only edit current edit target,
    but also other non-anonymous layers. Why anonymous layers is not counted is because
    anonymous layers are writable in Kit, and it's only existed when it's a new
    stage or under session layer. Any deltas inside those anonymous layers can be safely
    removed. Otherwise, this function will return false, which means it will not remove
    prim specs in all layers, but deactivates them to avoid editing non-anonymous layers except
    current edit target.
    """

    stage = usd_context.get_stage()
    usd_prim = stage.GetPrimAtPath(prim_path)
    if not usd_prim:
        return True

    # If it's under reference, it cannot be removed.
    if omni.usd.check_ancestral(usd_prim):
        return False

    with active_edit_context(usd_context):
        edit_target = stage.GetEditTarget()
        current_layer = edit_target.GetLayer()
        layer_stack = stage.GetLayerStack()

        has_delta_in_non_anonymous_layer = False
        for layer in layer_stack:
            prim_spec = layer.GetPrimAtPath(prim_path)
            if not prim_spec:
                continue

            if layer != current_layer and not layer.anonymous and not has_delta_in_non_anonymous_layer:
                has_delta_in_non_anonymous_layer = True

    return not has_delta_in_non_anonymous_layer


def write_refinement_override_enabled_hint(stage):
    # If the user authors refinementEnableOverride, drop a hint in customLayerData
    # that we can use to enable/disable the checking for override attributes
    # in the scene delegate (i.e., assuaging Pixar's concern that even assets
    # that do not opt into per-mesh refinement must check for their presence at load
    # time).
    #
    # The hint also gives us a numerical value that we can use to maintain
    # backwards compatibility, as it is almost certain that the attributes and
    # the value resolution logic governing this override behavior will be revisted,
    # i.e., also encodable in a more high-level enum like Complexity setting in
    # usdview, which could also be an attribute than lives on any prim, not just
    # meshes, and whose behavior would inherit down namespace.
    custom_data = stage.GetEditTarget().GetLayer().customLayerData
    custom_data["refinementOverrideImplVersion"] = 0
    stage.GetEditTarget().GetLayer().customLayerData = custom_data


def get_default_rotation_order_str():
    return carb.settings.get_settings().get("/persistent/app/primCreation/DefaultRotationOrder")


def get_default_camera_rotation_order_str():
    return carb.settings.get_settings().get("/persistent/app/primCreation/DefaultCameraRotationOrder")


def get_default_rotation_order_type(is_camera: bool = False):
    if is_camera:
        default_rotation_order = get_default_camera_rotation_order_str()
    else:
        default_rotation_order = get_default_rotation_order_str()
    type_dict = {
        "XYZ": UsdGeom.XformOp.TypeRotateXYZ,
        "XZY": UsdGeom.XformOp.TypeRotateXZY,
        "YXZ": UsdGeom.XformOp.TypeRotateYXZ,
        "YZX": UsdGeom.XformOp.TypeRotateYZX,
        "ZXY": UsdGeom.XformOp.TypeRotateZXY,
        "ZYX": UsdGeom.XformOp.TypeRotateZYX,
    }
    return type_dict.get(default_rotation_order, UsdGeom.XformOp.TypeRotateXYZ)


def ensure_parents_are_active(stage, path):
    """
    OM-70901: It will ensure parents are active. If they are not, it will change the active
    flag into active, and instead all of their children will be marked to inacitve.
    This is normally used when it's to create materials under /World/Looks, as it's
    possible /World/Looks is deactivated. While creating a prim under an inactive parent
    will throw exceptions by USD.
    """

    prim_path = Sdf.Path(path)
    prefixes = prim_path.GetParentPath().GetPrefixes()
    for prefix in prefixes:
        parent = stage.GetPrimAtPath(prefix)
        if not parent:
            return

        if parent.IsActive():
            continue

        parent.SetActive(True)
        with Sdf.ChangeBlock():
            for child in parent.GetAllChildren():
                child.SetActive(False)


class GroupPrimsCommand(omni.kit.commands.Command, UsdStageHelper):
    """
    Group primitive undoable **Command**.

    Args:
        prim_paths (List[str]): Prim paths that will be grouped.
        stage (Usd.Stage): Stage to operate. Optional.
        context_name (str): The usd context to operate. Optional.
        destructive (bool): If it's true, it will group all prims and remove original prims, which
                            may edit other layers that are not edit target currently.
                            If it's false, all changes will made only to the current edit target without
                            touching other layers. By default, it's true for back compatibility.
    """

    def __init__(
        self,
        prim_paths: List[Union[str, Sdf.Path]],
        stage: Optional[Usd.Stage] = None,
        context_name: Optional[str] = None,
        destructive=True,
    ):
        UsdStageHelper.__init__(self, stage, context_name)

        # Filter out empty and absolute root path
        self._prim_paths = []
        self._destructive = destructive
        stage = self._get_stage()
        self._all_path_prefix = Sdf.Path.emptyPath
        self._changed_layer_identifier = None
        for path in prim_paths:
            sdf_path = Sdf.Path(path)
            prim = stage.GetPrimAtPath(sdf_path)
            if not prim:
                continue

            if sdf_path and sdf_path != Sdf.Path.absoluteRootPath:
                parent_path = sdf_path.GetParentPath()
                if self._all_path_prefix == Sdf.Path.emptyPath:
                    self._all_path_prefix = parent_path
                else:
                    self._all_path_prefix = self._all_path_prefix.GetCommonPrefix(parent_path)
                self._prim_paths.append(sdf_path)

        if self._all_path_prefix == Sdf.Path.emptyPath:
            self._all_path_prefix = Sdf.Path.absoluteRootPath

        self._prim_paths = Sdf.Path.RemoveDescendentPaths(self._prim_paths)
        self._move_commands = []
        self._group_prim_path = None

    def do(self):
        self._move_commands = []
        if not self._prim_paths:
            return

        stage = self._get_stage()
        path = self._all_path_prefix.AppendElementString("Group")
        group_prim_path = omni.usd.get_stage_next_free_path(stage, path, False)
        self._group_prim_path = Sdf.Path(group_prim_path)
        group_prim = UsdGeom.Xform.Define(stage, self._group_prim_path)
        Usd.ModelAPI(group_prim).SetKind(Kind.Tokens.group)
        self._create_group_xform_impl(stage, group_prim, self._prim_paths)
        selection = self._get_context().get_selection()
        selection.set_prim_path_selected(group_prim_path, True, False, True, True)
        self._changed_layer_identifier = stage.GetEditTarget().GetLayer().identifier

    def undo(self):
        if self._changed_layer_identifier:
            changed_layer = Sdf.Find(self._changed_layer_identifier)
            if not changed_layer:
                carb.log_warn(f"Failed to ungroup prims as layer {self._changed_layer_identifier} is not found.")
                return

            stage = self._get_stage()
            with Usd.EditContext(stage, changed_layer):
                for command in reversed(self._move_commands):
                    command.undo()

                if self._group_prim_path:
                    delete_cmd = DeletePrimsCommand([self._group_prim_path])
                    delete_cmd.do()

    def _set_prim_pivot(self, prim, pivot):
        translation = Gf.Vec3d(0.0, 0.0, 0.0)
        rotation = Gf.Vec3f(0.0, 0.0, 0.0)
        scale = Gf.Vec3f(1.0, 1.0, 1.0)
        pivot = Gf.Vec3f(pivot[0], pivot[1], pivot[2])
        common_api = UsdGeom.XformCommonAPI(prim)
        common_api.SetTranslate(translation)
        common_api.SetRotate(rotation)
        common_api.SetScale(scale)
        common_api.SetPivot(pivot)

    @Trace.TraceFunction
    def _create_group_xform_impl(self, stage, group_prim, selected_prim_paths):
        old_world_matrices = {}
        new_paths = {}
        name_index = {}
        with Sdf.ChangeBlock():
            for prim_path in selected_prim_paths:
                prim = stage.GetPrimAtPath(prim_path)
                if not prim:
                    continue

                xformable = UsdGeom.Xformable(prim)
                if xformable:
                    old_world_matrices[prim_path] = omni.usd.get_world_transform_matrix(prim)
                move_to = group_prim.GetPath().AppendElementString(prim_path.name)
                index = name_index.get(move_to, -1)
                if index != -1:
                    name_index[move_to] += 1
                    move_to = group_prim.GetPath().AppendElementString(prim_path.name + "_" + str(index))
                else:
                    name_index[move_to] = 0

                move_prim_command = MovePrimCommand(
                    path_from=prim_path, path_to=move_to, keep_world_transform=False, destructive=self._destructive
                )
                move_prim_command.do()

                # Have to access internal state to make sure it's executed
                if move_prim_command._moved:
                    self._move_commands.append(move_prim_command)
                    new_paths[prim_path] = move_to

        if len(old_world_matrices):
            for prim_path in selected_prim_paths:
                if prim_path not in new_paths:
                    continue

                new_path = new_paths[prim_path]
                new_prim = stage.GetPrimAtPath(new_path)
                new_parent = new_prim.GetParent()
                new_parent_world_mtx = omni.usd.get_world_transform_matrix(new_parent)
                new_parent_world_to_local_mtx = new_parent_world_mtx.GetInverse()
                old_world_matrix = old_world_matrices.get(prim_path, None)

                # It's possible that the prim is not xformable.
                if not old_world_matrix:
                    continue

                new_local_mtx = old_world_matrix * new_parent_world_to_local_mtx
                if not Gf.IsClose(new_local_mtx, omni.usd.get_local_transform_matrix(new_prim), 1e-2):
                    # It will author the new transform on CURRENT edit target. If an transfrom exists on a layer
                    # with stronger opinion, prim xfrom will NOT keep in place.
                    # Note that due to the limitation of our undo command, the prim spec will not be identical
                    # after undo. This will need to be addressed globally for all commands.
                    cmd = TransformPrimCommand(path=new_path, new_transform_matrix=new_local_mtx)
                    cmd.do()

            bound_box = Gf.BBox3d()
            for prim_path in selected_prim_paths:
                if prim_path not in new_paths:
                    continue

                new_path = new_paths[prim_path]
                new_prim = stage.GetPrimAtPath(new_path)
                xformable = UsdGeom.Xformable(new_prim)
                if not xformable:
                    continue

                local_bound_box = xformable.ComputeLocalBound(Usd.TimeCode.Default(), UsdGeom.Tokens.default_)
                bound_box = Gf.BBox3d.Combine(bound_box, local_bound_box)

            self._set_prim_pivot(group_prim, bound_box.ComputeCentroid())


class CreatePrimWithDefaultXformCommand(omni.kit.commands.Command, UsdStageHelper):
    """
    Create primitive undoable **Command**.

    Args:
        prim_type (str): Primitive type, e.g. "Sphere", "Cube" etc.
        prim_path (str): Path of the primitive to be created at. If None is provided, it will be placed at stage root or under default prim using Type name.
        select_new_prim (bool) : Whether to select the prim after it's created.
        attributes (Dict[str, object]): optional attributes dict to set after creation.
    """

    def __init__(
        self,
        prim_type: str,
        prim_path: str = None,
        select_new_prim: bool = True,
        attributes: Dict[str, Any] = {},
        create_default_xform=True,
        stage: Optional[Usd.Stage] = None,
        context_name: Optional[str] = None,
    ):
        UsdStageHelper.__init__(self, stage, context_name)
        self._prim_type = prim_type
        self._prim_path = prim_path
        self._attributes = attributes
        self._selection = self._get_context().get_selection()
        self._select_new_prim = select_new_prim
        self._settings = carb.settings.get_settings()
        self._create_default_xform = create_default_xform
        self._move_commands = []

    def do(self):
        stage = self._get_stage()
        path = self._prim_path or omni.usd.get_stage_next_free_path(stage, "/" + self._prim_type, True)
        
        ensure_parents_are_active(stage, path)

        prim = stage.DefinePrim(path, self._prim_type)
        with Sdf.ChangeBlock():
            for attr in self._attributes:
                prim.GetProperty(attr).Set(self._attributes[attr])

        with Sdf.ChangeBlock():
            self._prim_path = prim.GetPath().pathString
            # Select the created prim.
            if self._select_new_prim:
                self._selection.set_prim_path_selected(path, True, True, True, True)
            # Ensure axis influenced geometry prims are adjusted based on stage upAxis
            if prim.IsA(UsdGeom.Cylinder) or prim.IsA(UsdGeom.Capsule) or prim.IsA(UsdGeom.Cone):
                prim.GetAttribute(UsdGeom.Tokens.axis).Set(UsdGeom.GetStageUpAxis(stage))

            if prim.IsA(UsdGeom.Xformable) and self._create_default_xform:
                create_xform_cmd = CreateDefaultXformOnPrimCommand(prim_path=self._prim_path)
                create_xform_cmd.do()

            # Set extent if not already provided
            if UsdGeom.Tokens.extent not in self._attributes:
                attr = prim.GetAttribute(UsdGeom.Tokens.extent) if prim else None
                if prim and attr:
                    bounds = UsdGeom.Boundable.ComputeExtentFromPlugins(UsdGeom.Boundable(prim), Usd.TimeCode.Default())

                    # Bounds can be None if prim has empty points
                    if bounds is not None:
                        attr.Set(bounds)

            self._set_refinement_level(prim, stage)
            self._create_light_extra(prim, stage)

    def undo(self):
        delete_cmd = DeletePrimsCommand([self._prim_path])
        delete_cmd.do()

    def _create_light_extra(self, prim, stage):
        if prim.IsA(UsdLux.Light):
            light_api = UsdLux.ShapingAPI.Apply(prim)
            light_api.CreateShapingConeAngleAttr(180)
            light_api.CreateShapingConeSoftnessAttr()
            light_api.CreateShapingFocusAttr()
            light_api.CreateShapingFocusTintAttr()
            light_api.CreateShapingIesFileAttr()

    def _set_refinement_level(self, prim, stage):
        if (
            prim.IsA(UsdGeom.Cylinder)
            or prim.IsA(UsdGeom.Capsule)
            or prim.IsA(UsdGeom.Cone)
            or prim.IsA(UsdGeom.Sphere)
        ) and self._settings.get(PERSISTENT_SETTINGS_PREFIX + "/app/primCreation/highQuality"):
            prim.CreateAttribute("refinementEnableOverride", Sdf.ValueTypeNames.Bool, True).Set(True)
            prim.CreateAttribute("refinementLevel", Sdf.ValueTypeNames.Int, True).Set(2)
            write_refinement_override_enabled_hint(stage)


class CreatePrimCommand(CreatePrimWithDefaultXformCommand):
    """
    Create primitive undoable **Command**. It is same as `CreatePrimWithDefaultXformCommand`.
    Kept for backward compatibility.

    Args:
        prim_type (str): Primitive type, e.g. "Sphere", "Cube" etc.
        prim_path (str): Path of the primitive to be created at. If None is provided, it will be placed at stage root or under default prim using Type name.
        select_new_prim (bool) : Whether to select the prim after it's created.
        attributes (Dict[str, object]): optional attributes dict to set after creation.
    """

    def __init__(
        self,
        prim_type: str,
        prim_path: str = None,
        select_new_prim: bool = True,
        attributes: Dict[str, Any] = {},
        create_default_xform=True,
        stage: Optional[Usd.Stage] = None,
        context_name: Optional[str] = None,
    ):
        super().__init__(prim_type, prim_path, select_new_prim, attributes, create_default_xform, stage, context_name)


class CopyPrimCommand(omni.kit.commands.Command):
    """
    Copy primitive undoable **Command**.

    Args:
        path_from (str): Path to copy from.

        path_to (str): Path to copy to. If `None` next free path is generated.

        duplicate_layers (bool): Duplicate layers on copy.

        combine_layers (bool): Combine layers on copy. When it's in omni.usd.LayerEditMode.AUTO_AUTHORING mode, this will always be true.

        exclusive_select (bool): If to exclusively select (clear old selections) the newly create object.

        flatten_references (bool): Flatten references during copy. It's only valid when combine_layers is True, and not in AUTO_AUTHORING mode.

        copy_to_introducing_layer (bool): If to copy it to the introducing layer, or the current edit target. By default, it's current edit target.
    """

    def __init__(
        self,
        path_from: str,
        path_to: str = None,
        duplicate_layers: bool = False,
        combine_layers: bool = False,
        exclusive_select: bool = True,
        usd_context_name: str = "",
        flatten_references: bool = False,
        copy_to_introducing_layer: bool = False,
    ):
        self._usd_context = omni.usd.get_context(usd_context_name)
        self._selection = self._usd_context.get_selection()

        stage = self._usd_context.get_stage()
        if not path_to:
            path_to = omni.usd.get_stage_next_free_path(stage, path_from, False)
        else:
            path_to = omni.usd.get_stage_next_free_path(stage, path_to, False)
        self._path_from = path_from
        self._path_to = path_to
        self._duplicate_layers = duplicate_layers
        self._combine_layers = combine_layers
        self._exclusive_select = exclusive_select
        self._flatten_references = flatten_references
        self._copy_to_introducing_layer = copy_to_introducing_layer

    # Code ported from UsdUtils::copyPrim
    def do(self):
        self._copied = False
        stage = self._usd_context.get_stage()
        usd_prim = stage.GetPrimAtPath(self._path_from)
        if not usd_prim:
            return

        if (
            usd_prim.IsA(UsdGeom.Gprim)
            and omni.usd.is_ancestor_prim_type(stage, Sdf.Path(self._path_to), UsdGeom.Gprim)
        ):
            post_notification(
                f"Cannot copy prim {self._path_from} to {self._path_to} as nested gprims are not supported."
            )
            return

        if not self._combine_layers and not self._copy_to_introducing_layer:
            omni.usd.duplicate_prim(stage, self._path_from, self._path_to, self._duplicate_layers)
        else:
            if not self._copy_to_introducing_layer:
                edit_target_layer = stage.GetEditTarget().GetLayer()
            else:
                edit_target_layer, _ = omni.usd.get_introducing_layer(usd_prim)

            # When combine_layers is True and it's to flatten references.
            if self._flatten_references and not self._copy_to_introducing_layer:
                if usd_prim.IsInstanceable():
                    carb.log_error("Duplicating instanceable prim with flattening is not supported.")
                    return

                # Make a temporary stage to hold the Prim to copy, and flatten it later
                flatten_stage = Usd.Stage.CreateInMemory()

                prim_stacks = []
                # If the prim is introduced by its ancestor, its primSpec might now exist in current stage (if no "over" is made to it)
                # we need to copy from its primStack
                if omni.usd.check_ancestral(usd_prim):
                    prim_stacks = usd_prim.GetPrimStack()
                else:
                    for layer in stage.GetLayerStack():
                        prim_spec = layer.GetPrimAtPath(self._path_from)
                        if prim_spec:
                            prim_stacks.append(prim_spec)

                for prim_spec in prim_stacks:
                    src_layer = prim_spec.layer
                    dst_layer = Sdf.Layer.CreateAnonymous()
                    Sdf.CreatePrimInLayer(dst_layer, self._path_from)
                    Sdf.CopySpec(src_layer, prim_spec.path, dst_layer, self._path_from)
                    # Convert all relative paths after copy to its real path.
                    omni.usd.resolve_paths(src_layer.identifier, dst_layer.identifier, False)
                    flatten_stage.GetRootLayer().subLayerPaths.append(dst_layer.identifier)

                flatten_layer = flatten_stage.Flatten()
                if flatten_layer.GetPrimAtPath(self._path_from):
                    omni.usd.resolve_paths(edit_target_layer.identifier, flatten_layer.identifier, True, True)
                    Sdf.CreatePrimInLayer(edit_target_layer, self._path_to)
                    Sdf.CopySpec(flatten_layer, self._path_from, edit_target_layer, self._path_to)
            else:
                Sdf.CreatePrimInLayer(edit_target_layer, self._path_to)
                omni.usd.stitch_prim_specs(stage, self._path_from, edit_target_layer, self._path_to, True)
        self._copied = True

        # Select the copied prim.
        self._selection.set_prim_path_selected(self._path_to, True, False, self._exclusive_select, True)

    def undo(self):
        if self._copied:
            delete_cmd = DeletePrimsCommand([self._path_to])
            delete_cmd.do()

    def modify_callback_info(self, cb_type: str, cmd_args: Dict[str, Any]) -> Dict[str, Any]:
        # The command invocation may not have specified the 'path_to' so let the callback know what we ended up using.
        cmd_args["path_to"] = self._path_to
        return cmd_args


class CopyPrimsCommand(omni.kit.commands.Command):
    """
    Copy multiple primitives undoable **Command**.

    Args:
        paths_from List[str]: Paths to copy from.

        paths_to List[str]: Paths to copy to. If `None` or length smaller than paths_from, then next free path is generated for missing paths.

        duplicate_layers (bool): Duplicate layers on copy.

        combine_layers (bool): Combine layers on copy.

        flatten_references (bool): Flatten references during copy. It's only valid when combine_layers is True, and not in AUTO_AUTHORING mode.

        copy_to_introducing_layer (bool): If to copy it to the introducing layer, or the current edit target. By default, it's current edit target.
                                          Its's valid only when combine_layers is true.
    """

    def __init__(
        self,
        paths_from: List[str],
        paths_to: List[str] = None,
        duplicate_layers: bool = False,
        combine_layers: bool = False,
        flatten_references: bool = False,
        copy_to_introducing_layer: bool = False,
    ):
        self._selection = omni.usd.get_context().get_selection()
        self._paths_from = paths_from.copy()
        self._paths_to = paths_to.copy() if paths_to is not None else None
        self._duplicate_layers = duplicate_layers
        self._combine_layers = combine_layers
        self._flatten_references = flatten_references
        self._copy_to_introducing_layer = copy_to_introducing_layer

    def do(self):
        self._previously_selected_paths = self._selection.get_selected_prim_paths()
        self._selection.clear_selected_prim_paths()
        for i in range(len(self._paths_from)):
            path_to = self._paths_to[i] if (self._paths_to is not None and i < len(self._paths_to)) else None
            omni.kit.commands.execute(
                "CopyPrim",
                path_from=self._paths_from[i],
                path_to=path_to,
                duplicate_layers=self._duplicate_layers,
                combine_layers=self._combine_layers,
                exclusive_select=False,
                flatten_references=self._flatten_references,
                copy_to_introducing_layer=self._copy_to_introducing_layer,
            )

    def undo(self):
        if self._previously_selected_paths:
            self._selection.set_selected_prim_paths(self._previously_selected_paths, False)


class CreateInstanceCommand(omni.kit.commands.Command):
    """
    Instance primitive undoable **Command**.

    It creates a new prim, adds the master object to references, and flags this prim as instanceable. It the prim is
    Xform, this command copies the transforms from the current frame. If the source prim is already instanceable, it
    tries to find master prim of this prim and uses it, so it's perfectly safe to press Ctrl-I multiple times.

    Args:
        path_from (str): Path to instance from.
    """

    def __init__(self, path_from: str):
        self._timeline = omni.timeline.get_timeline_interface()
        self._usd_context = omni.usd.get_context()
        self._selection = self._usd_context.get_selection()

        stage = self._usd_context.get_stage()
        path_to = omni.usd.get_stage_next_free_path(stage, path_from, False)
        self._path_from = path_from
        self._path_to = path_to

    def do(self):
        stage = self._usd_context.get_stage()
        timecode = self._timeline.get_current_time() * stage.GetTimeCodesPerSecond()
        prim_from = stage.GetPrimAtPath(self._path_from)

        # It only makes sence to instance Xforms
        allowed_types_for_instancing = ["Xform"]
        if not prim_from or prim_from.GetTypeName() not in allowed_types_for_instancing:
            message = f"Failed to instance prim {self._path_from} because it's not an Xform."
            carb.log_warn(message)
            post_notification(message)
            return False

        # By default the instance master is _path_from
        file_master = None
        path_master = self._path_from

        # Check if this prim already is an instance. If so, we don't want to produce instance of instance and we need to
        # find the master prim.
        references = []
        arcs = Usd.PrimCompositionQuery.GetDirectReferences(prim_from).GetCompositionArcs()
        for arc in arcs:
            arc_layer = arc.GetIntroducingLayer()
            arc_path = arc.GetIntroducingPrimPath()
            arc_prim = arc_layer.GetPrimAtPath(arc_path)
            reference_list = arc_prim.referenceList
            references += (
                reference_list.prependedItems[:] + reference_list.explicitItems[:] + reference_list.appendedItems[:]
            )

            if len(references) > 1:
                # ATM we don't consider complicated nested references. We are looking for a simple case when the user
                # presses Ctrl-I multiple times and wants to see multiple objects.
                continue

        if len(references) == 1:
            # It's a simple case, so we can use this reference as a master.
            file_master = references[0].assetPath
            path_master = references[0].primPath.pathString

        # Create a prim of the same type as _path_from
        prim_type = prim_from.GetTypeName()
        prim_to = stage.DefinePrim(self._path_to, prim_type)

        # If it's an Xform, we want the new prim to have the same position as the source
        xform_list = []
        xformable_to = None
        if prim_from.IsA(UsdGeom.Xformable):
            xformable_from = UsdGeom.Xformable(prim_from)
            xform_list = [(op, op.GetAttr().Get(timecode)) for op in xformable_from.GetOrderedXformOps()]
            xformable_to = UsdGeom.Xformable(prim_to)

        with Sdf.ChangeBlock():
            # Set inctanceable
            if file_master:
                prim_to.GetReferences().AddReference(file_master, path_master)
            else:
                prim_to.GetReferences().AddInternalReference(path_master)
            prim_to.SetInstanceable(True)

            # Copy all the Xforms from the source
            for op_from, val in xform_list:
                # to allow same typed transformable ops, we need to give the suffix as the original op
                names = op_from.GetName().split(":")
                # the name is e.g. xformOp:translate:pivot or xformOp:rotateXYZ. While HasSuffix is not
                # available in python, we filter the suffix by the number of the elements in names
                suffix = "" if len(names) < 3 else names[-1]
                op_to = xformable_to.AddXformOp(
                    op_from.GetOpType(), op_from.GetPrecision(), suffix, op_from.IsInverseOp()
                )
                op_to.GetAttr().Set(val)
        
        # OM-56752: If original prim has relationship that links to external paths of prim's namespace,
        # It needs to copy them so it will not lose information like material bindings.
        for relationship in prim_from.GetAuthoredRelationships():
            has_external_targets = False
            for path in relationship.GetTargets():
                if not path.HasPrefix(prim_from.GetPath()):
                    has_external_targets = True
                    break
            
            if has_external_targets:
                relationship.FlattenTo(prim_to)

        # Select the copied prim.
        self._selection.set_prim_path_selected(self._path_to, True, False, False, True)

    def undo(self):
        # Dereference this. Otherwise it fires error: Cannot remove ancestral prim
        stage = self._usd_context.get_stage()
        prim_to = stage.GetPrimAtPath(self._path_to)
        prim_to.GetReferences().ClearReferences()

        delete_cmd = DeletePrimsCommand([self._path_to])
        delete_cmd.do()


class CreateInstancesCommand(omni.kit.commands.Command):
    """
    Instance multiple primitives undoable **Command**.

    Args:
        paths_from List[str]: Paths to instance from.
    """

    def __init__(self, paths_from: List[str]):
        self._selection = omni.usd.get_context().get_selection()
        self._paths_from = paths_from.copy()
        self._previously_selected_paths = []

        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()

        # It only makes sence to instance Xforms
        allowed_types_for_instancing = ["Xform"]

        for path in self._paths_from:
            prim = stage.GetPrimAtPath(path)
            if not prim or prim.GetTypeName() not in allowed_types_for_instancing:
                message = f"Failed to instance prim {path} because it's not an Xform."
                carb.log_warn(message)
                post_notification(message)
                self._paths_from = []
                break

    def do(self):
        if self._paths_from:
            self._previously_selected_paths = self._selection.get_selected_prim_paths()
            self._selection.clear_selected_prim_paths()
            for paths_from in self._paths_from:
                omni.kit.commands.execute("CreateInstance", path_from=paths_from)

    def undo(self):
        if self._previously_selected_paths:
            self._selection.set_selected_prim_paths(self._previously_selected_paths, False)


class DeletePrimsCommand(omni.kit.commands.Command, UsdStageHelper):
    """
    Delete primitives undoable **Command**.

    Args:
        paths (List[str]): Paths to prims to delete.

        destructive: If it's false, the delete will only happen in the current target, and follows:
                         1. If the prim spec is a def, it will remove the prim spec.
                         2. If the prim spec is a over, it will only deactivate this prim.
                         3. If the prim spec is not existed, it will create over prim and deactivate it.
                         4. If there is an overridden in a stronger layer, it will report errors.

                         If it's true, it will remove all prim specs in all local layers.

                         By default, it's True and means the delete operation is destructive for back-compatibility.

        stage (Usd.Stage): Stage to operate. Optional.
        context_name (str): The usd context to operate. Optional.
    """

    def __init__(
        self,
        paths: List[Union[str, Sdf.Path]],
        destructive=True,
        stage: Optional[Usd.Stage] = None,
        context_name: Optional[str] = None,
    ):
        UsdStageHelper.__init__(self, stage, context_name)

        self._usd_context = self._get_context()
        self._selection = self._usd_context.get_selection()
        self._paths: List[Sdf.Path] = []
        self._destructive = destructive
        for path in paths:
            path = Sdf.Path(path)
            if path == Sdf.Path.absoluteRootPath:
                continue

            stage = self._get_stage()
            prim = stage.GetPrimAtPath(path)
            if prim:
                if omni.usd.editor.is_no_delete(prim):
                    carb.log_warn(f"{str(path)} is not deletable")
                else:
                    if self._destructive and omni.usd.check_ancestral(prim):
                        carb.log_warn(f"Cannot remove ancestral prim {str(path)}")
                    else:
                        self._paths.append(path)
            else:
                carb.log_error(f"{str(path)} does not exist")

        self._paths = Sdf.Path.RemoveDescendentPaths(self._paths)
        self._prev_selected_paths = list(self._selection.get_selected_prim_paths())
        self._temp_layers = {}
        self._default_prim_path = None
        self._active_state_changed_paths = {}
        self._changed_layer_identifier = None

    def _is_auto_authoring_layer(self, layer_identifier):
        try:
            import omni.kit.usd.layers as layers

            return layers.get_auto_authoring(self._usd_context).is_auto_authoring_layer(layer_identifier)
        except Exception:
            return False

    def _has_overridden_in_stronger_layer(self, stage, prim_path):
        edit_target = stage.GetEditTarget()
        edit_layer = edit_target.GetLayer()
        layer_stack = stage.GetLayerStack()
        for layer in layer_stack:
            if layer == edit_layer:
                break

            prim_spec = layer.GetPrimAtPath(prim_path)
            if not prim_spec:
                continue

            # If active flag is overridden in a stronger layer.
            if prim_spec.HasActive() and prim_spec.active:
                return True

        return False

    def _remove_prim_spec_in_auto_authoring_layer(self, stage, path):
        layer_stack = stage.GetLayerStack()
        for layer in layer_stack:
            if self._is_auto_authoring_layer(layer.identifier):
                remove_prim_spec(layer, path)
                break

    @Trace.TraceFunction
    def _remove_prim_specs(self, stage, paths):
        temp_layers = {}
        layer_stack = stage.GetLayerStack()
        for layer in layer_stack:
            temp_layer = Sdf.Layer.CreateAnonymous()
            edit = Sdf.BatchNamespaceEdit()
            for path in paths:
                prim_spec = layer.GetPrimAtPath(path)
                if prim_spec is None:
                    continue

                Sdf.CreatePrimInLayer(temp_layer, path)
                Sdf.CopySpec(layer, path, temp_layer, path)
                edit.Add(path, Sdf.Path.emptyPath)

            if layer.Apply(edit) and not self._is_auto_authoring_layer(layer.identifier):
                temp_layers[layer.identifier] = temp_layer

        return temp_layers

    def _has_prim_specs(self, stage, path):
        for layer in stage.GetLayerStack():
            prim_spec = layer.GetPrimAtPath(path)
            if prim_spec:
                return True

        return False

    def do(self):
        self._changed_layer_identifier = None
        self._active_state_changed_paths.clear()
        self._default_prim_path = None
        self._temp_layers.clear()

        stage = self._get_stage()
        clear_default_prim = False
        self._default_prim_path = stage.GetDefaultPrim().GetPath() if stage.HasDefaultPrim() else None
        if self._default_prim_path:
            clear_default_prim = self._default_prim_path in self._paths
        else:
            clear_default_prim = False

        with Sdf.ChangeBlock():
            to_be_removed_paths = []
            to_be_deactivated_paths = []
            if self._destructive:
                to_be_removed_paths = self._paths
            else:
                for path in self._paths:
                    usd_prim = stage.GetPrimAtPath(path)
                    if not usd_prim:
                        continue

                    if prim_can_be_removed_without_destruction(self._usd_context, path):
                        to_be_removed_paths.append(path)
                    else:
                        to_be_deactivated_paths.append(path)

            self._temp_layers = self._remove_prim_specs(stage, to_be_removed_paths)
            if to_be_deactivated_paths:
                # Working with current edit target, or default layer in auto_authoring mode.
                with active_edit_context(self._usd_context):
                    edit_target = stage.GetEditTarget()
                    current_layer = edit_target.GetLayer()
                    self._changed_layer_identifier = current_layer.identifier

                    temp_layer = self._temp_layers.get(current_layer.identifier, None)
                    if not temp_layer:
                        temp_layer = Sdf.Layer.CreateAnonymous()
                        self._temp_layers[current_layer.identifier] = temp_layer

                    for path in to_be_deactivated_paths:
                        # Removing auto-authoring copy always
                        self._remove_prim_spec_in_auto_authoring_layer(stage, path)

                        if self._has_overridden_in_stronger_layer(stage, path):
                            error = f"Failed to deactivate prim {path} because it is activated in a stronger layer."
                            carb.log_warn(error)
                            post_notification(error)
                            continue

                        created = False
                        prim_spec = current_layer.GetPrimAtPath(path)
                        # If it's def, removing it in current layer to save file size.
                        if prim_spec and prim_spec.specifier == Sdf.SpecifierDef:
                            Sdf.CreatePrimInLayer(temp_layer, path)
                            Sdf.CopySpec(current_layer, path, temp_layer, path)
                            remove_prim_spec(current_layer, path)
                            # Creates prim spec to set active meta as it has deltas in other layers.
                            prim_spec = Sdf.CreatePrimInLayer(current_layer, path)
                        else:
                            # Otherwise, we only deactivate it.
                            if not prim_spec:
                                prim_spec = Sdf.CreatePrimInLayer(current_layer, path)
                                # Record this so we can remove it in undo.
                                created = True

                        if prim_spec.HasActive():
                            if prim_spec.active != False:
                                self._active_state_changed_paths[path] = (prim_spec.active, created)
                        else:
                            self._active_state_changed_paths[path] = (None, created)
                        prim_spec.active = False

        if clear_default_prim:
            self._default_prim_path = stage.GetDefaultPrim().GetPath()
            stage.ClearDefaultPrim()

    def undo(self):
        with Sdf.ChangeBlock():
            for identifier, restore_from in self._temp_layers.items():
                restore_to = Sdf.Find(identifier)
                if not restore_to:
                    carb.log_warn(f"Failed to restore removed prims as target layer {identifier} cannot be found.")
                    continue

                for path in self._paths:
                    if restore_from.GetPrimAtPath(path):
                        Sdf.CreatePrimInLayer(restore_to, path)
                        Sdf.CopySpec(restore_from, path, restore_to, path)

            for path, value in self._active_state_changed_paths.items():
                restore_to = Sdf.Find(self._changed_layer_identifier)
                if not restore_to:
                    carb.log_warn(
                        f"Failed to restore removed prims as target layer {self._changed_layer_identifier} cannot be found."
                    )
                    continue

                prim_spec = restore_to.GetPrimAtPath(path)
                if not prim_spec:
                    carb.log_warn(
                        f"Failed to restore removed prim {path} to {self._changed_layer_identifier} as it cannot be found."
                    )
                    continue

                active, created = value
                if created:
                    parent_spec = prim_spec.realNameParent
                    if prim_spec.name in parent_spec.nameChildren:
                        del parent_spec.nameChildren[prim_spec.name]
                    continue

                if active is None or active == True:
                    prim_spec.ClearActive()
                else:
                    prim_spec.active = active

        stage = self._get_stage()
        if self._default_prim_path:
            stage.SetDefaultPrim(stage.GetPrimAtPath(self._default_prim_path))

        # Reselect restored objects
        self._selection.set_selected_prim_paths(self._prev_selected_paths, False)


class CreatePrimsCommand(omni.kit.commands.Command):
    """
    Create multiple primitives undoable **Command**.

    Example of command which calls other commands. Undo/Redo grouping handled automatically.

    Args:
        prim_types (List[str]): List of primitive types to create, e.g ["Sphere", "Cone"].
    """

    def __init__(self, prim_types: List[str]):
        self._prim_types = prim_types

    def do(self):
        for p in self._prim_types:
            omni.kit.commands.execute("CreatePrim", prim_type=p)

    def undo(self):
        pass


class CreateDefaultXformOnPrimCommand(omni.kit.commands.Command):
    """
    Create DefaultXform On Prim undoable **Command**.

    Args:
        prim_path (str): Path of the primitive to be create xform attribtues
    """

    def __init__(self, prim_path: str):
        self._prim_path = prim_path
        self._usd_context = omni.usd.get_context()
        self._settings = carb.settings.get_settings()
        self._added_attributes = []
        self._type_changed_attributes = []
        self._old_xform_op_order = None

    def do(self):
        self._added_attributes = []
        self._type_changed_attributes = []
        self._old_xformOrder = None
        stage = self._usd_context.get_stage()
        prim = stage.GetPrimAtPath(self._prim_path)
        if not prim or not prim.IsA(UsdGeom.Xformable):
            return
        with Sdf.ChangeBlock():
            is_prim_created_with_default_xform = self._settings.get(
                PERSISTENT_SETTINGS_PREFIX + "/app/primCreation/PrimCreationWithDefaultXformOps"
            )
            if not is_prim_created_with_default_xform:
                return
            defaultXformOpType = self._settings.get(PERSISTENT_SETTINGS_PREFIX + "/app/primCreation/DefaultXformOpType")
            if prim.IsA(UsdGeom.Camera):
                defaultRotationOrder = self._settings.get(
                    PERSISTENT_SETTINGS_PREFIX + "/app/primCreation/DefaultCameraRotationOrder"
                )
            else:
                defaultRotationOrder = self._settings.get(
                    PERSISTENT_SETTINGS_PREFIX + "/app/primCreation/DefaultRotationOrder"
                )
            defaultXformOpOrder = self._settings.get(
                PERSISTENT_SETTINGS_PREFIX + "/app/primCreation/DefaultXformOpOrder"
            )
            defaultXformPrecision = self._settings.get(
                PERSISTENT_SETTINGS_PREFIX + "/app/primCreation/DefaultXformOpPrecision"
            )
            vec3_type = Sdf.ValueTypeNames.Double3 if defaultXformPrecision == "Double" else Sdf.ValueTypeNames.Float3
            quat_type = Sdf.ValueTypeNames.Quatd if defaultXformPrecision == "Double" else Sdf.ValueTypeNames.Quatf
            mat4_type = Sdf.ValueTypeNames.Matrix4d  # there is no Matrix4f in SdfValueTypeNames
            default_translate = (
                Gf.Vec3d(0.0, 0.0, 0.0) if defaultXformPrecision == "Double" else Gf.Vec3f(0.0, 0.0, 0.0)
            )
            default_euler = self._get_default_euler_angle(
                prim, stage, Gf.Vec3d if defaultXformPrecision == "Double" else Gf.Vec3f
            )
            default_scale = Gf.Vec3d(1.0, 1.0, 1.0) if defaultXformPrecision == "Double" else Gf.Vec3f(1.0, 1.0, 1.0)
            rotation = (
                Gf.Rotation(Gf.Vec3d.XAxis(), default_euler[0])
                * Gf.Rotation(Gf.Vec3d.YAxis(), default_euler[1])
                * Gf.Rotation(Gf.Vec3d.ZAxis(), default_euler[2])
            )
            quat = rotation.GetQuat()
            default_orient = Gf.Quatd(quat) if defaultXformPrecision == "Double" else Gf.Quatf(quat)
            if defaultXformOpType == "Scale, Rotate, Translate":
                attr_translate = prim.GetAttribute("xformOp:translate")
                if not attr_translate:
                    attr_translate = prim.CreateAttribute("xformOp:translate", vec3_type, False)
                    attr_translate.Set(default_translate)
                    self._added_attributes.append(attr_translate)
                elif attr_translate.GetTypeName() != vec3_type:
                    attr_translate.SetTypeName(vec3_type)
                    self._type_changed_attributes.append([attr_translate, vec3_type])
                attr_rotate_name = "xformOp:rotate" + defaultRotationOrder
                attr_rotate = prim.GetAttribute(attr_rotate_name)
                if not attr_rotate:
                    attr_rotate = prim.CreateAttribute(attr_rotate_name, vec3_type, False)
                    euler = self._convert_default_euler_angle(rotation, default_euler, defaultRotationOrder)
                    attr_rotate.Set(euler)
                    self._added_attributes.append(attr_rotate)
                elif attr_rotate.GetTypeName() != vec3_type:
                    attr_rotate.SetTypeName(vec3_type)
                    self._type_changed_attributes.append([attr_rotate, vec3_type])
                attr_scale = prim.GetAttribute("xformOp:scale")
                if not attr_scale:
                    attr_scale = prim.CreateAttribute("xformOp:scale", vec3_type, False)
                    attr_scale.Set(default_scale)
                    self._added_attributes.append(attr_scale)
                elif attr_scale.GetTypeName() != vec3_type:
                    attr_scale.SetTypeName(vec3_type)
                    self._type_changed_attributes.append([attr_scale, vec3_type])
                attr_order = prim.GetAttribute("xformOpOrder")
                if not attr_order:
                    attr_order = prim.CreateAttribute("xformOpOrder", Sdf.ValueTypeNames.TokenArray, False)
                else:
                    self._old_xform_op_order = attr_order.Get()
                attr_order.Set(["xformOp:translate", attr_rotate_name, "xformOp:scale"])
            if defaultXformOpType == "Scale, Orient, Translate":
                attr_translate = prim.GetAttribute("xformOp:translate")
                if not attr_translate:
                    attr_translate = prim.CreateAttribute("xformOp:translate", vec3_type, False)
                    attr_translate.Set(default_translate)
                    self._added_attributes.append(attr_translate)
                elif attr_translate.GetTypeName() != vec3_type:
                    attr_translate.SetTypeName(vec3_type)
                    self._type_changed_attributes.append([attr_translate, vec3_type])
                attr_rotate = prim.GetAttribute("xformOp:orient")
                if not attr_rotate:
                    attr_rotate = prim.CreateAttribute("xformOp:orient", quat_type, False)
                    attr_rotate.Set(default_orient)
                    self._added_attributes.append(attr_rotate)
                elif attr_rotate.GetTypeName() != quat_type:
                    attr_rotate.SetTypeName(quat_type)
                    self._type_changed_attributes.append([attr_rotate, quat_type])
                attr_scale = prim.GetAttribute("xformOp:scale")
                if not attr_scale:
                    attr_scale = prim.CreateAttribute("xformOp:scale", vec3_type, False)
                    attr_scale.Set(default_scale)
                    self._added_attributes.append(attr_scale)
                elif attr_scale.GetTypeName() != vec3_type:
                    attr_scale.SetTypeName(vec3_type)
                    self._type_changed_attributes.append([attr_scale, vec3_type])
                attr_order = prim.GetAttribute("xformOpOrder")
                if not attr_order:
                    attr_order = prim.CreateAttribute("xformOpOrder", Sdf.ValueTypeNames.TokenArray, False)
                else:
                    self._old_xform_op_order = attr_order.Get()
                attr_order.Set(["xformOp:translate", "xformOp:orient", "xformOp:scale"])
            if defaultXformOpType == "Transform":
                attr_matrix = prim.GetAttribute("xformOp:transform")
                if not attr_matrix:
                    attr_matrix = prim.CreateAttribute("xformOp:transform", mat4_type, False)
                    attr_matrix.Set(
                        Gf.Matrix4d().SetScale(default_scale)
                        * Gf.Matrix4d().SetRotate(rotation)
                        * Gf.Matrix4d().SetTranslate(default_translate)
                    )
                    self._added_attributes.append(attr_matrix)
                attr_order = prim.GetAttribute("xformOpOrder")
                if not attr_order:
                    attr_order = prim.CreateAttribute("xformOpOrder", Sdf.ValueTypeNames.TokenArray, False)
                else:
                    self._old_xform_op_order = attr_order.Get()

                attr_order.Set(["xformOp:transform"])

    def undo(self):
        stage = self._usd_context.get_stage()
        prim = stage.GetPrimAtPath(self._prim_path)
        with Sdf.ChangeBlock():
            if not prim:
                self._added_attributes.clear()
                self._type_changed_attributes.clear()
                self._old_xform_op_order = None
                return
            for attr in self._added_attributes:
                prim.RemoveProperty(attr.GetName())
            if len(self._type_changed_attributes) > 0:
                for [attr, attr_type] in self._type_changed_attributes:
                    attr.SetTypeName(attr_type)
            self._added_attributes.clear()
            self._type_changed_attributes.clear()

            if self._old_xform_op_order is not None:
                attr_order = prim.GetAttribute("xformOpOrder")
                if self._old_xform_op_order is not None:
                    attr_order.Set(self._old_xform_op_order)
                else:
                    attr_order.Set("[]")

    def _get_default_euler_angle(self, prim, stage, vector_type):
        """
        rotation specified as if applied in XYZ order
        """
        up_axis = UsdGeom.GetStageUpAxis(stage)
        if prim.IsA(UsdLux.DistantLight):
            if up_axis == "Y":
                return vector_type(315.0, 0.0, 0.0)
            else:
                return vector_type(45.0, 0.0, 90)
        elif prim.IsA(UsdLux.DomeLight):
            if up_axis == "Y":
                return vector_type(270.0, 0.0, 0.0)
        elif (
            prim.IsA(UsdLux.SphereLight)
            or prim.IsA(UsdLux.CylinderLight)
            or prim.IsA(UsdLux.DiskLight)
            or prim.IsA(UsdLux.RectLight)
            or prim.IsA(UsdGeom.Camera)
        ):
            if up_axis == "Z":
                return vector_type(90.0, 0.0, 90.0)

        return vector_type(0.0, 0.0, 0.0)

    def _convert_default_euler_angle(self, rotation, default_euler, default_rotation_order):
        # default_euler is specified in XYZ order. If the target xfromOp order is not XYZ, need to convert the value

        converted_euler = default_euler

        conv_order_table = {
            # Do not convert XYZ
            "XZY": [0, 2, 1],
            "YXZ": [1, 0, 2],
            "YZX": [1, 2, 0],
            "ZXY": [2, 0, 1],
            "ZYX": [2, 1, 0],
        }

        axis = [Gf.Vec3d.XAxis(), Gf.Vec3d.YAxis(), Gf.Vec3d.ZAxis()]

        conv_order = conv_order_table.get(default_rotation_order, None)
        if conv_order is not None:
            decomp_rot = rotation.Decompose(axis[conv_order[2]], axis[conv_order[1]], axis[conv_order[0]])

            index_order = Gf.Vec3i()
            for i in range(0, 3):
                index_order[conv_order[i]] = 2 - i

            converted_euler[0] = decomp_rot[index_order[0]]
            converted_euler[1] = decomp_rot[index_order[1]]
            converted_euler[2] = decomp_rot[index_order[2]]

        return converted_euler


PERSISTENT_SETTINGS_PREFIX = "/persistent"


class BindMaterialCommand(omni.kit.commands.Command, UsdStageHelper):
    """
    Bind material undoable **Command**.

    Args:
        prim_path (str or list): Path(s) to prim or collection
        material_path (str): Path to material to bind.
        strength (float): Strength.
        stage (Usd.Stage): Stage to operate. Optional.
        context_name (str): The usd context to operate. Optional.
    """

    def __init__(
        self,
        prim_path: Union[str, list],
        material_path: str,
        strength=None,
        stage: Optional[Usd.Stage] = None,
        context_name: Optional[str] = None,
    ):
        UsdStageHelper.__init__(self, stage, context_name)

        self._path = prim_path
        self._material_path = material_path
        self._prev_material = []
        self._prev_strength = []

        self._strength = strength
        if self._strength is None:
            self._strength = self._get_binding_strength()

    @staticmethod
    def _get_binding_strength():
        settings = carb.settings.get_settings()
        strength_setting = settings.get(PERSISTENT_SETTINGS_PREFIX + "/app/stage/materialStrength")
        if strength_setting == "strongerThanDescendants":
            return UsdShade.Tokens.strongerThanDescendants
        if strength_setting == "fallbackStrength":
            return UsdShade.Tokens.fallbackStrength
        return UsdShade.Tokens.weakerThanDescendants

    def _bind(self, binding_api, material_prim, strength=None, collection_api=None):
        # Passed in strength-list may have None as members, re-resolve default strength in that case
        if not bool(strength):
            strength = self._get_binding_strength()
        if material_prim:
            material = UsdShade.Material(material_prim)
            if collection_api:
                binding_api.Bind(collection_api, material, collection_api.GetName(), strength)
            else:
                binding_api.Bind(material, strength)
        else:
            binding_api.UnbindAllBindings()

    class PathType(Enum):
        Prim = auto()
        Collection = auto()
        Neither = auto()

    def _get_path_type(self, path: str, stage: Usd.Stage):

        sdf_path = Sdf.Path(path)
        if Usd.CollectionAPI.IsCollectionAPIPath(sdf_path):
            prim = stage.GetPrimAtPath(sdf_path.GetPrimPath())
            return self.PathType.Collection, prim, Usd.CollectionAPI.Get(stage, sdf_path)
        elif sdf_path.IsPrimPath():
            prim = stage.GetPrimAtPath(sdf_path)
            return self.PathType.Prim, prim, None
        return self.PathType.Neither, None, None

    # list of prims, so there could be parent problems due to material inheritance
    def _bind_material_list(self, prim_paths, material_path, material_strength):

        stage = self._get_stage()
        if stage:
            prev_mat_path = []
            prev_mat_strength = []

            if not isinstance(material_path, list):
                material_path = [material_path] * len(prim_paths)
            if not isinstance(material_strength, list):
                material_strength = [material_strength] * len(prim_paths)

            failed_to_bind_prim_paths = []
            can_apply_paths = []

            # get list of previous values
            for path in prim_paths:
                path_type, prim, _ = self._get_path_type(path, stage)
                if prim:
                    if prim.IsInstanceProxy():
                        failed_to_bind_prim_paths.append(path)
                        continue
                    
                    can_apply_paths.append(path)
                    binding_api = UsdShade.MaterialBindingAPI(prim)

                    if path_type == self.PathType.Prim:
                        mat, rel = binding_api.ComputeBoundMaterial()
                        # ignore inherited materials
                        mat_path = mat.GetPath()
                        if rel and rel.GetPrim() != prim:
                            mat_path = None
                        prev_mat_path.append(mat_path)
                        prev_mat_strength.append(
                            UsdShade.MaterialBindingAPI.GetMaterialBindingStrength(rel) if rel else self._strength
                        )
                    elif path_type == self.PathType.Collection:
                        all_bindings = binding_api.GetCollectionBindings()
                        for b in all_bindings:
                            prev_mat_path.append(b.GetMaterialPath())
                            rel = b.GetBindingRel()
                            prev_mat_strength.append(
                                UsdShade.MaterialBindingAPI.GetMaterialBindingStrength(rel) if rel else self._strength
                            )

            # apply new material
            index = 0
            for path in can_apply_paths:
                _, prim, collection = self._get_path_type(path, stage)
                if prim:
                    material_prim = stage.GetPrimAtPath(material_path[index]) if material_path[index] else None
                    binding_api = UsdShade.MaterialBindingAPI(prim)
                    self._bind(binding_api, material_prim, material_strength[index], collection)
                    index = index + 1
            
            if failed_to_bind_prim_paths:
                message = "Failed to bind material to the following prims as they are instance proxies:\n"
                for path in failed_to_bind_prim_paths:
                    message += f"\n{str(path)}"
                
                post_notification(message)

            return prev_mat_path, prev_mat_strength
        return None

    def _bind_material(self, material_path, strength):
        if isinstance(self._path, list):
            return self._bind_material_list(self._path, material_path, strength)
        return self._bind_material_list([self._path], material_path, strength)

    def do(self):
        self._prev_material, self._prev_strength = self._bind_material(self._material_path, self._strength)

    def undo(self):
        self._bind_material(self._prev_material, self._prev_strength)


class SetMaterialStrengthCommand(omni.kit.commands.Command):
    """
    Set material binding strength undoable **Command**.

    Args:
        rel: Material binding relationship.
        strength (float): Strength.
    """

    def __init__(self, rel, strength):
        self._rel = rel
        self._strength = strength
        self._prev_strength = UsdShade.MaterialBindingAPI.GetMaterialBindingStrength(rel)

    def _set_strength(self, rel, strength):
        if rel:
            UsdShade.MaterialBindingAPI.SetMaterialBindingStrength(rel, strength)

    def do(self):
        self._set_strength(self._rel, self._strength)

    def undo(self):
        self._set_strength(self._rel, self._prev_strength)


class TransformPrimCommand(omni.kit.commands.Command):
    """
    Transform primitive undoable **Command**.

    Args:
        path (str): Prim path.
        new_transform_matrix: New transform matrix.
        old_transform_matrix: Optional old transform matrix to undo to. If `None` use current transform.
    """

    def __init__(
        self,
        path: str,
        new_transform_matrix: Gf.Matrix4d,
        old_transform_matrix: Gf.Matrix4d = None,
        time_code: Usd.TimeCode = Usd.TimeCode.Default(),
        had_transform_at_key: bool = False,
        usd_context_name: str = "",
    ):
        carb.log_verbose("init Transform Command")
        self._new_transform_matrix = new_transform_matrix
        self._path = path
        self._old_transform_matrix = old_transform_matrix
        self._time_code = time_code
        self._had_transform_at_key = had_transform_at_key
        self._usd_context_name = usd_context_name
        if self._old_transform_matrix == None:
            prim = self._stage().GetPrimAtPath(self._path)
            xformable = UsdGeom.Xformable(prim)
            self._old_transform_matrix = xformable.GetLocalTransformation(time_code)

    def _stage(self):
        return omni.usd.get_context(self._usd_context_name).get_stage()

    def _set_value_with_precision(
        self,
        xform_op,
        value,
        time_code: Usd.TimeCode = Usd.TimeCode.Default(),
        skip_equal_set_for_timesample: bool = False,
    ):
        stage = self._stage()
        set_time_code = time_code
        old_value = xform_op.Get(set_time_code)

        if not self._xform_op_is_time_sampled(xform_op):
            set_time_code = Usd.TimeCode.Default()

        if old_value is None:
            if not set_time_code.IsDefault():
                omni.usd.copy_timesamples_from_weaker_layer(stage, xform_op.GetAttr())
            return xform_op.Set(value, set_time_code)
        else:
            value_type = type(old_value)
            if skip_equal_set_for_timesample:
                if not set_time_code.IsDefault() and not self._has_time_sample(xform_op, set_time_code):
                    if Gf.IsClose(value_type(value), old_value, 1e-6):
                        return False
            if not set_time_code.IsDefault():
                omni.usd.copy_timesamples_from_weaker_layer(stage, xform_op.GetAttr())
            return xform_op.Set(value_type(value), set_time_code)

    def _xform_op_is_time_sampled(self, xform_op: UsdGeom.XformOp):
        return xform_op.GetNumTimeSamples() > 0

    def _has_time_sample(self, xform_op, time_code):
        if time_code.IsDefault():
            return False
        time_samples = xform_op.GetTimeSamples()
        time_code_value = time_code.GetValue()
        if round(time_code_value) != time_code_value:
            carb.log_warn(
                f"Error: try to identify attribute {str(xform_op.GetName())} has time sample on a non round key {time_code_value}"
            )
            return False
        if time_code_value in time_samples:
            return True
        return False

    def _xform_is_time_sampled(self, xform: UsdGeom.Xformable):
        xform_ops = xform.GetOrderedXformOps()
        for xform_op in xform_ops:
            if self._xform_op_is_time_sampled(xform_op):
                return True
        return False

    def _set_transform_matrix(
        self, matrix, time_code: Usd.TimeCode = Usd.TimeCode.Default(), skip_equal_set_for_timesample: bool = False
    ):
        Sdf.BeginChangeBlock()  # Use non-RAII style Sdf.ChangeBlock because it *may* need to be released in create_if_not_exist

        # re-fetch prim every time in case redoing on a deleted then restored prim
        stage = self._stage()
        prim = stage.GetPrimAtPath(self._path)
        if prim:
            xform = UsdGeom.Xformable(prim)

            found_transfrom_op = False
            xform_ops = xform.GetOrderedXformOps()
            for xform_op in xform.GetOrderedXformOps():
                if xform_op.GetOpType() == UsdGeom.XformOp.TypeTransform:
                    found_transfrom_op = True
                    # This is here to prevent the TransformGizmo from writing a translation, rotation and scale on every
                    # key where it sets a value. At some point we should revisit the gizmo to simplify the logic, and
                    # start setting only the transform value the user intends.
                    self._set_value_with_precision(xform_op, matrix, time_code, skip_equal_set_for_timesample)
                    break
            if not found_transfrom_op:
                _, scale_orient_mat_unused, scale, rot_mat, translation, persp_mat_unused = matrix.Factor()
                rot_mat.Orthonormalize(False)
                rotation = rot_mat.ExtractRotation()

                # Don't use UsdGeomXformCommonAPI. It can only manipulate a very limited subset of xformOpOrder combinations
                # Do it manually as non-destructively as possible
                new_xform_ops = []

                def find_or_add(xform_op_type, create_if_not_exist, precision, op_suffix=""):
                    # Look up the xformOp directly. It is possible that the xformOp exists
                    # as prim attribute but not listed in xform_ops. AddXformOp will fail if called.

                    # basically UsdGeomXformOp::GetOpName but it has no python binding
                    type_token = UsdGeom.XformOp.GetOpTypeToken(xform_op_type)
                    attr_name = "xformOp:" + type_token
                    if op_suffix:
                        attr_name += f":{op_suffix}"

                    xform_op_attr = prim.GetAttribute(attr_name)
                    if xform_op_attr:
                        xform_op = UsdGeom.XformOp(xform_op_attr)
                        if xform_op:
                            return True, xform_op, xform_op.GetPrecision()

                    if create_if_not_exist:
                        # It is not safe to create new xformOps inside of SdfChangeBlocks, since
                        # new attribute creation via anything above Sdf API requires the PcpCache
                        # to be up to date. Flush the current change block before creating
                        # the new xformOp.
                        Sdf.EndChangeBlock()

                        xform_op = xform.AddXformOp(xform_op_type, precision, op_suffix)
                        precision = xform_op.GetPrecision()

                        # Create a new change block to batch the subsequent authoring operations
                        # where possible.
                        Sdf.BeginChangeBlock()
                        return True, xform_op, precision
                    return False, None, precision

                def get_first_rotate_type():
                    for xform_op in xform_ops:
                        op_type = xform_op.GetOpType()
                        if op_type >= UsdGeom.XformOp.TypeRotateX and op_type <= UsdGeom.XformOp.TypeOrient:
                            return op_type, xform_op.GetPrecision()
                    return UsdGeom.XformOp.TypeInvalid, UsdGeom.XformOp.PrecisionFloat

                def decompose_and_set_value(
                    rotation_type,
                    axis_0,
                    axis_1,
                    axis_2,
                    x_index,
                    y_index,
                    z_index,
                    precision,
                    timecode: Usd.TimeCode = Usd.TimeCode.Default(),
                    skip_equal_set_for_timesample: bool = False,
                ):
                    ret = False
                    angles = rotation.Decompose(axis_0, axis_1, axis_2)
                    rotate = Gf.Vec3f(angles[x_index], angles[y_index], angles[z_index])
                    found, xform_op, precision = find_or_add(rotation_type, True, precision)
                    if found:
                        ret = self._set_value_with_precision(xform_op, rotate, timecode, skip_equal_set_for_timesample)
                        new_xform_ops.append(xform_op)
                    return ret

                # Set translation
                precision = UsdGeom.XformOp.PrecisionDouble
                found, xform_op, precision = find_or_add(UsdGeom.XformOp.TypeTranslate, True, precision)
                if found:
                    self._set_value_with_precision(xform_op, translation, time_code, skip_equal_set_for_timesample)
                    new_xform_ops.append(xform_op)

                # Set pivot
                precision = UsdGeom.XformOp.PrecisionFloat
                has_pivot, pivot_op, precision = find_or_add(UsdGeom.XformOp.TypeTranslate, False, precision, "pivot")
                if has_pivot:
                    new_xform_ops.append(pivot_op)

                # Set rotation
                precision = UsdGeom.XformOp.PrecisionFloat
                first_rotate_op_type, precision = get_first_rotate_type()

                if first_rotate_op_type == UsdGeom.XformOp.TypeInvalid:
                    first_rotate_op_type = get_default_rotation_order_type(prim.IsA(UsdGeom.Camera))

                if (
                    first_rotate_op_type == UsdGeom.XformOp.TypeRotateX
                    or first_rotate_op_type == UsdGeom.XformOp.TypeRotateY
                    or first_rotate_op_type == UsdGeom.XformOp.TypeRotateZ
                ):
                    angles = rotation.Decompose(Gf.Vec3d.ZAxis(), Gf.Vec3d.YAxis(), Gf.Vec3d.XAxis())
                    rotateZYX = Gf.Vec3f(angles[2], angles[1], angles[0])
                    found, xform_op, precision = find_or_add(UsdGeom.XformOp.TypeRotateZ, True, precision)
                    if found:
                        self._set_value_with_precision(xform_op, rotateZYX[2], time_code, skip_equal_set_for_timesample)
                        new_xform_ops.append(xform_op)
                    found, xform_op, precision = find_or_add(UsdGeom.XformOp.TypeRotateY, True, precision)
                    if found:
                        self._set_value_with_precision(xform_op, rotateZYX[1], time_code, skip_equal_set_for_timesample)
                        new_xform_ops.append(xform_op)
                        found, xform_op, precision = find_or_add(UsdGeom.XformOp.TypeRotateX, True, precision)
                    if found:
                        self._set_value_with_precision(xform_op, rotateZYX[0], time_code, skip_equal_set_for_timesample)
                        new_xform_ops.append(xform_op)
                elif first_rotate_op_type == UsdGeom.XformOp.TypeRotateZYX:
                    decompose_and_set_value(
                        first_rotate_op_type,
                        Gf.Vec3d.XAxis(),
                        Gf.Vec3d.YAxis(),
                        Gf.Vec3d.ZAxis(),
                        0,
                        1,
                        2,
                        precision,
                        time_code,
                        skip_equal_set_for_timesample,
                    )
                elif first_rotate_op_type == UsdGeom.XformOp.TypeRotateXZY:
                    decompose_and_set_value(
                        first_rotate_op_type,
                        Gf.Vec3d.YAxis(),
                        Gf.Vec3d.ZAxis(),
                        Gf.Vec3d.XAxis(),
                        2,
                        0,
                        1,
                        precision,
                        time_code,
                        skip_equal_set_for_timesample,
                    )
                elif first_rotate_op_type == UsdGeom.XformOp.TypeRotateYXZ:
                    decompose_and_set_value(
                        first_rotate_op_type,
                        Gf.Vec3d.ZAxis(),
                        Gf.Vec3d.XAxis(),
                        Gf.Vec3d.YAxis(),
                        1,
                        2,
                        0,
                        precision,
                        time_code,
                        skip_equal_set_for_timesample,
                    )
                elif first_rotate_op_type == UsdGeom.XformOp.TypeRotateYZX:
                    decompose_and_set_value(
                        first_rotate_op_type,
                        Gf.Vec3d.XAxis(),
                        Gf.Vec3d.ZAxis(),
                        Gf.Vec3d.YAxis(),
                        0,
                        2,
                        1,
                        precision,
                        time_code,
                        skip_equal_set_for_timesample,
                    )
                elif first_rotate_op_type == UsdGeom.XformOp.TypeRotateZXY:
                    decompose_and_set_value(
                        first_rotate_op_type,
                        Gf.Vec3d.YAxis(),
                        Gf.Vec3d.XAxis(),
                        Gf.Vec3d.ZAxis(),
                        1,
                        0,
                        2,
                        precision,
                        time_code,
                        skip_equal_set_for_timesample,
                    )
                elif first_rotate_op_type == UsdGeom.XformOp.TypeOrient:
                    found, xform_op, precision = find_or_add(first_rotate_op_type, False, precision)
                    if found:
                        self._set_value_with_precision(
                            xform_op, rotation.GetQuat(), time_code, skip_equal_set_for_timesample
                        )
                        new_xform_ops.append(xform_op)
                else:  # first_rotate_op_type == UsdGeom.XformOp.TypeRotateXYZ and all else
                    decompose_and_set_value(
                        UsdGeom.XformOp.TypeRotateXYZ,
                        Gf.Vec3d.ZAxis(),
                        Gf.Vec3d.YAxis(),
                        Gf.Vec3d.XAxis(),
                        2,
                        1,
                        0,
                        precision,
                        time_code,
                        skip_equal_set_for_timesample,
                    )

                # Set scale
                precision = UsdGeom.XformOp.PrecisionFloat
                found, xform_op, precision = find_or_add(UsdGeom.XformOp.TypeScale, True, precision)
                if found:
                    self._set_value_with_precision(xform_op, Gf.Vec3f(scale), time_code, skip_equal_set_for_timesample)
                    new_xform_ops.append(xform_op)

                # Set inverse pivot
                if has_pivot:
                    # Assume the last xformOps is the pivot
                    new_xform_ops.append(xform_ops[-1])

                xform.SetXformOpOrder(new_xform_ops, xform.GetResetXformStack())

        Sdf.EndChangeBlock()

    def _clear_transform_at_time(self, time_code: Usd.TimeCode):
        if time_code.IsDefault():
            return
        stage = self._stage()
        prim = stage.GetPrimAtPath(self._path)
        if prim:
            xform = UsdGeom.Xformable(prim)
            xform_ops = xform.GetOrderedXformOps()
            for xform_op in xform.GetOrderedXformOps():
                if self._has_time_sample(xform_op, time_code):
                    xform_op.GetAttr().ClearAtTime(time_code)

    def _switch_edit_tgt(self):
        stage = self._stage()
        def_layer, prim_spec = omni.usd.find_spec_on_session_or_its_sublayers(stage, self._path)
        if not prim_spec or not def_layer:
            return Usd.EditContext(stage)

        if prim_spec.specifier == Sdf.SpecifierDef:
            return Usd.EditContext(stage, Usd.EditTarget(def_layer))
        else:
            return Usd.EditContext(stage)

    def do(self):
        with self._switch_edit_tgt() as context:
            self._set_transform_matrix(self._new_transform_matrix, self._time_code, True)

    def undo(self):
        # Note the undo will not restore the exact original state if in do() new xformOp is created or reordered
        # it only guarantees the resolved transform is the same.
        # The better way to do this is moving Transfrom Gizmo into python and save original primSpec out on do()
        with self._switch_edit_tgt() as context:
            prim_transform_is_time_sampled = False
            stage = self._stage()
            prim = stage.GetPrimAtPath(self._path)
            if prim:
                xform = UsdGeom.Xformable(prim)
                prim_transform_is_time_sampled = self._xform_is_time_sampled(xform)
            if self._time_code.IsDefault() or self._had_transform_at_key or (not prim_transform_is_time_sampled):
                self._set_transform_matrix(self._old_transform_matrix, self._time_code, True)
            else:
                self._clear_transform_at_time(self._time_code)


class TransformPrimSRTCommand(omni.kit.commands.Command):
    """
    Transform primitive undoable **Command**.

    Args:
        path (str): Prim path.
        new_translation (Gf.Vec3d): New local translation.
        new_rotation_euler (Gf.Vec3d): New local rotation euler angles (in degree).
        new_scale (Gf.Vec3d): New scale.
        new_rotation_order (Gf.Vec3i): New rotation order (e.g. (0, 1, 2) means XYZ). Set to None to stay the same.
        old_translation (Gf.Vec3d): Old local translation. Leave to None to use current value.
        old_rotation_euler (Gf.Vec3d): Old local rotation euler angles. Leave to None to use current value.
        old_rotation_order (Gf.Vec3i): Old local rotation order. Leave to None to use current value.
        old_scale (Gf.Vec3d): Old scale. Leave to None to use current value.
        time_code (Usd.TimeCode): TimeCode to set transform to.
        had_transform_at_key (bool): If there's key for transfrom.
        usd_context_name (str): Usd context name to run the command on.
    """

    def __init__(
        self,
        path: str,
        new_translation: Gf.Vec3d = None,
        new_rotation_euler: Gf.Vec3d = None,
        new_scale: Gf.Vec3d = None,
        new_rotation_order: Gf.Vec3i = None,
        old_translation: Gf.Vec3d = None,
        old_rotation_euler: Gf.Vec3d = None,
        old_rotation_order: Gf.Vec3i = None,
        old_scale: Gf.Vec3d = None,
        time_code: Usd.TimeCode = Usd.TimeCode.Default(),
        had_transform_at_key: bool = False,
        usd_context_name: str = "",
    ):
        carb.log_verbose("init Transform SRT Command")
        self._settings = carb.settings.get_settings()
        self._path = path
        self._new_translation = new_translation
        self._new_rotation_euler = new_rotation_euler
        self._new_rotation_order = new_rotation_order
        self._new_scale = new_scale
        self._old_translation = old_translation
        self._old_rotation_euler = old_rotation_euler
        self._old_rotation_order = old_rotation_order
        self._old_scale = old_scale
        self._time_code = time_code
        self._had_transform_at_key = had_transform_at_key
        self._usd_context = omni.usd.get_context(usd_context_name)
        if (
            self._old_translation is None
            or self._old_rotation_euler is None
            or self._old_rotation_order is None
            or self._old_scale is None
        ):
            stage = self._usd_context.get_stage()
            prim = stage.GetPrimAtPath(self._path)
            if prim:
                (
                    old_scale,
                    old_rotation_euler,
                    old_rotation_order,
                    old_translation,
                ) = omni.usd.get_local_transform_SRT(prim, self._time_code)
                if self._old_scale is None:
                    self._old_scale = old_scale
                if self._old_rotation_euler is None:
                    self._old_rotation_euler = old_rotation_euler
                if self._old_rotation_order is None:
                    self._old_rotation_order = old_rotation_order
                if self._old_translation is None:
                    self._old_translation = old_translation
            else:
                carb.log_error("Invalid prim path to transform")

            if self._new_translation is None:
                self._new_translation = self._old_translation
            if self._new_rotation_euler is None:
                self._new_rotation_euler = self._old_rotation_euler
            if self._new_rotation_order is None:
                self._new_rotation_order = self._old_rotation_order
            if self._new_scale is None:
                self._new_scale = self._old_scale

    @carb.profiler.profile
    def _set_value_with_precision(
        self,
        xform_op,
        value,
        time_code: Usd.TimeCode = Usd.TimeCode.Default(),
        skip_equal_set_for_timesample: bool = False,
    ):
        set_time_code = time_code
        old_value = xform_op.Get(set_time_code)

        if not self._xform_op_is_time_sampled(xform_op):
            set_time_code = Usd.TimeCode.Default()

        if old_value is None:
            if not set_time_code.IsDefault():
                omni.usd.copy_timesamples_from_weaker_layer(self._usd_context.get_stage(), xform_op.GetAttr())

            attr = xform_op.GetAttr()
            type_name = attr.GetTypeName()
            default_value = type_name.defaultValue

            return xform_op.Set(type(default_value)(value), set_time_code)
        else:
            value_type = type(old_value)
            if skip_equal_set_for_timesample:
                if not set_time_code.IsDefault() and not self._has_time_sample(xform_op, set_time_code):
                    if Gf.IsClose(value_type(value), old_value, 1e-6):
                        return False
            if not set_time_code.IsDefault():
                omni.usd.copy_timesamples_from_weaker_layer(self._usd_context.get_stage(), xform_op.GetAttr())
            return xform_op.Set(value_type(value), set_time_code)

    def _xform_op_is_time_sampled(self, xform_op: UsdGeom.XformOp):
        return xform_op.GetNumTimeSamples() > 0

    def _has_time_sample(self, xform_op, time_code):
        if time_code.IsDefault():
            return False
        time_samples = xform_op.GetTimeSamples()
        time_code_value = time_code.GetValue()
        if round(time_code_value) != time_code_value:
            carb.log_warn(
                f"Error: try to identify attribute {str(xform_op.GetName())} has time sample on a non round key {time_code_value}"
            )
            return False
        if time_code_value in time_samples:
            return True
        return False

    def _xform_is_time_sampled(self, xform: UsdGeom.Xformable):
        xform_ops = xform.GetOrderedXformOps()
        for xform_op in xform_ops:
            if self._xform_op_is_time_sampled(xform_op):
                return True
        return False

    def _construct_transfrom_matrix_from_SRT(
        self, translation: Gf.Vec3d, rotation_euler: Gf.Vec3d, rotation_order: Gf.Vec3i, scale: Gf.Vec3d
    ):
        trans_mtx = Gf.Matrix4d()
        rot_mtx = Gf.Matrix4d()
        scale_mtx = Gf.Matrix4d()

        trans_mtx.SetTranslate(translation)

        axes = [Gf.Vec3d.XAxis(), Gf.Vec3d.YAxis(), Gf.Vec3d.ZAxis()]
        rotation = (
            Gf.Rotation(axes[rotation_order[0]], rotation_euler[rotation_order[0]])
            * Gf.Rotation(axes[rotation_order[1]], rotation_euler[rotation_order[1]])
            * Gf.Rotation(axes[rotation_order[2]], rotation_euler[rotation_order[2]])
        )
        rot_mtx.SetRotate(rotation)
        scale_mtx.SetScale(scale)
        return scale_mtx * rot_mtx * trans_mtx

    @carb.profiler.profile
    def _set_transform_srt(
        self,
        translation: Gf.Vec3d,
        rotation_euler: Gf.Vec3d,
        rotation_order: Gf.Vec3i,
        scale: Gf.Vec3d,
        time_code: Usd.TimeCode = Usd.TimeCode.Default(),
        skip_equal_set_for_timesample: bool = False,
    ):
        Sdf.BeginChangeBlock()  # Use non-RAII style Sdf.ChangeBlock because it *may* need to be released in create_if_not_exist

        # re-fetch prim every time in case redoing on a deleted then restored prim
        stage = self._usd_context.get_stage()
        prim = stage.GetPrimAtPath(self._path)
        if prim:
            xform = UsdGeom.Xformable(prim)

            found_transfrom_op = False
            xform_ops = xform.GetOrderedXformOps()
            for xform_op in xform.GetOrderedXformOps():
                if xform_op.GetOpType() == UsdGeom.XformOp.TypeTransform:
                    found_transfrom_op = True
                    matrix = self._construct_transfrom_matrix_from_SRT(
                        translation, rotation_euler, rotation_order, scale
                    )
                    self._set_value_with_precision(xform_op, matrix, time_code, skip_equal_set_for_timesample)
                    break
            if not found_transfrom_op:
                # Don't use UsdGeomXformCommonAPI. It can only manipulate a very limited subset of xformOpOrder combinations
                # Do it manually as non-destructively as possible
                new_xform_ops = []

                @carb.profiler.profile
                def find_or_add(xform_op_type, create_if_not_exist, precision, op_suffix=""):
                    # Look up the xformOp directly. It is possible that the xformOp exists
                    # as prim attribute but not listed in xform_ops. AddXformOp will fail if called.

                    # basically UsdGeomXformOp::GetOpName but it has no python binding
                    type_token = UsdGeom.XformOp.GetOpTypeToken(xform_op_type)
                    attr_name = "xformOp:" + type_token
                    if op_suffix:
                        attr_name += f":{op_suffix}"

                    xform_op_attr = prim.GetAttribute(attr_name)
                    if xform_op_attr:
                        xform_op = UsdGeom.XformOp(xform_op_attr)
                        if xform_op:
                            return True, xform_op, xform_op.GetPrecision()

                    if create_if_not_exist:
                        # It is not safe to create new xformOps inside of SdfChangeBlocks, since
                        # new attribute creation via anything above Sdf API requires the PcpCache
                        # to be up to date. Flush the current change block before creating
                        # the new xformOp.
                        Sdf.EndChangeBlock()

                        xform_op = xform.AddXformOp(xform_op_type, precision, op_suffix)
                        precision = xform_op.GetPrecision()

                        # Create a new change block to batch the subsequent authoring operations
                        # where possible.
                        Sdf.BeginChangeBlock()
                        return True, xform_op, precision
                    return False, None, precision

                @carb.profiler.profile
                def get_first_rotate_type():
                    for xform_op in xform_ops:
                        op_type = xform_op.GetOpType()
                        if op_type >= UsdGeom.XformOp.TypeRotateX and op_type <= UsdGeom.XformOp.TypeOrient:
                            return op_type, xform_op.GetPrecision()
                    return UsdGeom.XformOp.TypeInvalid, UsdGeom.XformOp.PrecisionFloat

                @carb.profiler.profile
                def set_euler_value(
                    rotation_type,
                    precision,
                    timecode: Usd.TimeCode = Usd.TimeCode.Default(),
                    skip_equal_set_for_timesample: bool = False,
                ):
                    ret = False
                    found, xform_op, precision = find_or_add(rotation_type, True, precision)
                    if found:
                        ret = self._set_value_with_precision(
                            xform_op, rotation_euler, timecode, skip_equal_set_for_timesample
                        )
                        new_xform_ops.append(xform_op)
                    return ret

                # Set translation
                precision = UsdGeom.XformOp.PrecisionDouble
                found, xform_op, precision = find_or_add(UsdGeom.XformOp.TypeTranslate, True, precision)
                if found:
                    self._set_value_with_precision(xform_op, translation, time_code, skip_equal_set_for_timesample)
                    new_xform_ops.append(xform_op)

                # Set pivot
                precision = UsdGeom.XformOp.PrecisionFloat
                has_pivot, pivot_op, precision = find_or_add(UsdGeom.XformOp.TypeTranslate, False, precision, "pivot")
                if has_pivot:
                    new_xform_ops.append(pivot_op)

                # Set rotation
                precision = UsdGeom.XformOp.PrecisionFloat
                first_rotate_op_type, precision = get_first_rotate_type()
                rotation_order_to_type_map = {
                    Gf.Vec3i(0, 1, 2): UsdGeom.XformOp.TypeRotateXYZ,
                    Gf.Vec3i(0, 2, 1): UsdGeom.XformOp.TypeRotateXZY,
                    Gf.Vec3i(1, 0, 2): UsdGeom.XformOp.TypeRotateYXZ,
                    Gf.Vec3i(1, 2, 0): UsdGeom.XformOp.TypeRotateYZX,
                    Gf.Vec3i(2, 0, 1): UsdGeom.XformOp.TypeRotateZXY,
                    Gf.Vec3i(2, 1, 0): UsdGeom.XformOp.TypeRotateZYX,
                }

                if first_rotate_op_type == UsdGeom.XformOp.TypeInvalid:
                    default_xform_ops = self._settings.get_as_string(
                        PERSISTENT_SETTINGS_PREFIX + "/app/primCreation/DefaultXformOpType"
                    )

                    if default_xform_ops == "Scale, Orient, Translate":
                        first_rotate_op_type = UsdGeom.XformOp.TypeOrient
                    else:
                        # TODO what if default_xform_ops == "Transform"?
                        first_rotate_op_type = rotation_order_to_type_map.get(
                            rotation_order, UsdGeom.XformOp.TypeInvalid
                        )
                if (
                    first_rotate_op_type == UsdGeom.XformOp.TypeRotateX
                    or first_rotate_op_type == UsdGeom.XformOp.TypeRotateY
                    or first_rotate_op_type == UsdGeom.XformOp.TypeRotateZ
                ):
                    # Add in reverse order
                    axis_type = [
                        UsdGeom.XformOp.TypeRotateX,
                        UsdGeom.XformOp.TypeRotateY,
                        UsdGeom.XformOp.TypeRotateZ,
                    ]
                    for i in range(2, -1, -1):
                        axis = rotation_order[i]
                        found, xform_op, precision = find_or_add(axis_type[axis], True, precision)
                        if found:
                            self._set_value_with_precision(
                                xform_op, rotation_euler[axis], time_code, skip_equal_set_for_timesample
                            )
                            new_xform_ops.append(xform_op)
                elif (
                    first_rotate_op_type == UsdGeom.XformOp.TypeRotateXYZ
                    or first_rotate_op_type == UsdGeom.XformOp.TypeRotateXZY
                    or first_rotate_op_type == UsdGeom.XformOp.TypeRotateYXZ
                    or first_rotate_op_type == UsdGeom.XformOp.TypeRotateYZX
                    or first_rotate_op_type == UsdGeom.XformOp.TypeRotateZXY
                    or first_rotate_op_type == UsdGeom.XformOp.TypeRotateZYX
                ):
                    provided_rotation_order = rotation_order_to_type_map.get(rotation_order, first_rotate_op_type)
                    if provided_rotation_order != first_rotate_op_type:
                        carb.log_warn(
                            f"Existing rotation order {first_rotate_op_type} on prim {self._path} is different than desired {provided_rotation_order}, overriding..."
                        )

                    set_euler_value(
                        provided_rotation_order,
                        precision,
                        time_code,
                        skip_equal_set_for_timesample,
                    )
                elif first_rotate_op_type == UsdGeom.XformOp.TypeOrient:
                    found, xform_op, precision = find_or_add(first_rotate_op_type, True, precision)
                    if found:
                        axes = [Gf.Vec3d.XAxis(), Gf.Vec3d.YAxis(), Gf.Vec3d.ZAxis()]
                        rotation = (
                            Gf.Rotation(axes[rotation_order[0]], rotation_euler[rotation_order[0]])
                            * Gf.Rotation(axes[rotation_order[1]], rotation_euler[rotation_order[1]])
                            * Gf.Rotation(axes[rotation_order[2]], rotation_euler[rotation_order[2]])
                        )
                        self._set_value_with_precision(
                            xform_op, rotation.GetQuat(), time_code, skip_equal_set_for_timesample
                        )
                        new_xform_ops.append(xform_op)
                    pass
                else:  # first_rotate_op_type == UsdGeom.XformOp.TypeRotateXYZ and all else
                    carb.log_error(f"Failed to determine rotation order {first_rotate_op_type}")

                # Set scale
                precision = UsdGeom.XformOp.PrecisionFloat
                found, xform_op, precision = find_or_add(UsdGeom.XformOp.TypeScale, True, precision)
                if found:
                    self._set_value_with_precision(xform_op, Gf.Vec3f(scale), time_code, skip_equal_set_for_timesample)
                    new_xform_ops.append(xform_op)

                # Set inverse pivot
                if has_pivot:
                    # Assume the last xformOps is the pivot
                    new_xform_ops.append(xform_ops[-1])

                xform.SetXformOpOrder(new_xform_ops, xform.GetResetXformStack())

        carb.profiler.begin(1, "Sdf.EndChangeBlock()")
        # Calling EndChangeBlock will trigger pending USD notices to be sent out.
        # All USD notice handler will spend time in here.
        # In this case it takes half of the function time (~0.4ms at the time of this profiling)
        Sdf.EndChangeBlock()
        carb.profiler.end(1)

    def _clear_transform_at_time(self, time_code: Usd.TimeCode):
        if time_code.IsDefault():
            return
        stage = self._usd_context.get_stage()
        prim = stage.GetPrimAtPath(self._path)
        if prim:
            xform = UsdGeom.Xformable(prim)
            for xform_op in xform.GetOrderedXformOps():
                if self._has_time_sample(xform_op, time_code):
                    xform_op.GetAttr().ClearAtTime(time_code)

    def _switch_edit_tgt(self):
        stage = self._usd_context.get_stage()
        def_layer, prim_spec = omni.usd.find_spec_on_session_or_its_sublayers(stage, self._path)
        if not prim_spec or not def_layer:
            return Usd.EditContext(stage)

        if prim_spec.specifier == Sdf.SpecifierDef:
            return Usd.EditContext(stage, Usd.EditTarget(def_layer))
        else:
            return Usd.EditContext(stage)

    def do(self):
        with self._switch_edit_tgt() as context:
            self._set_transform_srt(
                self._new_translation,
                self._new_rotation_euler,
                self._new_rotation_order,
                self._new_scale,
                self._time_code,
                True,
            )

    def undo(self):
        # Note the undo will not restore the exact original state if in do() new xformOp is created or reordered
        # it only guarantees the resolved transform is the same.
        # The better way to do this is moving Transfrom Gizmo into python and save original primSpec out on do()
        with self._switch_edit_tgt() as context:
            prim_transform_is_time_sampled = False
            stage = self._usd_context.get_stage()
            prim = stage.GetPrimAtPath(self._path)
            if prim:
                xform = UsdGeom.Xformable(prim)
                prim_transform_is_time_sampled = self._xform_is_time_sampled(xform)
            if self._time_code.IsDefault() or self._had_transform_at_key or (not prim_transform_is_time_sampled):
                self._set_transform_srt(
                    self._old_translation,
                    self._old_rotation_euler,
                    self._old_rotation_order,
                    self._old_scale,
                    self._time_code,
                    True,
                )
            else:
                self._clear_transform_at_time(self._time_code)


class TransformPrimsCommand(omni.kit.commands.Command):
    """
    Transform multiple primitives undoable **Command**.

    Undo/Redo grouping handled automatically.

    Args:
        prims_to_transform: List of primitive to transform in a tuple of (path, new_transform, old_transform).
    """

    def __init__(self, prims_to_transform: List[Tuple[str, Gf.Matrix4d, Gf.Matrix4d, Usd.TimeCode]]):
        self._prims_to_transform = prims_to_transform.copy()

    def do(self):
        for p in self._prims_to_transform:
            omni.kit.commands.execute(
                "TransformPrim",
                path=p[0],
                new_transform_matrix=p[1],
                old_transform_matrix=p[2],
                time_code=p[3],
                had_transform_at_key=p[4],
            )

    def undo(self):
        pass


class TransformPrimsSRTCommand(omni.kit.commands.Command):
    """
    Transform multiple primitives undoable **Command**.

    Undo/Redo grouping handled automatically.

    Args:
        prims_to_transform: List of primitive to transform in a tuple of
                            (path,
                            new_translation,
                            new_rotation_euler,
                            new_rotation_order,
                            new_scale,
                            old_translation,
                            old_rotation_euler,
                            old_rotation_order,
                            old_scale,
                            time_code,
                            had_transform_at_key).
    """

    def __init__(
        self,
        prims_to_transform: List[
            Tuple[
                str, Gf.Vec3d, Gf.Vec3d, Gf.Vec3i, Gf.Vec3d, Gf.Vec3d, Gf.Vec3d, Gf.Vec3i, Gf.Vec3d, Usd.TimeCode, bool
            ]
        ],
    ):
        self._prims_to_transform = prims_to_transform.copy()

    def do(self):
        for p in self._prims_to_transform:
            omni.kit.commands.execute(
                "TransformPrimSRT",
                path=p[0],
                new_translation=p[1],
                new_rotation_euler=p[2],
                new_rotation_order=p[3],
                new_scale=p[4],
                old_translation=p[5],
                old_rotation_euler=p[6],
                old_rotation_order=p[7],
                old_scale=p[8],
                time_code=p[9],
                had_transform_at_key=p[10],
            )

    def undo(self):
        pass


class FramePrimsCommand(omni.kit.commands.Command):
    """
    Transform a primitive to encompass the bounds of a list of paths.

    Args:
        prim_to_move: Path to the primitive that is being moved.
        prims_to_frame(Sequence[Union[str, Sdf.Path]]): Sequence of primitives to use to calculate the bounds to frame.
        time_code(Usd.TimeCode): Timecode to set values at.
        usd_context_name(str): Name of the usd context to work on.
        aspect_ratio(float): Width / Height of the final image.
        use_horizontal_fov(bool): Whether to use a camera's horizontal or vertical field of view for framing.
        horizontal_fov(float): Default horizontal field-of-view to use for framing if one cannot be calculated.
        zoom(float): Final zoom in or out of the framed box. Values above 0.5 move further away and below 0.5 go closer.
    """

    def __init__(
        self,
        prim_to_move: Union[str, Sdf.Path],
        prims_to_frame: Sequence[Union[str, Sdf.Path]] = None,
        time_code: Usd.TimeCode = None,
        usd_context_name: str = "",
        aspect_ratio: float = 1,
        use_horizontal_fov: bool = None,
        zoom: float = 0.45,
        horizontal_fov: float = 0.20656116130367255,
    ):
        self.__usd_context_name = usd_context_name
        self.__prim_to_move = prim_to_move
        self.__time_code = time_code if time_code is not None else Usd.TimeCode.Default()
        self.__prims_to_frame = prims_to_frame if prims_to_frame is not None else [Sdf.Path.absoluteRootPath.pathString]
        self.__created_property = False
        self.__aspect_ratio = abs(aspect_ratio) or 1.0
        self.__horizontal_fov = horizontal_fov
        self.__use_horizontal_fov = use_horizontal_fov
        self.__zoom = zoom

    def __compute_local_transform(self, stage: Usd.Stage):
        prim = stage.GetPrimAtPath(self.__prim_to_move)
        if not prim:
            carb.log_warn(f"Framing of UsdPrims failed, {self.__prim_to_move} doesn't exist")
            return None, None, None, None

        local_xform, world_xform = None, None
        xformable = UsdGeom.Xformable(prim)
        if xformable:
            local_xform = xformable.GetLocalTransformation(self.__time_code)

        imageable = UsdGeom.Imageable(prim)
        if imageable:
            parent_xform = imageable.ComputeParentToWorldTransform(self.__time_code)
            if not local_xform:
                world_xform = imageable.ComputeLocalToWorldTransform(self.__time_code)
                local_xform = world_xform * parent_xform.GetInverse()
            if not world_xform:
                world_xform = parent_xform * local_xform
            return local_xform, parent_xform, world_xform, prim

        carb.log_warn(f"Framing of UsdPrims failed, {self.__prim_to_move} isn't UsdGeom.Xformable or UsdGeom.Imageable")
        return None, None, None, None

    def __calculate_distance(self, radius, prim):
        camera = UsdGeom.Camera(prim)
        h_fov_rad, v_fov_rad = self.__horizontal_fov, self.__horizontal_fov
        if camera:
            focalLength = camera.GetFocalLengthAttr()
            h_aperture = camera.GetHorizontalApertureAttr()
            v_aperture = camera.GetVerticalApertureAttr()
            if focalLength and (h_aperture or v_aperture):
                focalLength = focalLength.Get(self.__time_code)
                if h_aperture and not v_aperture:
                    v_aperture = h_aperture
                elif v_aperture and not h_aperture:
                    h_aperture = v_aperture
                h_aperture = h_aperture.Get(self.__time_code)
                v_aperture = v_aperture.Get(self.__time_code)

                if camera.GetProjectionAttr().Get(self.__time_code) == "orthographic":
                    new_horz_ap = (max(0.001, radius) / Gf.Camera.APERTURE_UNIT) * 2.0
                    if new_horz_ap != h_aperture:
                        new_vert_ap = v_aperture * ((new_horz_ap / h_aperture) if h_aperture else new_horz_ap)
                        return (new_horz_ap, new_vert_ap), (h_aperture, v_aperture)

                # Real fov's are 2x these, but only need the half for triangle calculation
                h_fov_rad = math.atan(
                    (h_aperture * Gf.Camera.APERTURE_UNIT) / (2.0 * focalLength * Gf.Camera.FOCAL_LENGTH_UNIT)
                )
                v_fov_rad = math.atan(
                    (v_aperture * Gf.Camera.APERTURE_UNIT) / (2.0 * focalLength * Gf.Camera.FOCAL_LENGTH_UNIT)
                )

        def fit_horizontal():
            if self.__use_horizontal_fov is not None:
                return self.__use_horizontal_fov
            conform = carb.settings.get_settings().get("/app/hydra/aperture/conform")
            if conform == 0 or conform == "vertical":
                return False

            is_fit = conform == 2 or conform == "fit"
            if is_fit or (conform == 3 or conform == "crop"):
                fov_aspect = h_fov_rad / v_fov_rad
                return not (is_fit ^ (fov_aspect > self.__aspect_ratio))
            return True

        if fit_horizontal():
            v_fov_rad = h_fov_rad / self.__aspect_ratio
        else:
            h_fov_rad = v_fov_rad * self.__aspect_ratio

        # Calculate the distance to encompass radius from the fovs
        dist = radius / math.tan(min(h_fov_rad, v_fov_rad))
        return (dist, dist), False

    def do(self):
        # Prims to frame bounds can be slightly more expensive than this, so validate we can move what was requested first
        usd_context = omni.usd.get_context(self.__usd_context_name)
        stage = usd_context.get_stage()
        local_xform, parent_xform, world_xform, prim = self.__compute_local_transform(stage)
        if not prim:
            return False

        aabbox = Gf.Range3d()

        def add_to_range(prim_path):
            aab_min, aab_max = usd_context.compute_path_world_bounding_box(prim_path)
            in_range = Gf.Range3d(Gf.Vec3d(*aab_min), Gf.Vec3d(*aab_max))
            if in_range.IsEmpty():
                aa_range = Gf.Range3d(Gf.Vec3d(-20, -20, -20), Gf.Vec3d(20, 20, 20))
                matrix = Gf.Matrix4d(*usd_context.compute_path_world_transform(prim_path))
                bbox = Gf.BBox3d(aa_range, matrix)
                in_range = bbox.ComputeAlignedRange()
                # Could still end up with an empty range (0 scale)
                if in_range.IsEmpty():
                    pos = matrix.ExtractTranslation()
                    in_range.SetMin(pos - aa_range.GetMin())
                    in_range.SetMax(pos + aa_range.GetMax())
            aabbox.UnionWith(in_range)

        # Calculate the bounds of the prims (excluding the prim we are moving if it was included)
        for prim_path in self.__prims_to_frame:
            if prim_path != self.__prim_to_move:
                add_to_range(prim_path)

        if aabbox.IsEmpty():
            carb.log_warn(f"Framing of UsdPrims {self.__prims_to_frame} resulted in an empty bounding-box")
            return

        if True:
            # Orient the aabox to the camera
            target = aabbox.GetMidpoint()
            tr0 = Gf.Matrix4d().SetTranslate(-target)
            local_rot = Gf.Matrix4d().SetRotate(local_xform.GetOrthonormalized().ExtractRotationQuat())
            tr1 = Gf.Matrix4d().SetTranslate(target)
            # And compute the new range
            aabbox = Gf.BBox3d(aabbox, tr0 * local_rot * tr1).ComputeAlignedRange()
        # Compute where to move in the parent space
        aabbox = Gf.BBox3d(aabbox, parent_xform.GetInverse()).ComputeAlignedRange()
        # Target is in parent-space (just like the camera / object we're moving)
        target = aabbox.GetMidpoint()
        # Frame against the aabox's bounding sphere
        radius = aabbox.GetSize().GetLength() * self.__zoom

        # TODO: Get rid of some of this complication due to Viewport-1
        values, ortho_props = self.__calculate_distance(radius, prim)
        prim_path = prim.GetPath()

        # For perspective, we really need the eye (it's translation)
        # For ortho, only needed to get coi (length to target)
        eye_dir = Gf.Vec3d(0, 0, values[0] if not ortho_props else 50000)
        eye = target + local_xform.TransformDir(eye_dir)

        # Mark center-of-interest accordingly (just length from target in local-space)
        coi_value = Gf.Vec3d(0, 0, -(eye - target).GetLength())
        coi_attr_name = "omni:kit:centerOfInterest"
        coi_attr = prim.GetAttribute(coi_attr_name)
        if not coi_attr:
            prev_coi = coi_value
            self.__created_property = True
        else:
            prev_coi = coi_attr.Get()

        omni.kit.commands.execute(
            "ChangePropertyCommand",
            prop_path=prim_path.AppendProperty(coi_attr_name),
            value=coi_value,
            prev=prev_coi,
            type_to_create_if_not_exist=Sdf.ValueTypeNames.Vector3d,
            usd_context_name=self.__usd_context_name,
            is_custom=True,
            variability=Sdf.VariabilityUniform,
        )

        if ortho_props:
            # Using time here causes issues with Viewport-1, so use default time for now
            time = self.__time_code if False else Usd.TimeCode.Default()
            omni.kit.commands.execute(
                "ChangePropertyCommand",
                prop_path=prim_path.AppendProperty("horizontalAperture"),
                value=values[0],
                prev=ortho_props[0],
                timecode=time,
                usd_context_name=self.__usd_context_name,
            )
            omni.kit.commands.execute(
                "ChangePropertyCommand",
                prop_path=prim_path.AppendProperty("verticalAperture"),
                value=values[1],
                prev=ortho_props[1],
                timecode=time,
                usd_context_name=self.__usd_context_name,
            )

        new_local_xform = Gf.Matrix4d(local_xform)
        new_local_xform.SetTranslateOnly(eye)

        had_transform_at_key = False
        had_matrix = False
        if not self.__time_code.IsDefault():
            xformable = UsdGeom.Xformable(prim)
            if xformable:
                for xform_op in xformable.GetOrderedXformOps():
                    had_matrix = xform_op.GetOpType() == UsdGeom.XformOp.TypeTransform
                    had_transform_at_key = had_transform_at_key or (xform_op.GetNumTimeSamples() > 0)

        if had_matrix:
            omni.kit.commands.execute(
                "TransformPrimCommand",
                path=self.__prim_to_move,
                new_transform_matrix=new_local_xform,
                old_transform_matrix=local_xform,
                time_code=self.__time_code,
                had_transform_at_key=had_transform_at_key,
                usd_context_name=self.__usd_context_name,
            )
        else:
            omni.kit.commands.execute(
                "TransformPrimSRTCommand",
                path=self.__prim_to_move,
                new_translation=new_local_xform.Transform(Gf.Vec3d(0, 0, 0)),
                time_code=self.__time_code,
                had_transform_at_key=had_transform_at_key,
                usd_context_name=self.__usd_context_name,
            )

    def undo(self):
        if not self.__created_property:
            return
        usd_context = omni.usd.get_context(self.__usd_context_name)
        stage = usd_context.get_stage()
        if not stage:
            return
        prim = stage.GetPrimAtPath(self.__prim_to_move)
        if not prim:
            return
        prim.RemoveProperty("omni:kit:centerOfInterest")
        self.__created_property = False


class SelectPrimsCommand(omni.kit.commands.Command):
    """
    Select primitives undoable **Command**.

    Args:
        old_selected_paths (List[str]): Old selected prim paths.
        new_selected_paths (List[str]): Prim paths to be selected.
        expand_in_stage (bool, DEPRECATED): Whether to expand the path in Stage Window on selection.
        This param is left for compatibility.

    REMINDER: Both params old_selected_paths and new_selected_paths should be const
    out of the command. And it's caller's responsibility to maintain that. Otherwise, undo will not
    return to its original state.
    """

    def __init__(self, old_selected_paths: List[str], new_selected_paths: List[str], expand_in_stage: bool):
        self._selection = omni.usd.get_context().get_selection()
        self._old_selected_paths = old_selected_paths
        self._new_selected_paths = new_selected_paths
        self._expand_in_stage = expand_in_stage

    def do(self):
        self._selection.set_selected_prim_paths(self._new_selected_paths, self._expand_in_stage)

    def undo(self):
        self._selection.set_selected_prim_paths(self._old_selected_paths, self._expand_in_stage)


class ToggleVisibilitySelectedPrimsCommand(omni.kit.commands.Command):
    """
    Toggles the visiblity of the selected primitives undoable **Command**.

    Args:
        selected_paths (List[str]): Old selected prim paths.
    """

    def __init__(self, selected_paths: List[str]):
        self._timeline = omni.timeline.get_timeline_interface()
        self._stage = omni.usd.get_context().get_stage()
        self._selected_paths = selected_paths.copy()

    def _toggle_visibility(self):
        for selected_path in self._selected_paths:
            selected_prim = self._stage.GetPrimAtPath(selected_path)
            imageable = UsdGeom.Imageable(selected_prim)
            visibility_attr = imageable.GetVisibilityAttr()
            time_sampled = visibility_attr.GetNumTimeSamples() > 1
            curr_time = self._timeline.get_current_time()
            if time_sampled:
                self._curr_time_code = curr_time * self._stage.GetTimeCodesPerSecond()
            else:
                self._curr_time_code = Usd.TimeCode.Default()
            visibility = imageable.ComputeVisibility(self._curr_time_code)
            if visibility == UsdGeom.Tokens.invisible:
                imageable.MakeVisible()
            else:
                imageable.MakeInvisible()

    def do(self):
        self._toggle_visibility()

    def undo(self):
        self._toggle_visibility()


class UnhideAllPrimsCommand(omni.kit.commands.Command):
    def do(self):
        self._invisible_imageables = []

        stage = omni.usd.get_context().get_stage()
        for prim in stage.Traverse():
            imageable = UsdGeom.Imageable(prim)
            if imageable:
                if imageable.ComputeVisibility() == UsdGeom.Tokens.invisible:
                    self._invisible_imageables.append(imageable)
                    imageable.MakeVisible()

    def undo(self):
        for imagleable in self._invisible_imageables:
            imagleable.MakeInvisible()


class MovePrimCommand(omni.kit.commands.Command):
    """
    Move primitive undoable **Command**.

    Args:
        path_from (str): Path to move prim from.

        path_to(str): Path to move prim to.

        time_code(Usd.TimeCode): Current timecode of the stage.

        keep_world_transform(bool): True to keep world transform after prim path is moved. False to keep local transfrom only.

        on_move_fn(Callable): Function to call when prim is renamed

        destructive(bool): If it's false, it will not remove original prim but deactivate it. By default, it's true
                           for back compatibility.
    """

    def __init__(
        self,
        path_from: Union[str, Sdf.Path],
        path_to: Union[str, Sdf.Path],
        time_code: Usd.TimeCode = Usd.TimeCode.Default(),
        keep_world_transform: bool = True,
        on_move_fn: Callable = None,
        destructive=True,
    ):
        self._path_from = Sdf.Path(path_from)
        self._usd_context = omni.usd.get_context()
        self._selection = self._usd_context.get_selection()
        stage = self._usd_context.get_stage()
        self._path_to = Sdf.Path(omni.usd.get_stage_next_free_path(stage, path_to, False))
        self._time_code = time_code
        self._keep_world_transform = keep_world_transform
        self._moved = False
        self._prev_order = {}
        self._on_move_fn = on_move_fn
        self._destructive = destructive
        self._changed_layer_identifier = None
        self._delete_command = None

    @Trace.TraceFunction
    def _move_prim_spec(self, layer, path_from, path_to, is_undo):
        Sdf.CreatePrimInLayer(layer, path_to.GetParentPath())
        layer_path = layer.realPath

        if not is_undo:
            # keep the prim order when undo
            prim_spec = layer.GetPrimAtPath(path_from)
            if not prim_spec:
                return False
            parent_prim_spec = prim_spec.realNameParent

            # Each layer may have different children order. Store them separately.
            self._prev_order[layer_path] = parent_prim_spec.nameChildren.index(path_from.name)

        edit = Sdf.BatchNamespaceEdit()
        edit.Add(path_from, path_to, self._prev_order.get(layer_path, -1) if is_undo else -1)
        return layer.Apply(edit)

    def _is_auto_authoring_layer(self, layer_identifier):
        try:
            import omni.kit.usd.layers as layers

            return layers.get_auto_authoring(self._usd_context).is_auto_authoring_layer(layer_identifier)
        except Exception:
            return False

    def _remove_prim_spec_in_auto_authoring_layer(self, stage, path):
        layer_stack = stage.GetLayerStack()
        for layer in layer_stack:
            if self._is_auto_authoring_layer(layer.identifier):
                remove_prim_spec(layer, path)
                break

    # Utility class to track live objects that should reflect the rename operation.
    # This is currenlty targeted at Viewports only, but a separate event/extension/registry might be better
    # to allow aribtrary extensions to handle a rename event.
    class RenameHandler:
        def __init__(self, old_path: Sdf.Path):
            """Cache all objects that reference the old_path, before any rename occurs"""
            self.__new_vp_apis = []
            self.__legacy_vp_windows = []

            # Try on new Viewport if loaded
            try:
                from omni.kit.widget.viewport import ViewportWidget

                for instance in ViewportWidget.get_instances():
                    viewport_api = instance.viewport_api
                    if viewport_api and viewport_api.camera_path.HasPrefix(old_path):
                        self.__new_vp_apis.append(viewport_api)
            except (ImportError, ModuleNotFoundError):
                pass

            # Try on legacy Viewport if loaded
            try:
                import omni.kit.viewport_legacy as vp_legacy

                vp_iface = vp_legacy.get_viewport_interface()
                # Convert to string for comparison once
                for viewport_handle in vp_iface.get_instance_list():
                    vp_window = vp_iface.get_viewport_window(viewport_handle)
                    if Sdf.Path(vp_window.get_active_camera() if vp_window else "").HasPrefix(old_path):
                        self.__legacy_vp_windows.append(vp_window)
            except (ImportError, ModuleNotFoundError):
                pass

        def apply_change(self, old_path: Sdf.Path, new_path: Sdf.Path):
            # New viewport takes the Sdf.Path natively
            for viewport_api in self.__new_vp_apis:
                try:
                    viewport_api.camera_path = viewport_api.camera_path.ReplacePrefix(old_path, new_path)
                except:
                    carb.log_warn("Failure in new Viewport camera_path")

            # Legacy Viewport takes a string
            new_path_str = str(new_path)
            for vp_window in self.__legacy_vp_windows:
                try:
                    vp_window_path = Sdf.Path(vp_window.get_active_camera()).ReplacePrefix(old_path, new_path)
                    vp_window.set_active_camera(vp_window_path.pathString)
                except:
                    carb.log_warn("Failure in legacy Viewport set_active_camera")

    @Trace.TraceFunction
    def _move(self, path_from, path_to, is_undo):
        if not Sdf.Path.IsValidPathString(path_to.pathString):
            carb.log_error(f"Invalid path: {str(path_to)}")
            return

        stage = self._usd_context.get_stage()
        prim = stage.GetPrimAtPath(path_from)
        if prim:
            if (
                prim.IsA(UsdGeom.Gprim)
                and omni.usd.is_ancestor_prim_type(stage, Sdf.Path(self._path_to), UsdGeom.Gprim)
            ):
                post_notification(
                    f"Cannot move prim {self._path_from} to {self._path_to} as nested gprims are not supported."
                )
                return

            if omni.usd.editor.is_no_delete(prim):
                error = f"{str(path_from)} is not deletable"
                carb.log_error(error)
                post_notification(error)
                return

            if omni.usd.check_ancestral(prim):
                error = f"Cannot move/rename ancestral prim {str(path_from)}"
                carb.log_error(error)
                post_notification(error)
                return

            prim_to_parent = stage.GetPrimAtPath(path_to.GetParentPath())
            if prim_to_parent and (prim_to_parent.IsInstance() or prim_to_parent.IsInstanceProxy()):
                error = f"{str(path_from)} cannot be moved under an instance or instance proxy."
                post_notification(error)
                return

            # Get all of the objects that need to know about the path change
            rename_handler = MovePrimCommand.RenameHandler(path_from)

            old_world_matrices = {}
            if self._keep_world_transform and path_from.GetParentPath() != path_to.GetParentPath():
                # The moved prim might not be an Xformable (i.e. Scope), in this case, we need to find the
                # subtrees of this prim whose root are Xformable (handle nested Scope) and pin their transform.

                # Iterate all descendents in depth first order -> find first Xformable -> store its transform -> skip
                # all its children, find next subtree with Xformable root until visited the entire range.
                prim_range_it = iter(Usd.PrimRange(prim))
                for sub_prim in prim_range_it:
                    if sub_prim.IsA(UsdGeom.Xformable):
                        old_world_mtx = omni.usd.get_world_transform_matrix(sub_prim, self._time_code)
                        new_path = sub_prim.GetPath().ReplacePrefix(path_from, path_to)
                        old_world_matrices[new_path] = old_world_mtx

                        # Skip all its children
                        prim_range_it.PruneChildren()

            success = False
            was_default_prim = stage.GetDefaultPrim() == prim
            was_selected = self._selection.is_prim_path_selected(path_from.pathString)
            layer_stack = stage.GetLayerStack()
            prim_stack = prim.GetPrimStack()

            with Sdf.ChangeBlock():
                # Clean up copy inside auto-authoring firstly
                self._remove_prim_spec_in_auto_authoring_layer(stage, path_from)

                if self._destructive or (
                    not is_undo and prim_can_be_removed_without_destruction(self._usd_context, path_from)
                ):
                    self._destructive = True
                    for prim_spec in prim_stack:
                        layer = prim_spec.layer
                        # Only move from layers in the stage
                        if layer not in layer_stack:
                            continue
                        success = self._move_prim_spec(layer, path_from, path_to, is_undo) or success
                        if success:
                            omni.usd.resolve_prim_path_references(
                                layer.identifier, path_from.pathString, path_to.pathString
                            )
                else:
                    if is_undo:
                        if self._changed_layer_identifier:
                            edit_target_layer = Sdf.Find(self._changed_layer_identifier)
                            if not edit_target_layer:
                                carb.log_warn(
                                    f"Failed to activate {path_to} as target layer {self._changed_layer_identifier} cannot be found."
                                )
                                success = False
                            else:
                                DeletePrimsCommand([path_from]).do()
                                if self._delete_command:
                                    with Usd.EditContext(stage, edit_target_layer):
                                        self._delete_command.undo()
                                success = True
                    else:
                        with active_edit_context(self._usd_context):
                            edit_target_layer = stage.GetEditTarget().GetLayer()
                            self._changed_layer_identifier = edit_target_layer.identifier
                            Sdf.CreatePrimInLayer(edit_target_layer, path_to)
                            omni.usd.stitch_prim_specs(stage, path_from, edit_target_layer, path_to)
                            self._delete_command = DeletePrimsCommand([path_from], destructive=False)
                            self._delete_command.do()
                            success = True

                    if success:
                        omni.usd.resolve_prim_path_references(
                            edit_target_layer.identifier, path_from.pathString, path_to.pathString
                        )

            if not is_undo:
                self._moved = success
            if success:
                rename_handler.apply_change(path_from, path_to)
                if len(old_world_matrices):
                    new_prim = stage.GetPrimAtPath(path_to)
                    if not new_prim:
                        return
                    new_parent = new_prim.GetParent()

                    new_parent_world_mtx = omni.usd.get_world_transform_matrix(new_parent, self._time_code)
                    new_parent_world_to_local_mtx = new_parent_world_mtx.GetInverse()

                    for path, mtx in old_world_matrices.items():
                        new_local_mtx = mtx * new_parent_world_to_local_mtx

                        if not Gf.IsClose(
                            new_local_mtx, omni.usd.get_local_transform_matrix(new_prim, self._time_code), 1e-2
                        ):
                            # It will author the new transform on CURRENT edit target. If an transfrom exists on a layer
                            # with stronger opinion, prim xfrom will NOT keep in place.
                            # Note that due to the limitation of our undo command, the prim spec will not be identical
                            # after undo. This will need to be addressed globally for all commands.
                            cmd = TransformPrimCommand(
                                path=path, new_transform_matrix=new_local_mtx, time_code=self._time_code
                            )
                            cmd.do()
                if was_selected:
                    self._selection.set_prim_path_selected(path_to.pathString, True, False, False, True)
                if was_default_prim:
                    stage.SetDefaultPrim(stage.GetPrimAtPath(path_to))
                if self._on_move_fn:
                    try:
                        self._on_move_fn(path_from, path_to)
                    except:
                        carb.log_warn("error in MovePrimCommand on_move_fn")

    def do(self):
        carb.log_info(f"Moving prim from {self._path_from} to {self._path_to}")
        self._move(self._path_from, self._path_to, False)

    def undo(self):
        if self._moved:
            carb.log_info(f"Undo Move prim from {self._path_to} to {self._path_from}")
            self._move(self._path_to, self._path_from, True)


class MovePrimsCommand(omni.kit.commands.Command):
    """
    Move primitives undoable **Command**.

    Args:
        paths_to_move Dict[str, str]: dictionary contaning entry of path_from : path_to.
        time_code(Usd.TimeCode): Current timecode of the stage.
        keep_world_transform(bool): True to keep world transform after prim path is moved. False to keep local transfrom only.
        destructive(bool): If it's false, it will not remove original prim but deactivate it. By default, it's true
                           for back compatibility.
    """

    def __init__(
        self,
        paths_to_move: Dict[str, str],
        time_code: Usd.TimeCode = Usd.TimeCode.Default(),
        keep_world_transform: bool = True,
        on_move_fn: Callable = None,
        destructive=True,
    ):
        self._paths_to_move = paths_to_move
        self._time_code = time_code
        self._keep_world_transform = keep_world_transform
        self._on_move_fn = on_move_fn
        self._destructive = destructive

    def do(self):
        for src, dst in self._paths_to_move.items():
            omni.kit.commands.execute(
                "MovePrim",
                path_from=src,
                path_to=dst,
                time_code=self._time_code,
                keep_world_transform=self._keep_world_transform,
                on_move_fn=self._on_move_fn,
                destructive=self._destructive,
            )

    def undo(self):
        pass


class ReplaceReferencesCommand(omni.kit.commands.Command):
    """
    Clears/Add references undoable **Command**.

    NOTE: THIS COMMAND HAS A LOT OF ISSUES AND IS DEPRECATED. PLEASE USE ReplaceReferenceCommand instead!

    Args:
        path (str): Prim path.
        old_url(str): Url to be replaced.
        new_url(str): Replacement url.
    """

    def __init__(self, path: str, old_url: str, new_url: str):
        self._usd_context = omni.usd.get_context()
        self._selection = self._usd_context.get_selection()
        self._path = None
        self._old_url = old_url
        self._new_url = new_url
        self._prev_selected_paths = list(self._selection.get_selected_prim_paths())
        self._selection.clear_selected_prim_paths()

        stage = self._usd_context.get_stage()
        prim = stage.GetPrimAtPath(path)
        if prim and not omni.usd.editor.is_no_delete(prim):
            self._path = path
        else:
            carb.log_error(f"{str(path)} does not exist or is not deletable")

    def do(self):
        stage = self._usd_context.get_stage()
        prim = stage.GetPrimAtPath(self._path)
        if prim:
            refs = prim.GetReferences()
            refs.ClearReferences()
            for url in self._new_url:
                refs.AddReference(url)

    def undo(self):
        stage = self._usd_context.get_stage()
        prim = stage.GetPrimAtPath(self._path)
        if prim:
            refs = prim.GetReferences()
            refs.ClearReferences()
            for url in self._old_url:
                refs.AddReference(url)

        # Reselect restored objects
        self._selection.clear_selected_prim_paths()
        if self._path in self._prev_selected_paths:
            self._selection.set_prim_path_selected(self._path, True, True, False, True)


class CreateUsdAttributeOnPathCommand(omni.kit.commands.Command):
    """
    Create USD Attribute **Command**.

    Args:
        attr_path (Union[Sdf.Path, str]): Path to the new attribute to be created. The prim of this path must already exist.
        attr_type (Sdf.ValueTypeName): New attribute's type.
        custom (bool): If the attribute is custom.
        variability (Sdf.Variability): whether the attribute may vary over time and value coordinates, and if its value comes through authoring or from its owner.
        attr_value (Any, optional): New attribute's value. Leave it as None to use default value.
        usd_context_name(str): Name of the usd context to execute the command on.

    Example of usage:
        omni.kit.commands.execute("CreateUsdAttribute",
                                    prim=prim,
                                    attr_name="custom",
                                    attr_type=Sdf.ValueTypeNames.Double3)
    """

    def __init__(
        self,
        attr_path: Union[Sdf.Path, str],
        attr_type: Sdf.ValueTypeName,
        custom: bool = True,
        variability: Sdf.Variability = Sdf.VariabilityVarying,
        attr_value: Any = None,
        usd_context_name: str = "",
    ):
        self._usd_context = omni.usd.get_context(usd_context_name)
        self._attr_path = Sdf.Path(attr_path)
        self._attr_type = attr_type
        self._custom = custom
        self._variability = variability
        self._attr_value = attr_value
        self._created = False

    def do(self):
        prim = self._usd_context.get_stage().GetPrimAtPath(self._attr_path.GetPrimPath())
        if prim:
            omni.kit.commands.execute(
                "CreateUsdAttributeCommand",
                prim=prim,
                attr_name=self._attr_path.name,
                attr_type=self._attr_type,
                custom=self._custom,
                variability=self._variability,
                attr_value=self._attr_value,
            )

    def undo(self):
        pass


class CreateUsdAttributeCommand(omni.kit.commands.Command):
    """
    Create USD Attribute **Command**.

    Args:
        prim (Usd.Prim): Usd.Prim that will get a new attribute.
        attr_name (str): New attribute's name.
        attr_type (Sdf.ValueTypeName): New attribute's type.
        custom (bool): If the attribute is custom.
        variability (Sdf.Variability): whether the attribute may vary over time and value coordinates, and if its value comes through authoring or from its owner.
        attr_value (Any, optional): New attribute's value. Leave it as None to use default value.

    Example of usage:
        omni.kit.commands.execute("CreateUsdAttribute",
                                    prim=prim,
                                    attr_name="custom",
                                    attr_type=Sdf.ValueTypeNames.Double3)
    """

    def __init__(
        self,
        prim: Usd.Prim,
        attr_name: str,
        attr_type: Sdf.ValueTypeName,
        custom: bool = True,
        variability: Sdf.Variability = Sdf.VariabilityVarying,
        attr_value: Any = None,
    ):
        self._prim = prim
        self._attr_name = attr_name
        self._attr_type = attr_type
        self._custom = custom
        self._variability = variability
        self._attr_value = attr_value
        self._created = False

    def do(self):
        attr = self._prim.CreateAttribute(
            name=self._attr_name, typeName=self._attr_type, custom=self._custom, variability=self._variability
        )
        if attr.IsValid():
            self._created = True
            if self._attr_value is not None:
                attr.Set(self._attr_value)

    def undo(self):
        if not self._created:
            return

        self._prim.RemoveProperty(self._attr_name)
        self._created = False


class ChangePropertyCommand(omni.kit.commands.Command):
    """
    Change prim property undoable **Command**.

    Args:
        prop_path (str): Prim property path.
        value (Any): Value to change to.
        prev (Any): Value to undo to.
        timecode (Usd.TimeCode): The timecode to set property value to.
        type_to_create_if_not_exist (Sdf.ValueTypeName): If not None AND property does not already exist, a new property will be created with given type and value.
        target_layer (sdf.Layer): Target layer to write value to. Leave to None to use current stage's EditTarget.
        usd_context_name (Union[str, Usd.Stage]): Union that could be:
                        * Name of the usd context to work on. Leave to "" to use default USD context.
                        * Instance of UsdContext.
                        * Or stage instance.
        is_custom (bool): If the property is created, specifiy if it is a 'custom' property (not part of the Schema).
        variability (Sdf.Variability): If the property is created, specify the variability.
    """

    def __init__(
        self,
        prop_path: str,
        value: Any,
        prev: Any,
        timecode=Usd.TimeCode.Default(),
        type_to_create_if_not_exist: Sdf.ValueTypeNames = None,
        target_layer: Sdf.Layer = None,
        usd_context_name: Union[str, omni.usd.UsdContext, Usd.Stage]  = "",
        is_custom: bool = False,
        variability: Sdf.Variability = Sdf.VariabilityVarying,
    ):
        self._value = value
        self._prev = prev
        self._prop_path = Sdf.Path(prop_path)
        self._time_code = timecode
        self._type_to_create_if_not_exist = type_to_create_if_not_exist
        # Save identifier instead of layer handle to avoid holding it.
        self._target_layer_identifier = target_layer.identifier if target_layer else None
        # Note about _target_layer_had_old_spec vs _target_layer_had_old_value
        # - When _target_layer_had_old_spec is False, the target layer does not have property spec at given path, and
        #   thus _target_layer_had_old_value is also False since there will not be a value defined.
        # - When _target_layer_had_old_spec is True, _target_layer_had_old_value can be either True or False. If the
        #   property spec only have definition but doesn't assign a value, _target_layer_had_old_value will be False.
        #   In this case, we do not want to remove the property spec, but only clear the value during undo.
        self._target_layer_had_old_spec = False
        self._target_layer_had_old_value = False

        if isinstance(usd_context_name, omni.usd.UsdContext):
            self._stage = usd_context_name.get_stage()
        elif isinstance(usd_context_name, Usd.Stage):
            self._stage = usd_context_name
        else:
            self._stage = omni.usd.get_context(usd_context_name).get_stage()

        self._new_property = False
        self._new_time_code = False
        self._do_executed = False
        self.__is_custom = is_custom
        self.__variability = variability

    def _get_target_layer(self):
        if self._target_layer_identifier:
            current_layer = Sdf.Layer.Find(self._target_layer_identifier)
        else:
            # If target layer is not specified, it firstly finds the prop from session layer.
            current_layer, _ = omni.usd.find_spec_on_session_or_its_sublayers(self._stage, self._prop_path)

            # If it's still not existed, using the current edit target layer.
            if not current_layer:
                current_layer = self._stage.GetEditTarget().GetLayer()
        
        return current_layer

    def do(self):
        self._do_executed = False
        current_layer = self._get_target_layer()
        # If the target layer is destroyed or not existed, simply return.
        if not current_layer or not self._stage.HasLocalLayer(current_layer):
            carb.log_error(
                f"Failed to change property {self._prop_path} as target layer is not in the local stack of stage."
            )

            return False

        self._do_executed = True

        # Updates target layer so it could be fixed for undo to make sure changes can be revert back
        # to correct layer.
        self._target_layer_identifier = current_layer.identifier

        # Saves the flag to check if the target layer has property or not before the change.
        spec = current_layer.GetPropertyAtPath(self._prop_path)
        if current_layer.GetPropertyAtPath(self._prop_path):
            self._target_layer_had_old_spec = True
            self._target_layer_had_old_value = spec.HasDefaultValue()
        else:
            self._target_layer_had_old_spec = False
            self._target_layer_had_old_value = False

        with Usd.EditContext(self._stage, current_layer):
            prop = omni.usd.get_prop_at_path(self._prop_path, self._stage)
            if not prop:
                if self._type_to_create_if_not_exist is not None:
                    prim_path = self._prop_path.GetAbsoluteRootOrPrimPath()
                    prim = self._stage.GetPrimAtPath(prim_path)
                    prop = prim.CreateAttribute(
                        self._prop_path.name, self._type_to_create_if_not_exist, self.__is_custom, self.__variability
                    )
                    if prop:
                        self._new_property = True

            if prop:
                if self._prev is None:
                    self._prev = prop.Get(self._time_code)

                self._new_time_code = (
                    self._time_code != Usd.TimeCode.Default()
                    and not omni.usd.attr_has_timesample_on_key(prop, self._time_code)
                )
                omni.usd.set_prop_val(prop, self._value, self._time_code, auto_target_layer=False)

    def undo(self):
        if not self._do_executed:
            return

        current_layer = self._get_target_layer()
        # If the target layer is destroyed or not existed, simply return.
        if not current_layer:
            return

        with Usd.EditContext(self._stage, current_layer):
            if self._new_property or not self._target_layer_had_old_spec:
                property_spec = current_layer.GetPropertyAtPath(self._prop_path)
                if property_spec:
                    prim_path = self._prop_path.GetAbsoluteRootOrPrimPath()
                    prim_spec = current_layer.GetPrimAtPath(prim_path)
                    prim_spec.RemoveProperty(property_spec)
            elif self._target_layer_had_old_spec and not self._target_layer_had_old_value:
                property_spec = current_layer.GetPropertyAtPath(self._prop_path)
                property_spec.ClearDefaultValue()
            else:
                prop = omni.usd.get_prop_at_path(self._prop_path)
                if prop:
                    if self._new_time_code:
                        omni.usd.clear_attr_val_at_time(prop, self._time_code, auto_target_layer=False)
                    else:
                        omni.usd.set_prop_val(prop, self._prev, self._time_code, auto_target_layer=False)


class RemovePropertyCommand(omni.kit.commands.Command):
    """
    Remove Property **Command**.

    Args:
        prop_path (str): Path of the property to be removed.
        usd_context_name (str): Usd context name to run the command on.
    """

    def __init__(self, prop_path: Union[Sdf.Path, str], usd_context_name: str = ""):
        self._prop_path = Sdf.Path(prop_path)
        self._prim_path = self._prop_path.GetAbsoluteRootOrPrimPath()
        self._usd_context = omni.usd.get_context(usd_context_name)
        self._temp_layers = {}

    def do(self):
        stage = self._usd_context.get_stage()
        if stage:
            with Sdf.ChangeBlock():
                for layer in stage.GetLayerStack():
                    temp_layer = Sdf.Layer.CreateAnonymous()
                    prim_spec = layer.GetPrimAtPath(self._prim_path)
                    if prim_spec:
                        property_spec = layer.GetPropertyAtPath(self._prop_path)
                        if property_spec:
                            # create a proxy prim in the temp_layer, necessary?
                            # now we can copy the property_spec
                            if Sdf.CreatePrimInLayer(temp_layer, self._prim_path) and Sdf.CopySpec(
                                layer, self._prop_path, temp_layer, self._prop_path
                            ):
                                self._temp_layers[temp_layer] = layer
                                prim_spec.RemoveProperty(property_spec)

    def undo(self):
        with Sdf.ChangeBlock():
            for key, value in self._temp_layers.items():
                restore_to_layer = value
                restore_from_layer = key
                if restore_to_layer and restore_from_layer:
                    if not Sdf.CopySpec(restore_from_layer, self._prop_path, restore_to_layer, self._prop_path):
                        carb.log_error(f"failed to restore property {self._prop_path.pathString}")
        self._temp_layers.clear()


class ChangeMetadataInPrimsCommand(omni.kit.commands.Command):
    """
    Change prim metadata undoable **Command**.

    Args:
        prim_paths (List[str]): Prim paths.
        key: Key of metadata to change.
        value: Value of metadata to change to.
        usd_context_name (str): Name of the usd context to work on. Leave to "" to use default USD context.
    """

    def __init__(self, prim_paths: List[str], key: Any, value: Any, usd_context_name: str = ""):
        self._prim_paths = prim_paths
        self._key = key
        self._value = value
        self._usd_context_name = usd_context_name

    def do(self):
        omni.kit.commands.execute(
            "ChangeMetadata",
            object_paths=self._prim_paths,
            key=self._key,
            value=self._value,
            usd_context_name=self._usd_context_name,
        )

    def undo(self):
        pass


class ChangeMetadataCommand(omni.kit.commands.Command):
    """
    Change object metadata undoable **Command**.

    Args:
        object_paths (List[str]): Object paths, can be attribute or prim.
        key: Key of metadata to change.
        value: Value of metadata to change to.
        usd_context_name (str): Name of the usd context to work on. Leave to "" to use default USD context.
    """

    def __init__(self, object_paths: List[str], key: Any, value: Any, usd_context_name: str = ""):
        self._object_paths = object_paths
        self._key = key
        self._value = value
        self._old_values = {}
        self._usd_context_name = usd_context_name

    def do(self):
        stage = omni.usd.get_context(self._usd_context_name).get_stage()
        for path in self._object_paths:
            object = stage.GetObjectAtPath(path)
            if object:
                self._old_values[path] = object.GetMetadata(self._key) if object.HasMetadata(self._key) else None
                object.SetMetadata(self._key, self._value)

    def undo(self):
        stage = omni.usd.get_context(self._usd_context_name).get_stage()
        for path, old_value in self._old_values.items():
            object = stage.GetObjectAtPath(path)
            if object:
                if old_value is not None:
                    object.SetMetadata(self._key, old_value)
                else:
                    object.ClearMetadata(self._key)


class ChangeAttributesColorSpaceCommand(omni.kit.commands.Command):
    """
    Change attribute color space undoable **Command**.

    Args:
        attributes (List[str]): attributes to set color space on.
        color_space: Value of metadata to change to.
    """

    def __init__(self, attributes: List[Usd.Attribute], color_space: Any):
        self._attributes = attributes.copy()
        self._color_space = color_space
        self._old_values = {}

    def do(self):
        for attr in self._attributes:
            if attr:
                self._old_values[attr] = attr.GetColorSpace() if attr.HasColorSpace() else None
                attr.SetColorSpace(self._color_space)

    def undo(self):
        for attr, old_value in self._old_values.items():
            if attr:
                if old_value is not None:
                    attr.SetColorSpace(old_value)
                else:
                    attr.ClearColorSpace()


class CreateMdlMaterialPrimCommand(omni.kit.commands.Command, UsdStageHelper):
    """
    Create Mdl Material undoable **Command**.

    Args:
        mtl_url (str):
        mtl_name (str):
        mtl_path (str):
        select_new_prim (bool):
        stage (Usd.Stage): Stage to operate. Optional.
        context_name (str): The usd context to operate. Optional.
    """

    def __init__(
        self,
        mtl_url: str,
        mtl_name: str,
        mtl_path: str,
        select_new_prim: bool = False,
        stage: Optional[Usd.Stage] = None,
        context_name: Optional[str] = None,
    ):
        UsdStageHelper.__init__(self, stage, context_name)

        self._mtl_url = omni.usd.make_path_relative_to_current_edit_target(mtl_url, stage=self._get_stage())
        self._mtl_name = mtl_name
        self._mtl_path = mtl_path
        self._select_new_prim = select_new_prim
        self._author_old_mdl_schema = carb.settings.get_settings().get("/omni.kit.plugin/authorOldMdlSchema")

    def do(self):
        stage = self._get_stage()

        ensure_parents_are_active(stage, self._mtl_path)

        # It's possible that parents of material are inactive so the material path is existed
        # already after it's activated. Regenerating the path to avoid conflicts.
        self._mtl_path = omni.usd.get_stage_next_free_path(stage, self._mtl_path, False)

        # create Looks folder
        parts = str(self._mtl_path).split("/")
        parts.pop()
        prim_path = ""
        for part in parts:
            prim_path = f"{prim_path}/{part}" if part else prim_path
            prim = stage.GetPrimAtPath(Sdf.Path(prim_path)) if prim_path else None
            if prim_path and not prim:
                omni.kit.commands.execute(
                    "CreatePrim",
                    prim_path=prim_path,
                    prim_type="Scope",
                    select_new_prim=False,
                    stage=stage
                )

        # create material
        mat_prim = stage.DefinePrim(self._mtl_path, "Material")
        material_prim = UsdShade.Material.Get(stage, mat_prim.GetPath())
        if material_prim:
            shader_mtl_path = stage.DefinePrim("{}/Shader".format(self._mtl_path), "Shader")
            shader_prim = UsdShade.Shader.Get(stage, shader_mtl_path.GetPath())
            if shader_prim:
                if self._author_old_mdl_schema:
                    shader_out = shader_prim.CreateOutput("out", Sdf.ValueTypeNames.Token)
                    shader_out.SetRenderType("material")
                    material_prim.GetSurfaceOutput().ConnectToSource(shader_out)
                    shader_prim.CreateIdAttr("mdlMaterial")
                    shader_prim.GetPrim().CreateAttribute("module", Sdf.ValueTypeNames.Asset).Set(self._mtl_url)
                    shader_prim.GetPrim().CreateAttribute("name", Sdf.ValueTypeNames.String).Set(self._mtl_name)
                else:
                    shader_out = shader_prim.CreateOutput("out", Sdf.ValueTypeNames.Token)
                    shader_out.SetRenderType("material")

                    material_prim.CreateSurfaceOutput("mdl").ConnectToSource(shader_out)
                    material_prim.CreateVolumeOutput("mdl").ConnectToSource(shader_out)
                    material_prim.CreateDisplacementOutput("mdl").ConnectToSource(shader_out)
                    shader_prim.GetImplementationSourceAttr().Set(UsdShade.Tokens.sourceAsset)
                    shader_prim.SetSourceAsset(Sdf.AssetPath(self._mtl_url.replace("\\", "/")), "mdl")
                    shader_prim.SetSourceAssetSubIdentifier(self._mtl_name, "mdl")
                if self._select_new_prim:
                    omni.usd.get_context().get_selection().set_prim_path_selected(
                        self._mtl_path, True, True, True, True
                    )
            else:
                DeletePrimsCommand([material_prim.GetPath().pathString], stage=stage).do()
                carb.log_warn(f"failed to create shader {shader_mtl_path}")
        else:
            carb.log_warn(f"failed to create prim {mat_prim.GetPath().pathString}")

    def undo(self):
        stage = self._get_stage()
        mat_prim = stage.GetPrimAtPath(self._mtl_path)
        if mat_prim:
            DeletePrimsCommand([mat_prim.GetPath().pathString], stage=stage).do()


class CreatePreviewSurfaceMaterialPrimCommand(omni.kit.commands.Command):
    """
    Create Preview Surface Material undoable **Command**.

    Args:
        mtl_path (str):
        select_new_prim (bool):
    """

    def __init__(self, mtl_path: str, select_new_prim: bool = False):
        self._mtl_path = mtl_path
        self._select_new_prim = select_new_prim

    def do(self):
        stage = omni.usd.get_context().get_stage()

        # It's possible that parents of material are inactive so the material path is existed
        # already after it's activated. Regenerating the path to avoid conflicts.
        self._mtl_path = omni.usd.get_stage_next_free_path(stage, self._mtl_path, False)

        ensure_parents_are_active(stage, self._mtl_path)

        mat_prim = stage.DefinePrim(self._mtl_path, "Material")
        material_prim = UsdShade.Material.Get(stage, mat_prim.GetPath())
        if material_prim:
            shader_path = stage.DefinePrim("{}/Shader".format(self._mtl_path), "Shader")
            shader_prim = UsdShade.Shader.Get(stage, shader_path.GetPath())
            if shader_prim:
                shader_prim.CreateIdAttr("UsdPreviewSurface")
                shader_prim.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set((0.18, 0.18, 0.18))
                shader_prim.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set((0.0, 0.0, 0.0))

                use_specular_workflow = shader_prim.CreateInput("useSpecularWorkflow", Sdf.ValueTypeNames.Int)
                use_specular_workflow.Set(0)
                use_specular_workflow.GetAttr().SetCustomDataByKey("range:min", 0)
                use_specular_workflow.GetAttr().SetCustomDataByKey("range:max", 1)

                shader_prim.CreateInput("specularColor", Sdf.ValueTypeNames.Color3f).Set(
                    (0.0, 0.0, 0.0)
                )  # useSpecularWorkflow = 1: (Specular workflow )
                shader_prim.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(
                    0.0
                )  # useSpecularWorkflow = 0: (Metalness workflow )

                roughness = shader_prim.CreateInput("roughness", Sdf.ValueTypeNames.Float)
                roughness.Set(0.5)
                roughness.GetAttr().SetCustomDataByKey("range:min", 0.0)
                roughness.GetAttr().SetCustomDataByKey("range:max", 1.0)

                shader_prim.CreateInput("clearcoat", Sdf.ValueTypeNames.Float).Set(0.0)
                shader_prim.CreateInput("clearcoatRoughness", Sdf.ValueTypeNames.Float).Set(0.01)
                shader_prim.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(1.0)
                shader_prim.CreateInput("opacityThreshold", Sdf.ValueTypeNames.Float).Set(0.0)
                shader_prim.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(1.5)
                shader_prim.CreateInput("normal", Sdf.ValueTypeNames.Normal3f).Set((0.0, 0.0, 1.0))
                shader_prim.CreateInput("displacement", Sdf.ValueTypeNames.Float).Set(0.0)
                shader_prim.CreateInput("occlusion", Sdf.ValueTypeNames.Float).Set(1.0)

                surface_out = shader_prim.CreateOutput("surface", Sdf.ValueTypeNames.Token)
                surface_out.SetRenderType("material")

                shader_prim.CreateOutput("displacement", Sdf.ValueTypeNames.Token).SetRenderType("material")
                material_prim.CreateSurfaceOutput().ConnectToSource(surface_out)

                shader_prim.GetPrim().SetPropertyOrder(
                    [
                        "inputs:diffuseColor",
                        "inputs:emissiveColor",
                        "inputs:useSpecularWorkflow",
                        "inputs:specularColor",
                        "inputs:metallic",
                        "inputs:roughness",
                        "inputs:clearcoat",
                        "inputs:clearcoatRoughness",
                        "inputs:opacity",
                        "inputs:opacityThreshold",
                        "inputs:ior",
                        "inputs:normal",
                        "inputs:displacement",
                        "inputs:occlusion",
                        "outputs:surface",
                        "outputs:displacement",
                    ]
                )
                if self._select_new_prim:
                    omni.usd.get_context().get_selection().set_prim_path_selected(
                        self._mtl_path, True, True, True, True
                    )
            else:
                DeletePrimsCommand([material_prim.GetPath().pathString]).do()
                carb.log_warn(f"failed to create shader {shader_path}")
        else:
            carb.log_warn(f"failed to create prim {mat_prim.GetPath().pathString}")

    def undo(self):
        stage = omni.usd.get_context().get_stage()
        mat_prim = stage.GetPrimAtPath(self._mtl_path)
        if mat_prim:
            DeletePrimsCommand([mat_prim.GetPath().pathString]).do()


class CreatePreviewSurfaceTextureMaterialPrimCommand(omni.kit.commands.Command):
    """
    Create Preview Surface Texture Material undoable **Command**.

    Args:
        mtl_path (str):
        select_new_prim (bool):
    """

    def __init__(self, mtl_path, select_new_prim: bool = False):
        stage = omni.usd.get_context().get_stage()
        self._mtl_path = Sdf.Path(mtl_path)
        self._select_new_prim = select_new_prim

    def _create_shader(self, stage: Usd.Stage, shader_name: str, shader_id: str):
        shader_name = self._mtl_path.AppendElementString(shader_name)
        shader_path = stage.DefinePrim(shader_name, "Shader")
        shader_prim = UsdShade.Shader.Get(stage, shader_path.GetPath())
        if shader_prim:
            shader_prim.CreateIdAttr(shader_id)
            return shader_prim
        raise Exception(f"failed to create shader {shader_path}")

    def do(self):
        stage = omni.usd.get_context().get_stage()

        # It's possible that parents of material are inactive so the material path is existed
        # already after it's activated. Regenerating the path to avoid conflicts.
        self._mtl_path = Sdf.Path(omni.usd.get_stage_next_free_path(stage, self._mtl_path, False))

        ensure_parents_are_active(stage, self._mtl_path)

        mat_prim = stage.DefinePrim(self._mtl_path, "Material")
        material_prim = UsdShade.Material.Get(stage, mat_prim.GetPath())
        if material_prim:
            try:
                preview_shader_prim = self._create_shader(stage, "PreviewSurfaceTexture", "UsdPreviewSurface")
                preview_shader_prim.CreateInput("clearcoat", Sdf.ValueTypeNames.Float).Set(0.0)
                preview_shader_prim.CreateInput("clearcoatRoughness", Sdf.ValueTypeNames.Float).Set(0.0)
                preview_shader_prim.CreateInput("displacement", Sdf.ValueTypeNames.Float).Set(0)
                preview_shader_prim.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set((0.0, 0.0, 0.0))
                preview_shader_prim.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(1.5)
                preview_shader_prim.CreateInput("occlusion", Sdf.ValueTypeNames.Float).Set(1)
                preview_shader_prim.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(1)
                preview_shader_prim.CreateInput("opacityThreshold", Sdf.ValueTypeNames.Float).Set(0)
                preview_shader_prim.CreateInput("specularColor", Sdf.ValueTypeNames.Color3f).Set((0.0, 0.0, 0.0))
                preview_shader_prim.CreateInput("useSpecularWorkflow", Sdf.ValueTypeNames.Int).Set(0)
                surface_out = preview_shader_prim.CreateOutput("surface", Sdf.ValueTypeNames.Token)
                surface_out.SetRenderType("material")

                def set_default_usduvtexture_values(prim, color_space="auto"):
                    prim.CreateInput("fallback", Sdf.ValueTypeNames.Float4).Set((0, 0, 0, 1))
                    prim.CreateInput("file", Sdf.ValueTypeNames.Asset).Set("")
                    prim.CreateOutput("rgb", Sdf.ValueTypeNames.Color3f)
                    prim.CreateInput("scale", Sdf.ValueTypeNames.Float4).Set((1, 1, 1, 1))
                    prim.CreateInput("bias", Sdf.ValueTypeNames.Float4).Set((0, 0, 0, 0))
                    prim.CreateInput("sdrMetadata", Sdf.ValueTypeNames.Token).Set("texture")
                    attr = prim.CreateInput("wrapS", Sdf.ValueTypeNames.Token).GetAttr()
                    attr.Set("useMetadata")
                    attr.SetMetadata("allowedTokens", ["black", "clamp", "repeat", "mirror", "useMetadata"])
                    attr = prim.CreateInput("wrapT", Sdf.ValueTypeNames.Token).GetAttr()
                    attr.Set("useMetadata")
                    attr.SetMetadata("allowedTokens", ["black", "clamp", "repeat", "mirror", "useMetadata"])
                    attr = prim.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).GetAttr()
                    attr.Set(color_space)
                    attr.SetMetadata("allowedTokens", ["auto", "raw", "sRGB"])

                diffuse_prim = self._create_shader(stage, "diffuseColorTex", "UsdUVTexture")
                set_default_usduvtexture_values(diffuse_prim)

                metallic_prim = self._create_shader(stage, "metallicTex", "UsdUVTexture")
                set_default_usduvtexture_values(metallic_prim)

                roughness_prim = self._create_shader(stage, "roughnessTex", "UsdUVTexture")
                set_default_usduvtexture_values(roughness_prim)

                normal_prim = self._create_shader(stage, "normalTex", "UsdUVTexture")
                set_default_usduvtexture_values(normal_prim, color_space="raw")

                preview_shader_prim.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
                    diffuse_prim.GetOutput("rgb")
                )
                preview_shader_prim.CreateInput("metallic", Sdf.ValueTypeNames.Color3f).ConnectToSource(
                    metallic_prim.GetOutput("rgb")
                )
                preview_shader_prim.CreateInput("roughness", Sdf.ValueTypeNames.Color3f).ConnectToSource(
                    roughness_prim.GetOutput("rgb")
                )
                preview_shader_prim.CreateInput("normal", Sdf.ValueTypeNames.Normal3f).ConnectToSource(
                    normal_prim.GetOutput("rgb")
                )
                material_prim.CreateSurfaceOutput().ConnectToSource(surface_out)

            except:
                DeletePrimsCommand([material_prim.GetPath().pathString]).do()
                carb.log_warn(f"failed to create prim {mat_prim.GetPath().pathString}")
        else:
            carb.log_warn(f"failed to create prim {mat_prim.GetPath().pathString}")

    def undo(self):
        stage = omni.usd.get_context().get_stage()
        mat_prim = stage.GetPrimAtPath(self._mtl_path)
        if mat_prim:
            DeletePrimsCommand([mat_prim.GetPath().pathString]).do()


class ClearCurvesSplitsOverridesCommand(omni.kit.commands.Command):
    """
    Clear Curves Splits Overrides  **Command**.

    """

    def do(self):
        stage = omni.usd.get_context().get_stage()
        layer = stage.GetEditTarget().GetLayer()
        with Sdf.ChangeBlock():
            for prim in [x for x in stage.Traverse() if x.GetTypeName() in ["BasisCurves"]]:
                primSpec = layer.GetPrimAtPath(prim.GetPath())
                for attrName in ["primvars:numSplitsOverride", "primvars:numSplits"]:
                    propertySpec = layer.GetPropertyAtPath(prim.GetPath().AppendProperty(attrName))
                    if propertySpec:
                        primSpec.RemoveProperty(propertySpec)


class ClearRefinementOverridesCommand(omni.kit.commands.Command):
    """
    Clear Refinement Overrides  **Command**.

    """

    def __init__(self):
        self._undo_data = {"refinementOverrideImplVersion": None, "prim_attrs": {}}

    def do(self):
        stage = omni.usd.get_context().get_stage()
        layer = stage.GetEditTarget().GetLayer()
        custom_data = layer.customLayerData
        with Sdf.ChangeBlock():
            if "refinementOverrideImplVersion" in custom_data:
                self._undo_data["refinementOverrideImplVersion"] = custom_data["refinementOverrideImplVersion"]
                del custom_data["refinementOverrideImplVersion"]
                layer.customLayerData = custom_data

            for prim in [
                x for x in stage.Traverse() if x.GetTypeName() in ["Mesh", "Sphere", "Cylinder", "Cone", "Capsule"]
            ]:
                primSpec = layer.GetPrimAtPath(prim.GetPath())
                for attrName in ["refinementEnableOverride", "refinementLevel"]:
                    propertySpec = layer.GetPropertyAtPath(prim.GetPath().AppendProperty(attrName))
                    if propertySpec:
                        # keep undo copy
                        if not prim.GetPath().pathString in self._undo_data["prim_attrs"]:
                            self._undo_data["prim_attrs"][prim.GetPath().pathString] = {}
                        attr = prim.GetAttribute(attrName)
                        self._undo_data["prim_attrs"][prim.GetPath().pathString][attrName] = attr.Get()
                        # remove property
                        primSpec.RemoveProperty(propertySpec)

    def undo(self):
        stage = omni.usd.get_context().get_stage()
        layer = stage.GetEditTarget().GetLayer()
        custom_data = layer.customLayerData
        with Sdf.ChangeBlock():
            if self._undo_data["refinementOverrideImplVersion"]:
                custom_data["refinementOverrideImplVersion"] = self._undo_data["refinementOverrideImplVersion"]
                self._undo_data["refinementOverrideImplVersion"] = None
                layer.customLayerData = custom_data

        # create attributes 1st as its problematic to CreateAttribute & Set inside a Sdf.ChangeBlock
        for prim_path in self._undo_data["prim_attrs"]:
            prim = stage.GetPrimAtPath(prim_path)
            prim.CreateAttribute("refinementEnableOverride", Sdf.ValueTypeNames.Bool)
            prim.CreateAttribute("refinementLevel", Sdf.ValueTypeNames.Int)

        # set attributes
        with Sdf.ChangeBlock():
            for prim_path in self._undo_data["prim_attrs"]:
                attr_data = self._undo_data["prim_attrs"][prim_path]
                prim = stage.GetPrimAtPath(prim_path)
                prim.GetAttribute("refinementEnableOverride").Set(attr_data["refinementEnableOverride"])
                prim.GetAttribute("refinementLevel").Set(attr_data["refinementLevel"])
            self._undo_data["prim_attrs"] = {}


class RelationshipTargetBase(omni.kit.commands.Command):
    def __init__(self, relationship: Usd.Relationship, target: Sdf.Path):
        self._stage = weakref.ref(relationship.GetStage())
        self._rel_path = relationship.GetPath()
        self._target = target
        self._prev_targets = None

    def _get_relationship(self):
        stage = self._stage()
        if stage:
            rel = stage.GetRelationshipAtPath(self._rel_path)
            return rel
        return None

    def undo(self):
        rel = self._get_relationship()
        if rel and self._prev_targets is not None:
            rel.SetTargets(self._prev_targets)


class AddRelationshipTargetCommand(RelationshipTargetBase):
    """
    Add target to a relationship
    """

    def __init__(self, relationship: Usd.Relationship, target: Sdf.Path, position=Usd.ListPositionBackOfPrependList):
        super().__init__(relationship, target)
        self._position = position

    def do(self):
        rel = self._get_relationship()
        if rel:
            self._prev_targets = rel.GetTargets()
            rel.AddTarget(self._target, self._position)


class RemoveRelationshipTargetCommand(RelationshipTargetBase):
    """
    Remove target from a relationship
    """

    def __init__(self, relationship: Usd.Relationship, target: Sdf.Path):
        super().__init__(relationship, target)

    def do(self):
        rel = self._get_relationship()
        if rel:
            self._prev_targets = rel.GetTargets()
            rel.RemoveTarget(self._target)


class SetRelationshipTargetsCommand(RelationshipTargetBase):
    """
    Set target(s) to a relationship
    """

    def __init__(self, relationship: Usd.Relationship, targets: List[Sdf.Path]):
        super().__init__(relationship, None)
        self._targets = targets

    def do(self):
        rel = self._get_relationship()
        if rel:
            self._prev_targets = rel.GetTargets()
            rel.SetTargets(self._targets)


class ReferenceCommandBase(omni.kit.commands.Command):
    def __init__(self, stage, prim_path: Sdf.Path, reference: Sdf.Reference):
        self._prim_path = prim_path
        self._reference = reference
        self._stage = weakref.ref(stage)
        self._reference_list = None
        self._had_prim_spec = False

    def _get_references(self):
        stage = self._stage()
        if stage:
            prim = stage.GetPrimAtPath(self._prim_path)
            if prim:
                return prim.GetReferences()
        return None

    def _get_reference_list_op(self):
        stage = self._stage()
        if stage:
            prim = stage.GetPrimAtPath(self._prim_path)
            if prim:
                return prim.GetMetadata("references")
        return None

    def _save_current_reference_list(self):
        stage = self._stage()
        if stage:
            prim_spec = stage.GetEditTarget().GetLayer().GetPrimAtPath(self._prim_path)
            if prim_spec:
                self._had_prim_spec = True
                self._reference_list = prim_spec.referenceList
            else:
                self._had_prim_spec = False

    def _restore_saved_reference_list(self):
        stage = self._stage()
        if stage:
            if self._had_prim_spec:
                prim_spec = stage.GetEditTarget().GetLayer().GetPrimAtPath(self._prim_path)
                if prim_spec and self._reference_list:
                    if self._reference_list.isExplicit:
                        prim_spec.referenceList.explicitItems[:] = self._reference_list.explicitItems[:]
                    else:
                        prim_spec.referenceList.addedItems[:] = self._reference_list.addedItems[:]
                        prim_spec.referenceList.prependedItems[:] = self._reference_list.prependedItems[:]
                        prim_spec.referenceList.appendedItems[:] = self._reference_list.appendedItems[:]
                        prim_spec.referenceList.deletedItems[:] = self._reference_list.deletedItems[:]
                        prim_spec.referenceList.orderedItems[:] = self._reference_list.orderedItems[:]
            else:
                edit = Sdf.BatchNamespaceEdit()
                edit.Add(self._prim_path, Sdf.Path.emptyPath)
                stage.GetEditTarget().GetLayer().Apply(edit)


class AddReferenceCommand(ReferenceCommandBase):
    def __init__(
        self, stage, prim_path: Sdf.Path, reference: Sdf.Reference, position=Usd.ListPositionBackOfPrependList
    ):
        super().__init__(stage, prim_path, reference)
        self._position = position

    def do(self):
        references = self._get_references()
        if references:
            self._save_current_reference_list()
            references.AddReference(self._reference, self._position)

    def undo(self):
        self._restore_saved_reference_list()


class RemoveReferenceCommand(ReferenceCommandBase):
    def __init__(self, stage, prim_path: Sdf.Path, reference: Sdf.Reference):
        super().__init__(stage, prim_path, reference)

    def do(self):
        references = self._get_references()
        if references:
            self._save_current_reference_list()
            references.RemoveReference(self._reference)

    def undo(self):
        self._restore_saved_reference_list()


class ReplaceReferenceCommand(ReferenceCommandBase):
    def __init__(self, stage, prim_path: Sdf.Path, old_reference: Sdf.Reference, new_reference: Sdf.Reference):
        super().__init__(stage, prim_path, old_reference)
        self._new_reference = new_reference

    def do(self):
        stage = self._stage()
        if stage:
            self._save_current_reference_list()

            remove_cmd = RemoveReferenceCommand(stage, self._prim_path, self._reference)
            remove_cmd.do()

            add_cmd = AddReferenceCommand(stage, self._prim_path, self._new_reference)
            add_cmd.do()

    def undo(self):
        self._restore_saved_reference_list()


class PayloadCommandBase(omni.kit.commands.Command):
    def __init__(self, stage, prim_path: Sdf.Path, payload: Sdf.Payload):
        self._prim_path = prim_path
        self._payload = payload
        self._stage = weakref.ref(stage)
        self._payload_list = None
        self._had_prim_spec = False

    def _get_payloads(self):
        stage = self._stage()
        if stage:
            prim = stage.GetPrimAtPath(self._prim_path)
            if prim:
                return prim.GetPayloads()
        return None

    def _get_payload_list_op(self):
        stage = self._stage()
        if stage:
            prim = stage.GetPrimAtPath(self._prim_path)
            if prim:
                return prim.GetMetadata("payloads")
        return None

    def _save_current_payload_list(self):
        stage = self._stage()
        if stage:
            prim_spec = stage.GetEditTarget().GetLayer().GetPrimAtPath(self._prim_path)
            if prim_spec:
                self._had_prim_spec = True
                self._payload_list = prim_spec.payloadList
            else:
                self._had_prim_spec = False

    def _restore_saved_payload_list(self):
        stage = self._stage()
        if stage:
            if self._had_prim_spec:
                prim_spec = stage.GetEditTarget().GetLayer().GetPrimAtPath(self._prim_path)
                if prim_spec and self._payload_list:
                    if self._payload_list.isExplicit:
                        prim_spec.payloadList.explicitItems[:] = self._payload_list.explicitItems[:]
                    else:
                        prim_spec.payloadList.addedItems[:] = self._payload_list.addedItems[:]
                        prim_spec.payloadList.prependedItems[:] = self._payload_list.prependedItems[:]
                        prim_spec.payloadList.appendedItems[:] = self._payload_list.appendedItems[:]
                        prim_spec.payloadList.deletedItems[:] = self._payload_list.deletedItems[:]
                        prim_spec.payloadList.orderedItems[:] = self._payload_list.orderedItems[:]
            else:
                edit = Sdf.BatchNamespaceEdit()
                edit.Add(self._prim_path, Sdf.Path.emptyPath)
                stage.GetEditTarget().GetLayer().Apply(edit)


class AddPayloadCommand(PayloadCommandBase):
    def __init__(self, stage, prim_path: Sdf.Path, payload: Sdf.Payload, position=Usd.ListPositionBackOfPrependList):
        super().__init__(stage, prim_path, payload)
        self._position = position

    def do(self):
        payloads = self._get_payloads()
        if payloads:
            self._save_current_payload_list()
            payloads.AddPayload(self._payload, self._position)

    def undo(self):
        self._restore_saved_payload_list()


class RemovePayloadCommand(PayloadCommandBase):
    def __init__(self, stage, prim_path: Sdf.Path, payload: Sdf.Payload):
        super().__init__(stage, prim_path, payload)

    def do(self):
        payloads = self._get_payloads()
        if payloads:
            self._save_current_payload_list()
            payloads.RemovePayload(self._payload)

    def undo(self):
        self._restore_saved_payload_list()


class ReplacePayloadCommand(PayloadCommandBase):
    def __init__(self, stage, prim_path: Sdf.Path, old_payload: Sdf.Payload, new_payload: Sdf.Payload):
        super().__init__(stage, prim_path, old_payload)
        self._new_payload = new_payload

    def do(self):
        stage = self._stage()
        if stage:
            self._save_current_payload_list()

            remove_cmd = RemovePayloadCommand(stage, self._prim_path, self._payload)
            remove_cmd.do()

            add_cmd = AddPayloadCommand(stage, self._prim_path, self._new_payload)
            add_cmd.do()

    def undo(self):
        self._restore_saved_payload_list()


class CreatePrimCommandBase(omni.kit.commands.Command):
    """
    Base class to create a prim (and remove when undo)

    Args:
        usd_context (omni.usd.UsdContext): UsdContext this command to run on.
        path_to (Sdf.Path): Path to create a new prim.
        asset_path (str): The asset it's necessary to add to references.
        select_prim (bool): = True,  Whether to select the newly created UsdPrim or not.
    """

    def __init__(self, usd_context: omni.usd.UsdContext, path_to: Sdf.Path, asset_path: str, select_prim: bool = True):
        # TODO (105): Make these private and only cache UsdContext name
        self._usd_context = usd_context
        self._selection = self._usd_context.get_selection()

        stage = self._usd_context.get_stage()
        path_to = Sdf.Path(omni.usd.get_stage_next_free_path(stage, str(path_to), False))

        self._asset_path = asset_path
        self._path_to = path_to
        self._previous_selection = None
        self.__select_prim = select_prim

    def do(self):
        if not self.__select_prim:
            return

        # Save the selection and select the created prim.
        self._previous_selection = self._selection.get_selected_prim_paths()
        async def select_prims(self: CreatePrimCommandBase):
            self._selection.set_selected_prim_paths([str(self._path_to)], False)

        import asyncio
        asyncio.ensure_future(select_prims(self))

    def undo(self):
        delete_cmd = DeletePrimsCommand([self._path_to])
        delete_cmd.do()

        # Restore selection
        if self._previous_selection is not None:
            self._selection.set_selected_prim_paths(self._previous_selection, False)


class CreateReferenceCommand(CreatePrimCommandBase):
    """
    Create reference undoable **Command**.

    It creates a new prim and adds the asset and path as references.

    Args:
        usd_context (omni.usd.UsdContext): UsdContext this command to run on.
        path_to (Sdf.Path): Path to create a new prim.
        asset_path (str): The asset it's necessary to add to references.
        prim_path (Sdf.Path): The prim in asset to reference.
        instanceable (bool): Whether to set the prim instanceable. It works together with `/persistent/app/stage/instanceableOnCreatingReference` setting.
        select_prim (bool): = True,  Whether to select the newly created UsdPrim or not.
    """

    def __init__(
        self,
        usd_context: omni.usd.UsdContext,
        path_to: Sdf.Path,
        asset_path: str = None,
        prim_path: Sdf.Path = None,
        instanceable: bool = True,
        select_prim: bool = True,
    ):
        super().__init__(usd_context, path_to, asset_path, select_prim)
        self._prim_path = prim_path
        self._instanceable = instanceable
        self._settings = carb.settings.get_settings()

    def do(self):
        stage = self._usd_context.get_stage()
        
        ensure_parents_are_active(stage, self._path_to)

        prim_to = stage.DefinePrim(self._path_to)

        with Sdf.ChangeBlock():
            if self._asset_path:
                edit_target = stage.GetEditTarget()
                current_layer = edit_target.GetLayer()
                relative_url = clientutils.make_relative_url_if_possible(
                    current_layer.identifier, self._asset_path
                )
                if self._prim_path:
                    prim_to.GetReferences().AddReference(relative_url, self._prim_path)
                else:
                    prim_to.GetReferences().AddReference(relative_url)
            elif self._prim_path:
                prim_to.GetReferences().AddInternalReference(self._prim_path)

        # Set instanceable
        if prim_to.IsA(UsdGeom.Xform):
            prim_to.SetInstanceable(
                self._instanceable
                and self._settings.get(PERSISTENT_SETTINGS_PREFIX + "/app/stage/instanceableOnCreatingReference")
            )

        asset_layer = Sdf.Layer.FindOrOpen(self._asset_path)
        if prim_to.IsA(UsdGeom.Xformable) and asset_layer:
            # FIXME: OM-50609: WA to avoid crash if target_path includes format symbols.
            anonymous_layer = Sdf.Layer.CreateAnonymous()
            ref_stage = Usd.Stage.Open(asset_layer, anonymous_layer)
            if ref_stage:
                ref_up = UsdGeom.GetStageUpAxis(ref_stage)
                curr_up = UsdGeom.GetStageUpAxis(stage)

                if ref_up != curr_up:
                    ref_xform_mat = UsdGeom.Xformable(prim_to).GetLocalTransformation()
                    adj_mat = Gf.Matrix4d()
                    if ref_up == "Y":
                        adj_mat = Gf.Matrix4d(
                            0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0
                        )
                    elif ref_up == "Z":
                        adj_mat = Gf.Matrix4d(
                            0.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0
                        )
                    if adj_mat != Gf.Matrix4d():
                        ref_xform_mat = ref_xform_mat * adj_mat
                        omni.kit.commands.execute(
                            "TransformPrim", path=prim_to.GetPrimPath(), new_transform_matrix=ref_xform_mat
                        )

        super().do()

    def undo(self):
        # Dereference this. Otherwise it fires error: Cannot remove ancestral prim
        stage = self._usd_context.get_stage()
        prim_to = stage.GetPrimAtPath(self._path_to)
        prim_to.GetReferences().ClearReferences()

        super().undo()


class CreatePayloadCommand(CreatePrimCommandBase):
    """
    Create payload undoable **Command**.

    It creates a new prim and adds the asset and path as payloads.

    Args:
        usd_context (omni.usd.UsdContext): UsdContext this command to run on.
        path_to (Sdf.Path): Path to create a new prim.
        asset_path (str): The asset it's necessary to add to payloads.
        prim_path (Sdf.Path): The prim in asset to payload.
        instanceable (bool): Whether to set the prim instanceable. It works together with `/persistent/app/stage/instanceableOnCreatingReference` setting.
        select_prim (bool): = True,  Whether to select the newly created UsdPrim or not.
    """

    def __init__(
        self,
        usd_context: omni.usd.UsdContext,
        path_to: Sdf.Path,
        asset_path: str = None,
        prim_path: Sdf.Path = None,
        instanceable: bool = True,
        select_prim: bool = True,
    ):
        super().__init__(usd_context, path_to, asset_path, select_prim)
        self._prim_path = prim_path
        self._instanceable = instanceable
        self._settings = carb.settings.get_settings()

    def do(self):
        stage = self._usd_context.get_stage()

        ensure_parents_are_active(stage, self._path_to)

        prim_to = stage.DefinePrim(self._path_to)

        with Sdf.ChangeBlock():
            if self._asset_path:
                edit_target = stage.GetEditTarget()
                current_layer = edit_target.GetLayer()
                relative_url = clientutils.make_relative_url_if_possible(
                    current_layer.identifier, self._asset_path
                )
                if self._prim_path:
                    prim_to.GetPayloads().AddPayload(relative_url, self._prim_path)
                else:
                    prim_to.GetPayloads().AddPayload(relative_url)
            elif self._prim_path:
                prim_to.GetPayloads().AddInternalPayload(self._prim_path)

        # Set instanceable
        if prim_to.IsA(UsdGeom.Xform):
            prim_to.SetInstanceable(
                self._instanceable
                and self._settings.get(PERSISTENT_SETTINGS_PREFIX + "/app/stage/instanceableOnCreatingReference")
            )

        asset_layer = Sdf.Layer.FindOrOpen(self._asset_path)
        if prim_to.IsA(UsdGeom.Xformable) and asset_layer:
            # FIXME: OM-50609: WA to avoid crash if target_path includes format symbols.
            anonymous_layer = Sdf.Layer.CreateAnonymous()
            ref_stage = Usd.Stage.Open(asset_layer, anonymous_layer)
            if ref_stage:
                ref_up = UsdGeom.GetStageUpAxis(ref_stage)
                curr_up = UsdGeom.GetStageUpAxis(stage)

                if ref_up != curr_up:
                    ref_xform_mat = UsdGeom.Xformable(prim_to).GetLocalTransformation()
                    adj_mat = Gf.Matrix4d()
                    if ref_up == "Y":
                        adj_mat = Gf.Matrix4d(
                            0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0
                        )
                    elif ref_up == "Z":
                        adj_mat = Gf.Matrix4d(
                            0.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0
                        )
                    if adj_mat != Gf.Matrix4d():
                        ref_xform_mat = ref_xform_mat * adj_mat
                        omni.kit.commands.execute(
                            "TransformPrim", path=prim_to.GetPrimPath(), new_transform_matrix=ref_xform_mat
                        )

        super().do()

    def undo(self):
        # Dereference this. Otherwise it fires error: Cannot remove ancestral prim
        stage = self._usd_context.get_stage()
        prim_to = stage.GetPrimAtPath(self._path_to)
        prim_to.GetPayloads().ClearPayloads()

        super().undo()


class CreateAudioPrimFromAssetPathCommand(CreatePrimCommandBase):
    """
    Create reference undoable **Command**.

    It creates a new Audio prim.

    Args:
        usd_context (omni.usd.UsdContext): UsdContext this command to run on.
        path_to (Sdf.Path): Path to create a new prim.
        asset_path (str): The asset it's necessary to add to references.
        select_prim (bool): = True,  Whether to select the newly created UsdPrim or not.
    """

    def __init__(self, usd_context: omni.usd.UsdContext, path_to: Sdf.Path, asset_path: str, select_prim: bool = True):
        super().__init__(usd_context, path_to, asset_path, select_prim)

    def do(self):
        sound = AudioSchema.Sound.Define(self._usd_context.get_stage(), self._path_to)
        if sound:
            sound.CreateFilePathAttr(self._asset_path)
            super().do()
