# Copyright (c) 2020, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#

import omni.usd

from pxr import Usd, UsdGeom, Gf, Sdf


class TestEditorAPI(omni.kit.test.AsyncTestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    async def setUp(self):
        await omni.usd.get_context().new_stage_async() 
        self.stage = omni.usd.get_context().get_stage()
        self.context = omni.usd.get_context()

    async def tearDown(self):
        pass

    async def test_api(self):
        prim = self.stage.DefinePrim("/test", "Xform")
        self.assertFalse(omni.usd.editor.is_hide_in_ui(prim))
        omni.usd.editor.set_hide_in_ui(prim, True)
        self.assertTrue(omni.usd.editor.is_hide_in_ui(prim))
        omni.usd.editor.set_hide_in_ui(prim, False)
        self.assertFalse(omni.usd.editor.is_hide_in_ui(prim))
