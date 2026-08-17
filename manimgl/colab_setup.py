"""Safe ManimGL installer for a fresh Google Colab runtime.

Typical Colab usage::

    %run /content/manim-setup/manimgl/colab_setup.py
    setup_all(register_magic=True)

ManimGL is installed into /content/manimgl-env so its newer IPython dependency
never replaces Google Colab's own IPython packages.
"""

from __future__ import annotations

import runpy
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path


ENV_DIR = Path("/content/manimgl-env")
SOURCE_DIR = Path("/content/manimGL")
GET_PIP_FILE = Path("/content/get-pip.py")
VIDEO_DIR = Path("/content/manimgl_videos")
RUNTIME_DIR = Path("/tmp/runtime-colab")
THIS_DIR = Path(__file__).resolve().parent

ENV_PYTHON = ENV_DIR / "bin/python"
ENV_PIP = ENV_DIR / "bin/pip"
MANIMGL_EXECUTABLE = ENV_DIR / "bin/manimgl"

SYSTEM_PACKAGES = [
    "git",
    "curl",
    "ffmpeg",
    "build-essential",
    "python3-dev",
    "pkg-config",
    "libcairo2-dev",
    "libpango1.0-dev",
    "libgl1",
    "libegl1",
    "libgl1-mesa-dri",
    "mesa-vulkan-drivers",
    "fonts-cmu",
    "fonts-noto-core",
]


def _run(command: list[str], *, quiet: bool = False) -> None:
    """Run a command and stop immediately if it fails."""
    if not quiet:
        print("\n$ " + " ".join(command), flush=True)
    subprocess.run(command, check=True)


def install_system_dependencies() -> None:
    """Install FFmpeg, graphics libraries, build tools, and fonts."""
    print("\n[1/7] Installing system dependencies...", flush=True)
    _run(["apt-get", "update", "-qq"])
    _run([
        "apt-get",
        "install",
        "-y",
        *SYSTEM_PACKAGES,
    ])


def install_latex() -> None:
    """Optionally install TeX Live and dvisvgm for Tex/TexText objects."""
    print("\nInstalling optional LaTeX dependencies...", flush=True)

    packages = [
        "texlive-latex-base",
        "texlive-latex-recommended",
        "texlive-latex-extra",
        "texlive-fonts-recommended",
        "texlive-fonts-extra",
        "texlive-science",
        "dvisvgm",
        "cm-super",
    ]

    _run(["apt-get", "update", "-qq"])
    _run([
        "apt-get",
        "install",
        "-y",
        *packages,
    ])

    # ManimGL's default TeX template may require tipa.sty.
    tipa_available = subprocess.run(
        ["apt-cache", "show", "tipa"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0

    if tipa_available:
        _run(["apt-get", "install", "-y", "tipa"])
    else:
        print(
            "The separate tipa package is unavailable. "
            "The TeX installation may already provide tipa.sty."
        )

    _run(["mktexlsr"])
    _run(["latex", "--version"])
    _run(["dvisvgm", "--version"])
    print("LaTeX installation completed successfully.", flush=True)


def create_virtual_environment(*, force: bool = False) -> None:
    """Create an isolated environment without invoking broken ensurepip."""
    print("\n[2/7] Creating the isolated Python environment...", flush=True)

    if force and ENV_DIR.exists():
        shutil.rmtree(ENV_DIR)

    if ENV_PYTHON.exists():
        print(f"Environment already exists: {ENV_DIR}")
        return

    if ENV_DIR.exists():
        shutil.rmtree(ENV_DIR)

    _run([
        sys.executable,
        "-m",
        "venv",
        "--without-pip",
        str(ENV_DIR),
    ])


def install_pip() -> None:
    """Install pip manually inside the isolated environment."""
    print("\n[3/7] Installing pip inside the isolated environment...", flush=True)

    if ENV_PIP.exists():
        print(f"pip already exists: {ENV_PIP}")
        return

    if not ENV_PYTHON.exists():
        raise FileNotFoundError("The virtual environment does not exist.")

    urllib.request.urlretrieve(
        "https://bootstrap.pypa.io/get-pip.py",
        GET_PIP_FILE,
    )
    _run([str(ENV_PYTHON), str(GET_PIP_FILE)])


def download_manimgl(*, force: bool = False) -> None:
    """Clone the official 3Blue1Brown ManimGL repository."""
    print("\n[4/7] Downloading ManimGL...", flush=True)

    if force and SOURCE_DIR.exists():
        shutil.rmtree(SOURCE_DIR)

    if (SOURCE_DIR / ".git").exists():
        print(f"ManimGL source already exists: {SOURCE_DIR}")
        return

    if SOURCE_DIR.exists():
        shutil.rmtree(SOURCE_DIR)

    _run([
        "git",
        "clone",
        "--depth",
        "1",
        "https://github.com/3b1b/manim.git",
        str(SOURCE_DIR),
    ])


def install_manimgl(*, force: bool = False) -> None:
    """Install ManimGL only inside the isolated environment."""
    print("\n[5/7] Installing ManimGL...", flush=True)

    if MANIMGL_EXECUTABLE.exists() and not force:
        print(f"ManimGL is already installed: {MANIMGL_EXECUTABLE}")
        return

    if not ENV_PYTHON.exists():
        raise FileNotFoundError("The isolated Python environment does not exist.")
    if not SOURCE_DIR.exists():
        raise FileNotFoundError("The ManimGL source directory does not exist.")

    _run([
        str(ENV_PYTHON),
        "-m",
        "pip",
        "install",
        "-e",
        str(SOURCE_DIR),
    ])


def prepare_directories() -> None:
    """Create persistent-for-session render and runtime directories."""
    print("\n[6/7] Preparing rendering directories...", flush=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.chmod(0o700)
    print(f"Video directory: {VIDEO_DIR}")


def verify_installation() -> None:
    """Verify ManimGL, manimlib, and FFmpeg."""
    print("\n[7/7] Verifying the installation...", flush=True)

    _run([str(MANIMGL_EXECUTABLE), "--version"])
    _run([
        str(ENV_PYTHON),
        "-c",
        "import manimlib; print('manimlib:', manimlib.__file__)",
    ])
    _run(["ffmpeg", "-version"])


def register_magic() -> None:
    """Register ManimGL rendering, download, and file-management shortcuts."""
    magic_file = THIS_DIR / "colab_magic.py"
    file_tools_file = THIS_DIR / "file_tools.py"

    if not magic_file.exists():
        raise FileNotFoundError(f"Magic module not found: {magic_file}")
    if not file_tools_file.exists():
        raise FileNotFoundError(f"File tools module not found: {file_tools_file}")

    magic_namespace = runpy.run_path(str(magic_file))
    magic_namespace["register_manimgl_magic"]()

    file_tools_namespace = runpy.run_path(str(file_tools_file))
    file_tools_namespace["register_file_magics"]()


def setup_gpu(*, register_magic: bool = True, force: bool = False) -> None:
    """Install and configure the optional NVIDIA EGL/ModernGL GPU engine."""
    gpu_tools_file = THIS_DIR / "gpu_tools.py"
    if not gpu_tools_file.exists():
        raise FileNotFoundError(f"GPU tools module not found: {gpu_tools_file}")
    namespace = runpy.run_path(str(gpu_tools_file))
    namespace["setup_gpu"](register_magic=register_magic, force=force)


def setup_all(*, register_magic: bool = True, force: bool = False) -> None:
    """Run the complete safe Colab installation.

    Args:
        register_magic: Register ``%%manimgl`` after installation.
        force: Delete and rebuild the ManimGL environment and source checkout.
    """
    print("=" * 70)
    print("ManimGL setup for Google Colab")
    print("No LaTeX will be installed.")
    print("ManimGL is isolated from Colab's internal Python environment.")
    print("=" * 70)

    install_system_dependencies()
    create_virtual_environment(force=force)
    install_pip()
    download_manimgl(force=force)
    install_manimgl(force=force)
    prepare_directories()
    verify_installation()

    if register_magic:
        register_magic_function = globals()["register_magic"]
        register_magic_function()

    print("\n" + "=" * 70)
    print("Setup completed successfully.")
    print("You can now use %%manimgl in the next notebook cell.")
    print("=" * 70)


if __name__ == "__main__":
    print("Loaded ManimGL Colab setup functions.")
    print("Run: setup_all(register_magic=True)")
