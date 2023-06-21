# Copyright (c) 2020, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#

from pathlib import Path
import os.path
import tempfile
import omni.usd

from pxr import Usd, UsdGeom, Gf, Sdf


class TestAsyncAPI(omni.kit.test.AsyncTestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._test_scene = str(Path(__file__).parent.joinpath("data").joinpath("test_scene.usda"))

    async def test_usd_async_api(self):
        usd_context = omni.usd.get_context()
        test_prim_path = "/test_xform"
        original_prim_list = []

        # Test new_stage_async, load_set = LOAD_ALL
        (result, err) = await usd_context.new_stage_async()
        self.assertTrue(result)
        stage = usd_context.get_stage()
        self.assertIsNotNone(stage)

        # Try to save the new stage and make sure Sdf.Path.absolutePath is not unloaded.
        with tempfile.TemporaryDirectory() as tmpdirname:
            tmp_file_path = os.path.join(tmpdirname, "tmp3.usda")

            await omni.usd.get_context().save_as_stage_async(tmp_file_path)
            stage = omni.usd.get_context().get_stage()
            for path, rule in stage.GetLoadRules().GetRules():
                if path == Sdf.Path.absoluteRootPath:
                    self.assertEqual(rule, Usd.StageLoadRules.AllRule)
                    break

            # New stage to release tmp file
            await usd_context.new_stage_async()
        
        # With load_set = LOAD_NONE
        (result, err) = await usd_context.new_stage_async(omni.usd.UsdContextInitialLoadSet.LOAD_NONE)
        self.assertTrue(result)
        stage = usd_context.get_stage()
        self.assertIsNotNone(stage)
        self.assertEqual(stage.GetLoadRules(), Usd.StageLoadRules.LoadNone())

        payload_prim = stage.DefinePrim("/root/payload", "Xform")
        payload_prim.GetPayloads().AddPayload(self._test_scene)
        self.assertTrue(Sdf.Path("/root/payload") not in set(stage.GetLoadSet()))
        stage.Load("/root/payload")
        self.assertTrue(Sdf.Path("/root/payload") in set(stage.GetLoadSet()))

        # Try to save the new stage and make sure Sdf.Path.absolutePath is still unloaded.
        with tempfile.TemporaryDirectory() as tmpdirname:
            tmp_file_path = os.path.join(tmpdirname, "tmp2.usda")

            await omni.usd.get_context().save_as_stage_async(tmp_file_path)
            stage = omni.usd.get_context().get_stage()
            self.assertEqual(set(stage.GetLoadSet()), set([Sdf.Path("/root/payload")]))
        
            for path, rule in stage.GetLoadRules().GetRules():
                if path == Sdf.Path.absoluteRootPath:
                    self.assertEqual(rule, Usd.StageLoadRules.NoneRule)
                    break

            # New stage to release tmp file
            await usd_context.new_stage_async()

        # Test close_stage_async
        (result, err) = await usd_context.close_stage_async()
        self.assertTrue(result)
        stage = usd_context.get_stage()
        self.assertIsNone(stage)

        # Test open_stage_async
        (result, err) = await usd_context.open_stage_async(self._test_scene)
        self.assertTrue(result)
        stage = usd_context.get_stage()
        self.assertIsNotNone(stage)
        original_prim_list = [prim.GetPath() for prim in stage.TraverseAll()]

        xform_prim = UsdGeom.Xform.Define(stage, test_prim_path)
        self.assertTrue(xform_prim.GetPrim().IsValid())

        # Test reopen_stage_async
        (result, err) = await usd_context.reopen_stage_async()
        self.assertTrue(result)
        stage = usd_context.get_stage()
        self.assertIsNotNone(stage)
        xform_prim = stage.GetPrimAtPath(test_prim_path)
        self.assertFalse(xform_prim.GetPrim().IsValid())  # We didn't save, prim should be invalid
        prim_list = [prim.GetPath() for prim in stage.TraverseAll()]
        self.assertEqual(original_prim_list, prim_list)

        # Test save_as_stage_async
        with tempfile.TemporaryDirectory() as tmpdirname:
            tmp_file_path = os.path.join(tmpdirname, "tmp.usda")
            (result, err, saved_layers) = await usd_context.save_as_stage_async(tmp_file_path)
            self.assertTrue(result)
            stage = usd_context.get_stage()
            self.assertIsNotNone(stage)
            prim_list = [prim.GetPath() for prim in stage.TraverseAll()]
            self.assertEqual(original_prim_list, prim_list)

            # make a new prim
            xform_prim = UsdGeom.Xform.Define(stage, test_prim_path)
            self.assertTrue(xform_prim.GetPrim().IsValid())

            # Test save_stage_async
            (result, err, saved_layers) = await usd_context.save_stage_async()
            self.assertTrue(result)

            # reopen the newly saved file
            (result, err) = await usd_context.reopen_stage_async()
            self.assertTrue(result)
            stage = usd_context.get_stage()
            self.assertIsNotNone(stage)
            xform_prim = stage.GetPrimAtPath(test_prim_path)
            self.assertTrue(xform_prim.GetPrim().IsValid())  # We saved, prim should be valid

            # Test load_mdl_parameters_for_prim_async
            # TODO skip this test for now.
            # Random hang on Linux when shutting down omni.kit.window.viewport
             
            # prim = stage.GetPrimAtPath("/World/Looks/OmniPBR/Shader")
            # await usd_context.load_mdl_parameters_for_prim_async(prim)
            # attr = prim.GetAttribute("inputs:diffuse_color_constant")
            # self.assertIsNotNone(attr)
            # value = attr.Get()
            # self.assertTrue(Gf.IsClose(value, Gf.Vec3f(0.2, 0.2, 0.2), 0.000001))

            # Test export_as_stage_async
            tmp_file_path = os.path.join(tmpdirname, "tmp_export.usda")
            prim_list_before_export = [prim.GetPath() for prim in stage.TraverseAll()]

            (result, err) = await usd_context.export_as_stage_async(tmp_file_path)
            self.assertTrue(result)

            # open exported file
            (result, err) = await usd_context.open_stage_async(tmp_file_path)
            self.assertTrue(result)
            stage = usd_context.get_stage()
            self.assertIsNotNone(stage)

            prim_list = [prim.GetPath() for prim in stage.TraverseAll()]
            self.assertEqual(prim_list_before_export, prim_list)

    async def test_hydra_context(self):
        context_name = 'testcontext'
        hydra_engine_name = 'rtx'

        def stage_event_cb(event):
            pass

        new_usd_context = omni.usd.create_context(context_name)
        self.assertIsNotNone(new_usd_context)

        stage_event_subscription = new_usd_context.get_stage_event_stream().create_subscription_to_pop(
            stage_event_cb, name="StageUpdateEvent"
        )
        self.assertIsNotNone(stage_event_subscription)

        await new_usd_context.open_stage_async(self._test_scene)

        omni.usd.add_hydra_engine(hydra_engine_name, new_usd_context)

        omni.usd.release_all_hydra_engines(new_usd_context)

        omni.usd.destroy_context(context_name)
    
    async def test_save_as_with_layer_offsets(self):
        await omni.usd.get_context().new_stage_async()

        stage = omni.usd.get_context().get_stage()
        with tempfile.TemporaryDirectory() as tmpdirname:
            sublayer_path = os.path.join(tmpdirname, "sublayer.usda")
            layer = Sdf.Layer.CreateNew(sublayer_path)
            root_layer = stage.GetRootLayer() 
            root_layer.subLayerPaths.append(layer.identifier)
            root_layer.subLayerOffsets[0] = Sdf.LayerOffset(2.0, 3.0)
            sublayer_offset = root_layer.subLayerOffsets[0]
            self.assertTrue(float(sublayer_offset.offset) == 2.0 and float(sublayer_offset.scale) == 3.0)

            for ext in [".usdc", ".usda", ".usd"]:
                new_stage_path = os.path.join(tmpdirname, "new_stage" + ext)
                await omni.usd.get_context().save_as_stage_async(new_stage_path)
            
                stage = omni.usd.get_context().get_stage()
                root_layer = stage.GetRootLayer() 
                self.assertTrue(os.path.normpath(root_layer.identifier), os.path.normpath(new_stage_path))
                # Make sure offsets and scales are not changed
                sublayer_offset = root_layer.subLayerOffsets[0]
                self.assertTrue(float(sublayer_offset.offset) == 2.0 and float(sublayer_offset.scale) == 3.0)
            
            # Releases all to not hold handles to tmp folder.
            root_layer = None
            stage = None
            layer = None
            await omni.usd.get_context().new_stage_async()
    
    async def test_save_as_with_payloads_disabled(self):
        await omni.usd.get_context().new_stage_async()
        stage = omni.usd.get_context().get_stage()
        with tempfile.TemporaryDirectory() as tmpdirname:
            payload1 = os.path.join(tmpdirname, "payload1.usda")
            payload2 = os.path.join(tmpdirname, "payload2.usda")
            payload1_layer = Sdf.Layer.CreateNew(payload1)
            payload2_layer = Sdf.Layer.CreateNew(payload2)
            payload_stage = Usd.Stage.Open(payload1_layer)
            payload_stage.DefinePrim("/payload1/child", "Xform")
            payload_stage = Usd.Stage.Open(payload2_layer)
            payload_stage.DefinePrim("/payload2/child", "Xform")
            payload_stage = None

            payload1_prim = stage.DefinePrim("/root/payload1", "Xform")
            payload2_prim = stage.DefinePrim("/root/payload2", "Xform")
            payload1_prim.GetPayloads().AddPayload(payload1_layer.identifier)
            payload2_prim.GetPayloads().AddPayload(payload2_layer.identifier)
            stage.Unload("/root/payload2")

            self.assertEqual(set(stage.GetLoadSet()), set([Sdf.Path("/root/payload1")]))
            payload1_layer = None
            payload2_layer = None

            for extension in ["usda", "usd"]:
                new_stage_path = os.path.join(tmpdirname, f"new_stage_payloads_disabled.{extension}")
                await omni.usd.get_context().save_as_stage_async(new_stage_path)

                stage = omni.usd.get_context().get_stage()
                self.assertEqual(set(stage.GetLoadSet()), set([Sdf.Path("/root/payload1")]))
                
            # New stage to release layer references so temp files can be removed.
            await omni.usd.get_context().new_stage_async()

            
