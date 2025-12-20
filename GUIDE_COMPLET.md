# GUIDE COMPLET - BDC Generator

## 1. Installation et lancement
### Pré-requis
- Windows 10/11
- Python 3.11 (pour usage développeur)

### Lancement développeur
1. Placez le template PDF : `Templates/bon de commande V1.pdf`
2. Installez les dépendances :
   ```bash
   pip install -r requirements.txt
   ```
3. Lancez :
   ```bash
   python main.py
   ```

### Lancement utilisateur final
- Utilisez l'installateur `BDC_Generator_Setup_User.exe`
- Aucune élévation admin requise
- Raccourcis créés sur le Bureau et le menu Démarrer

## 2. Utilisation
1. Ouvrir l'application.
2. Glisser-déposer un ou plusieurs devis PDF.
3. Vérifier le toggle "Pose vendue" sur chaque ligne.
4. Cliquer sur **Générer les BDC**.
5. Les BDC sont générés dans `BDC_Output/`.

## 3. Règles métier appliquées
### Détection de pose
- Détecter la pose vendue **uniquement** si une ligne contient `Pose au ...` avec un montant.

### Si pose vendue
- `bdc_livraison_bloc` vide
- checkbox livraison poseur cochée
- checkbox livraison client décochée
- `bdc_montant_pose_ht` = montant `Pose au ...` si trouvé, sinon `prestations_ht`

### Si pas de pose
- `bdc_livraison_bloc` = "idem"
- checkbox livraison client cochée
- checkbox livraison poseur décochée
- `bdc_montant_pose_ht` = `prestations_ht`

### Montants extraits
- Montants avant libellés :
  - `PRIX DE LA FOURNITURE HT`
  - `PRIX PRESTATIONS ET SERVICES HT`
  - `TOTAL HORS TAXE`

### Référence devis
- Extraction `SRX(yymm)AFF(num)`
- Remplissage:
  - `bdc_devis_annee_mois = yymm`
  - `bdc_devis_num = num` (6 chiffres)
  - `bdc_devis_type = AFF`

### PDF
- **Ne jamais aplatir** le PDF
- `NeedAppearances` activé

## 4. Packaging
### Commandes locales
- `build_portable.bat` : génère le dossier PyInstaller.
- `build_installer.bat` : compile l'installateur Inno Setup.
- `make_release_zip.bat` : crée `BDC_Generator.zip`.

### Workflow GitHub Actions
- `windows-latest`
- Python 3.11
- PyInstaller `--onedir --windowed`
- Inno Setup per-user
- Artifact `BDC_Generator.zip`

## 5. Dossiers & Fichiers
```
main.py
requirements.txt
services/
Templates/
installer/
.github/workflows/
build_portable.bat
build_installer.bat
make_release_zip.bat
README.md
GUIDE_COMPLET.md
README_Installation.txt
```
