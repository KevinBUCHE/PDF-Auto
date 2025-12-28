import os
import pathlib
import platform
import sys


def print_header(title):
    print("=" * 80)
    print(title)
    print("=" * 80)


print_header("Python")
print("Executable:", sys.executable)
print("Version:", sys.version.replace("\n", " "))
print("Platform:", platform.platform())
print("CWD:", os.getcwd())

print_header("PySide6")
try:
    import PySide6
    from PySide6 import QtCore
except Exception as exc:  # pragma: no cover
    print("PySide6 import failed:", exc)
    sys.exit(1)

pyside_path = pathlib.Path(PySide6.__file__).resolve().parent
print("PySide6 module path:", pyside_path)
print("PySide6 version:", getattr(PySide6, "__version__", "unknown"))
print("QtCore version:", QtCore.__version__)

print_header("Qt runtime")
qt_dir = pyside_path / "Qt"
qt_bin = qt_dir / "bin"
print("Qt dir:", qt_dir)
print("Qt bin:", qt_bin)
print("Qt dir exists:", qt_dir.exists())
print("Qt bin exists:", qt_bin.exists())

if qt_bin.exists():
    qt_core = sorted([p.name for p in qt_bin.glob("Qt6Core*.dll")])
    qt_widgets = sorted([p.name for p in qt_bin.glob("Qt6Widgets*.dll")])
    qt_gui = sorted([p.name for p in qt_bin.glob("Qt6Gui*.dll")])
    qt_plugins = sorted([p.name for p in (qt_dir / "plugins").glob("**/*")]) if (qt_dir / "plugins").exists() else []

    print("Qt6Core DLLs:", qt_core[:10])
    print("Qt6Widgets DLLs:", qt_widgets[:10])
    print("Qt6Gui DLLs:", qt_gui[:10])
    print("Qt plugins sample:", qt_plugins[:10])

print_header("Environment")
print("PYTHONPATH:", os.environ.get("PYTHONPATH", ""))
print("PATH sample:")
for entry in os.environ.get("PATH", "").split(os.pathsep)[:10]:
    print("-", entry)
