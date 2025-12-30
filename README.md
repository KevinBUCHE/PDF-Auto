# BDC Generator (version Tkinter minimale)

Application Windows qui transforme un devis PDF SRX en bon de commande (BDC) en remplissant le template `bon de commande V1.pdf` via des règles déterministes (sans IA ni OCR).

## Prérequis
- Python 3.11
- Windows avec Tkinter disponible (fourni par l'installation Python officielle)
- Dépendances :
  ```bash
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
  ```

## Emplacement du template (à fournir par l'utilisateur)
Le fichier `bon de commande V1.pdf` n'est **pas** versionné. Il doit être placé dans l'un des emplacements suivants :
1. À côté de l'exécutable : `<dossier_exe>/Templates/bon de commande V1.pdf`
2. Dans les données utilisateur : `%APPDATA%/BDC Generator/Templates/bon de commande V1.pdf`

Si le fichier est absent, l'application affiche un message d'erreur avec ces chemins exacts.

## Lancer en local (interface Tkinter)
```bash
python main.py
```
- Bouton **Choisir devis PDF** : sélectionne un devis SRX.
- Bouton **Générer BDC** : parse le devis, contrôle l'adresse client (anti-RIAUX) et génère `<nom_devis>_BDC.pdf` dans le même dossier.

### Mode CLI (sans interface)
```bash
python main.py --cli --devis "chemin/vers/SRXxxxx.pdf"
```

## Sorties
- Le BDC généré est écrit à côté du devis source avec le suffixe `_BDC.pdf`.
- Les logs texte sont stockés dans `logs/bdc_generator.log` (à côté du script ou de l'exécutable PyInstaller).

## Tests
Les tests unitaires couvrent le parsing sur du texte simulé et le mapping des champs PDF.
```bash
pytest
```
- Si des PDF sont ajoutés dans `fixtures/`, les tests tenteront de les parser ; sinon ils sont ignorés automatiquement.

## Build portable Windows (PyInstaller onedir)
Une build portable sans dépendance Qt est produite via PowerShell :
```powershell
pwsh ./scripts/build_portable.ps1
```
Le script crée `dist/bdc-generator-portable.zip` contenant l'application et un dossier `Templates/` vide prêt à recevoir le fichier utilisateur.

## CI GitHub Actions
Le workflow `.github/workflows/clean-build.yml` (Windows + Python 3.11) :
1. Installe les dépendances.
2. Exécute `pytest`.
3. Construit l'archive PyInstaller et publie l'artifact `bdc-generator-portable.zip`.

## Notes de robustesse
- Aucun import PySide6, Qt, Gemini ou OCR.
- Anti-RIAUX : génération refusée si l'adresse client correspond à une adresse interne connue.
- Champs obligatoires vérifiés après écriture PDF : `bdc_client_nom`, `bdc_ref_affaire`, `bdc_devis_annee_mois`.
