"""Fast Google Colab cell magic for ManimGL with enhanced error reports."""

from __future__ import annotations

import html
import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any


MANIMGL_PYTHON = Path("/content/manimgl-env/bin/python")
MANIMGL_EXECUTABLE = Path("/content/manimgl-env/bin/manimgl")
MANIMGL_SCENE_FILE = Path("/content/manimgl_cell.py")
MANIMGL_VIDEO_DIRECTORY = Path("/content/manimgl_videos")
MANIMGL_RUNTIME_DIRECTORY = Path("/tmp/runtime-colab")
MANIMGL_ERROR_REPORT = Path("/content/manimgl_error_report.json")
THIS_DIRECTORY = Path(__file__).resolve().parent
MANIMGL_ERROR_RUNNER = THIS_DIRECTORY / "error_runner.py"

ANSI_PATTERN = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
TRACEBACK_FRAME_PATTERN = re.compile(
    r'^\s*File "(?P<filename>.+?)", line (?P<line>\d+), in (?P<function>.+?)\s*$',
    re.MULTILINE,
)
EXCEPTION_LINE_PATTERN = re.compile(
    r"^(?P<type>[A-Za-z_][\w.]*(?:Error|Exception|Interrupt|Exit)):\s*(?P<message>.*)$",
    re.MULTILINE,
)


class ManimGLRenderError(RuntimeError):
    """A short notebook-facing exception; the detailed report is shown in HTML."""

    def _render_traceback_(self) -> list[str]:
        return [str(self)]


def _strip_ansi(text: str) -> str:
    return ANSI_PATTERN.sub("", text).replace("\r", "\n")


def _run_and_capture(
    command: list[str],
    environment: dict[str, str],
    *,
    stream_output: bool,
) -> tuple[int, str]:
    """Run a child process, preserve all output, and optionally stream it live."""
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=environment,
    )

    output_parts: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        output_parts.append(line)
        if stream_output:
            print(line, end="", flush=True)

    return process.wait(), "".join(output_parts)


def _fallback_report(raw_output: str) -> dict[str, Any]:
    """Build a minimal report when no structured Python exception is available."""
    clean_output = _strip_ansi(raw_output)
    exception_matches = list(EXCEPTION_LINE_PATTERN.finditer(clean_output))
    frame_matches = list(TRACEBACK_FRAME_PATTERN.finditer(clean_output))

    if exception_matches:
        final_match = exception_matches[-1]
        exception_type = final_match.group("type").split(".")[-1]
        message = final_match.group("message")
    else:
        exception_type = "ManimGLRenderError"
        message = "The renderer exited without a structured Python exception."

    frames = [
        {
            "filename": match.group("filename"),
            "lineno": int(match.group("line")),
            "function": match.group("function"),
            "line": "",
            "colno": None,
            "end_colno": None,
            "end_lineno": None,
        }
        for match in frame_matches
    ]

    return {
        "version": 0,
        "exception": {
            "type": exception_type,
            "qualified_type": exception_type,
            "message": message,
            "frames": frames,
            "syntax_frame": None,
            "relation": None,
            "cause": None,
        },
    }


def _load_error_report(raw_output: str) -> dict[str, Any]:
    if MANIMGL_ERROR_REPORT.exists():
        try:
            return json.loads(MANIMGL_ERROR_REPORT.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return _fallback_report(raw_output)


def _exception_chain(exception: dict[str, Any]) -> list[dict[str, Any]]:
    """Return exceptions root-cause first and final exception last."""
    chain: list[dict[str, Any]] = []
    cause = exception.get("cause")
    if isinstance(cause, dict):
        chain.extend(_exception_chain(cause))
    chain.append(exception)
    return chain


def _is_user_frame(frame: dict[str, Any]) -> bool:
    filename = str(frame.get("filename", ""))
    try:
        return Path(filename).resolve() == MANIMGL_SCENE_FILE.resolve()
    except OSError:
        return filename.endswith("manimgl_cell.py")


def _read_source_lines(frame: dict[str, Any]) -> list[str]:
    filename = str(frame.get("filename", ""))
    try:
        return Path(filename).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        line = str(frame.get("line", ""))
        return [line] if line else []


def _highlight_code(code: str, frame: dict[str, Any], is_error_line: bool) -> str:
    if not is_error_line:
        return html.escape(code)

    colno = frame.get("colno")
    end_colno = frame.get("end_colno")
    if not isinstance(colno, int) or not isinstance(end_colno, int):
        return html.escape(code)
    if colno < 0 or end_colno <= colno or colno >= len(code):
        return html.escape(code)

    end_colno = min(end_colno, len(code))
    return (
        html.escape(code[:colno])
        + '<span style="text-decoration:underline 3px #ff5f56; font-weight:700;">'
        + html.escape(code[colno:end_colno])
        + "</span>"
        + html.escape(code[end_colno:])
    )


def _source_context_html(frame: dict[str, Any], *, extra_lines: int = 3) -> str:
    lineno = int(frame.get("lineno") or 1)
    source_lines = _read_source_lines(frame)

    if source_lines:
        start = max(1, lineno - extra_lines)
        end = min(len(source_lines), lineno + extra_lines)
    else:
        start = lineno
        end = lineno

    rows: list[str] = []
    for number in range(start, end + 1):
        if source_lines and 1 <= number <= len(source_lines):
            code = source_lines[number - 1]
        else:
            code = str(frame.get("line", "")) if number == lineno else ""

        is_error = number == lineno
        marker = "❱" if is_error else " "
        background = "#584b16" if is_error else "transparent"
        border = "3px solid #ffd43b" if is_error else "3px solid transparent"
        code_html = _highlight_code(code, frame, is_error)

        rows.append(
            f'<div style="display:flex; background:{background}; border-left:{border};">'
            f'<span style="width:2em; color:#ffd43b; user-select:none;">{marker}</span>'
            f'<span style="width:3.5em; color:#8b949e; text-align:right; padding-right:1em; '
            f'user-select:none;">{number}</span>'
            f'<span style="white-space:pre; color:#f0f3f6;">{code_html or " "}</span>'
            "</div>"
        )

    return (
        '<div style="background:#0d1117; padding:10px 8px; overflow-x:auto; '
        'font:13px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;">'
        + "".join(rows)
        + "</div>"
    )


def _frame_panel_html(
    frame: dict[str, Any],
    *,
    title: str | None = None,
    full_mode: bool = False,
) -> str:
    filename = str(frame.get("filename", "unknown file"))
    lineno = int(frame.get("lineno") or 0)
    function = str(frame.get("function", "<unknown>"))
    user_frame = _is_user_frame(frame)

    if title is None:
        title = "Your scene" if user_frame else "ManimGL backend"

    border_color = "#ffd43b" if user_frame else "#586069"
    title_color = "#ffd43b" if user_frame else "#79c0ff"
    context = _source_context_html(frame, extra_lines=3 if user_frame else 2)

    return f"""
    <div style="border:1px solid {border_color}; border-radius:8px; margin:10px 0;
                overflow:hidden; background:#161b22;">
      <div style="padding:9px 12px; border-bottom:1px solid {border_color};">
        <strong style="color:{title_color};">{html.escape(title)}</strong><br>
        <span style="color:#c9d1d9; font-family:monospace;">
          {html.escape(filename)}:{lineno} in {html.escape(function)}
        </span>
      </div>
      {context}
    </div>
    """


def _select_compact_frame(exception: dict[str, Any]) -> dict[str, Any] | None:
    syntax_frame = exception.get("syntax_frame")
    if isinstance(syntax_frame, dict):
        return syntax_frame

    frames = [frame for frame in exception.get("frames", []) if isinstance(frame, dict)]
    user_frames = [frame for frame in frames if _is_user_frame(frame)]
    if user_frames:
        return user_frames[-1]
    return frames[-1] if frames else None


def _display_error_report(
    report: dict[str, Any],
    raw_output: str,
    *,
    full_mode: bool,
    scene_name: str,
) -> tuple[str, str]:
    from IPython.display import HTML, display

    final_exception = report.get("exception") or {}
    chain = _exception_chain(final_exception)
    exception_type = str(final_exception.get("type") or "ManimGLRenderError")
    message = str(final_exception.get("message") or "Unknown rendering failure")
    clean_raw = _strip_ansi(raw_output).strip()

    sections: list[str] = []
    mode_label = "FULL BACKEND TRACEBACK" if full_mode else "COMPACT ERROR"
    sections.append(
        f"""
        <div style="border:2px solid #f85149; border-radius:10px; overflow:hidden;
                    margin:12px 0; background:#0d1117; color:#f0f3f6;">
          <div style="background:#5a1d1d; padding:12px 14px;">
            <strong style="font-size:17px;">{html.escape(exception_type)} in {html.escape(scene_name)}</strong>
            <span style="float:right; color:#ffb3ad; font-size:12px;">{mode_label}</span>
          </div>
          <div style="padding:12px 14px; color:#ffb3ad; font-family:monospace;">
            {html.escape(message)}
          </div>
        </div>
        """
    )

    if full_mode:
        frame_number = 0
        for chain_index, exception in enumerate(chain, start=1):
            if len(chain) > 1:
                sections.append(
                    f'<div style="color:#d2a8ff; margin-top:14px; font-weight:700;">'
                    f'Exception chain {chain_index}: {html.escape(str(exception.get("type", "Exception")))}'
                    "</div>"
                )

            syntax_frame = exception.get("syntax_frame")
            frames = [frame for frame in exception.get("frames", []) if isinstance(frame, dict)]
            if isinstance(syntax_frame, dict):
                frames.append(syntax_frame)

            for frame in frames[-80:]:
                filename = str(frame.get("filename", ""))
                if filename.endswith("/error_runner.py"):
                    continue
                frame_number += 1
                sections.append(
                    _frame_panel_html(
                        frame,
                        title=f"Frame {frame_number} — "
                        + ("Your scene" if _is_user_frame(frame) else "ManimGL backend"),
                        full_mode=True,
                    )
                )
    else:
        compact_frame = _select_compact_frame(final_exception)
        if compact_frame is not None:
            sections.append(
                _frame_panel_html(compact_frame, title="Error in your scene")
            )
        else:
            sections.append(
                '<div style="padding:12px; color:#ffa198; background:#161b22; '
                'border:1px solid #f85149; border-radius:8px;">'
                "No Python source frame was available. Open raw output below."
                "</div>"
            )

    if clean_raw:
        raw_title = "Complete raw ManimGL / LaTeX / FFmpeg output"
        sections.append(
            f"""
            <details style="margin:14px 0; background:#161b22; border:1px solid #30363d;
                            border-radius:8px; padding:10px 12px;">
              <summary style="cursor:pointer; color:#79c0ff; font-weight:700;">
                {raw_title}
              </summary>
              <pre style="white-space:pre-wrap; overflow-x:auto; color:#c9d1d9;
                          font-size:12px; line-height:1.45;">{html.escape(clean_raw)}</pre>
            </details>
            """
        )

    # ManimCE-style final exception name and message at the bottom.
    sections.append(
        f"""
        <div style="margin-top:14px; padding:12px 14px; border-left:5px solid #f85149;
                    background:#2d1214; color:#ffb3ad; font:700 14px/1.5 monospace;">
          {html.escape(exception_type)}: {html.escape(message)}
        </div>
        """
    )

    display(HTML("".join(sections)))
    return exception_type, message


def register_manimgl_magic() -> None:
    """Register ``%%manimgl`` and ``%manimgl_download`` in Colab/IPython."""
    from IPython import get_ipython
    from IPython.display import Video, display

    ipython = get_ipython()
    if ipython is None:
        raise RuntimeError("This function must be run inside Google Colab or IPython.")

    last_rendered_video: Path | None = None

    def manimgl_magic(line: str, cell: str) -> None:
        """Render a ManimGL scene and automatically display its MP4."""
        nonlocal last_rendered_video

        total_start = time.perf_counter()
        tokens = shlex.split(line)
        if not tokens:
            raise ValueError(
                "A scene class name is required. Example: "
                "%%manimgl -v WARNING -ql MyScene"
            )

        scene_name = tokens[-1]
        options = tokens[:-1]
        quality = "-l"
        log_level = "WARNING"
        display_width = 560
        draft_mode = False
        use_prerun = False
        show_progress = False
        full_error = False
        extra_options: list[str] = []

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
                    raise ValueError("--display-width must be followed by a pixel width.")
                try:
                    display_width = int(options[index + 1])
                except ValueError as error:
                    raise ValueError("Display width must be an integer, such as 560.") from error
                if display_width < 100:
                    raise ValueError("Display width must be at least 100 pixels.")
                index += 1
            elif normalized == "--draft":
                draft_mode = True
            elif normalized == "--prerun":
                use_prerun = True
            elif normalized == "--progress":
                show_progress = True
            elif normalized in ("--error", "--full-error"):
                full_error = True
            else:
                extra_options.append(option)
            index += 1

        if not MANIMGL_EXECUTABLE.exists() or not MANIMGL_PYTHON.exists():
            raise FileNotFoundError(
                "ManimGL was not found. Run setup_all(register_magic=True) first."
            )
        if not MANIMGL_ERROR_RUNNER.exists():
            raise FileNotFoundError(f"Error runner was not found: {MANIMGL_ERROR_RUNNER}")

        MANIMGL_VIDEO_DIRECTORY.mkdir(parents=True, exist_ok=True)
        MANIMGL_RUNTIME_DIRECTORY.mkdir(parents=True, exist_ok=True)
        MANIMGL_RUNTIME_DIRECTORY.chmod(0o700)
        MANIMGL_SCENE_FILE.write_text(cell, encoding="utf-8")

        expected_video = MANIMGL_VIDEO_DIRECTORY / f"{scene_name}.mp4"
        if expected_video.exists():
            expected_video.unlink()
        if MANIMGL_ERROR_REPORT.exists():
            MANIMGL_ERROR_REPORT.unlink()

        environment = os.environ.copy()
        environment["XDG_RUNTIME_DIR"] = str(MANIMGL_RUNTIME_DIRECTORY)
        environment["LIBGL_ALWAYS_SOFTWARE"] = "1"
        environment["PYTHONUNBUFFERED"] = "1"
        environment["MANIMGL_ERROR_REPORT"] = str(MANIMGL_ERROR_REPORT)

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
            optional_options.extend(["--show_animation_progress", "--leave_progress_bars"])

        command = [
            str(MANIMGL_PYTHON),
            str(MANIMGL_ERROR_RUNNER),
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
        print(f"Prerun: {'enabled' if use_prerun else 'disabled'}")
        print(f"Progress: {'enabled' if show_progress else 'disabled'}")
        print(f"Error mode: {'FULL' if full_error else 'compact'}")
        print("\n[1/3] Starting ManimGL immediately...", flush=True)

        process_start = time.perf_counter()
        stream_output = show_progress or log_level in ("INFO", "DEBUG")
        return_code, raw_output = _run_and_capture(
            command,
            environment,
            stream_output=stream_output,
        )
        process_seconds = time.perf_counter() - process_start

        if return_code != 0:
            print(f"\nRender failed after {process_seconds:.2f} seconds.", flush=True)
            report = _load_error_report(raw_output)
            exception_type, message = _display_error_report(
                report,
                raw_output,
                full_mode=full_error,
                scene_name=scene_name,
            )
            raise ManimGLRenderError(f"{exception_type}: {message}") from None

        # Preserve important warnings even when quiet output is selected.
        if not stream_output:
            clean_output = _strip_ansi(raw_output)
            important_lines = [
                line for line in clean_output.splitlines()
                if "WARNING" in line.upper() or "ERROR" in line.upper()
            ]
            if important_lines:
                print("\n".join(important_lines), flush=True)

        print(f"[2/3] Render process finished in {process_seconds:.2f} seconds.")
        print("[3/3] Preparing video preview...", flush=True)
        preview_start = time.perf_counter()

        if not expected_video.exists():
            videos = sorted(
                MANIMGL_VIDEO_DIRECTORY.glob(f"{scene_name}*.mp4"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            if not videos:
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
        video = Video(str(expected_video), embed=True, html_attributes=video_attributes)
        preview_seconds = time.perf_counter() - preview_start
        display(video)

        total_seconds = time.perf_counter() - total_start
        print("\n" + "=" * 68)
        print("Video ready")
        print("=" * 68)
        print(f"Path: {expected_video}")
        print(f"File size: {video_size_mb:.2f} MB")
        print(f"Render process: {process_seconds:.2f} seconds")
        print(f"Preview preparation: {preview_seconds:.2f} seconds")
        print(f"Total magic time: {total_seconds:.2f} seconds")
        print(f"Download: %manimgl_download {scene_name}")

    def manimgl_download_magic(line: str) -> None:
        """Download the latest render, optionally selected by scene class name."""
        from google.colab import files

        requested_scene = line.strip()
        selected_video: Path | None = None

        if requested_scene:
            candidates = sorted(
                MANIMGL_VIDEO_DIRECTORY.glob(f"{requested_scene}*.mp4"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            if candidates:
                selected_video = candidates[0]
        elif last_rendered_video is not None and last_rendered_video.exists():
            selected_video = last_rendered_video
        else:
            candidates = sorted(
                MANIMGL_VIDEO_DIRECTORY.glob("*.mp4"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            if candidates:
                selected_video = candidates[0]

        if selected_video is None or not selected_video.exists():
            raise FileNotFoundError(
                f"No rendered MP4 was found for '{requested_scene}'."
                if requested_scene else "No rendered MP4 was found. Render a scene first."
            )

        size_mb = selected_video.stat().st_size / (1024 * 1024)
        print(f"Downloading: {selected_video.name} ({size_mb:.2f} MB)")
        files.download(str(selected_video))

    ipython.register_magic_function(manimgl_magic, magic_kind="cell", magic_name="manimgl")
    ipython.register_magic_function(
        manimgl_download_magic,
        magic_kind="line",
        magic_name="manimgl_download",
    )

    print("Enhanced %%manimgl registered successfully.")
    print("Compact error: %%manimgl --draft SceneName")
    print("Full traceback: %%manimgl --draft --ERROR SceneName")
    print("Download latest: %manimgl_download")
    print("Download scene:  %manimgl_download SceneName")


if __name__ == "__main__":
    register_manimgl_magic()
