## Copyright (c) 2018-2019, NVIDIA CORPORATION.  All rights reserved.
##
## NVIDIA CORPORATION and its licensors retain all intellectual property
## and proprietary rights in and to this software, related documentation
## and any modifications thereto.  Any use, reproduction, disclosure or
## distribution of this software and related documentation without an express
## license agreement from NVIDIA CORPORATION is strictly prohibited.
##
import unittest
from .test_base import OmniUiTest
from functools import partial
import omni.kit.app
import omni.ui as ui

TEXT = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut "
    "labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco "
    "laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in "
    "voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat "
    "non proident, sunt in culpa qui officia deserunt mollit anim id est laborum."
)


class TestCanvasFrame(OmniUiTest):
    """Testing ui.CanvasFrame"""

    async def test_general(self):
        """Testing general properties of ui.CanvasFrame"""
        window = await self.create_test_window()

        with window.frame:
            with ui.CanvasFrame():
                with ui.VStack(height=0):
                    # Simple text
                    ui.Label("Hello world")

                    # Word wrap
                    ui.Label(TEXT, word_wrap=True)

                    # Gray button
                    ui.Button(
                        "Button",
                        style={
                            "Button": {"background_color": 0xFF666666, "margin": 0, "padding": 4, "border_radius": 0}
                        },
                    )

        await self.finalize_test()

    @unittest.skip("Disabling temporarily to avoid failure due to bold 'l' on linux font")
    async def test_zoom(self):
        """Testing zoom of ui.CanvasFrame"""
        window = await self.create_test_window()

        with window.frame:
            with ui.CanvasFrame(zoom=0.5):
                with ui.VStack(height=0):
                    # Simple text
                    ui.Label("Hello world")

                    # Word wrap
                    ui.Label(TEXT, word_wrap=True)

                    # Gray button
                    ui.Button(
                        "Button",
                        style={
                            "Button": {"background_color": 0xFF666666, "margin": 0, "padding": 8, "border_radius": 0}
                        },
                    )

        await self.finalize_test()

    async def test_pan(self):
        """Testing zoom of ui.CanvasFrame"""
        window = await self.create_test_window()

        with window.frame:
            with ui.CanvasFrame(pan_x=64, pan_y=128):
                with ui.VStack(height=0):
                    # Simple text
                    ui.Label("Hello world")

                    # Word wrap
                    ui.Label(TEXT, word_wrap=True)

                    # Gray button
                    ui.Button(
                        "Button",
                        style={
                            "Button": {"background_color": 0xFF666666, "margin": 0, "padding": 4, "border_radius": 0}
                        },
                    )

        await self.finalize_test()

    async def test_space(self):
        """Testing transforming screen space to canvas space of ui.CanvasFrame"""
        window = await self.create_test_window()

        with window.frame:
            frame = ui.CanvasFrame(pan_x=512, pan_y=1024)
            with frame:
                placer = ui.Placer()
                with placer:
                    # Gray button
                    ui.Button(
                        "Button",
                        width=0,
                        height=0,
                        style={
                            "Button": {"background_color": 0xFF666666, "margin": 0, "padding": 4, "border_radius": 0}
                        },
                    )

        await omni.kit.app.get_app().next_update_async()
        await omni.kit.app.get_app().next_update_async()

        placer.offset_x = frame.screen_to_canvas_x(frame.screen_position_x + 128)
        placer.offset_y = frame.screen_to_canvas_y(frame.screen_position_y + 128)

        await self.finalize_test()

    async def test_navigation_pan(self):
        """Test how CanvasFrame interacts with mouse"""
        import omni.kit.ui_test as ui_test

        pan = [0, 0]

        def pan_changed(axis, value):
            pan[axis] = value

        window = await self.create_test_window(block_devices=False)

        with window.frame:
            canvas = ui.CanvasFrame(smooth_zoom=False)
            canvas.set_pan_key_shortcut(0, 0)
            canvas.set_pan_x_changed_fn(partial(pan_changed, 0))
            canvas.set_pan_y_changed_fn(partial(pan_changed, 1))
            with canvas:
                with ui.VStack(height=0):
                    # Simple text
                    ui.Label("Hello world")

                    # Word wrap
                    ui.Label(TEXT, word_wrap=True)

                    # Button
                    ui.Button("Button")

        ref = ui_test.WidgetRef(window.frame, "")

        for i in range(2):
            await omni.kit.app.get_app().next_update_async()

        await ui_test.emulate_mouse_move(ref.center)
        await ui_test.emulate_mouse_drag_and_drop(ref.center, ref.center * 0.8, human_delay_speed=1)

        for i in range(2):
            await omni.kit.app.get_app().next_update_async()

        await self.finalize_test()

        self.assertEqual(pan[0], -26)
        self.assertEqual(pan[1], -26)

    async def test_navigation_zoom(self):
        """Test how CanvasFrame interacts with mouse zoom"""
        import omni.kit.ui_test as ui_test

        window = await self.create_test_window(block_devices=False)
        with window.frame:
            canvas = ui.CanvasFrame(smooth_zoom=False)
            canvas.set_zoom_key_shortcut(1, 0)

        self.assertEqual(canvas.zoom, 1.0)
        ref = ui_test.WidgetRef(window.frame, "")

        for i in range(2):
            await omni.kit.app.get_app().next_update_async()

        await ui_test.emulate_mouse_move(ref.center)
        await ui_test.emulate_mouse_drag_and_drop(ref.center, ref.center * 0.5, right_click=True, human_delay_speed=1)

        for i in range(2):
            await omni.kit.app.get_app().next_update_async()

        # check the zoom is changed with the key_index press and right click
        self.assertAlmostEqual(canvas.zoom, 0.8950250148773193, 1)

    async def test_zoom_with_limits(self):
        """Testing zoom is limited by the zoom_min and zoom_max"""
        window = await self.create_test_window()

        with window.frame:
            frame = ui.CanvasFrame(zoom=2.5, zoom_max=2.0, zoom_min=0.5)
            with frame:
                with ui.HStack():
                    ui.Spacer()
                    with ui.VStack():
                        ui.Spacer()
                        ui.Rectangle(width=50, height=50, style={"background_color": 0xFF000066})
                        ui.Spacer()
                    ui.Spacer()

        await omni.kit.app.get_app().next_update_async()
        await self.finalize_test()

        # check the zoom is limited by zoom_max = 2.0
        self.assertEqual(frame.screen_position_x, 2.0)
        self.assertEqual(frame.screen_position_y, 2.0)

    async def test_compatibility(self):
        """Testing zoom of ui.CanvasFrame"""
        window = await self.create_test_window()

        with window.frame:
            with ui.CanvasFrame(zoom=0.5, pan_x=64, pan_y=64, compatibility=False):
                with ui.VStack(height=0):
                    # Simple text
                    ui.Label("NVIDIA")

                    # Word wrap
                    ui.Label(TEXT, word_wrap=True)

                    # Gray button
                    ui.Button(
                        "Button",
                        style={
                            "Button": {"background_color": 0xFF666666, "margin": 0, "padding": 8, "border_radius": 0}
                        },
                    )

        await self.finalize_test()

    async def test_compatibility_text(self):
        """Testing zoom of ui.CanvasFrame"""
        window = await self.create_test_window()

        with window.frame:
            with ui.CanvasFrame(zoom=4.0, compatibility=False):
                with ui.VStack(height=0):
                    # Simple text
                    ui.Label("NVIDIA")

                    # Word wrap
                    ui.Label(TEXT, word_wrap=True)

                    # Gray button
                    ui.Button(
                        "Button",
                        style={
                            "Button": {"background_color": 0xFF666666, "margin": 0, "padding": 8, "border_radius": 0}
                        },
                    )

        await self.finalize_test()