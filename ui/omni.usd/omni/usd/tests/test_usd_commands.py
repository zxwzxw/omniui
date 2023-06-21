from cgitb import strong
from pathlib import Path
import carb
from numpy import delete
import omni.kit.test

import omni.kit.undo
import omni.kit.commands
import omni.timeline
import omni.usd
import omni.client
import omni.client.utils as clientutils

from pxr import Gf, Kind, Sdf, Usd, UsdGeom, UsdShade

CURRENT_PATH = Path(__file__).parent.joinpath("data").absolute().resolve()

FILE_PATH_ROOT = str(CURRENT_PATH.joinpath("material_root.usda")).replace("\\", "/")
FILE_PATH_SUB = str(CURRENT_PATH.joinpath("material_sub.usda")).replace("\\", "/")


def getStageDefaultPrimPath(stage):
    if stage.HasDefaultPrim():
        return stage.GetDefaultPrim().GetPath()
    else:
        return Sdf.Path.absoluteRootPath


class TestUsdCommands(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()

    async def tearDown(self):
        await omni.usd.get_context().close_stage_async()

    async def test_create_prim(self):
        omni.kit.commands.execute("CreatePrim", prim_type="Sphere")
        stage = omni.usd.get_context().get_stage()
        default_prim_path = getStageDefaultPrimPath(stage)

        def check_exist():
            prim = stage.GetPrimAtPath(default_prim_path.AppendChild("Sphere"))
            self.assertTrue(prim)
            self.assertFalse(prim.IsA(UsdGeom.Mesh))
            self.assertTrue(prim.IsA(UsdGeom.Xformable))
            self.assertTrue(prim.IsA(UsdGeom.Sphere))
            self.assertFalse(prim.IsA(UsdGeom.Cylinder))
            model_api = Usd.ModelAPI(prim)
            kind = model_api.GetKind()
            self.assertFalse(kind == Kind.Tokens.model)

        def check_does_not_exist():
            self.assertFalse(stage.GetPrimAtPath(default_prim_path.AppendChild("Sphere")))

        check_exist()

        # give hydra a frame before deleting to catch up so it doesn't spew coding error about not finding prim
        await omni.kit.app.get_app().next_update_async()
        omni.kit.undo.undo()
        check_does_not_exist()
        omni.kit.undo.redo()
        check_exist()
        omni.kit.undo.undo()
        check_does_not_exist()

    async def test_copy_prim(self):
        stage = omni.usd.get_context().get_stage()
        default_prim_path = getStageDefaultPrimPath(stage)
        root_layer = stage.GetRootLayer()
        ref_stage = Usd.Stage.CreateInMemory()
        ref_layer = ref_stage.GetRootLayer()

        root_ref_cube = UsdGeom.Cube.Define(ref_stage, "/Cube")
        UsdGeom.Cube.Define(ref_stage, "/Cube/Cube2")
        ref_stage.SetDefaultPrim(root_ref_cube.GetPrim())

        layer_strong = Sdf.Layer.CreateAnonymous()
        layer_weak = Sdf.Layer.CreateAnonymous()
        layer_copy = Sdf.Layer.CreateAnonymous()

        root_layer.subLayerPaths = [layer_strong.identifier, layer_weak.identifier, layer_copy.identifier]

        with Usd.EditContext(stage, layer_weak):
            omni.kit.commands.execute("CreatePrim", prim_type="Sphere")
            stage.DefinePrim("/RefCube").GetReferences().AddReference(ref_layer.identifier)

        prim = stage.GetPrimAtPath(default_prim_path.AppendChild("Sphere"))
        prim_ref_leaf = stage.GetPrimAtPath("/RefCube/Cube2")
        self.assertTrue(prim)
        self.assertTrue(prim_ref_leaf)
        self.assertTrue(layer_weak.GetPrimAtPath(default_prim_path.AppendChild("Sphere")))
        self.assertFalse(layer_strong.GetPrimAtPath(default_prim_path.AppendChild("Sphere")))
        sphere = UsdGeom.Sphere(prim)

        # Create delta on strong layer
        with Usd.EditContext(stage, layer_strong):
            sphere.CreateRadiusAttr(1.234)

        radius = sphere.GetRadiusAttr().Get()
        self.assertTrue(radius == 1.234)

        def check(expected_path, expected_radius, assert_strong, assert_weak, assert_copy):
            nonlocal layer_strong
            nonlocal layer_weak
            nonlocal layer_copy
            assert_strong(layer_strong.GetPrimAtPath(expected_path))
            assert_weak(layer_weak.GetPrimAtPath(expected_path))
            assert_copy(layer_copy.GetPrimAtPath(expected_path))
            sphere = UsdGeom.Sphere(stage.GetPrimAtPath(expected_path))
            radius = sphere.GetRadiusAttr().Get()
            self.assertTrue(radius == expected_radius)

        # Test default copy behavior
        # Expected: default_prim_path.AppendChild("Sphere_01") created only on layer_copy. delta on layer_strong will be discarded.
        expected_path = default_prim_path.AppendChild("Sphere_01")
        carb.log_info("Test Duplicate")
        with Usd.EditContext(stage, layer_copy):
            omni.kit.commands.execute("CopyPrim", path_from=default_prim_path.AppendChild("Sphere").pathString)
            check(expected_path, 1.0, self.assertFalse, self.assertFalse, self.assertTrue)
            omni.kit.undo.undo()
            self.assertFalse(stage.GetPrimAtPath(expected_path))
            omni.kit.undo.redo()
            check(expected_path, 1.0, self.assertFalse, self.assertFalse, self.assertTrue)

        # Test copy all layers separately
        # Expected: default_prim_path.AppendChild("SphereAllLayer") created on layer_weak and layer_strong. Delta preserved in layer_strong.
        expected_path = default_prim_path.AppendChild("SphereAllLayers")
        carb.log_info("Test Duplicate - All Layers")
        with Usd.EditContext(stage, layer_copy):
            omni.kit.commands.execute(
                "CopyPrim",
                path_from=default_prim_path.AppendChild("Sphere").pathString,
                path_to=expected_path.pathString,
                duplicate_layers=True,
            )
            check(expected_path, 1.234, self.assertTrue, self.assertTrue, self.assertFalse)
            omni.kit.undo.undo()
            self.assertFalse(stage.GetPrimAtPath(expected_path))
            omni.kit.undo.redo()
            check(expected_path, 1.234, self.assertTrue, self.assertTrue, self.assertFalse)

        # Test copy all layers and collapse to one combined prim.
        # Expected: default_prim_path.AppendChild("SphereCollapsed") created on layer_copy. Delta combined into final result.
        expected_path = default_prim_path.AppendChild("SphereCollapsed")
        carb.log_info("Test Duplicate - Collapsed")
        with Usd.EditContext(stage, layer_copy):
            omni.kit.commands.execute(
                "CopyPrim",
                path_from=default_prim_path.AppendChild("Sphere").pathString,
                path_to=expected_path.pathString,
                combine_layers=True,
            )
            check(expected_path, 1.234, self.assertFalse, self.assertFalse, self.assertTrue)
            omni.kit.undo.undo()
            self.assertFalse(stage.GetPrimAtPath(expected_path))
            omni.kit.undo.redo()
            check(expected_path, 1.234, self.assertFalse, self.assertFalse, self.assertTrue)

        # Test collaps a child of a referenced prim.
        # Expected: /RefCube/Cube2_01 will not be created on layer_copy as its ancestor is a gprim.
        expected_path = "/RefCube/Cube2_01"
        self.assertFalse(stage.GetPrimAtPath(expected_path))
        with Usd.EditContext(stage, layer_copy):
            omni.kit.commands.execute("CopyPrim", path_from="/RefCube/Cube2", combine_layers=True)
            self.assertFalse(stage.GetPrimAtPath(expected_path))

        expected_path = "/Root/Cube2"
        self.assertFalse(stage.GetPrimAtPath(expected_path))
        with Usd.EditContext(stage, layer_copy):
            omni.kit.commands.execute("CopyPrim", path_from="/RefCube/Cube2", path_to=expected_path, combine_layers=True)
            self.assertTrue(stage.GetPrimAtPath(expected_path))
            omni.kit.undo.undo()
            self.assertFalse(stage.GetPrimAtPath(expected_path))
            omni.kit.undo.redo()
            self.assertTrue(stage.GetPrimAtPath(expected_path))

    async def test_copy_prims(self):
        usd_context = omni.usd.get_context()
        selection = usd_context.get_selection()
        stage = usd_context.get_stage()
        default_prim_path = getStageDefaultPrimPath(stage)
        sublayer = Sdf.Layer.CreateAnonymous()
        root_layer = stage.GetRootLayer()
        root_layer.subLayerPaths.append(sublayer.identifier)

        with Usd.EditContext(stage, sublayer):
            omni.kit.commands.execute("CreatePrims", prim_types=["Sphere", "Cone", "Cube"])

        for combine_layers in [False, True]:
            for copy_to_introducing_layer in [False, True]:
                # Creates prims to sublayer to test copy to introducing layer.
                self.assertTrue(stage.GetPrimAtPath(default_prim_path.AppendChild("Sphere")))
                self.assertTrue(stage.GetPrimAtPath(default_prim_path.AppendChild("Cone")))
                self.assertTrue(stage.GetPrimAtPath(default_prim_path.AppendChild("Cube")))

                selected_paths_before = [
                    default_prim_path.AppendChild("Sphere").pathString,
                    default_prim_path.AppendChild("Cone").pathString,
                    default_prim_path.AppendChild("Cube").pathString,
                ]
                selection.set_selected_prim_paths(selected_paths_before, False)

                omni.kit.commands.execute("CopyPrims", paths_from=selection.get_selected_prim_paths(), combine_layers=combine_layers, copy_to_introducing_layer=copy_to_introducing_layer)

                self.assertTrue(stage.GetPrimAtPath(default_prim_path.AppendChild("Sphere_01")))
                self.assertTrue(stage.GetPrimAtPath(default_prim_path.AppendChild("Cone_01")))
                self.assertTrue(stage.GetPrimAtPath(default_prim_path.AppendChild("Cube_01")))
                
                # Copy to introducing layer only works if combine_layers is true
                if copy_to_introducing_layer:
                    target_layer = sublayer
                    false_layer = root_layer
                else:
                    target_layer = root_layer
                    false_layer = sublayer
                self.assertTrue(target_layer.GetPrimAtPath(default_prim_path.AppendChild("Sphere_01")))
                self.assertTrue(target_layer.GetPrimAtPath(default_prim_path.AppendChild("Cone_01")))
                self.assertTrue(target_layer.GetPrimAtPath(default_prim_path.AppendChild("Cube_01")))
                self.assertFalse(false_layer.GetPrimAtPath(default_prim_path.AppendChild("Sphere_01")))
                self.assertFalse(false_layer.GetPrimAtPath(default_prim_path.AppendChild("Cone_01")))
                self.assertFalse(false_layer.GetPrimAtPath(default_prim_path.AppendChild("Cube_01")))

                selected_paths_after = [
                    default_prim_path.AppendChild("Sphere_01").pathString,
                    default_prim_path.AppendChild("Cone_01").pathString,
                    default_prim_path.AppendChild("Cube_01").pathString,
                ]
                self.assertTrue(selection.get_selected_prim_paths() == selected_paths_after)

                omni.kit.undo.undo()

                self.assertFalse(stage.GetPrimAtPath(default_prim_path.AppendChild("Sphere_01")))
                self.assertFalse(stage.GetPrimAtPath(default_prim_path.AppendChild("Cone_01")))
                self.assertFalse(stage.GetPrimAtPath(default_prim_path.AppendChild("Cube_01")))
                self.assertTrue(selection.get_selected_prim_paths() == selected_paths_before)

                omni.kit.undo.redo()

                self.assertTrue(stage.GetPrimAtPath(default_prim_path.AppendChild("Sphere_01")))
                self.assertTrue(stage.GetPrimAtPath(default_prim_path.AppendChild("Cone_01")))
                self.assertTrue(stage.GetPrimAtPath(default_prim_path.AppendChild("Cube_01")))
                self.assertTrue(selection.get_selected_prim_paths() == selected_paths_after)
                
                omni.kit.undo.undo()
            
    async def test_delete_prims_with_multiple_sublayers(self):
        stage = omni.usd.get_context().get_stage()
        root_layer = stage.GetRootLayer()
        session_layer = stage.GetSessionLayer()
        format = Sdf.FileFormat.FindByExtension(".usd")
        strong_layer = Sdf.Layer.New(format, "z:/fake-path/subfolder/test.usd")
        weak_layer = Sdf.Layer.CreateAnonymous()
        root_layer.subLayerPaths.append(weak_layer.identifier)
        session_layer.subLayerPaths.append(strong_layer.identifier)

        test_prim_path = "/root/test"
        layer_list = [session_layer, strong_layer, root_layer, weak_layer]
        def delete_and_check(def_layer, current_layer, test_prim_path):
            has_prim_spec_before = not not current_layer.GetPrimAtPath(test_prim_path) 
            with Usd.EditContext(stage, current_layer):
                omni.kit.commands.execute("DeletePrims", paths=[test_prim_path], destructive=False)
                usd_prim = stage.GetPrimAtPath(test_prim_path)
                if def_layer == current_layer or (def_layer.anonymous and (not has_prim_spec_before or current_layer.anonymous)):
                    self.assertFalse(usd_prim)
                else:
                    self.assertTrue(usd_prim)
                    self.assertFalse(usd_prim.IsActive())
                    def_prim_spec = def_layer.GetPrimAtPath(test_prim_path)
                    current_prim_spec = current_layer.GetPrimAtPath(test_prim_path)
                    if def_layer.anonymous:
                        self.assertFalse(def_prim_spec)
                        if not current_layer.anonymous and has_prim_spec_before:
                            self.assertTrue(current_prim_spec)
                            self.assertTrue(current_prim_spec.HasActive())
                            self.assertFalse(current_prim_spec.active)
                        else:
                            self.assertFalse(current_prim_spec)
                    else:
                        self.assertTrue(def_prim_spec)
                        self.assertFalse(def_prim_spec.HasActive())
                        self.assertTrue(current_prim_spec)
                        self.assertTrue(current_prim_spec.HasActive())
                        self.assertFalse(current_prim_spec.active)

            omni.kit.undo.undo()
            usd_prim = stage.GetPrimAtPath(test_prim_path)
            self.assertTrue(usd_prim)
            self.assertTrue(usd_prim.IsActive())
            prim_spec = def_layer.GetPrimAtPath(test_prim_path)
            self.assertTrue(prim_spec)
            self.assertFalse(prim_spec.HasActive())
            prim_spec = current_layer.GetPrimAtPath(test_prim_path)
            if has_prim_spec_before:
                self.assertTrue(prim_spec)
                self.assertFalse(prim_spec.HasActive())
            else:
                self.assertFalse(prim_spec)

        layer_list = [session_layer, strong_layer, root_layer, weak_layer]
        for def_layer in layer_list:
            with Usd.EditContext(stage, def_layer):
                stage.DefinePrim(test_prim_path, "Xform")

            for current_layer in layer_list:
                if current_layer != def_layer:
                    for has_delta_before in [False, True]:
                        if has_delta_before:
                            with Usd.EditContext(stage, current_layer):
                                stage.DefinePrim(test_prim_path)

                        delete_and_check(def_layer, current_layer, test_prim_path)
                        with Usd.EditContext(stage, current_layer):
                            stage.RemovePrim(test_prim_path)
                else:
                    delete_and_check(def_layer, current_layer, test_prim_path)
            
            with Usd.EditContext(stage, def_layer):
                stage.RemovePrim(test_prim_path)

    async def test_delete_prims(self):
        stage = omni.usd.get_context().get_stage()
        default_prim_path = getStageDefaultPrimPath(stage)

        def check(assert_fn):
            nonlocal stage
            assert_fn(stage.GetPrimAtPath(default_prim_path.AppendChild("Sphere")))
            assert_fn(stage.GetPrimAtPath(default_prim_path.AppendChild("Cube")))
            assert_fn(stage.GetPrimAtPath(default_prim_path.AppendChild("Cone")))
            assert_fn(stage.GetPrimAtPath(default_prim_path.AppendChild("Cylinder")))
            assert_fn(stage.GetPrimAtPath(default_prim_path.AppendChild("Capsule")))
            assert_fn(stage.GetPrimAtPath(default_prim_path.AppendChild("Camera")))
            assert_fn(stage.GetPrimAtPath(default_prim_path.AppendChild("DistantLight")))
            assert_fn(stage.GetPrimAtPath(default_prim_path.AppendChild("DomeLight")))
            assert_fn(stage.GetPrimAtPath(default_prim_path.AppendChild("SphereLight")))

        omni.kit.commands.execute(
            "CreatePrims",
            prim_types=[
                "Sphere",
                "Cube",
                "Cone",
                "Cylinder",
                "Capsule",
                "Camera",
                "DistantLight",
                "DomeLight",
                "SphereLight",
            ],
        )
        check(self.assertTrue)

        # give hydra a frame before deleting to catch up so it doesn't spew coding error about not finding prim
        await omni.kit.app.get_app().next_update_async()
        omni.kit.commands.execute(
            "DeletePrims",
            paths=[
                default_prim_path.AppendChild("Sphere").pathString,
                default_prim_path.AppendChild("Cube").pathString,
                default_prim_path.AppendChild("Cone").pathString,
                default_prim_path.AppendChild("Cylinder").pathString,
                default_prim_path.AppendChild("Capsule").pathString,
                default_prim_path.AppendChild("Camera").pathString,
                default_prim_path.AppendChild("DistantLight").pathString,
                default_prim_path.AppendChild("DomeLight").pathString,
                default_prim_path.AppendChild("SphereLight").pathString,
            ],
        )

        check(self.assertFalse)

        omni.kit.undo.undo()
        check(self.assertTrue)

        # give hydra a frame before deleting to catch up so it doesn't spew coding error about not finding prim
        await omni.kit.app.get_app().next_update_async()
        omni.kit.undo.redo()
        check(self.assertFalse)

    async def test_transform_prim(self):
        stage = omni.usd.get_context().get_stage()
        default_prim_path = getStageDefaultPrimPath(stage)

        omni.kit.commands.execute("CreatePrim", prim_type="Cube")
        prim = stage.GetPrimAtPath(default_prim_path.AppendChild("Cube"))
        self.assertTrue(prim)

        xformable = UsdGeom.Xformable(prim)
        self.assertTrue(xformable.GetLocalTransformation() == Gf.Matrix4d(1.0))

        translate_mtx = Gf.Matrix4d()
        rotate_mtx = Gf.Matrix4d()
        scale_mtx = Gf.Matrix4d()

        translate_mtx.SetTranslate(Gf.Vec3d(1, 2, 3))
        rotation = Gf.Rotation(Gf.Vec3d(0, 1, 0), 60)
        rotate_mtx.SetRotate(rotation)
        scale_mtx = scale_mtx.SetScale(Gf.Vec3d(3, 2, 1))
        transform_matrix = scale_mtx * rotate_mtx * translate_mtx
        omni.kit.commands.execute(
            "TransformPrim", path=default_prim_path.AppendChild("Cube"), new_transform_matrix=transform_matrix
        )

        transform_matrix_1 = xformable.GetLocalTransformation()
        self.assertTrue(Gf.IsClose(transform_matrix, transform_matrix_1, 0.00001))

        translate_mtx.SetTranslate(Gf.Vec3d(3, 5, 2))
        rotation = Gf.Rotation(Gf.Vec3d(1, 0, 0), 60)
        rotate_mtx.SetRotate(rotation)
        scale_mtx = scale_mtx.SetScale(Gf.Vec3d(1, 3, 4))
        transform_matrix_2 = scale_mtx * rotate_mtx * translate_mtx
        omni.kit.commands.execute(
            "TransformPrim", path=default_prim_path.AppendChild("Cube"), new_transform_matrix=transform_matrix_2
        )

        transform_matrix_3 = xformable.GetLocalTransformation()
        self.assertTrue(Gf.IsClose(transform_matrix_2, transform_matrix_3, 0.00001))

        omni.kit.undo.undo()
        transform_matrix_4 = xformable.GetLocalTransformation()
        self.assertTrue(Gf.IsClose(transform_matrix_4, transform_matrix_1, 0.00001))

        omni.kit.undo.redo()
        transform_matrix_5 = xformable.GetLocalTransformation()
        self.assertTrue(Gf.IsClose(transform_matrix_3, transform_matrix_5, 0.00001))

        omni.kit.undo.undo()
        omni.kit.undo.undo()

        transform_matrix_6 = xformable.GetLocalTransformation()
        self.assertTrue(Gf.IsClose(transform_matrix_6, Gf.Matrix4d(1.0), 0.00001))

    async def test_transform_prim_srt(self):
        stage = omni.usd.get_context().get_stage()
        default_prim_path = getStageDefaultPrimPath(stage)

        omni.kit.commands.execute("CreatePrim", prim_type="Cube", create_default_xform=False)
        prim = stage.GetPrimAtPath(default_prim_path.AppendChild("Cube"))
        self.assertTrue(prim)

        xformable = UsdGeom.Xformable(prim)
        self.assertTrue(xformable.GetLocalTransformation() == Gf.Matrix4d(1.0))

        translation = Gf.Vec3d(1, 2, 3)
        rotation_euler = Gf.Vec3f(0, 60, 0)
        scale = Gf.Vec3f(3, 2, 1)
        omni.kit.commands.execute(
            "TransformPrimSRT",
            path=default_prim_path.AppendChild("Cube"),
            new_translation=translation,
            new_rotation_euler=rotation_euler,
            new_scale=scale,
        )

        scale_1, rotation_euler_1, _, translation_1 = omni.usd.get_local_transform_SRT(prim)
        self.assertTrue(Gf.IsClose(translation, translation_1, 0.00001))
        self.assertTrue(Gf.IsClose(rotation_euler, rotation_euler_1, 0.00001))
        self.assertTrue(Gf.IsClose(scale, scale_1, 0.00001))

        translation_2 = Gf.Vec3d(3, 5, 2)
        rotation_euler_2 = Gf.Vec3f(60, 0, 0)
        scale_2 = Gf.Vec3f(1, 3, 4)
        omni.kit.commands.execute(
            "TransformPrimSRT",
            path=default_prim_path.AppendChild("Cube"),
            new_translation=translation_2,
            new_rotation_euler=rotation_euler_2,
            new_scale=scale_2,
        )

        scale_3, rotation_euler_3, _, translation_3 = omni.usd.get_local_transform_SRT(prim)
        self.assertTrue(Gf.IsClose(translation_2, translation_3, 0.00001))
        self.assertTrue(Gf.IsClose(rotation_euler_2, rotation_euler_3, 0.00001))
        self.assertTrue(Gf.IsClose(scale_2, scale_3, 0.00001))

        omni.kit.undo.undo()
        scale_4, rotation_euler_4, _, translation_4 = omni.usd.get_local_transform_SRT(prim)
        self.assertTrue(Gf.IsClose(translation_1, translation_4, 0.00001))
        self.assertTrue(Gf.IsClose(rotation_euler_1, rotation_euler_4, 0.00001))
        self.assertTrue(Gf.IsClose(scale_1, scale_4, 0.00001))

        omni.kit.undo.redo()
        scale_5, rotation_euler_5, _, translation_5 = omni.usd.get_local_transform_SRT(prim)
        self.assertTrue(Gf.IsClose(translation_3, translation_5, 0.00001))
        self.assertTrue(Gf.IsClose(rotation_euler_3, rotation_euler_5, 0.00001))
        self.assertTrue(Gf.IsClose(scale_3, scale_5, 0.00001))

        omni.kit.undo.undo()
        omni.kit.undo.undo()

        transform_matrix_6 = xformable.GetLocalTransformation()
        self.assertTrue(Gf.IsClose(transform_matrix_6, Gf.Matrix4d(1.0), 0.00001))

        scale_6, rotation_euler_6, _, translation_6 = omni.usd.get_local_transform_SRT(prim)
        self.assertTrue(Gf.IsClose(Gf.Vec3d(0), translation_6, 0.00001))
        self.assertTrue(Gf.IsClose(Gf.Vec3f(0), rotation_euler_6, 0.00001))
        self.assertTrue(Gf.IsClose(Gf.Vec3f(1), scale_6, 0.00001))

    async def test_move_prim_without_destruction(self):
        stage = omni.usd.get_context().get_stage()
        root_layer = stage.GetRootLayer()
        session_layer = stage.GetSessionLayer()
        format = Sdf.FileFormat.FindByExtension(".usd")
        strong_layer = Sdf.Layer.New(format, "z:/fake-path/subfolder/test.usd")
        weak_layer = Sdf.Layer.CreateAnonymous()
        root_layer.subLayerPaths.append(weak_layer.identifier)
        session_layer.subLayerPaths.append(strong_layer.identifier)

        test_prim_path = "/root/test"
        test_prim_path_move_to = "/root/test2"
        layer_list = [session_layer, strong_layer, root_layer, weak_layer]
        def move_and_check(def_layer, current_layer, test_prim_path):
            has_prim_spec_before = not not current_layer.GetPrimAtPath(test_prim_path) 
            with Usd.EditContext(stage, current_layer):
                omni.kit.commands.execute("MovePrim", path_from=test_prim_path, path_to=test_prim_path_move_to, destructive=False)
                old_usd_prim = stage.GetPrimAtPath(test_prim_path)
                new_usd_prim = stage.GetPrimAtPath(test_prim_path_move_to)
                if def_layer == current_layer or (def_layer.anonymous and (not has_prim_spec_before or current_layer.anonymous)):
                    self.assertFalse(old_usd_prim)
                else:
                    old_prim_spec = current_layer.GetPrimAtPath(test_prim_path)
                    if def_layer.anonymous:
                        if not current_layer.anonymous and has_prim_spec_before:
                            self.assertTrue(old_prim_spec)
                            self.assertTrue(old_prim_spec.HasActive())
                            self.assertFalse(old_prim_spec.active)
                        else:
                            self.assertFalse(old_prim_spec)
                    else:
                        self.assertTrue(old_prim_spec)
                        self.assertTrue(old_prim_spec.HasActive())
                        self.assertFalse(old_prim_spec.active)
                self.assertTrue(new_usd_prim)

            omni.kit.undo.undo()
            old_usd_prim = stage.GetPrimAtPath(test_prim_path)
            new_usd_prim = stage.GetPrimAtPath(test_prim_path_move_to)
            self.assertTrue(old_usd_prim)
            self.assertTrue(old_usd_prim.IsActive())
            prim_spec = def_layer.GetPrimAtPath(test_prim_path)
            self.assertTrue(prim_spec)
            self.assertFalse(prim_spec.HasActive())
            prim_spec = current_layer.GetPrimAtPath(test_prim_path)
            if has_prim_spec_before:
                self.assertTrue(prim_spec)
                self.assertFalse(prim_spec.HasActive())
            else:
                self.assertFalse(prim_spec)
            self.assertFalse(new_usd_prim)

        layer_list = [session_layer, strong_layer, root_layer, weak_layer]
        for def_layer in layer_list:
            for current_layer in layer_list:
                with Usd.EditContext(stage, def_layer):
                    stage.DefinePrim(test_prim_path, "Xform")
                if current_layer != def_layer:
                    for has_delta_before in [False, True]:
                        if has_delta_before:
                            with Usd.EditContext(stage, current_layer):
                                stage.DefinePrim(test_prim_path)

                        move_and_check(def_layer, current_layer, test_prim_path)
                        with Usd.EditContext(stage, current_layer):
                            stage.RemovePrim(test_prim_path)
                            stage.RemovePrim(test_prim_path_move_to)
                else:
                    move_and_check(def_layer, current_layer, test_prim_path)
                    with Usd.EditContext(stage, current_layer):
                        stage.RemovePrim(test_prim_path)
                        stage.RemovePrim(test_prim_path_move_to)
            
            with Usd.EditContext(stage, def_layer):
                stage.RemovePrim(test_prim_path)
                stage.RemovePrim(test_prim_path_move_to)

    async def test_move_prim(self):
        async def test():
            stage = omni.usd.get_context().get_stage()
            default_prim_path = getStageDefaultPrimPath(stage)

            cube_path = default_prim_path.AppendChild("Cube")
            cube_new_path = default_prim_path.AppendChild("Cube_Renamed")
            cube_new_path2 = "/Cube"
            cube_translate = Gf.Vec3d(1, 0, 0)

            sphere_path = default_prim_path.AppendChild("Sphere")
            sphere_new_path = cube_new_path.AppendChild("Sphere_Moved")
            sphere_new_path2 = "/Sphere_02"
            sphere_translate = Gf.Vec3d(0, 1, 0)

            # /Stage/Cube
            omni.kit.commands.execute("CreatePrim", prim_type="Cube")
            cube = stage.GetPrimAtPath(cube_path)
            self.assertTrue(cube)
            cube_xform_api = UsdGeom.XformCommonAPI(cube)
            cube_xform_api.SetTranslate(translation=cube_translate)

            # /Stage/Cube
            # /Stage/Sphere
            omni.kit.commands.execute("CreatePrim", prim_type="Sphere")
            sphere = stage.GetPrimAtPath(sphere_path)
            self.assertTrue(sphere)
            sphere_xform_api = UsdGeom.XformCommonAPI(sphere)
            sphere_xform_api.SetTranslate(translation=sphere_translate)

            # Should raise a value error
            with self.assertRaises(ValueError):
                omni.kit.commands.execute(
                    "MovePrim", path_from=cube_path, path_to="123invalid", keep_world_transform=False
                )

            # /Stage/Cube_Renamed
            # /Stage/Sphere
            omni.kit.commands.execute(
                "MovePrim", path_from=cube_path, path_to=cube_new_path, keep_world_transform=False
            )
            self.assertFalse(stage.GetPrimAtPath(cube_path))
            cube = stage.GetPrimAtPath(cube_new_path)
            self.assertTrue(cube)

            # Cannot move gprim under a gprim
            # /Stage/Cube_Renamed
            # /Stage/Sphere
            omni.kit.commands.execute(
                "MovePrim", path_from=sphere_path, path_to=sphere_new_path, keep_world_transform=False
            )
            self.assertTrue(stage.GetPrimAtPath(sphere_path))
            sphere = stage.GetPrimAtPath(sphere_new_path)
            self.assertFalse(sphere)
            omni.kit.undo.undo()

            # Create xform and move sphere under a xform
            # /Stage/Cube_Renamed
            # /Stage/root/Sphere
            xform_path = default_prim_path.AppendChild("root")
            xform = UsdGeom.Xform.Define(stage, xform_path)
            self.assertTrue(xform)
            xform_api = UsdGeom.XformCommonAPI(xform)
            xform_api.SetTranslate(translation=cube_translate)

            sphere_new_path = xform_path.AppendChild("Sphere")
            omni.kit.commands.execute(
                "MovePrim", path_from=sphere_path, path_to=sphere_new_path, keep_world_transform=False
            )
            self.assertFalse(stage.GetPrimAtPath(sphere_path))
            sphere = stage.GetPrimAtPath(sphere_new_path)
            self.assertTrue(sphere)
            sphere_world_mtx = omni.usd.get_world_transform_matrix(sphere)
            self.assertTrue(sphere_world_mtx.GetRow3(3) == sphere_translate + cube_translate)

            # /Stage/Cube_Renamed
            # /Stage/Sphere
            omni.kit.undo.undo()

            # /Stage/Cube
            # /Stage/Sphere
            omni.kit.undo.undo()
            self.assertTrue(stage.GetPrimAtPath(cube_path))
            self.assertFalse(stage.GetPrimAtPath(cube_new_path))
            self.assertTrue(stage.GetPrimAtPath(sphere_path))
            self.assertFalse(stage.GetPrimAtPath(sphere_new_path))

            # /Stage/Cube_Renamed
            # /Stage/Sphere
            omni.kit.undo.redo()
            self.assertFalse(stage.GetPrimAtPath(cube_path))
            self.assertTrue(stage.GetPrimAtPath(cube_new_path))
            self.assertTrue(stage.GetPrimAtPath(sphere_path))
            self.assertFalse(stage.GetPrimAtPath(sphere_new_path))

            # Test keep_world_transform
            # /Stage/Cube_Renamed
            # /Stage/Cube_Renamed/Sphere
            omni.kit.commands.execute(
                "MovePrim", path_from=sphere_path, path_to=sphere_new_path, keep_world_transform=True
            )
            self.assertFalse(stage.GetPrimAtPath(sphere_path))
            sphere = stage.GetPrimAtPath(sphere_new_path)
            self.assertTrue(sphere)

            sphere_world_mtx = omni.usd.get_world_transform_matrix(sphere)
            self.assertTrue(sphere_world_mtx.GetRow3(3) == sphere_translate)

            omni.kit.undo.undo()

            # Test batched move
            batch_move = {}
            batch_move[cube_new_path] = cube_new_path2
            batch_move[sphere_path] = sphere_new_path2

            children_order = str(stage.GetPrimAtPath(default_prim_path).GetChildren())
            # /Stage
            # /Cube
            # /Sphere
            omni.kit.commands.execute("MovePrims", paths_to_move=batch_move)
            self.assertTrue(stage.GetPrimAtPath(cube_new_path2))
            self.assertFalse(stage.GetPrimAtPath(cube_new_path))
            self.assertFalse(stage.GetPrimAtPath(sphere_new_path))
            self.assertTrue(stage.GetPrimAtPath(sphere_new_path2))

            # /Stage/Cube_Renamed
            # /Stage/Sphere
            omni.kit.undo.undo()
            self.assertFalse(stage.GetPrimAtPath(cube_path))
            self.assertTrue(stage.GetPrimAtPath(cube_new_path))
            self.assertTrue(stage.GetPrimAtPath(sphere_path))
            self.assertFalse(stage.GetPrimAtPath(sphere_new_path))
            self.assertTrue(str(stage.GetPrimAtPath(default_prim_path).GetChildren()) == children_order)  # Check order

            # /Stage
            # /Cube
            # /Sphere
            omni.kit.undo.redo()
            self.assertTrue(stage.GetPrimAtPath(cube_new_path2))
            self.assertFalse(stage.GetPrimAtPath(cube_new_path))
            self.assertFalse(stage.GetPrimAtPath(sphere_new_path))
            self.assertTrue(stage.GetPrimAtPath(sphere_new_path2))

            # Tests for https://nvidia-omniverse.atlassian.net/browse/OM-21961
            # Create prim /reference and it references /cube
            reference_prim = stage.DefinePrim("/reference")
            reference_prim.GetReferences().AddInternalReference(cube_new_path2)

            omni.kit.commands.execute(
                "MovePrim", path_from=cube_new_path2, path_to=cube_new_path, keep_world_transform=False
            )
            self.assertFalse(stage.GetPrimAtPath(cube_new_path2))
            cube = stage.GetPrimAtPath(cube_new_path)
            self.assertTrue(cube)

            def get_reference_prims(prim):
                prim_paths = []
                for prim_spec in prim.GetPrimStack():
                    items = prim_spec.referenceList.prependedItems
                    for item in items:
                        if item.primPath:
                            prim_paths.append(item.primPath)

                return prim_paths

            prim_paths = get_reference_prims(reference_prim)
            # After move, the reference path should be changed also.
            self.assertTrue(len(prim_paths) == 1 and prim_paths[0] == cube_new_path)

            # /Stage
            # /Cube
            # /Sphere
            omni.kit.undo.undo()
            self.assertTrue(stage.GetPrimAtPath(cube_new_path2))
            self.assertFalse(stage.GetPrimAtPath(cube_new_path))
            self.assertFalse(stage.GetPrimAtPath(sphere_new_path))
            self.assertTrue(stage.GetPrimAtPath(sphere_new_path2))

            prim_paths = get_reference_prims(reference_prim)
            # After undo, the reference path should be changed back.
            self.assertTrue(len(prim_paths) == 1 and prim_paths[0] == cube_new_path2)

            # Create prim /reference2 and it references "../test/test.usd"</sphere>
            reference_prim2 = stage.DefinePrim("/reference2")
            # Add a non-existent external reference
            reference_prim2.GetReferences().AddReference("../test/test.usd", sphere_new_path2)

            omni.kit.commands.execute(
                "MovePrim", path_from=sphere_new_path2, path_to=sphere_new_path, keep_world_transform=False
            )
            self.assertFalse(stage.GetPrimAtPath(sphere_new_path2))
            sphere = stage.GetPrimAtPath(sphere_new_path)
            self.assertTrue(sphere)

            def get_reference_prims(prim):
                prim_paths = []
                for prim_spec in prim.GetPrimStack():
                    items = prim_spec.referenceList.prependedItems
                    for item in items:
                        if item.primPath:
                            prim_paths.append(item.primPath)

                return prim_paths

            prim_paths = get_reference_prims(reference_prim2)
            # After move, the reference path should not be changed since it points to an external USD
            self.assertTrue(len(prim_paths) == 1 and prim_paths[0] == sphere_new_path2)

            omni.kit.undo.undo()
            prim_paths = get_reference_prims(reference_prim2)
            # After undo, the reference path should not be changed also.
            self.assertTrue(len(prim_paths) == 1 and prim_paths[0] == sphere_new_path2)

        carb.log_info("Test Move/Rename")
        await test()

    async def test_move_non_xformable_prim(self):
        stage = omni.usd.get_context().get_stage()
        default_prim_path = getStageDefaultPrimPath(stage)
        bbox_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), includedPurposes=[UsdGeom.Tokens.default_])

        cube_path = default_prim_path.AppendChild("Cube")
        xform_path = default_prim_path.AppendChild("Xform")
        scope_path = default_prim_path.AppendChild("Scope")

        cube_translate = Gf.Vec3d(1, 0, 0)
        xform_translate = Gf.Vec3d(1, 1, 1)

        cube = UsdGeom.Cube.Define(stage, cube_path)
        xform = UsdGeom.Xform.Define(stage, xform_path)
        scope = UsdGeom.Scope.Define(stage, scope_path)

        cube_xform_api = UsdGeom.XformCommonAPI(cube.GetPrim())
        cube_xform_api.SetTranslate(translation=cube_translate)

        xform_xform_api = UsdGeom.XformCommonAPI(xform.GetPrim())
        xform_xform_api.SetTranslate(translation=xform_translate)

        cube_original_bound = bbox_cache.ComputeWorldBound(cube.GetPrim())

        def check_cube_bound(cube_path):
            nonlocal cube_original_bound
            nonlocal bbox_cache
            cube = stage.GetPrimAtPath(cube_path)
            self.assertTrue(cube)

            bbox_cache.Clear()
            cube_bound = bbox_cache.ComputeWorldBound(cube.GetPrim())
            self.assertTrue(cube_bound == cube_original_bound)

        # Move /Scope tp /Xform/Scope
        scope_under_xform_path = xform_path.AppendChild("Scope")
        omni.kit.commands.execute(
            "MovePrim", path_from=scope_path, path_to=scope_under_xform_path, keep_world_transform=True
        )

        # Move /Cube to /Xform/Scope/Cube
        cube_under_scope_path = scope_under_xform_path.AppendChild("Cube")
        omni.kit.commands.execute(
            "MovePrim", path_from=cube_path, path_to=cube_under_scope_path, keep_world_transform=True
        )

        check_cube_bound(cube_under_scope_path)

        # Move /Xform/Scope to /Scope (didn't move Cube directly but its transform should stay the same)
        omni.kit.commands.execute(
            "MovePrim", path_from=scope_under_xform_path, path_to=scope_path, keep_world_transform=True
        )

        cube_under_scope_path = scope_path.AppendChild("Cube")
        check_cube_bound(cube_under_scope_path)

        omni.kit.undo.undo()

        cube_under_scope_path = scope_under_xform_path.AppendChild("Cube")
        check_cube_bound(cube_under_scope_path)

        omni.kit.undo.undo()
        check_cube_bound(cube_path)

        omni.kit.undo.redo()
        check_cube_bound(cube_under_scope_path)

        omni.kit.undo.redo()
        cube_under_scope_path = scope_path.AppendChild("Cube")
        check_cube_bound(cube_under_scope_path)

    async def test_toggle_visibility_selected(self):
        carb.log_info("Test ToggleVisibilitySelectedPrimsCommand")
        timeline = omni.timeline.get_timeline_interface()
        usd_context = omni.usd.get_context()
        selection = usd_context.get_selection()
        stage = usd_context.get_stage()
        default_prim_path = getStageDefaultPrimPath(stage)
        root_layer = stage.GetRootLayer()

        with Usd.EditContext(stage, root_layer):
            omni.kit.commands.execute("CreatePrim", prim_type="Cube")
            omni.kit.commands.execute("CreatePrim", prim_type="Sphere")
            omni.kit.commands.execute("CreatePrim", prim_type="Cone")

        def test_visibility(paths, visible):
            paths = selection.get_selected_prim_paths()
            for path in paths:
                prim = stage.GetPrimAtPath(path)
                imageable = UsdGeom.Imageable(prim)
                visibilityAttr = imageable.GetVisibilityAttr()
                timeSampled = visibilityAttr.GetNumTimeSamples() > 1
                currTime = timeline.get_current_time()
                if timeSampled:
                    self._currTimeCode = currTime * stage.GetTimeCodesPerSecond()
                else:
                    self._currTimeCode = Usd.TimeCode.Default()
                visibility = imageable.ComputeVisibility(self._currTimeCode)
                if visible:
                    self.assertFalse(visibility == UsdGeom.Tokens.invisible)
                else:
                    self.assertTrue(visibility == UsdGeom.Tokens.invisible)

        # if nothing selected, visiblity should not change.
        selection.clear_selected_prim_paths()
        paths = selection.get_selected_prim_paths()
        test_visibility(paths, True)
        omni.kit.commands.execute("ToggleVisibilitySelectedPrims", selected_paths=paths)
        paths = selection.get_selected_prim_paths()
        test_visibility(paths, True)
        self.assertTrue(len(paths) == 0)

        # select all the paths and there should be 3 selected.
        selection.set_selected_prim_paths(
            [
                default_prim_path.AppendChild("Cube").pathString,
                default_prim_path.AppendChild("Sphere").pathString,
                default_prim_path.AppendChild("Cone").pathString,
            ],
            False,
        )
        paths = selection.get_selected_prim_paths()
        self.assertTrue(len(paths) == 3)
        # toggle and test they are all hidden
        omni.kit.commands.execute("ToggleVisibilitySelectedPrims", selected_paths=paths)
        paths = selection.get_selected_prim_paths()
        test_visibility(paths, False)
        # toggle again and test they are all visible again
        omni.kit.commands.execute("ToggleVisibilitySelectedPrims", selected_paths=paths)
        paths = selection.get_selected_prim_paths()
        test_visibility(paths, True)
        omni.kit.undo.undo()
        test_visibility(paths, False)
        omni.kit.undo.redo()
        test_visibility(paths, True)

        # select one and it should be visible
        selection.set_selected_prim_paths([default_prim_path.AppendChild("Cube").pathString], False)
        paths = selection.get_selected_prim_paths()
        test_visibility(paths, True)

        # toggle and test they are all hidden
        omni.kit.commands.execute("ToggleVisibilitySelectedPrims", selected_paths=paths)
        paths = selection.get_selected_prim_paths()
        test_visibility(paths, False)
        # toggle again and test they are all visible again
        omni.kit.commands.execute("ToggleVisibilitySelectedPrims", selected_paths=paths)
        paths = selection.get_selected_prim_paths()
        test_visibility(paths, True)

        omni.kit.undo.undo()
        test_visibility(paths, False)
        omni.kit.undo.redo()
        test_visibility(paths, True)

    async def test_set_material_strength(self):
        carb.log_info("Test SetMaterialStrengthCommand")
        stage = omni.usd.get_context().get_stage()

        mat = UsdShade.Material.Define(stage, "/mat")
        prim = stage.OverridePrim("/prim")

        omni.kit.commands.execute(
            "BindMaterial",
            prim_path=prim.GetPath(),
            material_path=mat.GetPrim().GetPath(),
            strength=UsdShade.Tokens.strongerThanDescendants,
        )
        binding_api = UsdShade.MaterialBindingAPI(prim)
        mat, rel = binding_api.ComputeBoundMaterial()

        self.assertTrue(mat)
        self.assertTrue(rel)

        strength = UsdShade.MaterialBindingAPI.GetMaterialBindingStrength(rel)
        self.assertTrue(strength == UsdShade.Tokens.strongerThanDescendants)

        omni.kit.commands.execute("SetMaterialStrength", rel=rel, strength=UsdShade.Tokens.weakerThanDescendants)

        strength = UsdShade.MaterialBindingAPI.GetMaterialBindingStrength(rel)
        self.assertTrue(strength == UsdShade.Tokens.weakerThanDescendants)

        omni.kit.undo.undo()

        strength = UsdShade.MaterialBindingAPI.GetMaterialBindingStrength(rel)
        self.assertTrue(strength == UsdShade.Tokens.strongerThanDescendants)

        omni.kit.undo.redo()

        strength = UsdShade.MaterialBindingAPI.GetMaterialBindingStrength(rel)
        self.assertTrue(strength == UsdShade.Tokens.weakerThanDescendants)

        omni.kit.commands.execute("SetMaterialStrength", rel=rel, strength=UsdShade.Tokens.strongerThanDescendants)

        strength = UsdShade.MaterialBindingAPI.GetMaterialBindingStrength(rel)
        self.assertTrue(strength == UsdShade.Tokens.strongerThanDescendants)

        omni.kit.undo.undo()

        strength = UsdShade.MaterialBindingAPI.GetMaterialBindingStrength(rel)
        self.assertTrue(strength == UsdShade.Tokens.weakerThanDescendants)

        omni.kit.undo.redo()

        strength = UsdShade.MaterialBindingAPI.GetMaterialBindingStrength(rel)
        self.assertTrue(strength == UsdShade.Tokens.strongerThanDescendants)

    async def test_collection_material_assignment(self):
        stage = omni.usd.get_context().get_stage()

        mat = UsdShade.Material.Define(stage, "/mat")
        prim = stage.DefinePrim("/prim")
        test_collection = Usd.CollectionAPI.ApplyCollection(prim, "test_collection")
        coll_path = test_collection.GetCollectionPath()

        omni.kit.commands.execute(
            "BindMaterialCommand",
            prim_path=coll_path,
            material_path=mat.GetPrim().GetPath(),
            strength=UsdShade.Tokens.strongerThanDescendants,
        )
        material = None
        relationship = None
        binding_api = UsdShade.MaterialBindingAPI(prim)
        all_bindings = binding_api.GetCollectionBindings()
        for b in all_bindings:
            curr_collection = b.GetCollection()
            if curr_collection.GetName() == "test_collection":
                relationship = b.GetBindingRel()
                material = b.GetMaterial()

        self.assertTrue(mat.GetPath() == material.GetPath())
        self.assertTrue(relationship)

    async def test_multiple_collections_single_prim(self):
        """
        check assigning different materials to different collections on a single prim
        """
        stage = omni.usd.get_context().get_stage()

        mat1 = UsdShade.Material.Define(stage, "/mat1")
        mat2 = UsdShade.Material.Define(stage, "/mat2")
        materials = [mat1.GetPath(), mat2.GetPath()]
        prim = stage.DefinePrim("/prim")
        test_collection1 = Usd.CollectionAPI.ApplyCollection(prim, "test_collection1")
        test_collection2 = Usd.CollectionAPI.ApplyCollection(prim, "test_collection2")
        collections = [test_collection1.GetCollectionPath(), test_collection2.GetCollectionPath()]
        coll_path1 = test_collection1.GetCollectionPath()
        coll_path2 = test_collection2.GetCollectionPath()
        omni.kit.commands.execute(
            "BindMaterialCommand",
            prim_path=coll_path1,
            material_path=mat1.GetPrim().GetPath(),
            strength=UsdShade.Tokens.strongerThanDescendants,
        )
        omni.kit.commands.execute(
            "BindMaterialCommand",
            prim_path=coll_path2,
            material_path=mat2.GetPrim().GetPath(),
            strength=UsdShade.Tokens.strongerThanDescendants,
        )

        binding_api = UsdShade.MaterialBindingAPI(prim)
        all_bindings = binding_api.GetCollectionBindings()
        self.assertTrue(len(all_bindings) == 2)
        for b in all_bindings:
            curr_collection = b.GetCollection()
            self.assertTrue(curr_collection.GetCollectionPath() in collections)
            material = b.GetMaterial()
            self.assertTrue(material.GetPath() in materials)

    async def test_set_metadata(self):
        carb.log_info("Test ChangeMetadataInPrimsCommand")
        stage = omni.usd.get_context().get_stage()
        default_prim_path = getStageDefaultPrimPath(stage)

        omni.kit.commands.execute("CreatePrims", prim_types=["Sphere", "Cone", "Cube"])
        prim_paths = [
            default_prim_path.AppendChild("Cube"),
            default_prim_path.AppendChild("Sphere"),
            default_prim_path.AppendChild("Cone"),
        ]

        sphere_path = default_prim_path.AppendChild("Sphere")
        cone_path = default_prim_path.AppendChild("Cone")
        cube_path = default_prim_path.AppendChild("Cube")

        sphere_prim = stage.GetPrimAtPath(sphere_path)
        cone_prim = stage.GetPrimAtPath(cone_path)
        cube_prim = stage.GetPrimAtPath(cube_path)

        sphere_prim_model_api = Usd.ModelAPI(sphere_prim)
        cone_prim_model_api = Usd.ModelAPI(cone_prim)
        cube_prim_model_api = Usd.ModelAPI(cube_prim)

        sphere_kind = Kind.Tokens.component
        cone_kind = Kind.Tokens.subcomponent
        cube_kind = Kind.Tokens.component

        all_kind = Kind.Tokens.assembly

        omni.kit.commands.execute("ChangeMetadataInPrims", prim_paths=[sphere_path], key="kind", value=sphere_kind)
        omni.kit.commands.execute("ChangeMetadataInPrims", prim_paths=[cone_path], key="kind", value=cone_kind)
        omni.kit.commands.execute("ChangeMetadataInPrims", prim_paths=[cube_path], key="kind", value=cube_kind)

        self.assertTrue(sphere_prim_model_api.GetKind() == sphere_kind)
        self.assertTrue(cone_prim_model_api.GetKind() == cone_kind)
        self.assertTrue(cube_prim_model_api.GetKind() == cube_kind)

        omni.kit.commands.execute(
            "ChangeMetadataInPrims", prim_paths=[sphere_path, cone_path, cube_path], key="kind", value=all_kind
        )

        self.assertTrue(sphere_prim_model_api.GetKind() == all_kind)
        self.assertTrue(cone_prim_model_api.GetKind() == all_kind)
        self.assertTrue(cube_prim_model_api.GetKind() == all_kind)

        omni.kit.undo.undo()

        self.assertTrue(sphere_prim_model_api.GetKind() == sphere_kind)
        self.assertTrue(cone_prim_model_api.GetKind() == cone_kind)
        self.assertTrue(cube_prim_model_api.GetKind() == cube_kind)

        omni.kit.undo.redo()

        self.assertTrue(sphere_prim_model_api.GetKind() == all_kind)
        self.assertTrue(cone_prim_model_api.GetKind() == all_kind)
        self.assertTrue(cube_prim_model_api.GetKind() == all_kind)

    async def test_change_property(self):
        stage = omni.usd.get_context().get_stage()
        default_prim_path = getStageDefaultPrimPath(stage)

        omni.kit.commands.execute("CreatePrim", prim_type="Cube")

        cube_path = default_prim_path.AppendChild("Cube")
        cube = stage.GetPrimAtPath(cube_path)
        self.assertTrue(cube is not None)

        size_attr = cube.GetAttribute("size")
        self.assertTrue(size_attr.Get() == 2.0)

        # test changing exisitng attr
        size_attr_path = cube_path.AppendProperty("size")
        args = {"prop_path": size_attr_path, "value": 10.0, "prev": None, "timecode": Usd.TimeCode.Default()}
        omni.kit.commands.execute("ChangeProperty", **args)

        self.assertTrue(size_attr.Get() == 10.0)

        omni.kit.undo.undo()
        self.assertTrue(size_attr.Get() == 2.0)

        omni.kit.undo.redo()
        self.assertTrue(size_attr.Get() == 10.0)

        # test changing non-exisitng attr
        my_attr_path = cube_path.AppendProperty("not_exist")
        args = {
            "prop_path": my_attr_path,
            "value": True,
            "prev": None,
            "timecode": Usd.TimeCode.Default(),
            "type_to_create_if_not_exist": Sdf.ValueTypeNames.Bool,
        }
        omni.kit.commands.execute("ChangeProperty", **args)

        my_attr = cube.GetAttribute("not_exist")
        self.assertTrue(my_attr is not None)
        self.assertTrue(my_attr.Get() == True)

        omni.kit.undo.undo()
        my_attr = cube.GetAttribute("not_exist")
        self.assertFalse(my_attr.IsValid())

        omni.kit.undo.redo()
        my_attr = cube.GetAttribute("not_exist")
        self.assertTrue(my_attr.IsValid())
        self.assertTrue(my_attr.Get() == True)

        # test changing non-existing attribute that does not get created
        fake_attr_path = cube_path.AppendProperty("another_fake")
        omni.kit.commands.execute("ChangeProperty", prop_path=fake_attr_path, value=0, prev=1)
        self.assertFalse(cube.GetAttribute("another_fake").IsValid())

        omni.kit.undo.undo()
        self.assertFalse(cube.GetAttribute("another_fake").IsValid())

        omni.kit.undo.redo()
        self.assertFalse(cube.GetAttribute("another_fake").IsValid())

    async def test_relationship_target(self):
        stage = omni.usd.get_context().get_stage()
        xform = UsdGeom.Xform.Define(stage, "/Xform")
        xform_rel = UsdGeom.Xform.Define(stage, "/XformRel")
        imageable = UsdGeom.Imageable(xform.GetPrim())
        rel = imageable.GetProxyPrimRel()

        omni.kit.commands.execute("AddRelationshipTarget", relationship=rel, target=xform_rel.GetPrim().GetPath())
        targets = rel.GetTargets()
        self.assertTrue(targets == [xform_rel.GetPrim().GetPath()])

        omni.kit.undo.undo()
        targets = rel.GetTargets()
        self.assertTrue(targets == [])

        omni.kit.undo.redo()
        targets = rel.GetTargets()
        self.assertTrue(targets == [xform_rel.GetPrim().GetPath()])

        omni.kit.commands.execute("RemoveRelationshipTarget", relationship=rel, target=xform_rel.GetPrim().GetPath())
        targets = rel.GetTargets()
        self.assertTrue(targets == [])

        omni.kit.undo.undo()
        targets = rel.GetTargets()
        self.assertTrue(targets == [xform_rel.GetPrim().GetPath()])

        omni.kit.undo.redo()
        targets = rel.GetTargets()
        self.assertTrue(targets == [])

    async def test_group_prims(self):
        async def test():
            stage = omni.usd.get_context().get_stage()
            default_prim_path = getStageDefaultPrimPath(stage)

            cube_path = default_prim_path.AppendChild("Cube")
            cube_translate = Gf.Vec3d(100, 0, 0)

            sphere_path = default_prim_path.AppendChild("Sphere")
            sphere_translate = Gf.Vec3d(0, 100, 0)

            cylinder_xform_path = default_prim_path.AppendChild("CylinderXform")
            cylinder_xform_translate = Gf.Vec3d(0, 0, 100)

            cylinder_path = cylinder_xform_path.AppendChild("Cylinder")
            cylinder_translate = Gf.Vec3d(0, 0, 100)
            
            scope_path = default_prim_path.AppendChild("Scope")

            # /Stage/Cube
            omni.kit.commands.execute("CreatePrim", prim_type="Cube")
            cube = stage.GetPrimAtPath(cube_path)
            self.assertTrue(cube)
            cube_xform_api = UsdGeom.XformCommonAPI(cube)
            cube_xform_api.SetTranslate(translation=cube_translate)

            # /Stage/Cube
            # /Stage/Sphere
            omni.kit.commands.execute("CreatePrim", prim_type="Sphere")
            sphere = stage.GetPrimAtPath(sphere_path)
            self.assertTrue(sphere)
            sphere_xform_api = UsdGeom.XformCommonAPI(sphere)
            sphere_xform_api.SetTranslate(translation=sphere_translate)

            # /Stage/Cube
            # /Stage/Sphere
            # /Stage/CylinderXform/Cylinder
            prim = UsdGeom.Xform.Define(stage, cylinder_xform_path)
            cylinder_xform = prim.GetPrim()

            prim = UsdGeom.Cylinder.Define(stage, cylinder_path)
            cylinder = prim.GetPrim()

            cylinder_xform_api = UsdGeom.XformCommonAPI(cylinder_xform)
            cylinder_xform_api.SetTranslate(translation=cylinder_xform_translate)

            cylinder_api = UsdGeom.XformCommonAPI(cylinder)
            cylinder_api.SetTranslate(translation=cylinder_translate)

        
            # /Stage/Cube
            # /Stage/Sphere
            # /Stage/CylinderXform/Cylinder
            # /Stage/Sceope
            # Non xformable prim
            omni.kit.commands.execute("CreatePrim", prim_type="Scope")

            # /Stage/Group/Cube
            # /Stage/Group/Sphere
            # /Stage/Group/Cylinder
            # /Stage/Group/Scope
            omni.kit.commands.execute("GroupPrims", prim_paths=[cube_path, sphere_path, cylinder_path, scope_path])
            group_prim_path = default_prim_path.AppendElementString("Group")
            group_prim = stage.GetPrimAtPath(group_prim_path)
            xform_vectors = UsdGeom.XformCommonAPI(group_prim).GetXformVectors(Usd.TimeCode.Default())
            _, _, _, pivot, _ = xform_vectors
            # Pivot is the center of the bound box
            self.assertEqual(pivot, Gf.Vec3f(50, 50, 100))
            self.assertFalse(stage.GetPrimAtPath(cube_path))
            self.assertFalse(stage.GetPrimAtPath(sphere_path))
            self.assertFalse(stage.GetPrimAtPath(cylinder_path))
            self.assertFalse(stage.GetPrimAtPath(scope_path))
            self.assertTrue(stage.GetPrimAtPath(cylinder_xform_path))
            cube_new_path = default_prim_path.AppendPath("Group/Cube")
            sphere_new_path = default_prim_path.AppendPath("Group/Sphere")
            cylinder_new_path = default_prim_path.AppendPath("Group/Cylinder")
            scope_new_path = default_prim_path.AppendPath("Group/Scope")
            cube = stage.GetPrimAtPath(cube_new_path)
            self.assertTrue(cube)
            sphere = stage.GetPrimAtPath(sphere_new_path)
            self.assertTrue(sphere)
            cylinder = stage.GetPrimAtPath(cylinder_new_path)
            self.assertTrue(cylinder)
            scope = stage.GetPrimAtPath(scope_new_path)
            self.assertTrue(scope)

            sphere_world_mtx = omni.usd.get_world_transform_matrix(sphere)
            self.assertTrue(sphere_world_mtx.GetRow3(3) == sphere_translate)

            cube_world_mtx = omni.usd.get_world_transform_matrix(cube)
            self.assertTrue(cube_world_mtx.GetRow3(3) == cube_translate)

            cylinder_world_mtx = omni.usd.get_world_transform_matrix(cylinder)
            self.assertTrue(cylinder_world_mtx.GetRow3(3) == cylinder_xform_translate + cylinder_translate)

            omni.kit.undo.undo()

            self.assertTrue(stage.GetPrimAtPath(cube_path))
            self.assertFalse(stage.GetPrimAtPath(cube_new_path))
            self.assertTrue(stage.GetPrimAtPath(sphere_path))
            self.assertFalse(stage.GetPrimAtPath(sphere_new_path))
            self.assertTrue(stage.GetPrimAtPath(cylinder_path))
            self.assertFalse(stage.GetPrimAtPath(cylinder_new_path))
            self.assertTrue(stage.GetPrimAtPath(scope_path))
            self.assertFalse(stage.GetPrimAtPath(scope_new_path))

            omni.kit.undo.redo()
            self.assertFalse(stage.GetPrimAtPath(cube_path))
            self.assertTrue(stage.GetPrimAtPath(cube_new_path))
            self.assertFalse(stage.GetPrimAtPath(sphere_path))
            self.assertTrue(stage.GetPrimAtPath(sphere_new_path))
            self.assertFalse(stage.GetPrimAtPath(cylinder_path))
            self.assertTrue(stage.GetPrimAtPath(cylinder_new_path))
            self.assertFalse(stage.GetPrimAtPath(scope_path))
            self.assertTrue(stage.GetPrimAtPath(scope_new_path))

        await test()

    async def test_basic_instance(self):
        stage = omni.usd.get_context().get_stage()
        # create a cube
        omni.kit.commands.execute("CreatePrim", prim_type="Cube")
        await omni.kit.app.get_app().next_update_async()
        # create a parent xform
        omni.kit.commands.execute("GroupPrims", prim_paths=["/Cube"])
        await omni.kit.app.get_app().next_update_async()
        # create instances to mesh will fail
        omni.kit.commands.execute("CreateInstances", paths_from=["/Cube"])
        await omni.kit.app.get_app().next_update_async()
        instance = stage.GetPrimAtPath("/Cube_01")
        self.assertFalse(instance)
        omni.kit.commands.execute("CreateInstance", path_from="/Cube")
        await omni.kit.app.get_app().next_update_async()
        instance = stage.GetPrimAtPath("/Cube_01")
        self.assertFalse(instance)
        # create instance from the group
        omni.kit.commands.execute("CreateInstances", paths_from=["/Group"])
        await omni.kit.app.get_app().next_update_async()
        # check the instance is created successfully
        instance = stage.GetPrimAtPath("/Group_01")
        await omni.kit.app.get_app().next_update_async()
        self.assertTrue(instance.IsValid())
        # check the instance ops names are the same as the original prim
        # not adding extra suffix on top
        original = stage.GetPrimAtPath("/Group")
        xformable_original = UsdGeom.Xformable(original)
        xformable_instance = UsdGeom.Xformable(instance)
        ops_original = [op.GetName() for op in xformable_original.GetOrderedXformOps()]
        ops_instance = [op.GetName() for op in xformable_instance.GetOrderedXformOps()]
        self.assertEqual(ops_original, ops_instance)

        # Creates a material that's outside of /Group namespace, and bind to /Group
        stage.DefinePrim("/Material", "Material")
        rel = original.CreateRelationship("material:binding", False)
        rel.SetTargets(["/Material"])
        omni.kit.commands.execute("CreateInstances", paths_from=["/Group"])
        
        root_layer = stage.GetRootLayer()
        prop_spec = root_layer.GetPropertyAtPath("/Group_02.material:binding")
        self.assertTrue(prop_spec)
        self.assertTrue(prop_spec.GetInfo("targetPaths").HasItem(Sdf.Path('/Material')))

    async def test_nested_layer_removal_with_stage_update(self):
        stage = Usd.Stage.Open(FILE_PATH_ROOT)
        await omni.kit.app.get_app().next_update_async()
        # check the material prim is defined in the stage
        material_prim = stage.GetPrimAtPath("/World/Looks/OmniPBR")
        self.assertTrue(material_prim.IsDefined())
        material_prim = stage.GetPrimAtPath("/World/Looks/OmniGlass")
        self.assertTrue(material_prim.IsDefined())

        # remove the Looks folder from the `material_sub`subLayer
        sub_layer = Sdf.FindOrOpenRelativeToLayer(stage.GetRootLayer(), FILE_PATH_SUB)
        with Usd.EditContext(stage, sub_layer):
            stage.RemovePrim("/World/Looks")
        await omni.kit.app.get_app().next_update_async()
        # check the material prim is not there anymore
        material_prim = stage.GetPrimAtPath("/World/Looks/OmniPBR")
        self.assertFalse(material_prim.IsValid())
        material_prim = stage.GetPrimAtPath("/World/Looks/OmniGlass")
        self.assertFalse(material_prim.IsValid())
        # check the cube from the root layer is still there
        scope_prim = stage.GetPrimAtPath("/World/Cube")
        self.assertTrue(scope_prim.IsValid())

    async def test_create_attribute(self):
        desired_value = 1.23456

        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()
        default_prim_path = getStageDefaultPrimPath(stage)
        prim = stage.DefinePrim(default_prim_path.AppendChild("Cube"), "Cube")
        omni.kit.commands.execute(
            "CreateUsdAttribute",
            prim=prim,
            attr_name="attr1",
            attr_type=Sdf.ValueTypeNames.Double,
            attr_value=desired_value,
        )

        attr = prim.GetAttribute("attr1")
        self.assertTrue(attr.IsValid())
        value = attr.Get()
        self.assertEqual(value, desired_value)

        omni.kit.undo.undo()

        self.assertFalse(prim.GetAttribute("attr1").IsValid())

        omni.kit.undo.redo()

        attr = prim.GetAttribute("attr1")
        self.assertIsNotNone(attr)
        value = attr.Get()
        self.assertEqual(value, desired_value)

    async def test_create_attribute_path(self):
        desired_value = 1.23456

        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()
        default_prim_path = getStageDefaultPrimPath(stage)
        prim = stage.DefinePrim(default_prim_path.AppendChild("Cube"), "Cube")

        omni.kit.commands.execute(
            "CreateUsdAttributeOnPath",
            attr_path=prim.GetPath().AppendProperty("attr1"),
            attr_type=Sdf.ValueTypeNames.Double,
            attr_value=desired_value,
        )

        attr = prim.GetAttribute("attr1")
        self.assertTrue(attr.IsValid())
        value = attr.Get()
        self.assertEqual(value, desired_value)

        omni.kit.undo.undo()

        self.assertFalse(prim.GetAttribute("attr1").IsValid())

        omni.kit.undo.redo()

        attr = prim.GetAttribute("attr1")
        self.assertIsNotNone(attr)
        value = attr.Get()
        self.assertEqual(value, desired_value)

    async def test_remove_property(self):
        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()

        root_layer = stage.GetRootLayer()

        layer_2 = Sdf.Layer.CreateAnonymous()
        layer_1 = Sdf.Layer.CreateAnonymous()

        root_layer.subLayerPaths = [layer_2.identifier, layer_1.identifier]

        with Usd.EditContext(stage, layer_1):
            default_prim_path = getStageDefaultPrimPath(stage)
            prim = stage.DefinePrim(default_prim_path.AppendChild("Cube"), "Cube")
            attr = prim.CreateAttribute("attr1", Sdf.ValueTypeNames.Double)
            attr.Set(1.234)

        with Usd.EditContext(stage, layer_2):
            attr.Set(2.345)

        with Usd.EditContext(stage, root_layer):
            attr.Set(3.456)

        self.assertEqual(attr.Get(), 3.456)

        attr_path = attr.GetPath()

        omni.kit.commands.execute("RemovePropertyCommand", prop_path=attr_path)

        self.assertIsNone(layer_2.GetAttributeAtPath(attr_path))
        self.assertIsNone(layer_1.GetAttributeAtPath(attr_path))
        self.assertIsNone(root_layer.GetAttributeAtPath(attr_path))

        attr = stage.GetAttributeAtPath(attr_path)
        self.assertFalse(attr.IsValid())

        omni.kit.undo.undo()

        spec2 = layer_2.GetAttributeAtPath(attr_path)
        spec1 = layer_1.GetAttributeAtPath(attr_path)
        spec_root = root_layer.GetAttributeAtPath(attr_path)

        self.assertIsNotNone(spec2)
        self.assertIsNotNone(spec1)
        self.assertIsNotNone(spec_root)

        self.assertEqual(spec2.default, 2.345)
        self.assertEqual(spec1.default, 1.234)
        self.assertEqual(spec_root.default, 3.456)

        attr = stage.GetAttributeAtPath(attr_path)
        self.assertTrue(attr.IsValid())
        self.assertEqual(attr.Get(), 3.456)

        omni.kit.undo.redo()

        self.assertIsNone(layer_2.GetAttributeAtPath(attr_path))
        self.assertIsNone(layer_1.GetAttributeAtPath(attr_path))
        self.assertIsNone(root_layer.GetAttributeAtPath(attr_path))

        attr = stage.GetAttributeAtPath(attr_path)
        self.assertFalse(attr.IsValid())
    
    async def test_create_references(self):
        usd_context = omni.usd.get_context()
        await usd_context.new_stage_async()
        format = Sdf.FileFormat.FindByExtension(".usd")
        sublayer = Sdf.Layer.New(format, "z:/fake-path/subfolder/test.usd")
        reference_layer = Sdf.Layer.New(format, "z:/fake-path/subfolder/nestpath/test2.usd")
        another_layer = Sdf.Layer.New(format, "p:/fake-path/subfolder/nestpath/test2.usd")
        stage = omni.usd.get_context().get_stage()
        root_layer = stage.GetRootLayer()
        root_layer.subLayerPaths.append(sublayer.identifier)

        def create_reference_and_check(stage, target_layer, asset_path):
            target_url = omni.client.break_url(target_layer.identifier)
            asset_url = omni.client.break_url(asset_path)
            relative_url = clientutils.make_relative_url_if_possible(target_layer.identifier, asset_path)
            with Usd.EditContext(stage, target_layer):
                test_path = omni.usd.get_stage_next_free_path(stage, "/test", True)
                omni.kit.commands.execute("CreateReference", usd_context=usd_context, path_to=test_path, asset_path=asset_path)
                test_prim = stage.GetPrimAtPath(test_path)
                reference_list = omni.usd.get_composed_references_from_prim(test_prim)
                for (reference, layer) in reference_list:
                    self.assertTrue(clientutils.equal_urls(reference.assetPath, relative_url))
                    self.assertEqual(layer, target_layer)
        
        create_reference_and_check(stage, sublayer, reference_layer.identifier)
        create_reference_and_check(stage, root_layer, reference_layer.identifier)
        create_reference_and_check(stage, sublayer, another_layer.identifier)
        # Don't use omnvierse to avoid trigger authentication
        create_reference_and_check(stage, sublayer, "fake-scheme://fake-url/invalid/path/test.usd")
        create_reference_and_check(stage, root_layer, "fake-scheme://fake-url/invalid/path/test.usd")


    async def test_change_property_creation(self):
        usd_context = omni.usd.get_context()
        await usd_context.new_stage_async()
        stage = usd_context.get_stage()
        xformable = UsdGeom.Xform.Define(stage, "/World/TestXform")

        omni.kit.commands.execute(
            "ChangePropertyCommand",
            prop_path=xformable.GetPath().AppendProperty("CustomAttribute3"),
            value=Gf.Vec3d(10, 10, 10),
            prev=None,
            type_to_create_if_not_exist=Sdf.ValueTypeNames.Vector3d
        )

        attr = xformable.GetPrim().GetAttribute("CustomAttribute3")
        self.assertTrue(attr.IsValid())
        # 103 behavior defaults to custom as False, and Sdf.VariabilityVarying
        self.assertFalse(attr.IsCustom())
        self.assertEqual(attr.GetVariability(), Sdf.VariabilityVarying)
        self.assertEqual(attr.Get(), Gf.Vec3d(10, 10, 10))


        omni.kit.commands.execute(
            "ChangePropertyCommand",
            prop_path=xformable.GetPath().AppendProperty("CustomAttribute2"),
            value=Gf.Vec2f(20, 20),
            prev=None,
            type_to_create_if_not_exist=Sdf.ValueTypeNames.Float2,
            is_custom=True,
            variability=Sdf.VariabilityUniform
        )

        attr = xformable.GetPrim().GetAttribute("CustomAttribute2")
        self.assertTrue(attr.IsValid())
        # 103 behavior defaults to custom as False, and Sdf.VariabilityVarying
        self.assertTrue(attr.IsCustom())
        self.assertEqual(attr.GetVariability(), Sdf.VariabilityUniform)
        self.assertEqual(attr.Get(), Gf.Vec2f(20, 20))
    
    async def test_om_70901(self):
        usd_context = omni.usd.get_context()
        await usd_context.new_stage_async()

        stage = usd_context.get_stage()
        looks_prim = stage.DefinePrim("/World/Looks", "Scope")
        stage.DefinePrim("/World/Looks/material", "Material")
        looks_prim.SetActive(False)

        omni.kit.commands.execute(
            "CreateMdlMaterialPrim",
            mtl_url="OmniPBR.mdl",
            mtl_name="OmniPBR",
            mtl_path="/World/Looks/material"
        )

        # Since looks is inactive, it will activate it and deactivate all of its children.
        prim = stage.GetPrimAtPath("/World/Looks/material")
        self.assertFalse(prim.IsActive())
        self.assertTrue(stage.GetPrimAtPath("/World/Looks/material_01"))

        
