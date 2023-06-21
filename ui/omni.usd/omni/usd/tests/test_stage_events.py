# Copyright (c) 2020, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#
import os
import tempfile
import omni.usd

from pathlib import Path
from omni.usd import StageEventType
from pxr import Usd, Sdf


class TestStageEvents(omni.kit.test.AsyncTestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._test_scene = str(Path(__file__).parent.joinpath("data").joinpath("test_scene.usda"))
        self._interested_events = [int(StageEventType.SAVED), int(StageEventType.CLOSING), int(StageEventType.CLOSED), int(StageEventType.OPENING), int(StageEventType.OPENED)]
        self._stage_is_not_null_during_closing = True

    async def setUp(self):
        usd_context = omni.usd.get_context()
        # Open and close to make sure no stage is created.
        usd_context.new_stage()
        await usd_context.close_stage_async()

        usd_context.set_pending_edit(False)
        self.usd_context = usd_context

        events = usd_context.get_stage_event_stream()
        self._stage_event_sub = events.create_subscription_to_pop(
            self._on_stage_event, name="omni.usd test_stage_events"
        )
        self._events_received = []
    
    def _on_stage_event(self, event):
        if event.type in self._interested_events:
            self._events_received.append(event.type)
            if event.type == int(StageEventType.CLOSING):
                stage = self.usd_context.get_stage()
                self._stage_is_not_null_during_closing = stage != None
    
    async def tearDown(self):
        self._events_received.clear()
        self._stage_event_sub = None

    async def test_usd_stage_events(self):
        # New and close stage
        self.usd_context.new_stage()
        self.assertEqual(self._events_received, [int(StageEventType.OPENING), int(StageEventType.OPENED)])

        self._events_received.clear()
        await self.usd_context.new_stage_async()
        self.assertEqual(self._events_received, [int(StageEventType.CLOSING), int(StageEventType.CLOSED), int(StageEventType.OPENING), int(StageEventType.OPENED)])
        self.assertTrue(self._stage_is_not_null_during_closing, "Stage should not be null during closing.")

        self._events_received.clear()
        await self.usd_context.close_stage_async()
        self.assertEqual(self._events_received, [int(StageEventType.CLOSING), int(StageEventType.CLOSED)])
        self.assertTrue(self._stage_is_not_null_during_closing, "Stage should not be null during closing.")

        # Attach stage
        self._events_received.clear()
        stage = Usd.Stage.CreateInMemory()
        await self.usd_context.attach_stage_async(stage)
        self.assertEqual(self._events_received, [int(StageEventType.OPENING), int(StageEventType.OPENED)])

        self._events_received.clear()
        another_stage = Usd.Stage.CreateInMemory()
        await self.usd_context.attach_stage_async(another_stage)
        self.assertEqual(self._events_received, [int(StageEventType.CLOSING), int(StageEventType.CLOSED), int(StageEventType.OPENING), int(StageEventType.OPENED)])
        self.assertTrue(self._stage_is_not_null_during_closing, "Stage should not be null during closing.")

        # Open stage
        with tempfile.TemporaryDirectory() as tmpdirname:
            tmp_file_path = os.path.join(tmpdirname, "tmp.usda")
            Sdf.Layer.CreateNew(tmp_file_path)
            tmp_file_path2 = os.path.join(tmpdirname, "tmp2.usda")
            Sdf.Layer.CreateNew(tmp_file_path2)
            
            self._events_received.clear()
            await self.usd_context.close_stage_async()
            self.assertEqual(self._events_received, [int(StageEventType.CLOSING), int(StageEventType.CLOSED)])
            self.assertTrue(self._stage_is_not_null_during_closing, "Stage should not be null during closing.")

            self._events_received.clear()
            await self.usd_context.open_stage_async(tmp_file_path)
            self.assertEqual(self._events_received, [int(StageEventType.OPENING), int(StageEventType.OPENED)])
            
            self._events_received.clear()
            await self.usd_context.open_stage_async(tmp_file_path2)
            self.assertEqual(self._events_received, [int(StageEventType.CLOSING), int(StageEventType.CLOSED), int(StageEventType.OPENING), int(StageEventType.OPENED)])
            self.assertTrue(self._stage_is_not_null_during_closing, "Stage should not be null during closing.")

            stage = self.usd_context.get_stage()
            stage.DefinePrim("/World/test")

            self._events_received.clear()
            self.usd_context.save_stage()
            self.assertEqual(self._events_received, [int(StageEventType.SAVED)])
            
            self._events_received.clear()
            stage.DefinePrim("/World/test2")
            await self.usd_context.save_stage_async()
            self.assertEqual(self._events_received, [int(StageEventType.SAVED)])
            
            # If it's the same format, it will do in-place save so no re-open is sent.
            self._events_received.clear()
            tmp_file_path3 = os.path.join(tmpdirname, "tmp3.usda")
            await self.usd_context.save_layers_async(tmp_file_path3, [])
            self.assertEqual(self._events_received, [int(StageEventType.SAVED)])

            # For format change, it will open stage.
            tmp_file_path4 = os.path.join(tmpdirname, "tmp3.usd")
            self._events_received.clear()
            await self.usd_context.save_layers_async(tmp_file_path4, [])
            # Copy to avoid later close events.
            events_received = self._events_received[:]
            await self.usd_context.close_stage_async()
            self.assertEqual(events_received, [int(StageEventType.CLOSING), int(StageEventType.CLOSED), int(StageEventType.OPENING), int(StageEventType.OPENED), int(StageEventType.SAVED)])
            self.assertTrue(self._stage_is_not_null_during_closing, "Stage should not be null during closing.")
            