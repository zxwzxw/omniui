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
from omni.ui import color as cl


class TestSlider(OmniUiTest):
    """Testing ui.Frame"""

    async def test_general(self):
        """Testing general properties of ui.Slider"""
        window = await self.create_test_window()

        with window.frame:
            with ui.VStack(height=0, spacing=2):
                ui.FloatSlider(style={"draw_mode": ui.SliderDrawMode.HANDLE}).model.set_value(0.5)
                ui.IntSlider(style={"draw_mode": ui.SliderDrawMode.HANDLE}).model.set_value(15)
                ui.FloatSlider(
                    style={
                        "draw_mode": ui.SliderDrawMode.FILLED,
                        "background_color": 0xFF333333,
                        "secondary_color": 0xFF666666,
                    }
                ).model.set_value(0.25)
                ui.IntSlider(
                    style={
                        "draw_mode": ui.SliderDrawMode.FILLED,
                        "background_color": 0xFF333333,
                        "secondary_color": 0xFF666666,
                    }
                ).model.set_value(10)
                ui.FloatSlider(
                    style={
                        "draw_mode": ui.SliderDrawMode.FILLED,
                        "background_color": 0xFF333333,
                        "secondary_color": 0xFF666666,
                        "secondary_color": 0xFF666666,
                        "border_color": 0xFFFFFFFF,
                        "border_width": 1,
                        "border_radius": 20,
                    }
                ).model.set_value(0.4375)
                # 0.015625 will be rounded differently on linux and windows
                # See https://stackoverflow.com/questions/4649554 for details
                # To fix it, add something small
                ui.FloatSlider(
                    style={
                        "draw_mode": ui.SliderDrawMode.FILLED,
                        "background_color": 0xFF333333,
                        "secondary_color": 0xFF666666,
                        "secondary_color": 0xFF666666,
                        "border_color": 0xFFFFFFFF,
                        "border_width": 1,
                        "border_radius": 20,
                    }
                ).model.set_value(0.015625 + 1e-10)
                ui.FloatDrag().model.set_value(0.375)
                ui.IntDrag().model.set_value(25)

        await self.finalize_test()

    async def test_padding(self):
        """Testing slider's padding"""
        style = {
            "background_color": cl.grey,
            "draw_mode": ui.SliderDrawMode.FILLED,
            "border_width": 1,
            "border_color": cl.black,
            "border_radius": 0,
            "font_size": 16,
            "padding": 0,
        }

        window = await self.create_test_window()

        with window.frame:
            with ui.VStack(height=0):
                for i in range(8):
                    style["padding"] = i * 2
                    with ui.HStack(height=0):
                        ui.FloatSlider(style=style, height=0)
                        ui.FloatField(style=style, height=0)

        await self.finalize_test()

    async def test_float_slider_precision(self):
        window = await self.create_test_window()

        with window.frame:
            with ui.VStack(height=0):
                ui.FloatSlider(precision=7, height=0).model.set_value(0.00041233)
                ui.FloatDrag(precision=8, height=0).model.set_value(0.00041233)
                ui.FloatField(precision=5, height=0).model.set_value(0.00041233)
        await self.finalize_test()
