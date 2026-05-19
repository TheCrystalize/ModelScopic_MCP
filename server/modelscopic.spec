# PyInstaller spec for the unified `modelscopic` binary.
#
# Build with:
#   cd server
#   pyinstaller modelscopic.spec --clean --noconfirm
#
# Output: dist/modelscopic.exe (single-file)

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Submodules that PyInstaller misses via static analysis. The MCP SDK uses
# anyio + various runtime-imported submodules; mss has a per-platform module
# selected by runtime detection; pytesseract reflects on its package data.
def _safe_submodules(pkg, skip_prefixes=()):
    """collect_submodules but skip optional subpackages that explode on import."""
    try:
        mods = collect_submodules(pkg, filter=lambda name: not any(
            name == pkg + "." + s or name.startswith(pkg + "." + s + ".")
            for s in skip_prefixes
        ))
    except SystemExit:
        mods = [pkg]
    return mods


hidden = []
# mcp.cli requires typer (we don't use it) and exits the interpreter on import
# during PyInstaller's static walk. Skip the whole subpackage.
hidden += _safe_submodules("mcp", skip_prefixes=("cli",))
hidden += _safe_submodules("mss")
hidden += _safe_submodules("anyio")
hidden += ["pytesseract"]

# Data files (none of our own; deps usually pull in tessdata if installed
# alongside, but Tesseract binary stays system-installed).
datas = []
datas += collect_data_files("mcp", include_py_files=False)

# Generate a small launcher that imports the package so relative imports work
import os
launcher = os.path.abspath("_modelscopic_launcher.py")
with open(launcher, "w", encoding="utf8") as f:
    f.write("from modelscopic.__main__ import main\nif __name__ == '__main__':\n    main()\n")

# Make sure the modelscopic package itself ships fully -- not just what
# static analysis from __main__ pulled in.
hidden += _safe_submodules("modelscopic")

a = Analysis(
    [launcher],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Trim dead weight -- these only get pulled in if someone tries them
        "tkinter",
        "test",
        "unittest",
        "pydoc_data",
        "pyinstaller",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="modelscopic",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                  # UPX would help size but is brittle on Win11
    console=True,               # we ARE the stdio interface
    disable_windowed_traceback=False,
    icon=None,
)
