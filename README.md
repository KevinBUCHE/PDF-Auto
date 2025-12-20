# BDC Generator

Application Windows (Python 3.11 + PySide6) pour générer des bons de commande (BDC) à partir de devis PDF.

## Fonctionnalités
- Drag & drop de devis PDF.
- Liste des devis avec toggle AVEC/SANS pose.
- Bouton "Générer" pour produire les BDC.
- Logs lisibles.

## Structure
- `main.py` : interface et orchestration.
- `services/` : parsing devis, détection de pose, remplissage BDC.
- `Templates/` : template PDF (non versionné).
- `installer/` : script Inno Setup.
- `.github/workflows/` : build Windows + installer + ZIP.

## Prérequis
- Python 3.11
- Dépendances : `pip install -r requirements.txt`

## Lancement local
1. Placez le template PDF : `Templates/bon de commande V1.pdf`
2. Lancez l'app :
   ```bash
   python main.py
   ```

## Packaging local (Windows)
- Build portable : `build_portable.bat`
- Build installer : `build_installer.bat`
- ZIP release : `make_release_zip.bat`

## CI/CD GitHub Actions
Le workflow **Build Windows Installer** produit un ZIP `BDC_Generator.zip` contenant :
- `BDC_Generator_Setup_User.exe`
- `README_Installation.txt`

### Où cliquer
GitHub → **Actions** → **Build Windows Installer** → **Run workflow** → télécharger l'artifact.

## Notes importantes
- Le template `Templates/bon de commande V1.pdf` est requis. Le workflow échoue si absent.
- Le PDF de sortie n'est jamais aplati.
- NeedAppearances est activé.

## Documentation complète
Voir `GUIDE_COMPLET.md`.
