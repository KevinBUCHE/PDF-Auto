"""
Diagnostic PySide6 / Qt (CI-safe, ASCII only)

But:
- Verifier que PySide6 est installable/importable
- Verifier que les DLL Qt6 existent
- Copier les DLL Qt6 et plugins dans le dist PyInstaller

IMPORTANT:
- Sortie ASCII uniquement (pas de caracteres Unicode) pour eviter UnicodeEncodeError sur Windows CP1252.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Iterable


CRITICAL_DLLS = ["Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll"]


def _safe_io_utf8() -> None:
    """Force UTF-8 if supported (does not fail if not supported)."""
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        # Never fail the diagnostic because of encoding.
        pass


def _section(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def _qlibraryinfo_path(path_enum: object) -> str:
    try:
        from PySide6.QtCore import QLibraryInfo  # type: ignore

        if hasattr(QLibraryInfo, "path"):
            return QLibraryInfo.path(path_enum) or ""
        if hasattr(QLibraryInfo, "location"):
            return QLibraryInfo.location(path_enum) or ""
    except Exception:
        return ""
    return ""


def get_qt_bins_candidates(pyside_root: Path) -> list[Path]:
    candidates: list[Path] = []

    try:
        from PySide6.QtCore import QLibraryInfo  # type: ignore

        qlib_bins = _qlibraryinfo_path(QLibraryInfo.LibraryPath.BinariesPath)
        if qlib_bins:
            candidates.append(Path(qlib_bins))
    except Exception:
        pass

    candidates.extend(
        [
            pyside_root / "Qt" / "bin",
            pyside_root / "Qt" / "lib",
        ]
    )

    seen: set[Path] = set()
    unique: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve() if candidate.exists() else candidate
        if resolved not in seen:
            seen.add(resolved)
            unique.append(candidate)

    return unique


def get_qt_plugins_candidates(pyside_root: Path) -> list[Path]:
    candidates: list[Path] = []

    try:
        from PySide6.QtCore import QLibraryInfo  # type: ignore

        qlib_plugins = _qlibraryinfo_path(QLibraryInfo.LibraryPath.PluginsPath)
        if qlib_plugins:
            candidates.append(Path(qlib_plugins))
    except Exception:
        pass

    candidates.append(pyside_root / "Qt" / "plugins")

    seen: set[Path] = set()
    unique: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve() if candidate.exists() else candidate
        if resolved not in seen:
            seen.add(resolved)
            unique.append(candidate)

    return unique


def _find_critical_dlls(search_roots: Iterable[Path]) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for root in search_roots:
        if not root.exists():
            continue
        for dll_name in CRITICAL_DLLS:
            if dll_name in found:
                continue
            try:
                match = next(root.rglob(dll_name), None)
            except Exception:
                match = None
            if match is not None:
                found[dll_name] = match
        if len(found) == len(CRITICAL_DLLS):
            break
    return found


def find_qt_bin_dir(candidates: Iterable[Path]) -> tuple[Path | None, list[Path]]:
    checked: list[Path] = []
    for candidate in candidates:
        checked.append(candidate)
        if not candidate.exists():
            continue
        if all((candidate / dll).exists() for dll in CRITICAL_DLLS):
            return candidate, checked
    return None, checked


def _copy_qt_dlls(source_dirs: Iterable[Path], target_bin: Path) -> int:
    copied = 0
    seen: set[str] = set()
    for source_dir in source_dirs:
        if not source_dir.exists():
            continue
        for dll in source_dir.glob("Qt6*.dll"):
            if dll.name in seen:
                continue
            target = target_bin / dll.name
            target_bin.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dll, target)
            seen.add(dll.name)
            copied += 1
    return copied


def _copy_plugins(plugin_dir: Path, target_plugins: Path) -> int:
    if not plugin_dir.exists():
        return 0
    shutil.copytree(plugin_dir, target_plugins, dirs_exist_ok=True)
    count = sum(1 for _ in target_plugins.rglob("*"))
    return count


def main() -> None:
    _safe_io_utf8()

    _section("DIAGNOSTIC INSTALLATION PySide6 / Qt")

    try:
        import PySide6  # type: ignore

        pyside_root = Path(PySide6.__file__).resolve().parent  # type: ignore
        print(f"INFO: PySide6 version : {getattr(PySide6, '__version__', 'unknown')}")
        print(f"INFO: PySide6 root    : {pyside_root}")
    except Exception as exc:
        print(f"FAIL: Import PySide6  : {type(exc).__name__}: {exc}")
        raise SystemExit(1)

    if len(sys.argv) < 2:
        print("FAIL: Missing dist path argument.")
        print("Usage: python scripts/copy_qt_runtime.py <dist_dir>")
        raise SystemExit(1)

    dist_dir = Path(sys.argv[1]).resolve()
    target_bin = dist_dir / "_internal" / "PySide6" / "Qt" / "bin"
    target_plugins = dist_dir / "_internal" / "PySide6" / "Qt" / "plugins"

    print(f"INFO: Dist target     : {dist_dir}")
    print(f"INFO: Target bin dir  : {target_bin}")

    candidates = get_qt_bins_candidates(pyside_root)
    print("INFO: Qt bin candidates:")
    for candidate in candidates:
        print(f"  - {candidate}")

    qt_bin, checked = find_qt_bin_dir(candidates)
    for candidate in checked:
        if candidate.exists():
            print(f"INFO: Checked         : {candidate} (exists)")
        else:
            print(f"INFO: Checked         : {candidate} (missing)")

    search_roots = [pyside_root, pyside_root.parent]
    print("INFO: Recursive search roots:")
    for root in search_roots:
        print(f"  - {root}")

    found_critical = _find_critical_dlls(search_roots)

    missing = [dll for dll in CRITICAL_DLLS if dll not in found_critical]
    if missing:
        print("FAIL: Missing critical Qt DLLs:")
        for dll in missing:
            print(f"  - {dll}")
        raise SystemExit(1)

    if qt_bin is None:
        qt_bin = found_critical[CRITICAL_DLLS[0]].parent
        print(f"WARN: No bin dir with all critical DLLs found; using {qt_bin}")

    print(f"INFO: Selected Qt bin : {qt_bin}")

    source_dirs = [qt_bin]
    for dll_path in found_critical.values():
        source_dirs.append(dll_path.parent)

    source_dirs_unique: list[Path] = []
    seen_dirs: set[Path] = set()
    for source in source_dirs:
        resolved = source.resolve() if source.exists() else source
        if resolved not in seen_dirs:
            seen_dirs.add(resolved)
            source_dirs_unique.append(source)

    copied_count = _copy_qt_dlls(source_dirs_unique, target_bin)
    print(f"INFO: Copied Qt DLLs  : {copied_count}")

    for dll_name in CRITICAL_DLLS:
        target_path = target_bin / dll_name
        if target_path.exists():
            size_mb = target_path.stat().st_size / (1024 * 1024)
            print(f"OK: {dll_name} copied ({size_mb:.2f} MB)")
        else:
            print(f"FAIL: {dll_name} not copied")
            raise SystemExit(1)

    plugins_candidates = get_qt_plugins_candidates(pyside_root)
    print("INFO: Qt plugins candidates:")
    for candidate in plugins_candidates:
        print(f"  - {candidate}")

    plugins_copied = 0
    for candidate in plugins_candidates:
        if candidate.exists():
            plugins_copied = _copy_plugins(candidate, target_plugins)
            print(f"INFO: Copied plugins  : {plugins_copied} from {candidate}")
            break

    if plugins_copied == 0:
        print("INFO: No Qt plugins copied (not found)")

    print("INFO: Qt runtime copy complete")


if __name__ == "__main__":
    main()
