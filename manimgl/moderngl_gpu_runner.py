"""Headless EGL bootstrap for the official ModernGL ManimGL release."""

from __future__ import annotations

import os
import runpy
import warnings
from pathlib import Path


# The official ModernGL release still imports pkg_resources. It remains
# available through the pinned legacy Setuptools package; hide only its known
# deprecation warning so render output stays readable.
warnings.filterwarnings(
    "ignore",
    message=r"pkg_resources is deprecated as an API.*",
    category=UserWarning,
)

os.environ["PYGLET_HEADLESS"] = "true"
os.environ["PYOPENGL_PLATFORM"] = "egl"

import pyglet

pyglet.options["headless"] = True
pyglet.options["headless_device"] = 0
pyglet.options["shadow_window"] = False

ERROR_RUNNER = Path(__file__).resolve().parent / "error_runner.py"
runpy.run_path(str(ERROR_RUNNER), run_name="__main__")
