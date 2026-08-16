"""Fast Google Colab cell magic for headless ManimGL rendering."""

from __future__ import annotations

import os
import shlex
import subprocess
import time
from pathlib import Path


MANIMGL_EXECUTABLE = Path("/content/manimgl-env/bin/manimgl")
MANIMGL_SCENE_FILE = Path("/content/manimgl_cell.py")
MANIMGL_VIDEO_DIRECTORY = Path("/content/manimgl_videos")
MANIMGL_RUNTIME_DIRECTORY = Path("/tmp/runtime-colab")


def register_manimgl_magic() -> None:
    """Register the fast ``%%manimgl`` cell magic in Colab/IPython."""
    from IPython import get_ipython
    from IPython.display import Video, display

    ipython = get_ipython()
    if ipython is None:
        raise RuntimeError("This function must be run inside Google Colab or IPython.")

    # Remember the most recent successful render in this Colab runtime.
    last_rendered_video: Path | None = None

    def manimgl_magic(line: str, cell: str) -> None:
        """Render a ManimGL scene and automatically display its MP4.

        Examples:
            %%manimgl --draft MyScene
            %%manimgl -v WARNING -ql --display-width 560 MyScene
            %%manimgl -qm --prerun MyScene
            %%manimgl -ql --progress MyScene
        """
        nonlocal last_rendered_video

        total_start = time.perf_counter()
        tokens = shlex.split(line)

        if not tokens:
            raise ValueError(
                "A scene class name is required. Example: "
                "%%manimgl -v WARNING -ql MyScene"
            )

        # Convention: the final argument is the scene class name.
        scene_name = tokens[-1]
        options = tokens[:-1]

        quality = "-l"
        log_level = "WARNING"
        display_width = 560
        draft_mode = False
        use_prerun = False
        show_progress = False
        extra_options: list[str] = []

        index = 0
        while index < len(options):
            option = options[index]

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
                    raise ValueError(
                        "-v must be followed by DEBUG, INFO, WARNING, ERROR, or CRITICAL."
                    )
                log_level = options[index + 1].upper()
                index += 1
            elif option == "--display-width":
                if index + 1 >= len(options):
                    raise ValueError("--display-width must be followed by a pixel width.")
                try:
                    display_width = int(options[index + 1])
                except ValueError as error:
                    raise ValueError("Display width must be an integer, such as 560.") from error
                if display_width < 100:
                    raise ValueError("Display width must be at least 100 pixels.")
                index += 1
            elif option == "--draft":
                draft_mode = True
            elif option == "--prerun":
                use_prerun = True
            elif option == "--progress":
                show_progress = True
            else:
                extra_options.append(option)

            index += 1

        if not MANIMGL_EXECUTABLE.exists():
            raise FileNotFoundError(
                f"ManimGL was not found at {MANIMGL_EXECUTABLE}. "
                "Run setup_all(register_magic=True) first."
            )

        MANIMGL_VIDEO_DIRECTORY.mkdir(parents=True, exist_ok=True)
        MANIMGL_RUNTIME_DIRECTORY.mkdir(parents=True, exist_ok=True)
        MANIMGL_RUNTIME_DIRECTORY.chmod(0o700)
        MANIMGL_SCENE_FILE.write_text(cell, encoding="utf-8")

        expected_video = MANIMGL_VIDEO_DIRECTORY / f"{scene_name}.mp4"
        if expected_video.exists():
            expected_video.unlink()

        environment = os.environ.copy()
        environment["XDG_RUNTIME_DIR"] = str(MANIMGL_RUNTIME_DIRECTORY)
        environment["LIBGL_ALWAYS_SOFTWARE"] = "1"
        environment["PYTHONUNBUFFERED"] = "1"

        # Draft mode intentionally overrides the standard quality preset.
        if draft_mode:
            render_options = ["-r", "640x360", "--fps", "15"]
            quality_description = "draft (640x360, 15 FPS)"
        else:
            render_options = [quality]
            quality_description = quality

        optional_options: list[str] = []
        if use_prerun:
            optional_options.append("--prerun")
        if show_progress:
            optional_options.extend([
                "--show_animation_progress",
                "--leave_progress_bars",
            ])

        command = [
            str(MANIMGL_EXECUTABLE),
            str(MANIMGL_SCENE_FILE),
            scene_name,
            "-w",
            *render_options,
            "-c",
            "#000000",
            "--video_dir",
            str(MANIMGL_VIDEO_DIRECTORY),
            "--log-level",
            log_level,
            *optional_options,
            *extra_options,
        ]

        print("=" * 68)
        print("Fast ManimGL render")
        print("=" * 68)
        print(f"Scene: {scene_name}")
        print(f"Render mode: {quality_description}")
        print(f"Log level: {log_level}")
        print(f"Prerun: {'enabled' if use_prerun else 'disabled'}")
        print(f"Progress: {'enabled' if show_progress else 'disabled'}")
        print(f"Preview width: {display_width}px")
        print("\n[1/3] Starting ManimGL immediately...", flush=True)

        process_start = time.perf_counter()
        result = subprocess.run(command, env=environment, check=False)
        process_seconds = time.perf_counter() - process_start

        if result.returncode != 0:
            raise RuntimeError(
                f"ManimGL rendering failed with exit code {result.returncode}."
            )

        print(f"[2/3] Render process finished in {process_seconds:.2f} seconds.", flush=True)
        print("[3/3] Preparing video preview...", flush=True)
        preview_start = time.perf_counter()

        if not expected_video.exists():
            videos = sorted(
                MANIMGL_VIDEO_DIRECTORY.glob("*.mp4"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            if not videos:
                raise FileNotFoundError("Rendering completed, but no MP4 file was found.")
            expected_video = videos[0]

        last_rendered_video = expected_video
        video_size_mb = expected_video.stat().st_size / (1024 * 1024)
        video_attributes = (
            "controls autoplay muted loop "
            f'width="{display_width}" style="max-width:100%; height:auto;"'
        )

        # Video(embed=True) is the most reliable Colab preview method.
        video = Video(
            str(expected_video),
            embed=True,
            html_attributes=video_attributes,
        )
        preview_prepare_seconds = time.perf_counter() - preview_start
        display(video)

        total_seconds = time.perf_counter() - total_start
        print("\n" + "=" * 68)
        print("Video ready")
        print("=" * 68)
        print(f"Path: {expected_video}")
        print(f"File size: {video_size_mb:.2f} MB")
        print(f"Render process: {process_seconds:.2f} seconds")
        print(f"Preview preparation: {preview_prepare_seconds:.2f} seconds")
        print(f"Total magic time: {total_seconds:.2f} seconds")
        print(f"Download: %manimgl_download {scene_name}")

    def manimgl_download_magic(line: str) -> None:
        """Download the latest render, optionally selected by scene class name."""
        from google.colab import files

        scene_name = line.strip()
        selected_video: Path | None = None

        if scene_name:
            # Match both a normal render (Scene.mp4) and partial renders such
            # as Scene_20_30.mp4. Select the newest matching file.
            candidates = list(
                MANIMGL_VIDEO_DIRECTORY.glob(f"{scene_name}*.mp4")
            )
            candidates.sort(
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            if candidates:
                selected_video = candidates[0]
        elif last_rendered_video is not None and last_rendered_video.exists():
            selected_video = last_rendered_video
        else:
            # If the magic was re-registered, recover the newest video from disk.
            candidates = list(MANIMGL_VIDEO_DIRECTORY.glob("*.mp4"))
            candidates.sort(
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            if candidates:
                selected_video = candidates[0]

        if selected_video is None or not selected_video.exists():
            if scene_name:
                raise FileNotFoundError(
                    f"No rendered MP4 was found for scene '{scene_name}'."
                )
            raise FileNotFoundError(
                "No rendered MP4 was found. Render a scene first."
            )

        size_mb = selected_video.stat().st_size / (1024 * 1024)
        print(f"Downloading: {selected_video.name} ({size_mb:.2f} MB)")
        files.download(str(selected_video))

    ipython.register_magic_function(
        manimgl_magic,
        magic_kind="cell",
        magic_name="manimgl",
    )
    ipython.register_magic_function(
        manimgl_download_magic,
        magic_kind="line",
        magic_name="manimgl_download",
    )

    print("Fast %%manimgl registered successfully.")
    print("Draft:    %%manimgl --draft SceneName")
    print("Standard: %%manimgl -ql --display-width 560 SceneName")
    print("Optional: add --prerun and/or --progress when needed")
    print("Download latest: %manimgl_download")
    print("Download scene:  %manimgl_download SceneName")


if __name__ == "__main__":
    register_manimgl_magic()
