# ManimGL Setup for Google Colab

A safe, repeatable ManimGL v1.7.x setup for a fresh Google Colab runtime.

## Features

- Installs ManimGL in `/content/manimgl-env`, isolated from Colab's Python.
- Avoids the Colab IPython dependency crash.
- Uses headless CPU/software rendering; no desktop window is required.
- Installs FFmpeg, Computer Modern, Noto Serif, and Noto Serif Bengali.
- Does **not** install LaTeX.
- Adds a `%%manimgl` cell magic with ManimCE-style quality flags.
- Automatically displays the rendered video at a configurable preview width.

## Use in a new Colab notebook

Start with a CPU runtime. Run these cells in order and do not restart after setup.

### Cell 1 — Clone this repository

```bash
!rm -rf /content/manim-setup
!git clone --depth 1 \
    https://github.com/myabdur2121-cpu/manim-setup.git \
    /content/manim-setup
```

### Cell 2 — Install and register `%%manimgl`

```python
%run /content/manim-setup/manimgl/colab_setup.py
setup_all(register_magic=True)
```

### Cell 3 — Render

```python
%%manimgl -v WARNING -ql --display-width 560 RotatingSphere
from manimlib import *


class RotatingSphere(ThreeDScene):
    def construct(self):
        self.frame.reorient(25, 70)

        sphere = Sphere(radius=2.2, resolution=(25, 25))
        sphere.set_color(BLUE_D)
        sphere.set_opacity(0.95)
        sphere.set_shading(0.35, 0.55, 0.25)

        mesh = SurfaceMesh(sphere, resolution=(25, 25))
        mesh.set_stroke(BLUE_A, width=0.8, opacity=0.55)
        sphere.add(mesh)

        self.play(FadeIn(sphere), run_time=1)
        self.play(
            Rotate(sphere, angle=TAU, axis=UP + 0.25 * RIGHT),
            run_time=5,
            rate_func=linear,
        )
        self.wait(1)
```

The MP4 is saved under `/content/manimgl_videos/` and displayed automatically.

## Fast rendering modes

The default command starts rendering without prerun or progress overhead:

```python
%%manimgl -v WARNING -ql --display-width 560 MyScene
```

For the fastest layout and timing check, use draft mode (640×360 at 15 FPS):

```python
%%manimgl --draft MyScene
```

Optional validation and progress flags:

```python
%%manimgl -ql --prerun MyScene
%%manimgl -ql --progress MyScene
%%manimgl -ql --prerun --progress MyScene
```

Progress output is terminal-dependent and may not render correctly in Google Colab. It is disabled by default.

## Enhanced error reports

The default compact mode highlights the most relevant line in your scene and ends with the exception name and message:

```python
%%manimgl --draft MyScene
```

For a complete ManimGL backend traceback, add `--ERROR` (case-insensitive):

```python
%%manimgl --draft --ERROR MyScene
```

The following are equivalent:

```text
--error
--ERROR
--Error
```

Full mode shows user and backend frames, source context, highlighted lines, exception chains, and expandable raw ManimGL/LaTeX/FFmpeg output.

## Quality flags

| Colab command | ManimGL output |
|---|---|
| `--draft` | Fast preview, 640×360 at 15 FPS |
| `-ql` | Low quality, 480p |
| `-qm` | Medium quality, 720p |
| `-qh` | High quality, 1080p |
| `-qk` | 4K |
| `-r 960x540` | Custom resolution |

Example:

```python
%%manimgl -v INFO -qm --display-width 560 MyScene
```

`--display-width` changes only the notebook preview size. It preserves the aspect ratio and does not alter the MP4 resolution.

## File viewer and editor shortcuts

Open any runtime text file in Colab's editable panel and show a colorful, line-numbered preview:

```python
%openfile /content/manimGL/manimlib/scene/scene.py
```

Open with a target line:

```python
%openfile /content/manimGL/manimlib/scene/scene.py:114
```

A copied Python traceback header is accepted directly:

```python
%openfile File "/content/manimGL/manimlib/scene/scene.py", line 114, in run
```

Paths containing spaces can be quoted:

```python
%openfile "/content/drive/My Drive/project/file.py" 20
```

Change the number of surrounding preview lines:

```python
%openfile --context 20 /content/manimGL/manimlib/scene/scene.py:114
```

A timestamped backup is created automatically before the editable panel opens. List and restore backups with:

```python
%filebackups /content/manimGL/manimlib/scene/scene.py
%restorefile /content/manimGL/manimlib/scene/scene.py
```

The newest backup is restored, while the current version is backed up first.

## Download shortcuts

Download the most recently rendered video without remembering its filename:

```python
%manimgl_download
```

Download the newest video belonging to a specific scene class:

```python
%manimgl_download MyScene
```

This also finds partial-render filenames such as `MyScene_20_30.mp4`, so only the class name is required.

## Fonts without LaTeX

```python
Text("Computer Modern", font="CMU Serif")
Text("Noto Serif", font="Noto Serif")
Text("বাংলা ভাষা", font="Noto Serif Bengali")
```

Use `Text`, not `Tex` or `MathTex`, until LaTeX is installed separately.

## Functions available for manual setup

```python
install_system_dependencies()
create_virtual_environment()
install_pip()
download_manimgl()
install_manimgl()
prepare_directories()
verify_installation()
register_magic()
```

Normal complete setup:

```python
setup_all(register_magic=True)
```

Clean reinstall:

```python
setup_all(register_magic=True, force=True)
```

## Colab persistence

A completely new or deleted Colab runtime loses `/content` and system packages. Run Cell 1 and Cell 2 again for every new runtime. Videos you want to keep should be downloaded or copied to Google Drive.
