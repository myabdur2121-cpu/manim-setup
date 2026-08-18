"""Public Python API for the ManimGL Google Colab setup repository."""

from manimgl.colab_setup import (
    create_virtual_environment,
    download_manimgl,
    enable_manim_autocomplete,
    install_latex,
    install_manimgl,
    install_pip,
    install_system_dependencies,
    prepare_directories,
    register_magic,
    setup_all,
    setup_gpu,
    verify_installation,
)

__all__ = [
    "create_virtual_environment",
    "download_manimgl",
    "enable_manim_autocomplete",
    "install_latex",
    "install_manimgl",
    "install_pip",
    "install_system_dependencies",
    "prepare_directories",
    "register_magic",
    "setup_all",
    "setup_gpu",
    "verify_installation",
]

__version__ = "0.1.0"
