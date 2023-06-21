## Copyright (c) 2018-2019, NVIDIA CORPORATION.  All rights reserved.
##
## NVIDIA CORPORATION and its licensors retain all intellectual property
## and proprietary rights in and to this software, related documentation
## and any modifications thereto.  Any use, reproduction, disclosure or
## distribution of this software and related documentation without an express
## license agreement from NVIDIA CORPORATION is strictly prohibited.
##
__all__ = ["TestShapes"]

from .test_base import OmniUiTest
import omni.ui as ui
from omni.ui import color as cl


class TestShapes(OmniUiTest):
    """Testing ui.Shape"""

    async def test_offsetline(self):
        """Testing general properties of ui.OffsetLine"""
        window = await self.create_test_window()

        with window.frame:
            with ui.ZStack(
                style={
                    "Rectangle": {"background_color": cl(0, 0, 0, 0), "border_color": cl.white, "border_width": 1},
                    "OffsetLine": {"color": cl.white, "border_width": 1},
                }
            ):
                with ui.VStack():
                    with ui.HStack(height=32):
                        rect1 = ui.Rectangle(width=32)
                        ui.Spacer()
                    ui.Spacer()
                    with ui.HStack(height=32):
                        ui.Spacer()
                        rect2 = ui.Rectangle(width=32)

                ui.OffsetLine(
                    rect1,
                    rect2,
                    alignment=ui.Alignment.UNDEFINED,
                    begin_arrow_type=ui.ArrowType.ARROW,
                    offset=7,
                    bound_offset=20,
                )
                ui.OffsetLine(
                    rect2,
                    rect1,
                    alignment=ui.Alignment.UNDEFINED,
                    begin_arrow_type=ui.ArrowType.ARROW,
                    offset=7,
                    bound_offset=20,
                )

        await self.finalize_test()

    async def test_freebezier(self):
        """Testing general properties of ui.OffsetLine"""
        window = await self.create_test_window()

        with window.frame:
            with ui.ZStack(
                style={
                    "Rectangle": {"background_color": cl(0, 0, 0, 0), "border_color": cl.white, "border_width": 1},
                    "FreeBezierCurve": {"color": cl.white, "border_width": 1},
                }
            ):
                with ui.VStack():
                    with ui.HStack(height=32):
                        rect1 = ui.Rectangle(width=32)
                        ui.Spacer()
                    ui.Spacer()
                    with ui.HStack(height=32):
                        ui.Spacer()
                        rect2 = ui.Rectangle(width=32)

                # Default tangents
                ui.FreeBezierCurve(rect1, rect2, style={"color": cl.chartreuse})

                # 0 tangents
                ui.FreeBezierCurve(
                    rect1,
                    rect2,
                    start_tangent_width=0,
                    start_tangent_height=0,
                    end_tangent_width=0,
                    end_tangent_height=0,
                    style={"color": cl.darkslategrey},
                )

                # Fraction tangents
                ui.FreeBezierCurve(
                    rect1,
                    rect2,
                    start_tangent_width=0,
                    start_tangent_height=ui.Fraction(2),
                    end_tangent_width=0,
                    end_tangent_height=ui.Fraction(-2),
                    style={"color": cl.dodgerblue},
                )

                # Percent tangents
                ui.FreeBezierCurve(
                    rect1,
                    rect2,
                    start_tangent_width=0,
                    start_tangent_height=ui.Percent(100),
                    end_tangent_width=0,
                    end_tangent_height=ui.Percent(-100),
                    style={"color": cl.peru},
                )

                # Super big tangents
                ui.FreeBezierCurve(
                    rect1,
                    rect2,
                    start_tangent_width=0,
                    start_tangent_height=1e8,
                    end_tangent_width=0,
                    end_tangent_height=-1e8,
                    style={"color": cl.indianred},
                )

        await self.finalize_test()
