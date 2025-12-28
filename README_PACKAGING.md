# Packaging Windows (PySide6)

## Recommandation
Utiliser **PyInstaller en mode `--onedir`**. Ce mode embarque toutes les DLL Qt
et dépendances Microsoft nécessaires dans un dossier unique, ce qui évite
les erreurs `ImportError: DLL load failed while importing QtCore`.

## Pourquoi `--onedir` ?
- Le chargement des DLL Qt (Qt6*.dll, Shiboken) est plus fiable avec un dossier dédié.
- Les runtimes MSVC (vcruntime140*.dll, msvcp140.dll, concrt140.dll) restent visibles
  à côté de l’exécutable, sans installation admin chez l’utilisateur.

## Hook runtime
Le hook `hooks/runtime_qt_path.py` préfixe `PATH` avec le dossier de l’exe en mode
frozen pour garantir que Qt retrouve ses DLL à l’exécution.
