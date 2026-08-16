"""Google Colab cell magic for headless ManimGL rendering with live output."""

from __future__ import annotations

import os
import pty
import select
import shlex
import subprocess
import sys
from pathlib import Path


MANIMGL_EXECUTABLE = Path("/content/manimgl-env/bin/manimgl")
MANIMGL_SCENE_FILE = Path("/content/manimgl_cell.py")
MANIMGL_VIDEO_DIRECTORY = Path("/content/manimgl_videos")
MANIMGL_RUNTIME_DIRECTORY = Path("/tmp/runtime-colab")


def run_with_live_terminal(command: list[str], environment: dict[str, str]) -> int:
    """Run ManimGL in a pseudo-terminal and stream its output into Colab."""
    master_fd, slave_fd = pty.openpty()

    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=slave_fd,
        stderr=slave_fd,
        env=environment,
        close_fds=True,
    )
    os.close(slave_fd)

    try:
        while True:
            readable, _, _ = select.select([master_fd], [], [], 0.1)

            if readable:
                try:
                    output = os.read(master_fd, 8192)
                except OSError:
                    break

                if not output:
                    break

                sys.stdout.write(output.decode("utf-8", errors="replace"))
                sys.stdout.flush()

            if process.poll() is not None:
                # Drain any output left after the process exits.
                while True:
                    readable, _, _ = select.select([master_fd], [], [], 0)
                    if not readable:
                        break

                    try:
                        output = os.read(master_fd, 8192)
                    except OSError:
                        break

                    if not output:
                        break

                    sys.stdout.write(output.decode("utf-8", errors="replace"))
                    sys.stdout.flush()
                break
    finally:
        try:
            os.close(master_fd)
        except OSError:
            pass

    return process.wait()


def register_manimgl_magic() -> None:
    """Register ``%%manimgl`` in the active Google Colab notebook."""
    from IPython import get_ipython
    from IPython.display import Video, display

    ipython = get_ipython()
    if ipython is None:
        raise RuntimeError("This function must be run inside Google Colab or IPython.")

    def manimgl_magic(line: str, cell: str) -> None:
        """Render a ManimGL scene and automatically display its MP4."""
        tokens = shlex.split(line)

        if not tokens:
            raise ValueError(
                "Scene name পাওয়া যায়নি।\n"
                "Example: %%manimgl -v INFO -ql MyScene"
            )

        # The final argument is the scene class name.
        scene_name = tokens[-1]
        options = tokens[:-1]

        quality = "-l"
        log_level = "INFO"
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
                    raise ValueError(
                        "-v এর পরে log level দিতে হবে।\n"
                        "Example: -v INFO"
                    )
                log_level = options[index + 1].upper()
                index += 1
            elif option == "--display-width":
                if index + 1 >= len(options):
                    raise ValueError(
                        "--display-width এর পরে pixel width দিতে হবে।"
                    )
                try:
                    display_width = int(options[index + 1])
                except ValueError as error:
                    raise ValueError(
                        "Display width অবশ্যই integer হতে হবে, যেমন 560।"
                    ) from error
                if display_width < 100:
                    raise ValueError("Display width কমপক্ষে 100 pixels হতে হবে।")
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
        environment["TERM"] = "xterm-256color"

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
            "--show_animation_progress",
            "--leave_progress_bars",
            "--prerun",
            *extra_options,
        ]

        print("=" * 65)
        print("ManimGL rendering শুরু হচ্ছে")
        print("=" * 65)
        print(f"Scene: {scene_name}")
        print(f"Quality: {quality}")
        print(f"Log level: {log_level}")
        print(f"Preview width: {display_width}px")
        print("\nপ্রথমে ManimGL মোট frame গণনা করবে।")
        print("তারপর actual rendering progress দেখাবে।")
        print("=" * 65, flush=True)

        return_code = run_with_live_terminal(command, environment)
        if return_code != 0:
            raise RuntimeError(
                f"ManimGL rendering failed. Exit code: {return_code}"
            )

        if not expected_video.exists():
            videos = sorted(
                MANIMGL_VIDEO_DIRECTORY.glob("*.mp4"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            if not videos:
                raise FileNotFoundError(
                    "Rendering শেষ হয়েছে, কিন্তু MP4 পাওয়া যায়নি।"
                )
            expected_video = videos[0]

        video_size_mb = expected_video.stat().st_size / (1024 * 1024)
        print("\n" + "=" * 65)
        print("Rendering completed successfully")
        print("=" * 65)
        print(f"Video: {expected_video}")
        print(f"File size: {video_size_mb:.2f} MB")

        video_attributes = (
            "controls autoplay muted loop "
            f'style="width:{display_width}px; max-width:100%; height:auto;"'
        )
        display(
            Video(
                str(expected_video),
                embed=True,
                html_attributes=video_attributes,
            )
        )

    ipython.register_magic_function(
        manimgl_magic,
        magic_kind="cell",
        magic_name="manimgl",
    )

    print("Live-progress %%manimgl command registered successfully.")
    print("Example: %%manimgl -v INFO -ql --display-width 560 SceneName")


if __name__ == "__main__":
    register_manimgl_magic()
