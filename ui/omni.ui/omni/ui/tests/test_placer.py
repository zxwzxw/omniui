## Copyright (c) 2018-2019, NVIDIA CORPORATION.  All rights reserved.
##
## NVIDIA CORPORATION and its licensors retain all intellectual property
## and proprietary rights in and to this software, related documentation
## and any modifications thereto.  Any use, reproduction, disclosure or
## distribution of this software and related documentation without an express
## license agreement from NVIDIA CORPORATION is strictly prohibited.
##
from .test_base import OmniUiTest
import omni.ui as ui
import omni.kit.app


RECT_SIZE = 10
RECT_STYLE = {"background_color": 0xFFFFFFFF}
RECT_TRANSPARENT_STYLE = {"background_color": 0x66FFFFFF, "border_color": 0xFFFFFFFF, "border_width": 1}


class TestPlacer(OmniUiTest):
    """Testing ui.Placer"""

    async def test_general(self):
        """Testing general properties of ui.Placer"""
        window = await self.create_test_window()

        with window.frame:
            with ui.ZStack():
                with ui.Placer(offset_x=10, offset_y=10):
                    ui.Rectangle(width=RECT_SIZE, height=RECT_SIZE, style=RECT_STYLE)
                with ui.Placer(offset_x=90, offset_y=10):
                    ui.Rectangle(width=RECT_SIZE, height=RECT_SIZE, style=RECT_STYLE)
                with ui.Placer(offset_x=90, offset_y=90):
                    ui.Rectangle(width=RECT_SIZE, height=RECT_SIZE, style=RECT_STYLE)
                with ui.Placer(offset_x=10, offset_y=90):
                    ui.Rectangle(width=RECT_SIZE, height=RECT_SIZE, style=RECT_STYLE)

        await self.finalize_test()

    async def test_percents(self):
        """Testing ability to offset in percents of ui.Placer"""
        window = await self.create_test_window()

        with window.frame:
            with ui.ZStack():
                with ui.Placer(offset_x=ui.Percent(10), offset_y=ui.Percent(10)):
                    ui.Rectangle(width=RECT_SIZE, height=RECT_SIZE, style=RECT_STYLE)
                with ui.Placer(offset_x=ui.Percent(90), offset_y=ui.Percent(10)):
                    ui.Rectangle(width=RECT_SIZE, height=RECT_SIZE, style=RECT_STYLE)
                with ui.Placer(offset_x=ui.Percent(90), offset_y=ui.Percent(90)):
                    ui.Rectangle(width=RECT_SIZE, height=RECT_SIZE, style=RECT_STYLE)
                with ui.Placer(offset_x=ui.Percent(10), offset_y=ui.Percent(90)):
                    ui.Rectangle(width=RECT_SIZE, height=RECT_SIZE, style=RECT_STYLE)

        await self.finalize_test()

    async def test_child_percents(self):
        """Testing ability to offset in percents of ui.Placer"""
        window = await self.create_test_window()

        with window.frame:
            with ui.ZStack():
                with ui.Placer(offset_x=ui.Percent(10), offset_y=ui.Percent(10)):
                    ui.Rectangle(width=ui.Percent(80), height=ui.Percent(80), style=RECT_TRANSPARENT_STYLE)
                with ui.Placer(offset_x=ui.Percent(50), offset_y=ui.Percent(50)):
                    ui.Rectangle(width=ui.Percent(50), height=ui.Percent(50), style=RECT_TRANSPARENT_STYLE)

        await self.finalize_test()

    async def test_resize(self):
        window = await self.create_test_window()

        with window.frame:
            placer = ui.Placer(width=200)
            with placer:
                ui.Rectangle(height=100, style={"background_color": omni.ui.color.red})

        await omni.kit.app.get_app().next_update_async()
        await omni.kit.app.get_app().next_update_async()

        placer.width = ui.Percent(5)

        await self.finalize_test()
