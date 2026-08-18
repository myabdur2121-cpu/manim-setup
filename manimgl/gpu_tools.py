"""Safe NVIDIA EGL/ModernGL GPU setup for ManimGL in Google Colab."""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import runpy
import shutil
import site
import subprocess
import sys
import urllib.request
import warnings
from pathlib import Path


THIS_DIR = Path(__file__).resolve().parent
GPU_ENV = Path("/content/manimgl-gpu-env")
GPU_SOURCE = Path("/content/manimGL-gpu")
NVIDIA_ROOT = Path("/content/manimgl-nvidia-root")
NVIDIA_DEBS = Path("/content/manimgl-nvidia-debs")
GPU_CONFIG = Path("/content/manimgl_gpu_config.json")
GET_PIP = Path("/content/get-pip-gpu.py")
GPU_PYTHON = GPU_ENV / "bin/python"
GPU_MANIMGL = GPU_ENV / "bin/manimgl"

NVIDIA_PACKAGES = (
    "libnvidia-common-{major}",
    "libnvidia-compute-{major}",
    "libnvidia-gpucomp-{major}",
    "libnvidia-gl-{major}",
)


def _run(command: list[str], *, cwd: Path | None = None, capture: bool = False) -> str:
    print("\n$ " + " ".join(str(part) for part in command), flush=True)
    result = subprocess.run(
        [str(part) for part in command],
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if capture and result.stdout:
        print(result.stdout)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}: "
            + " ".join(str(part) for part in command)
        )
    return result.stdout or ""


def detect_nvidia_gpu() -> dict[str, str]:
    """Return the first Colab NVIDIA GPU and kernel-driver version."""
    result = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,driver_version,memory.total",
            "--format=csv,noheader,nounits",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(
            "No NVIDIA GPU was detected. In Colab select Runtime → "
            "Change runtime type → GPU, reconnect, and run setup again."
        )

    first_line = result.stdout.strip().splitlines()[0]
    parts = [part.strip() for part in first_line.split(",")]
    if len(parts) < 3:
        raise RuntimeError(f"Unexpected nvidia-smi output: {first_line}")
    return {
        "name": parts[0],
        "driver_version": parts[1],
        "memory_mib": parts[2],
    }


def _available_exact_version(package: str, driver_version: str) -> str:
    output = _run(["apt-cache", "madison", package], capture=True)
    versions: list[str] = []
    for line in output.splitlines():
        fields = [field.strip() for field in line.split("|")]
        if len(fields) >= 2:
            versions.append(fields[1])

    exact = [version for version in versions if version.startswith(driver_version + "-")]
    if not exact:
        raise RuntimeError(
            f"No exact userspace package matching NVIDIA driver {driver_version} "
            f"was found for {package}. Available: {versions}"
        )
    return exact[0]


def install_gpu_system_tools() -> None:
    """Install generic EGL/OpenGL diagnostics without replacing NVIDIA drivers."""
    _run(["apt-get", "update", "-qq"])
    _run([
        "apt-get",
        "install",
        "-y",
        "libegl1",
        "libgl1",
        "libgles2",
        "mesa-utils",
        "ffmpeg",
        "git",
        "curl",
        "build-essential",
        "python3-dev",
        "pkg-config",
        "libcairo2-dev",
        "libpango1.0-dev",
    ])


def extract_matching_nvidia_libraries(
    driver_version: str,
    *,
    force: bool = False,
) -> dict[str, str]:
    """Download and extract matching NVIDIA userspace packages locally."""
    major = driver_version.split(".", 1)[0]
    package_names = [pattern.format(major=major) for pattern in NVIDIA_PACKAGES]
    package_versions = {
        package: _available_exact_version(package, driver_version)
        for package in package_names
    }

    if force:
        shutil.rmtree(NVIDIA_ROOT, ignore_errors=True)
        shutil.rmtree(NVIDIA_DEBS, ignore_errors=True)

    if not NVIDIA_ROOT.exists():
        NVIDIA_ROOT.mkdir(parents=True)
        NVIDIA_DEBS.mkdir(parents=True, exist_ok=True)

        for package, version in package_versions.items():
            _run(["apt-get", "download", f"{package}={version}"], cwd=NVIDIA_DEBS)

        deb_files = sorted(NVIDIA_DEBS.glob("*.deb"))
        if not deb_files:
            raise RuntimeError("NVIDIA packages downloaded, but no .deb files were found.")

        for deb_file in deb_files:
            _run(["dpkg-deb", "--extract", str(deb_file), str(NVIDIA_ROOT)])

    library_dir = NVIDIA_ROOT / "usr/lib/x86_64-linux-gnu"
    egl_library = library_dir / f"libEGL_nvidia.so.{driver_version}"
    glx_library = library_dir / f"libGLX_nvidia.so.{driver_version}"

    for path in (library_dir, egl_library, glx_library):
        if not path.exists():
            raise FileNotFoundError(f"Required extracted NVIDIA file is missing: {path}")

    egl_json = Path("/content/manimgl_nvidia_egl_vendor.json")
    egl_json.write_text(
        json.dumps(
            {
                "file_format_version": "1.0.0",
                "ICD": {"library_path": str(library_dir / "libEGL_nvidia.so.0")},
            },
            indent=4,
        )
        + "\n",
        encoding="utf-8",
    )

    return {
        "major": major,
        "driver_version": driver_version,
        "library_dir": str(library_dir),
        "egl_json": str(egl_json),
        "package_versions": package_versions,
    }


def create_gpu_environment(*, force: bool = False) -> None:
    """Install the official ModernGL-based ManimGL tag in an isolated env."""
    if force:
        shutil.rmtree(GPU_ENV, ignore_errors=True)
        shutil.rmtree(GPU_SOURCE, ignore_errors=True)

    if not GPU_PYTHON.exists():
        _run([sys.executable, "-m", "venv", "--without-pip", str(GPU_ENV)])
        urllib.request.urlretrieve("https://bootstrap.pypa.io/get-pip.py", GET_PIP)
        _run([str(GPU_PYTHON), str(GET_PIP)])

    if not (GPU_SOURCE / ".git").exists():
        shutil.rmtree(GPU_SOURCE, ignore_errors=True)
        _run([
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            "v1.7.2",
            "https://github.com/3b1b/manim.git",
            str(GPU_SOURCE),
        ])

    _run([str(GPU_PYTHON), "-m", "pip", "install", "--force-reinstall", "setuptools<81"])
    _run([str(GPU_PYTHON), "-m", "pip", "install", "-e", str(GPU_SOURCE)])
    # Editable installation can leave a newer setuptools; enforce compatibility again.
    _run([str(GPU_PYTHON), "-m", "pip", "install", "--force-reinstall", "setuptools<81"])


def patch_gpu_source() -> None:
    """Force NVIDIA EGL OpenGL 4.3 and fix the legacy FPS CLI type."""
    camera_file = GPU_SOURCE / "manimlib/camera/camera.py"
    config_file = GPU_SOURCE / "manimlib/config.py"

    camera_source = camera_file.read_text(encoding="utf-8")
    old_context = "moderngl.create_standalone_context()"
    new_context = 'moderngl.create_standalone_context(backend="egl", require=430)'
    if old_context in camera_source:
        camera_source = camera_source.replace(old_context, new_context, 1)
        camera_file.write_text(camera_source, encoding="utf-8")
    if new_context not in camera_file.read_text(encoding="utf-8"):
        raise RuntimeError("Could not apply the ModernGL EGL camera patch.")

    config_source = config_file.read_text(encoding="utf-8")
    fps_block = 'parser.add_argument(\n            "--fps",\n            help="Frame rate, as an integer",\n        )'
    patched_fps_block = 'parser.add_argument(\n            "--fps",\n            type=int,\n            help="Frame rate, as an integer",\n        )'
    if fps_block in config_source:
        config_source = config_source.replace(fps_block, patched_fps_block, 1)
        config_file.write_text(config_source, encoding="utf-8")
    if patched_fps_block not in config_file.read_text(encoding="utf-8"):
        raise RuntimeError("Could not apply the legacy --fps integer patch.")


def gpu_environment(config: dict[str, object]) -> dict[str, str]:
    environment = os.environ.copy()
    library_dir = str(config["library_dir"])
    environment["LD_LIBRARY_PATH"] = (
        f"{library_dir}:/usr/lib64-nvidia:{environment.get('LD_LIBRARY_PATH', '')}"
    )
    environment["__EGL_VENDOR_LIBRARY_FILENAMES"] = str(config["egl_json"])
    environment["__GLX_VENDOR_LIBRARY_NAME"] = "nvidia"
    environment["PYGLET_HEADLESS"] = "true"
    environment["PYOPENGL_PLATFORM"] = "egl"
    environment["XDG_RUNTIME_DIR"] = "/tmp/runtime-colab"
    for name in (
        "LIBGL_ALWAYS_SOFTWARE",
        "VK_ICD_FILENAMES",
        "VK_DRIVER_FILES",
        "DISPLAY",
        "WAYLAND_DISPLAY",
    ):
        environment.pop(name, None)
    return environment


def verify_gpu_context(config: dict[str, object]) -> dict[str, str]:
    """Create an EGL OpenGL 4.3 context and require an NVIDIA renderer."""
    code = r'''
import json
import moderngl
ctx = moderngl.create_standalone_context(backend="egl", require=430)
info = {
    "vendor": str(ctx.info.get("GL_VENDOR", "")),
    "renderer": str(ctx.info.get("GL_RENDERER", "")),
    "version": str(ctx.info.get("GL_VERSION", "")),
    "version_code": str(ctx.version_code),
}
print(json.dumps(info))
ctx.release()
'''
    result = subprocess.run(
        [str(GPU_PYTHON), "-c", code],
        env=gpu_environment(config),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("NVIDIA EGL context test failed:\n" + result.stdout)

    json_line = next(
        (line for line in reversed(result.stdout.splitlines()) if line.startswith("{")),
        None,
    )
    if not json_line:
        raise RuntimeError("GPU context did not return adapter JSON:\n" + result.stdout)
    info = json.loads(json_line)
    combined = (info["vendor"] + " " + info["renderer"]).lower()
    if "nvidia" not in combined and "tesla" not in combined:
        raise RuntimeError(f"Expected NVIDIA renderer, got: {info}")
    if int(info["version_code"]) < 430:
        raise RuntimeError(f"OpenGL 4.3+ required, got: {info}")
    return info


def enable_manim_autocomplete() -> dict[str, object]:
    """Expose the real GPU ManimGL source to Colab's IDE and autocomplete.

    The GPU environment remains isolated for rendering. A symlink and a .pth
    dependency bridge let Colab's language server resolve ``manimlib`` without
    upgrading or replacing Colab's own IPython installation.
    """
    if not GPU_PYTHON.exists() or not (GPU_SOURCE / "manimlib").exists():
        raise FileNotFoundError("GPU ManimGL is not installed. Run setup_gpu() first.")

    colab_site = Path(site.getsitepackages()[0])
    gpu_site_output = subprocess.check_output(
        [
            str(GPU_PYTHON),
            "-c",
            "import site; print(site.getsitepackages()[0])",
        ],
        text=True,
    ).strip()
    gpu_site = Path(gpu_site_output)
    gpu_manimlib = (GPU_SOURCE / "manimlib").resolve()

    pth_file = colab_site / "manimgl_gpu_autocomplete.pth"
    pth_file.write_text(str(gpu_site) + "\n", encoding="utf-8")

    manimlib_link = colab_site / "manimlib"
    if manimlib_link.is_symlink():
        if manimlib_link.resolve() != gpu_manimlib:
            manimlib_link.unlink()
            manimlib_link.symlink_to(gpu_manimlib, target_is_directory=True)
    elif manimlib_link.exists():
        # A real base-kernel package must never be deleted automatically.
        if manimlib_link.resolve() != gpu_manimlib:
            raise RuntimeError(
                "A different real manimlib package already exists in Colab's "
                f"site-packages: {manimlib_link}"
            )
    else:
        manimlib_link.symlink_to(gpu_manimlib, target_is_directory=True)

    for path in (str(gpu_site), str(GPU_SOURCE)):
        if path not in sys.path:
            sys.path.append(path)
    importlib.invalidate_caches()

    os.environ["PYGLET_HEADLESS"] = "true"
    os.environ["PYOPENGL_PLATFORM"] = "egl"
    warnings.filterwarnings(
        "ignore",
        message=r"pkg_resources is deprecated.*",
        category=UserWarning,
    )

    import pyglet

    pyglet.options["headless"] = True
    pyglet.options["headless_device"] = 0
    pyglet.options["shadow_window"] = False

    existing = sys.modules.get("manimlib")
    if existing is not None:
        existing_file = str(getattr(existing, "__file__", ""))
        if not existing_file.startswith(str(GPU_SOURCE)):
            for module_name in list(sys.modules):
                if module_name == "manimlib" or module_name.startswith("manimlib."):
                    sys.modules.pop(module_name, None)

    manimlib = importlib.import_module("manimlib")
    public_symbols = {
        name: getattr(manimlib, name)
        for name in dir(manimlib)
        if not name.startswith("_")
    }

    try:
        from IPython import get_ipython

        ipython = get_ipython()
        if ipython is not None:
            ipython.user_ns.update(public_symbols)
    except ImportError:
        pass

    specification = importlib.util.find_spec("manimlib")
    result: dict[str, object] = {
        "module": str(getattr(manimlib, "__file__", "")),
        "resolved": str(specification.origin if specification else ""),
        "symbols": len(public_symbols),
        "pth_file": str(pth_file),
        "package_link": str(manimlib_link),
    }

    print("\nManimGL editor bridge enabled successfully.")
    print(f"Resolved module: {result['resolved']}")
    print(f"Autocomplete symbols: {result['symbols']}")
    print("IDE hints: enabled")
    print("Missing-import underlines: resolved")
    return result


def register_gpu_magic() -> None:
    namespace = runpy.run_path(str(THIS_DIR / "gpu_magic.py"))
    namespace["register_manimgl_gpu_magic"]()


def setup_gpu(
    *,
    register_magic: bool = True,
    enable_autocomplete: bool = True,
    force: bool = False,
) -> None:
    """Perform the complete safe Colab NVIDIA GPU setup."""
    print("=" * 72)
    print("ManimGL NVIDIA GPU setup (EGL + ModernGL)")
    print("System NVIDIA drivers will not be replaced.")
    print("=" * 72)

    gpu = detect_nvidia_gpu()
    print(f"GPU: {gpu['name']}")
    print(f"Driver: {gpu['driver_version']}")
    print(f"VRAM: {gpu['memory_mib']} MiB")

    install_gpu_system_tools()
    config: dict[str, object] = {
        **gpu,
        **extract_matching_nvidia_libraries(gpu["driver_version"], force=force),
    }
    create_gpu_environment(force=force)
    patch_gpu_source()

    Path("/tmp/runtime-colab").mkdir(parents=True, exist_ok=True)
    Path("/tmp/runtime-colab").chmod(0o700)

    context_info = verify_gpu_context(config)
    config["context"] = context_info
    config["gpu_python"] = str(GPU_PYTHON)
    config["gpu_manimgl"] = str(GPU_MANIMGL)
    config["gpu_source"] = str(GPU_SOURCE)
    config["runner"] = str(THIS_DIR / "moderngl_gpu_runner.py")
    GPU_CONFIG.write_text(json.dumps(config, indent=2), encoding="utf-8")

    if enable_autocomplete:
        enable_manim_autocomplete()

    if register_magic:
        register_gpu_magic()

    print("\n" + "=" * 72)
    print("GPU setup completed successfully.")
    print(f"Renderer: {context_info['renderer']}")
    print(f"OpenGL: {context_info['version']}")
    print("Use: %%manimgl_gpu --draft SceneName")
    print("=" * 72)


if __name__ == "__main__":
    print("Loaded GPU setup tools. Run: setup_gpu()")
