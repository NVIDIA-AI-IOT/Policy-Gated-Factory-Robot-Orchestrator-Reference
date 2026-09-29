# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Camera frames retain their colors and crop after image dependency updates."""

import io
from types import SimpleNamespace

import pytest

from policy_gated_factory_robot_orchestrator_reference.floor.ros2 import _image_to_jpeg

np = pytest.importorskip("numpy")
Image = pytest.importorskip("PIL.Image")


@pytest.mark.parametrize(
    ("encoding", "pixel", "expected"),
    [
        ("rgb8", (220, 30, 60), (220, 30, 60)),
        ("bgr8", (60, 30, 220), (220, 30, 60)),
        ("rgba8", (220, 30, 60, 255), (220, 30, 60)),
        ("mono8", (120,), (120, 120, 120)),
    ],
)
def test_camera_jpeg_preserves_dimensions_and_color(
    encoding: str, pixel: tuple[int, ...], expected: tuple[int, ...]
) -> None:
    pixels = np.zeros((12, 16, len(pixel)), dtype=np.uint8)
    pixels[:] = pixel
    frame = SimpleNamespace(height=12, width=16, data=pixels.tobytes(), encoding=encoding)
    with Image.open(io.BytesIO(_image_to_jpeg(frame))) as decoded:
        assert decoded.format == "JPEG"
        assert decoded.size == (16, 12)
        np.testing.assert_allclose(decoded.convert("RGB").getpixel((8, 6)), expected, atol=3)


def test_camera_crop_selects_the_requested_region() -> None:
    pixels = np.zeros((56, 56, 3), dtype=np.uint8)
    pixels[:, :28] = (220, 30, 60)
    pixels[:, 28:] = (20, 40, 220)
    frame = SimpleNamespace(height=56, width=56, data=pixels.tobytes(), encoding="rgb8")
    with Image.open(io.BytesIO(_image_to_jpeg(frame, (0.5, 0.0, 1.0, 1.0)))) as decoded:
        assert decoded.size == (56, 112)
        np.testing.assert_allclose(decoded.convert("RGB").getpixel((28, 56)), (20, 40, 220), atol=3)
