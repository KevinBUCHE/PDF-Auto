"""
Script de test pour vérifier l'installation de PySide6 et Qt
À lancer AVANT le build pour diagnostiquer les problèmes
"""
import sys
from pathlib import Path


def test_pyside6_import():
    """Test 1: Import de PySide6"""
    print("\n" + "=" * 60)
    print("TEST 1: Import PySide6")
    print("=" * 60)
    
    try:
        import PySide6
        print(f"✓ PySide6 version: {PySide6.__version__}")
        print(f"✓ PySide6 location: {PySide6.__file__}")
        return True
    except ImportError as e:
        print(f"✗ Erreur import PySide6: {e}")
        return False


def test_qt_dlls():
    """Test 2: Vérification des DLLs Qt"""
    print("\n" + "=" * 60)
    print("TEST 2: Vérification DLLs Qt")
    print("=" * 60)
    
    try:
        import PySide6
        pyside_root = Path(PySide6.__file__).parent
        qt_bin = pyside_root / "Qt" / "bin"
        
        print(f"\n📍 PySide6 root: {pyside_root}")
        print(f"📍 Qt bin: {qt_bin}")
        
        if not qt_bin.exists():
            print(f"✗ Dossier Qt bin inexistant: {qt_bin}")
            return False
        
        print(f"✓ Dossier Qt bin existe")
        
        # Lister les DLLs Qt
        qt_dlls = list(qt_bin.glob("Qt6*.dll"))
        if not qt_dlls:
            print(f"✗ Aucune DLL Qt6 trouvée dans {qt_bin}")
            return False
        
        print(f"\n✓ {len(qt_dlls)} DLLs Qt6 trouvées:")
        for dll in sorted(qt_dlls)[:10]:  # Afficher les 10 premières
            size_mb = dll.stat().st_size / (1024 * 1024)
            print(f"  - {dll.name} ({size_mb:.2f} MB)")
        
        if len(qt_dlls) > 10:
            print(f"  ... et {len(qt_dlls) - 10} autres")
        
        # Vérifier les DLLs critiques
        critical_dlls = [
            "Qt6Core.dll",
            "Qt6Gui.dll",
            "Qt6Widgets.dll"
        ]
        
        print("\n🔍 DLLs critiques:")
        all_ok = True
        for dll_name in critical_dlls:
            dll_path = qt_bin / dll_name
            if dll_path.exists():
                size_mb = dll_path.stat().st_size / (1024 * 1024)
                print(f"  ✓ {dll_name} ({size_mb:.2f} MB)")
            else:
                print(f"  ✗ {dll_name} MANQUANT")
                all_ok = False
        
        return all_ok
        
    except Exception as e:
        print(f"✗ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_shiboken6():
    """Test 3: Vérification Shiboken6"""
    print("\n" + "=" * 60)
    print("TEST 3: Vérification Shiboken6")
    print("=" * 60)
    
    try:
        import shiboken6
        print(f"✓ Shiboken6 version: {shiboken6.__version__}")
        
        shiboken_root = Path(shiboken6.__file__).parent
        print(f"✓ Shiboken6 location: {shiboken_root}")
        
        # Chercher les DLLs shiboken
        shiboken_dlls = list(shiboken_root.glob("shiboken6*.dll"))
        if shiboken_dlls:
            print(f"✓ {len(shiboken_dlls)} DLL(s) Shiboken trouvée(s):")
            for dll in shiboken_dlls:
                print(f"  - {dll.name}")
        else:
            print("⚠ Aucune DLL Shiboken trouvée (peut être dans PySide6)")
        
        return True
        
    except ImportError as e:
        print(f"✗ Erreur import Shiboken6: {e}")
        return False


def test_qt_modules():
    """Test 4: Import des modules Qt"""
    print("\n" + "=" * 60)
    print("TEST 4: Import modules Qt")
    print("=" * 60)
    
    modules = [
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets"
    ]
    
    all_ok = True
    for module in modules:
        try:
            __import__(module)
            print(f"✓ {module}")
        except ImportError as e:
            print(f"✗ {module}: {e}")
            all_ok = False
    
    return all_ok


def main():
    """Exécute tous les tests"""
    print("\n" + "=" * 70)
    print(" DIAGNOSTIC INSTALLATION PySide6 / Qt ".center(70, "="))
    print("=" * 70)
    
    results = {
        "Import PySide6": test_pyside6_import(),
        "DLLs Qt": test_qt_dlls(),
        "Shiboken6": test_shiboken6(),
        "Modules Qt": test_qt_modules()
    }
    
    # Résumé
    print("\n" + "=" * 70)
    print(" RÉSUMÉ ".center(70, "="))
    print("=" * 70)
    
    for test_name, result in results.items():
        status = "✅ OK" if result else "❌ ÉCHEC"
        print(f"{test_name:30} {status}")
    
    all_ok = all(results.values())
    
    print("\n" + "=" * 70)
    if all_ok:
        print("✅ TOUS LES TESTS RÉUSSIS".center(70))
        print("Vous pouvez lancer le build PyInstaller".center(70))
    else:
        print("❌ CERTAINS TESTS ONT ÉCHOUÉ".center(70))
        print("Réinstallez PySide6: pip install --force-reinstall PySide6".center(70))
    print("=" * 70 + "\n")
    
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
