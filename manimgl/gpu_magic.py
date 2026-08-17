"""Google Colab cell magic for NVIDIA EGL/ModernGL ManimGL rendering."""

from __future__ import annotations

import json
import os
import runpy
import shlex
import time
from pathlib import Path


THIS_DIR = Path(__file__).resolve().parent
GPU_CONFIG = Path("/content/manimgl_gpu_config.json")
SCENE_FILE = Path("/content/manimgl_cell.py")
VIDEO_DIR = Path("/content/manimgl_videos")
ERROR_REPORT = Path("/content/manimgl_error_report.json")
RUNTIME_DIR = Path("/tmp/runtime-colab")


def _load_helpers():
    return runpy.run_path(str(THIS_DIR / "colab_magic.py"))


def _gpu_environment(config: dict) -> dict[str, str]:
    environment = os.environ.copy()
    environment["LD_LIBRARY_PATH"] = (
        f"{config['library_dir']}:/usr/lib64-nvidia:"
        f"{environment.get('LD_LIBRARY_PATH', '')}"
    )
    environment["__EGL_VENDOR_LIBRARY_FILENAMES"] = str(config["egl_json"])
    environment["__GLX_VENDOR_LIBRARY_NAME"] = "nvidia"
    environment["PYGLET_HEADLESS"] = "true"
    environment["PYOPENGL_PLATFORM"] = "egl"
    environment["XDG_RUNTIME_DIR"] = str(RUNTIME_DIR)
    environment["MANIMGL_ERROR_REPORT"] = str(ERROR_REPORT)
    for name in (
        "LIBGL_ALWAYS_SOFTWARE",
        "VK_ICD_FILENAMES",
        "VK_DRIVER_FILES",
        "DISPLAY",
        "WAYLAND_DISPLAY",
    ):
        environment.pop(name, None)
    return environment


def register_manimgl_gpu_magic() -> None:
    """Register ``%%manimgl_gpu`` and ``%manimgl_gpuinfo``."""
    from IPython import get_ipython
    from IPython.display import Video, display

    ipython = get_ipython()
    if ipython is None:
        raise RuntimeError("GPU magic requires Google Colab or IPython.")

    helpers = _load_helpers()
    run_and_capture = helpers["_run_and_capture"]
    load_error_report = helpers["_load_error_report"]
    display_error_report = helpers["_display_error_report"]
    render_error_class = helpers["ManimGLRenderError"]

    def gpu_magic(line: str, cell: str) -> None:
        start_total = time.perf_counter()
        if not GPU_CONFIG.exists():
            raise FileNotFoundError("GPU configuration is missing. Run setup_gpu() first.")
        config = json.loads(GPU_CONFIG.read_text(encoding="utf-8"))

        tokens = shlex.split(line)
        if not tokens:
            raise ValueError("Scene name required. Example: %%manimgl_gpu --draft MyScene")
        scene_name = tokens[-1]
        options = tokens[:-1]

        quality = "-l"
        log_level = "WARNING"
        display_width = 560
        draft = False
        prerun = False
        progress = False
        full_error = False
        extra: list[str] = []

        index = 0
        while index < len(options):
            option = options[index]
            normalized = option.lower()
            if option in ("-ql", "--quality=l"):
                quality = "-l"
            elif option in ("-qm", "--quality=m"):
                quality = "-m"
            elif option in ("-qh", "--quality=h"):
                quality = "--hd"
            elif option in ("-qk", "--quality=k"):
                quality = "--uhd"
            elif option in ("-v", "--verbosity"):
                if index + 1 >= len(options):
                    raise ValueError("-v must be followed by a log level.")
                log_level = options[index + 1].upper()
                index += 1
            elif option == "--display-width":
                if index + 1 >= len(options):
                    raise ValueError("--display-width requires a number.")
                display_width = int(options[index + 1])
                index += 1
            elif normalized == "--draft":
                draft = True
            elif normalized == "--prerun":
                prerun = True
            elif normalized == "--progress":
                progress = True
            elif normalized in ("--error", "--full-error"):
                full_error = True
            else:
                extra.append(option)
            index += 1

        gpu_python = Path(config["gpu_python"])
        runner = Path(config["runner"])
        if not gpu_python.exists() or not runner.exists():
            raise FileNotFoundError("GPU environment is incomplete. Run setup_gpu(force=True).")

        VIDEO_DIR.mkdir(parents=True, exist_ok=True)
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        RUNTIME_DIR.chmod(0o700)
        SCENE_FILE.write_text(cell, encoding="utf-8")
        if ERROR_REPORT.exists():
            ERROR_REPORT.unlink()

        expected_video = VIDEO_DIR / f"{scene_name}.mp4"
        if expected_video.exists():
            expected_video.unlink()

        render_options = ["-r", "640x360", "--fps", "15"] if draft else [quality]
        optional: list[str] = []
        if prerun:
            optional.append("--prerun")
        if progress:
            optional.extend(["--show_animation_progress", "--leave_progress_bars"])

        command = [
            str(gpu_python),
            str(runner),
            str(SCENE_FILE),
            scene_name,
            "-w",
            *render_options,
            "-c",
            "#000000",
            "--video_dir",
            str(VIDEO_DIR),
            "--log-level",
            log_level,
            *optional,
            *extra,
        ]

        context = config.get("context", {})
        print("=" * 68)
        print("NVIDIA ManimGL GPU render")
        print("=" * 68)
        print(f"Scene: {scene_name}")
        print(f"GPU: {config.get('name', 'NVIDIA GPU')}")
        print(f"Renderer: {context.get('renderer', 'NVIDIA EGL')}")
        print(f"Mode: {'draft 640x360 @ 15 FPS' if draft else quality}")
        print(f"Error mode: {'FULL' if full_error else 'compact'}")
        print("\n[1/3] Rendering on NVIDIA GPU...", flush=True)

        process_start = time.perf_counter()
        status, output = run_and_capture(
            command,
            _gpu_environment(config),
            stream_output=progress or log_level in ("INFO", "DEBUG"),
        )
        process_time = time.perf_counter() - process_start

        if status != 0:
            report = load_error_report(output)
            error_type, message = display_error_report(
                report,
                output,
                full_mode=full_error,
                scene_name=scene_name,
            )
            raise render_error_class(f"{error_type}: {message}") from None

        print(f"[2/3] GPU render finished in {process_time:.2f} seconds.")
        print("[3/3] Preparing video preview...", flush=True)
        preview_start = time.perf_counter()

        if not expected_video.exists():
            matches = sorted(
                VIDEO_DIR.glob(f"{scene_name}*.mp4"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            if not matches:
                raise FileNotFoundError("GPU render finished, but no MP4 was found.")
            expected_video = matches[0]

        attributes = (
            "controls autoplay muted loop "
            f'width="{display_width}" style="max-width:100%; height:auto;"'
        )
        video = Video(str(expected_video), embed=True, html_attributes=attributes)
        preview_time = time.perf_counter() - preview_start
        display(video)

        print("\n" + "=" * 68)
        print("NVIDIA GPU video ready")
        print("=" * 68)
        print(f"Path: {expected_video}")
        print(f"Size: {expected_video.stat().st_size / (1024 * 1024):.2f} MB")
        print(f"Render: {process_time:.2f} seconds")
        print(f"Preview preparation: {preview_time:.2f} seconds")
        print(f"Total: {time.perf_counter() - start_total:.2f} seconds")
        print(f"Download: %manimgl_download {scene_name}")

    def gpuinfo_magic(line: str) -> None:
        if not GPU_CONFIG.exists():
            print("GPU is not configured. Run setup_gpu().")
            return
        config = json.loads(GPU_CONFIG.read_text(encoding="utf-8"))
        print("ManimGL GPU configuration")
        print(f"GPU: {config.get('name')}")
        print(f"Driver: {config.get('driver_version')}")
        print(f"VRAM: {config.get('memory_mib')} MiB")
        print(f"Renderer: {config.get('context', {}).get('renderer')}")
        print(f"OpenGL: {config.get('context', {}).get('version')}")
        print(f"Environment: {config.get('gpu_python')}")

    ipython.register_magic_function(gpu_magic, magic_kind="cell", magic_name="manimgl_gpu")
    ipython.register_magic_function(
        gpuinfo_magic,
        magic_kind="line",
        magic_name="manimgl_gpuinfo",
    )
    print("NVIDIA GPU magic registered successfully.")
    print("Render: %%manimgl_gpu --draft SceneName")
    print("Info:   %manimgl_gpuinfo")


if __name__ == "__main__":
    register_manimgl_gpu_magic()
