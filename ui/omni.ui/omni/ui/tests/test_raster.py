## Copyright (c) 2018-2019, NVIDIA CORPORATION.  All rights reserved.
##
## NVIDIA CORPORATION and its licensors retain all intellectual property
## and proprietary rights in and to this software, related documentation
## and any modifications thereto.  Any use, reproduction, disclosure or
## distribution of this software and related documentation without an express
## license agreement from NVIDIA CORPORATION is strictly prohibited.
##
from functools import partial
from .test_base import OmniUiTest
import omni.ui as ui
import omni.kit.app


class TestRaster(OmniUiTest):
    """Testing ui.Frame"""

    async def test_general(self):
        import omni.kit.ui_test as ui_test
        from carb.input import MouseEventType

        window = await self.create_test_window(block_devices=False)

        with window.frame:
            with ui.HStack():
                left_frame = ui.Frame(raster_policy=ui.RasterPolicy.AUTO)
                right_frame = ui.Frame(raster_policy=ui.RasterPolicy.AUTO)

        with left_frame:
            ui.Rectangle(style={"background_color": ui.color.grey})

        with right_frame:
            ui.Rectangle(style={"background_color": ui.color.grey})

        left_frame_ref = ui_test.WidgetRef(left_frame, "")
        right_frame_ref = ui_test.WidgetRef(right_frame, "")

        await ui_test.input.wait_n_updates_internal()
        await ui_test.input.emulate_mouse_move(right_frame_ref.center)
        await ui_test.input.wait_n_updates_internal()
        await ui_test.input.emulate_mouse_move(left_frame_ref.center)
        await ui_test.input.wait_n_updates_internal()

        await self.finalize_test()

    async def test_edit(self):
        import omni.kit.ui_test as ui_test
        from carb.input import MouseEventType

        window = await self.create_test_window(block_devices=False)

        with window.frame:
            with ui.HStack():
                left_frame = ui.Frame(raster_policy=ui.RasterPolicy.AUTO)
                right_frame = ui.Frame(raster_policy=ui.RasterPolicy.AUTO)

        with left_frame:
            ui.Rectangle(style={"background_color": ui.color.grey})

        with right_frame:
            with ui.ZStack():
                ui.Rectangle(style={"background_color": ui.color.grey})
                with ui.VStack():
                    ui.Spacer()
                    field = ui.StringField(height=0)
                    ui.Spacer()

        left_frame_ref = ui_test.WidgetRef(left_frame, "")
        field_ref = ui_test.WidgetRef(field, "")

        await ui_test.input.wait_n_updates_internal()
        await ui_test.input.emulate_mouse_move_and_click(field_ref.center)
        await ui_test.input.wait_n_updates_internal()
        await ui_test.input.emulate_mouse_move(left_frame_ref.center)
        await ui_test.input.wait_n_updates_internal()

        await self.finalize_test()

    async def test_dnd(self):
        import omni.kit.ui_test as ui_test
        from carb.input import MouseEventType

        window = await self.create_test_window(
            block_devices=False,
            window_flags=ui.WINDOW_FLAGS_NO_SCROLLBAR
            | ui.WINDOW_FLAGS_NO_TITLE_BAR
            | ui.WINDOW_FLAGS_NO_RESIZE
            | ui.WINDOW_FLAGS_NO_MOVE,
        )

        with window.frame:
            with ui.HStack():
                left_frame = ui.Frame(raster_policy=ui.RasterPolicy.AUTO)
                right_frame = ui.Frame(raster_policy=ui.RasterPolicy.AUTO)

        with left_frame:
            ui.Rectangle(style={"background_color": ui.color.grey})

        with right_frame:
            ui.Rectangle(style={"background_color": ui.color.grey})

        left_frame_ref = ui_test.WidgetRef(left_frame, "")
        right_frame_ref = ui_test.WidgetRef(right_frame, "")

        await ui_test.input.wait_n_updates_internal()
        await ui_test.input.emulate_mouse(MouseEventType.MOVE, left_frame_ref.center)
        await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_DOWN)
        await ui_test.input.wait_n_updates_internal()
        await ui_test.input.emulate_mouse_slow_move(left_frame_ref.center, right_frame_ref.center)

        await self.finalize_test()

        await ui_test.input.emulate_mouse(MouseEventType.LEFT_BUTTON_UP)

    async def test_update(self):
        import omni.kit.ui_test as ui_test
        from carb.input import MouseEventType

        window = await self.create_test_window(block_devices=False)

        with window.frame:
            with ui.HStack():
                left_frame = ui.Frame(raster_policy=ui.RasterPolicy.AUTO)
                right_frame = ui.Frame(raster_policy=ui.RasterPolicy.AUTO)

        with left_frame:
            ui.Rectangle(style={"background_color": ui.color.grey})

        with right_frame:
            ui.Rectangle(style={"background_color": ui.color.grey})

        await ui_test.input.wait_n_updates_internal()
        await ui_test.input.emulate_mouse_move(ui_test.input.Vec2(0, 0))

        with right_frame:
            ui.Rectangle(style={"background_color": ui.color.beige})

        await ui_test.input.wait_n_updates_internal(update_count=4)

        await self.finalize_test()


    async def test_model(self):
        import omni.kit.ui_test as ui_test
        from carb.input import MouseEventType

        window = await self.create_test_window(block_devices=False)

        with window.frame:
            with ui.HStack():
                left_frame = ui.Frame(raster_policy=ui.RasterPolicy.AUTO)
                right_frame = ui.Frame(raster_policy=ui.RasterPolicy.AUTO)

        with left_frame:
            ui.Rectangle(style={"background_color": ui.color.grey})

        with right_frame:
            with ui.ZStack():
                ui.Rectangle(style={"background_color": ui.color.grey})
                with ui.VStack():
                    ui.Spacer()
                    field = ui.StringField(height=0)
                    ui.Spacer()

        await ui_test.input.wait_n_updates_internal()
        await ui_test.input.emulate_mouse_move(ui_test.input.Vec2(0, 0))

        field.model.as_string = "NVIDIA"

        await ui_test.input.wait_n_updates_internal(update_count=4)

        await self.finalize_test()

    async def test_on_demand(self):
        import omni.kit.ui_test as ui_test
        from carb.input import MouseEventType

        window = await self.create_test_window(block_devices=False)

        with window.frame:
            with ui.HStack():
                right_frame = ui.Frame(raster_policy=ui.RasterPolicy.ON_DEMAND)

        with right_frame:
            with ui.ZStack():
                ui.Rectangle(style={"background_color": ui.color.grey})
                with ui.VStack():
                    ui.Spacer()
                    field = ui.StringField(height=0)
                    ui.Spacer()

        right_frame_ref = ui_test.WidgetRef(right_frame, "")

        await ui_test.input.wait_n_updates_internal()
        await ui_test.input.emulate_mouse_move(right_frame_ref.center)

        field.model.as_string = "NVIDIA"

        await ui_test.input.wait_n_updates_internal(update_count=4)

        await self.finalize_test()

    async def test_on_demand_invalidate(self):
        import omni.kit.ui_test as ui_test
        from carb.input import MouseEventType

        window = await self.create_test_window(block_devices=False)

        with window.frame:
            with ui.HStack():
                right_frame = ui.Frame(raster_policy=ui.RasterPolicy.ON_DEMAND)

        with right_frame:
            with ui.ZStack():
                ui.Rectangle(style={"background_color": ui.color.grey})
                with ui.VStack():
                    ui.Spacer()
                    field = ui.StringField(height=0)
                    ui.Spacer()

        right_frame_ref = ui_test.WidgetRef(right_frame, "")

        await ui_test.input.wait_n_updates_internal()
        await ui_test.input.emulate_mouse_move(right_frame_ref.center)

        field.model.as_string = "NVIDIA"

        await ui_test.input.wait_n_updates_internal(update_count=4)

        right_frame.invalidate_raster()

        await ui_test.input.wait_n_updates_internal(update_count=4)

        await self.finalize_test()
