import omni.usd
import omni.kit.test


class TestLegacyAPI(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        await omni.usd.get_context().new_stage_async() 
        self.stage = omni.usd.get_context().get_stage()
        self.context = omni.usd.get_context()

    async def tearDown(self):
        pass

    def test_live_apis(self):
        self.assertFalse(self.context.is_stage_live())
        self.assertFalse(self.context.is_layer_live(self.stage.GetRootLayer().identifier))
        self.context.set_stage_live(omni.usd.StageLiveModeType.TOGGLE_ON)
        self.context.set_stage_live(omni.usd.StageLiveModeType.ALWAYS_ON)
        self.context.set_stage_live(omni.usd.StageLiveModeType.TOGGLE_OFF)
        live_mode = self.context.get_stage_live_mode()
        self.assertEqual(live_mode, omni.usd.StageLiveModeType.TOGGLE_OFF)
        self.context.set_layer_live(self.stage.GetRootLayer().identifier, False)

    def test_layer_apis(self):
        self.context.get_layers().subscribe_to_default_edit_layer_events(None)
        self.context.get_layers().subscribe_to_lock_events(None)
        self.context.get_layers().subscribe_to_layer_muteness_events(None)
        self.context.get_layers().subscribe_to_layer_muteness_scope_events(None)
        self.context.get_layers().subscribe_to_layer_metadata_events(None)
        self.context.get_layers().subscribe_to_layer_edit_mode_events(None)
        self.context.get_layers().subscribe_to_sublayer_events(None)
        self.context.get_layers().subscribe_to_prim_spec_events(None)
