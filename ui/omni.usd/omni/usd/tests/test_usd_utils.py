## Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
##
## NVIDIA CORPORATION and its licensors retain all intellectual property
## and proprietary rights in and to this software, related documentation
## and any modifications thereto.  Any use, reproduction, disclosure or
## distribution of this software and related documentation without an express
## license agreement from NVIDIA CORPORATION is strictly prohibited.
##

from pathlib import Path
import omni.kit.test
import omni.usd

from pxr import Sdf, Usd, UsdGeom, Gf


class TestUsdUtils(omni.kit.test.AsyncTestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._test_payload = str(Path(__file__).parent.joinpath("data").joinpath("test_payload.usda"))

    async def setUp(self):
        usd_context = omni.usd.get_context()
        await usd_context.new_stage_async()
    
    async def tearDown(self):
        usd_context = omni.usd.get_context()
        await usd_context.close_stage_async()

    def test_is_usd_writable_filetype(self):
        for path, is_writable in [
            ("omniverse://test-server/test.usd", True),
            ("omniverse://test-server/test.usda", True),
            ("omniverse://test-server/test.usdc", True),
            ("omniverse://test-server/test.usdz", False),
            ("omniverse://test-server/test.usdg", False),
            ("omniverse://test-server/test.abc", False),
            ("omniverse://test-server/test.sdf", False),
            ("omniverse://test-server/test.drc", False),
            ("omniverse://test-server/test.txt", False),
            ("omniverse://test-server/test.usd?a=1", True),
            ("omniverse://test-server/test.usd?a=1#fragment", True),
            ("omniverse://test-server/test.usd.a=1#fragment", False),
            ("omniverse://test-server/test.txt?otherFile.usd?a=1", False),
            ("omniverse://test-server/invalid_path", False),
        ]:
            self.assertEqual(omni.usd.is_usd_writable_filetype(path),
                             is_writable)
            self.assertEqual(bool(omni.usd.writable_usd_re().match(path)),
                             is_writable)

    def test_is_usd_readable_filetype(self):
        for path, is_writable in [
            ("omniverse://test-server/test.usd", True),
            ("omniverse://test-server/test.usda", True),
            ("omniverse://test-server/test.usdc", True),
            ("omniverse://test-server/test.usdz", True),
            ("omniverse://test-server/test.usdg", False),
            ("omniverse://test-server/test.abc", True),
            ("omniverse://test-server/test.sdf", False),
            ("omniverse://test-server/test.drc", True),
            ("omniverse://test-server/test.txt", False),
            ("omniverse://test-server/test.abc?a=1", True),
            ("omniverse://test-server/test.abc?a=1#fragment", True),
            ("omniverse://test-server/test.abc.a=1#fragment", False),
            ("omniverse://test-server/test.txt?otherFile.abc?a=1", False),
            ("omniverse://test-server/invalid_path", False),
        ]:
            self.assertEqual(omni.usd.is_usd_readable_filetype(path),
                             is_writable)
            self.assertEqual(bool(omni.usd.readable_usd_re().match(path)),
                             is_writable)

    async def test_get_stage_next_free_path(self):
        stage = omni.usd.get_context().get_stage()
        prim = stage.DefinePrim("/World")
        stage.DefinePrim("/World_01")
        stage.SetDefaultPrim(prim)

        # Verifies it raises an exception on invalid path
        with self.assertRaises(ValueError):
            omni.usd.get_stage_next_free_path(stage, "1234567", False)

        # Verifies path without leading slash + not parent under default prim
        path = omni.usd.get_stage_next_free_path(stage, "World", False)
        self.assertEqual(path, "/World_02")

        # Verifies path with leading slash + not parent under default prim
        path = omni.usd.get_stage_next_free_path(stage, "/World", False)
        self.assertEqual(path, "/World_02")

        # Verifies path without leading slash + parent under default prim
        path = omni.usd.get_stage_next_free_path(stage, "World", True)
        self.assertEqual(path, "/World/World")

        # Verifies path with leading slash + parent under default prim
        path = omni.usd.get_stage_next_free_path(stage, "/World", True)
        self.assertEqual(path, "/World/World")

        # Verifies path without leading slash + parent under default prim
        path = omni.usd.get_stage_next_free_path(stage, "Path", True)
        self.assertEqual(path, "/World/Path")

        # Verifies path with leading slash + parent under default prim
        path = omni.usd.get_stage_next_free_path(stage, "/Path", True)
        self.assertEqual(path, "/World/Path")

        # Verifies path with leading slash matching default prim is not modified
        path = omni.usd.get_stage_next_free_path(stage, "World/Path", True)
        self.assertEqual(path, "/World/Path")
        
        # Verifies path without leading slash matching default prim is correct but not modified
        path = omni.usd.get_stage_next_free_path(stage, "/World/Path", True)
        self.assertEqual(path, "/World/Path")
    
    def _get_test_stage_with_references_and_payloads(self):
        layer_content = '''\
            #usda 1.0
        '''

        layer0_content = """\
            #usda 1.0

            over "root" (
                delete payload = [
                    @assets/Cube.usda@,
                    @assets/Capsule.usda@
                ]
                delete references = [
                    @assets/Cube.usda@,
                    @assets/Capsule.usda@
                ]
            )
            {
            }
        """

        layer1_content = """\
            #usda 1.0

            over "root" (
                append payload = [
                    @assets/Cylinder.usda@,
                    @assets/Capsule.usda@
                ]
                append references = [
                    @assets/Cylinder.usda@,
                    @assets/Capsule.usda@
                ]
            )
            {
            }
        """

        layer2_content = """\
            #usda 1.0

            over "root" (
                payload = [
                    @assets/Cube.usda@,
                    @assets/Sphere.usda@
                ]
                references = [
                    @assets/Cube.usda@,
                    @assets/Sphere.usda@
                ]
            )
            {
            }
        """

        layer3_content = """\
            #usda 1.0

            over "root" (
                prepend payload = [
                    @assets/Cone.usda@,
                ]
                prepend references = [
                    @assets/Cone.usda@,
                ]
            )
            {
            }
        """

        layer4_content = """\
            #usda 1.0

            def Xform "root" (
            )
            {
            }
        """

        format = Sdf.FileFormat.FindByExtension(".usd")
        layer = Sdf.Layer.New(format, "omniverse://test-ov-fake-server/fake/path/a.usd")
        layer0 = Sdf.Layer.New(format, "omniverse://test-ov-fake-server/fake/path/sublayers/sublayer0.usd")
        layer1 = Sdf.Layer.New(format, "omniverse://test-ov-fake-server/fake/path/sublayers/sublayer1.usd")
        layer2 = Sdf.Layer.New(format, "omniverse://test-ov-fake-server/fake/path/sublayers/sublayer2.usd")
        layer3 = Sdf.Layer.New(format, "omniverse://test-ov-fake-server/fake/path/sublayers/sublayer3.usd")
        layer4 = Sdf.Layer.New(format, "omniverse://test-ov-fake-server/fake/path/sublayers/sublayer4.usd")
        layer.ImportFromString(layer_content)
        layer0.ImportFromString(layer0_content)
        layer1.ImportFromString(layer1_content)
        layer2.ImportFromString(layer2_content)
        layer3.ImportFromString(layer3_content)
        layer4.ImportFromString(layer4_content)
        layer.subLayerPaths.append(layer0.identifier)
        layer.subLayerPaths.append(layer1.identifier)
        layer.subLayerPaths.append(layer2.identifier)
        layer.subLayerPaths.append(layer3.identifier)
        layer.subLayerPaths.append(layer4.identifier)

        stage = Usd.Stage.Open(layer)

        ref_and_layer_map = {
            "assets/Cone.usda": layer3,
            "assets/Cube.usda": layer2,
            "assets/Sphere.usda": layer2,
            "assets/Cylinder.usda": layer1,
            "assets/Capsule.usda": layer1
        }

        layers = {
            "delete": layer0,
            "append": layer1,
            "explicit": layer2,
            "prepend": layer3
        }

        return stage, ref_and_layer_map, layers

    async def test_get_composed_references(self):
        stage, ref_and_layer_map, layers = self._get_test_stage_with_references_and_payloads()

        def verify(ref_and_layers, ref_paths):
            # same size
            self.assertTrue(len(ref_and_layers) == len(ref_paths))

            # same ref and layer and order:
            for i in range(len(ref_paths)):
                ref_path = ref_paths[i]
                info = ref_and_layers[i]
                self.assertTrue(info[0].assetPath == ref_path)
                golden_layer = ref_and_layer_map.get(info[0].assetPath, None)
                self.assertTrue(golden_layer is not None)
                self.assertTrue(info[1] is not None)
                self.assertTrue(info[1] == golden_layer)

        test_prim = stage.GetPrimAtPath("/root")
        references = omni.usd.get_composed_references_from_prim(test_prim)
        verify(references, ["assets/Sphere.usda", "assets/Cylinder.usda"])

        async def mute_and_test(layer_to_mute, ref_paths):
            stage.MuteLayer(layer_to_mute.identifier)
            await omni.kit.app.get_app().next_update_async()
            await omni.kit.app.get_app().next_update_async()
            references = omni.usd.get_composed_references_from_prim(test_prim)
            verify(references, ref_paths)

        # Mute delete layer, more references should be composed
        await mute_and_test(layers["delete"], ["assets/Cube.usda", "assets/Sphere.usda", "assets/Cylinder.usda", "assets/Capsule.usda"])

        # Mute append layer, reference should be removed
        await mute_and_test(layers["append"], ["assets/Cube.usda", "assets/Sphere.usda"])

        # Mute explicit layer, reference should be removed from explicit layer and prepend layer show up
        await mute_and_test(layers["explicit"], ["assets/Cone.usda"])

        # Mute prepend layer, reference should be empty
        await mute_and_test(layers["prepend"], [])

    async def test_get_composed_payloads(self):
        stage, payload_and_layer_map, layers = self._get_test_stage_with_references_and_payloads()
        
        def verify(ref_and_layers, ref_paths):
            # same size
            self.assertTrue(len(ref_and_layers) == len(ref_paths))

            # same ref and layer and order:
            for i in range(len(ref_paths)):
                ref_path = ref_paths[i]
                info = ref_and_layers[i]
                self.assertTrue(info[0].assetPath == ref_path)
                golden_layer = payload_and_layer_map.get(info[0].assetPath, None)
                self.assertTrue(golden_layer is not None)
                self.assertTrue(info[1] is not None)
                self.assertTrue(info[1] == golden_layer)

        test_prim = stage.GetPrimAtPath("/root")
        payloads = omni.usd.get_composed_payloads_from_prim(test_prim)
        verify(payloads, ["assets/Sphere.usda", "assets/Cylinder.usda"])

        async def mute_and_test(layer_to_mute, ref_paths):
            stage.MuteLayer(layer_to_mute.identifier)
            await omni.kit.app.get_app().next_update_async()
            await omni.kit.app.get_app().next_update_async()
            payloads = omni.usd.get_composed_payloads_from_prim(test_prim)
            verify(payloads, ref_paths)

        # Mute delete layer, more payloads should be composed
        await mute_and_test(layers["delete"], ["assets/Cube.usda", "assets/Sphere.usda", "assets/Cylinder.usda", "assets/Capsule.usda"])

        # Mute append layer, payload should be removed
        await mute_and_test(layers["append"], ["assets/Cube.usda", "assets/Sphere.usda"])

        # Mute explicit layer, payload should be removed from explicit layer and prepend layer show up
        await mute_and_test(layers["explicit"], ["assets/Cone.usda"])

        # Mute prepend layer, payload should be empty
        await mute_and_test(layers["prepend"], [])
    
    async def test_get_introducing_layer(self):
        root_layer = Sdf.Layer.CreateAnonymous()
        reference_layer = Sdf.Layer.CreateAnonymous()
        payload_layer = Sdf.Layer.CreateAnonymous()
        stage = Usd.Stage.Open(reference_layer)
        cube_prim = UsdGeom.Cube.Define(stage, '/root/cube')
        stage.SetDefaultPrim(cube_prim.GetPrim().GetParent())
        stage = Usd.Stage.Open(payload_layer)
        sphere_prim = UsdGeom.Cube.Define(stage, '/root/sphere')
        stage.SetDefaultPrim(sphere_prim.GetPrim().GetParent())
        stage = Usd.Stage.Open(root_layer)
        root_prim = UsdGeom.Xform.Define(stage, "/root")
        root_prim.GetPrim().GetReferences().AddReference(reference_layer.identifier)
        root_prim.GetPrim().GetPayloads().AddPayload(payload_layer.identifier)
        self.assertEqual(omni.usd.get_introducing_layer(root_prim.GetPrim())[0], root_layer)

        cube_prim = stage.GetPrimAtPath("/root/cube")
        self.assertTrue(cube_prim)
        sphere_prim = stage.GetPrimAtPath("/root/cube")
        self.assertTrue(sphere_prim)
        UsdGeom.XformCommonAPI(cube_prim).SetTranslate(Gf.Vec3d(0.0, 0.0, 0.0))
        UsdGeom.XformCommonAPI(sphere_prim).SetTranslate(Gf.Vec3d(0.0, 0.0, 0.0))

        self.assertEqual(omni.usd.get_introducing_layer(cube_prim.GetPrim())[0], root_layer)
        self.assertEqual(omni.usd.get_introducing_layer(sphere_prim.GetPrim())[0], root_layer)
        
    async def test_load_payload(self):
        # LOAD_ALL
        (result, err) = await omni.usd.get_context().close_stage_async()
        self.assertTrue(result)

        (result, err) = await omni.usd.get_context().open_stage_async(
            self._test_payload, omni.usd.UsdContextInitialLoadSet.LOAD_ALL
        )
        self.assertTrue(result)

        stage = omni.usd.get_context().get_stage()
        world = stage.GetPrimAtPath("/World")
        # World should have children because we loaded all
        self.assertNotEqual(len(world.GetChildren()), 0)

        # LOAD_NONE
        (result, err) = await omni.usd.get_context().close_stage_async()
        self.assertTrue(result)

        (result, err) = await omni.usd.get_context().open_stage_async(
            self._test_payload, omni.usd.UsdContextInitialLoadSet.LOAD_NONE
        )
        self.assertTrue(result)

        stage = omni.usd.get_context().get_stage()
        world = stage.GetPrimAtPath("/World")
        # World should not have children because we loaded all
        self.assertEqual(len(world.GetChildren()), 0)
    
    async def test_duplicate(self):
        format = Sdf.FileFormat.FindByExtension(".usd")
        reference_layer = Sdf.Layer.New(format, "omniverse://invalid-fake-server/test_dir/references/reference1.usd")
        stage1 = Usd.Stage.Open(reference_layer)
        xform = stage1.DefinePrim("/xform")
        stage1.SetDefaultPrim(xform)
        reference_path = xform.GetPath().AppendElementString("reference")
        reference1_prim = stage1.DefinePrim(reference_path)

        reference_layer2 = Sdf.Layer.New(format, "omniverse://invalid-fake-server/test_dir/references/deep/reference2.usd")
        stage2 = Usd.Stage.Open(reference_layer2)
        cube = UsdGeom.Cube.Define(stage2, "/cube")
        # Creates another cube under the parent and defines its relationship so that 
        # it can be used to check if the relationship is remapped after duplicate.
        cube2 = UsdGeom.Cube.Define(stage2, "/cube/test_cube")
        rel = cube2.GetPrim().CreateRelationship("test_relationship");
        rel.SetTargets(["/cube"])
        stage2.SetDefaultPrim(cube.GetPrim())
        reference1_prim.GetReferences().AddReference("./deep/reference2.usd")

        sublayer = Sdf.Layer.New(format, "omniverse://invalid-fake-server/test_dir/sublayers/sublayer.usd")
        stage3 = Usd.Stage.Open(sublayer)
        xform = UsdGeom.Xform.Define(stage3, "/World/xform")
        stage3.SetDefaultPrim(xform.GetPrim().GetParent())
        xform.GetPrim().GetReferences().AddReference("../references/reference1.usd")

        root_layer = Sdf.Layer.New(format, "omniverse://invalid-fake-server/test_dir/stage/root.usd")
        root_layer.subLayerPaths.append(sublayer.identifier)
        stage = Usd.Stage.Open(root_layer)

        def verify_references(prim, expected_reference_paths):
            references = omni.usd.get_composed_references_from_prim(prim)
            reference_paths = set()
            for ref_and_layer in references:
                reference, layer = ref_and_layer
                reference_paths.add(layer.ComputeAbsolutePath(reference.assetPath))
            
            self.assertEqual(reference_paths, set(expected_reference_paths))

        # Duplicates prim to the edit target
        for layer in [sublayer, root_layer]:
            with Usd.EditContext(stage, layer):
                duplicate_prim_path = omni.usd.get_stage_next_free_path(stage, "/World/xform", False)
                omni.usd.duplicate_prim(stage, "/World/xform", duplicate_prim_path, False)

                prim_spec = layer.GetPrimAtPath(duplicate_prim_path)
                self.assertTrue(prim_spec)

                prim = stage.GetPrimAtPath(duplicate_prim_path)
                self.assertTrue(prim)
                verify_references(prim, ["omniverse://invalid-fake-server/test_dir/references/reference1.usd"])
                
                prim = stage.GetPrimAtPath(Sdf.Path(duplicate_prim_path).AppendElementString("reference"))
                self.assertTrue(prim)
                verify_references(prim, ["omniverse://invalid-fake-server/test_dir/references/deep/reference2.usd"])

                # Duplicate prim from external reference layer
                duplicate_prim_path = omni.usd.get_stage_next_free_path(stage, "/World/xform/reference", False)
                omni.usd.duplicate_prim(stage, "/World/xform/reference", duplicate_prim_path, False)

                prim_spec = layer.GetPrimAtPath(duplicate_prim_path)
                self.assertTrue(prim_spec)

                # Check relationship to see if it's remapped also.
                test_cube_path = Sdf.Path(duplicate_prim_path).AppendElementString("test_cube")
                prim = stage.GetPrimAtPath(test_cube_path)
                self.assertTrue(prim)
                rel = prim.GetRelationship("test_relationship")
                targets = rel.GetTargets()
                self.assertEqual(len(targets), 1)
                self.assertTrue(str(targets[0]).startswith("/World/xform/reference"))

                prim = stage.GetPrimAtPath(duplicate_prim_path)
                self.assertTrue(prim)
                verify_references(prim, ["omniverse://invalid-fake-server/test_dir/references/deep/reference2.usd"])
        
        # Duplicate all layers
        with Usd.EditContext(stage, root_layer):
            prim = stage.GetPrimAtPath("/World/xform")
            prim.CreateAttribute("test_attribute", Sdf.ValueTypeNames.Bool)
            
            prim = stage.GetPrimAtPath("/World/xform/reference")
            prim.CreateAttribute("test_attribute", Sdf.ValueTypeNames.Bool)
            
        duplicate_prim_path = omni.usd.get_stage_next_free_path(stage, "/World/xform", False)
        omni.usd.duplicate_prim(stage, "/World/xform", duplicate_prim_path, True)
        prim_spec = sublayer.GetPrimAtPath(duplicate_prim_path)
        self.assertTrue(prim_spec)
        prim_spec = root_layer.GetPrimAtPath(duplicate_prim_path)
        self.assertTrue(prim_spec)

        prim = stage.GetPrimAtPath(duplicate_prim_path)
        self.assertTrue(prim)
        verify_references(prim, ["omniverse://invalid-fake-server/test_dir/references/reference1.usd"])
        
        prim = stage.GetPrimAtPath(Sdf.Path(duplicate_prim_path).AppendElementString("reference"))
        self.assertTrue(prim)
        verify_references(prim, ["omniverse://invalid-fake-server/test_dir/references/deep/reference2.usd"])
            
        # It has only one reference
        references = omni.usd.get_composed_references_from_prim(prim)
        self.assertEqual(len(references), 1)
        self.assertEqual(references[0][1], reference_layer)

        # Duplicate prim from external reference layer
        duplicate_prim_path = omni.usd.get_stage_next_free_path(stage, "/World/xform/reference", False)
        omni.usd.duplicate_prim(stage, "/World/xform/reference", duplicate_prim_path, True)

        prim_spec = sublayer.GetPrimAtPath(duplicate_prim_path)
        self.assertTrue(prim_spec)
        prim_spec = root_layer.GetPrimAtPath(duplicate_prim_path)
        self.assertTrue(prim_spec)

        prim = stage.GetPrimAtPath(duplicate_prim_path)
        self.assertTrue(prim)
        verify_references(prim, ["omniverse://invalid-fake-server/test_dir/references/deep/reference2.usd"])
        
        references = omni.usd.get_composed_references_from_prim(prim)
        self.assertEqual(len(references), 1)
        self.assertEqual(references[0][1], sublayer)
                
        # Bug test for OM-56561
        layer1_content = """\
#usda 1.0
(
    defaultPrim = "Xform"
)

def Xform "Xform"
{
    double3 xformOp:rotateXYZ = (0, 0, 0)
    double3 xformOp:scale = (1, 1, 1)
    double3 xformOp:translate = (0, 0, 0)
    uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ", "xformOp:scale"]

    def Cube "Cube"
    {
        float3[] extent = [(-50, -50, -50), (50, 50, 50)]
        double size = 100
        double3 xformOp:rotateXYZ = (0, 0, 0)
        double3 xformOp:scale = (1, 1, 1)
        double3 xformOp:translate = (0, 0, 0)
        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ", "xformOp:scale"]
    }
}
        """

        layer2_content = """\
#usda 1.0
(
    defaultPrim = "World"
)

def Xform "World"
{
    def "test_cube" (
        instanceable = false
        prepend references = @./1.usd@
    )
    {
        double3 xformOp:rotateXYZ = (0, -0, 0)
        double3 xformOp:scale = (1, 1, 1)
        double3 xformOp:translate = (-233.219, 17.7878, -7.136)
        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ", "xformOp:scale"]
    }
}
        """

        expected_string = """\
#usda 1.0

def Xform "test" (
    prepend references = @omniverse://invalid-fake-server/test_dir/2.usd@
)
{
    def "test_cube2" (
        instanceable = false
        prepend references = @./1.usd@
    )
    {
        double3 xformOp:rotateXYZ = (0, -0, 0)
        double3 xformOp:scale = (1, 1, 1)
        double3 xformOp:translate = (-233.219, 17.7878, -7.136)
        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ", "xformOp:scale"]
    }
}
"""
        reference_layer = Sdf.Layer.New(format, "omniverse://invalid-fake-server/test_dir/1.usd")
        reference_layer.ImportFromString(layer1_content)
        
        parent_reference_layer = Sdf.Layer.New(format, "omniverse://invalid-fake-server/test_dir/2.usd")
        parent_reference_layer.ImportFromString(layer2_content)

        root_layer = Sdf.Layer.New(format, "omniverse://invalid-fake-server/test_dir/3.usd")
        stage = Usd.Stage.Open(root_layer)
        prim = stage.DefinePrim("/test", "Xform")
        prim.GetReferences().AddReference(parent_reference_layer.identifier)
        omni.usd.duplicate_prim(stage, "/test/test_cube", "/test/test_cube2", False)
        string = root_layer.ExportToString()
        self.assertEqual(string.strip(), expected_string.strip())
    
    async def test_get_usd_context_from_stage(self):
        usd_context = omni.usd.get_context()
        await usd_context.new_stage_async()
        stage = usd_context.get_stage()
        self.assertTrue(omni.usd.get_context_from_stage(stage), usd_context)

        stage = Usd.Stage.CreateInMemory()
        await usd_context.attach_stage_async(stage)
        self.assertTrue(omni.usd.get_context_from_stage(stage), usd_context)





