"""Google Colab cell magic for headless ManimGL rendering."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path


MANIMGL_EXECUTABLE = Path("/content/manimgl-env/bin/manimgl")
MANIMGL_SCENE_FILE = Path("/content/manimgl_cell.py")
MANIMGL_VIDEO_DIRECTORY = Path("/content/manimgl_videos")
MANIMGL_RUNTIME_DIRECTORY = Path("/tmp/runtime-colab")


def register_manimgl_magic() -> None:
    """Register ``%%manimgl`` in the active IPython/Colab notebook."""
    from IPython import get_ipython
    from IPython.display import Video, display

    ipython = get_ipython()
    if ipython is None:
        raise RuntimeError("This function must be run inside Google Colab or IPython.")

    def manimgl_magic(line: str, cell: str) -> None:
        """Render a ManimGL scene and display the resulting MP4."""
        tokens = shlex.split(line)
        if not tokens:
            raise ValueError(
                "A scene class name is required. Example: "
                "%%manimgl -v WARNING -ql MyScene"
            )

        # Convention: the scene class name is the final argument.
        scene_name = tokens[-1]
        options = tokens[:-1]

        quality = "-l"
        log_level = "WARNING"
        display_width = 560
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
                    raise ValueError("-v must be followed by DEBUG, INFO, WARNING, ERROR, or CRITICAL.")
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

        command = [
            str(MANIMGL_EXECUTABLE),
            str(MANIMGL_SCENE_FILE),
            scene_name,
            "-w",
            quality,
            "-c",
            "#000000",
            "--video_dir",
            str(MANIMGL_VIDEO_DIRECTORY),
            "--log-level",
            log_level,
            *extra_options,
        ]

        print("=" * 65)
        print("ManimGL rendering started")
        print("=" * 65)
        print(f"Scene: {scene_name}")
        print(f"Quality: {quality}")
        print(f"Log level: {log_level}")
        print(f"Preview width: {display_width}px")
        print("\nCommand:")
        print(" ".join(shlex.quote(part) for part in command))
        print("=" * 65, flush=True)

        result = subprocess.run(command, env=environment, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"ManimGL rendering failed with exit code {result.returncode}.")

        if not expected_video.exists():
            videos = sorted(
                MANIMGL_VIDEO_DIRECTORY.glob("*.mp4"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            if not videos:
                raise FileNotFoundError("Rendering completed, but no MP4 file was found.")
            expected_video = videos[0]

        video_size_mb = expected_video.stat().st_size / (1024 * 1024)
        print("\n" + "=" * 65)
        print("Rendering completed successfully")
        print("=" * 65)
        print(f"Video: {expected_video}")
        print(f"File size: {video_size_mb:.2f} MB")

        attributes = (
            "controls autoplay muted loop "
            f'width="{display_width}" style="max-width:100%; height:auto;"'
        )
        display(Video(str(expected_video), embed=True, html_attributes=attributes))

    ipython.register_magic_function(
        manimgl_magic,
        magic_kind="cell",
        magic_name="manimgl",
    )
    print("%%manimgl registered successfully.")
    print("Example: %%manimgl -v WARNING -ql --display-width 560 SceneName")


if __name__ == "__main__":
    register_manimgl_magic()
