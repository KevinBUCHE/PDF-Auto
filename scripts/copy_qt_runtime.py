"""
Diagnostic PySide6 / Qt (CI-safe, ASCII only)

But:
- Verifier que PySide6 est installable/importable
- Verifier que les DLL Qt6 existent dans PySide6/Qt/bin
- Verifier Shiboken6
- Verifier imports PySide6.QtCore/QtGui/QtWidgets

IMPORTANT:
- Sortie ASCII uniquement (pas de ✓ / emojis) pour eviter UnicodeEncodeError sur Windows CP1252.
"""

from __future__ import annotations

import sys
from pathlib import Path


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


def test_pyside6_import() -> bool:
    _section("TEST 1: Import PySide6")
    try:
        import PySide6  # type: ignore

        print(f"OK: PySide6 version   : {getattr(PySide6, '__version__', 'unknown')}")
        print(f"OK: PySide6 location  : {getattr(PySide6, '__file__', 'unknown')}")
        return True
    except Exception as e:
        print(f"FAIL: Import PySide6  : {type(e).__name__}: {e}")
        return False


def test_qt_dlls() -> bool:
    _section("TEST 2: Verification DLLs Qt (Qt6*.dll)")

    try:
        import PySide6  # type: ignore

        pyside_root = Path(PySide6.__file__).resolve().parent  # type: ignore
        qt_bin = pyside_root / "Qt" / "bin"

        print(f"INFO: PySide6 root    : {pyside_root}")
        print(f"INFO: Qt bin          : {qt_bin}")

        if not qt_bin.exists():
            print(f"FAIL: Qt bin missing  : {qt_bin}")
            return False

        print("OK: Qt bin exists")

        qt_dlls = sorted(qt_bin.glob("Qt6*.dll"))
        if not qt_dlls:
            print("FAIL: No Qt6*.dll found in Qt/bin")
            return False

        print(f"OK: Found {len(qt_dlls)} Qt6 DLL(s) (showing up to 15):")
        for dll in qt_dlls[:15]:
            try:
                size_mb = dll.stat().st_size / (1024 * 1024)
                print(f"  - {dll.name} ({size_mb:.2f} MB)")
            except Exception:
                print(f"  - {dll.name}")

        if len(qt_dlls) > 15:
            print(f"  ... plus {len(qt_dlls) - 15} other(s)")

        # Critical DLLs
        critical = ["Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll"]
        print("\nINFO: Critical DLLs:")
        all_ok = True
        for name in critical:
            p = qt_bin / name
            if p.exists():
                size_mb = p.stat().st_size / (1024 * 1024)
                print(f"  OK  : {name} ({size_mb:.2f} MB)")
            else:
                print(f"  FAIL: {name} missing")
                all_ok = False

        return all_ok

    except Exception as e:
        print(f"FAIL: Qt DLL check    : {type(e).__name__}: {e}")
        return False


def test_shiboken6() -> bool:
    _section("TEST 3: Verification Shiboken6")
    try:
        import shiboken6  # type: ignore

        print(f"OK: Shiboken6 version : {getattr(shiboken6, '__version__', 'unknown')}")
        root = Path(shiboken6.__file__).resolve().parent  # type: ignore
        print(f"OK: Shiboken6 path    : {root}")

        dlls = sorted(root.glob("shiboken6*.dll"))
        if dlls:
            print(f"OK: Found {len(dlls)} shiboken DLL(s):")
            for d in dlls:
                print(f"  - {d.name}")
        else:
            print("WARN: No shiboken6*.dll in shiboken6 folder (may be bundled under PySide6)")
        return True

    except Exception as e:
        print(f"FAIL: Import shiboken6: {type(e).__name__}: {e}")
        return False


def test_qt_modules() -> bool:
    _section("TEST 4: Import Qt modules")
    modules = ["PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"]
    all_ok = True

    for mod in modules:
        try:
            __import__(mod)
            print(f"OK: {mod}")
        except Exception as e:
            print(f"FAIL: {mod} : {type(e).__name__}: {e}")
            all_ok = False

    return all_ok


def main() -> None:
    _safe_io_utf8()

    print("\n" + "=" * 70)
    print("DIAGNOSTIC INSTALLATION PySide6 / Qt".center(70))
    print("=" * 70)

    results = {
        "Import PySide6": test_pyside6_import(),
        "Qt DLLs": test_qt_dlls(),
        "Shiboken6": test_shiboken6(),
        "Qt modules": test_qt_modules(),
    }

    _section("SUMMARY")
    for name, ok in results.items():
        status = "OK" if ok else "FAIL"
        print(f"{name:20} : {status}")

    all_ok = all(results.values())
    print("\n" + "=" * 70)
    if all_ok:
        print("ALL TESTS PASSED - You can run PyInstaller.".center(70))
        exit_code = 0
    else:
        print("SOME TESTS FAILED - Fix dependencies before building.".center(70))
        print("Hint: python -m pip install --force-reinstall PySide6 shiboken6".center(70))
        exit_code = 1
    print("=" * 70 + "\n")

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
