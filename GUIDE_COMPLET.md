# GUIDE COMPLET - BDC Generator

## 1. Installation et lancement
### Pré-requis
- Windows 10/11
- Python 3.11 (pour usage développeur)

### Lancement développeur
1. Placez le template PDF (optionnel, pour copie automatique au premier démarrage) :
   `Templates/bon de commande V1.pdf`
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
2. Vérifier l'indicateur **Template: OK** (sinon utiliser **Ouvrir le dossier Templates** ou **Choisir un template…**).
3. Glisser-déposer un ou plusieurs devis PDF `SRX*.pdf`.
4. La pose est détectée automatiquement (colonne **Origine** = Auto). Vous pouvez forcer via le checkbox si besoin.
5. Cliquer sur **Générer les BDC**.
6. Les BDC sont générés dans `BDC_Output/`.
7. Si la pose est vendue, le bloc livraison est rempli avec l'adresse dépôt configurée dans l'UI.

## 3. Règles métier appliquées
### Template PDF
- Template requis (source de vérité) : `%LOCALAPPDATA%\BDC Generator\Templates\bon de commande V1.pdf`
- Le template est conservé même après désinstallation de l'application.
- Si un template est présent dans le dossier app (`Templates/bon de commande V1.pdf`),
  il est copié automatiquement dans le dossier utilisateur au démarrage.
- Les boutons **Ouvrir le dossier Templates** et **Choisir un template…** permettent de corriger rapidement.
- Le bouton **Ouvrir le log** affiche le fichier de log utilisateur `%LOCALAPPDATA%\BDC Generator\logs\bdc_generator.log`.
- `NeedAppearances` activé (Adobe Reader)
- **Ne jamais aplatir** le PDF (formulaire éditable)

### Numéro de devis (SRX)
- Extraction ancrée sur la ligne `DEVIS N° SRX...`
- Remplissage:
  - `bdc_devis_annee_mois = référence complète SRX`
  - `bdc_devis_type = AFF`
  - `bdc_devis_num = num` (6 chiffres)

### Date
- `bdc_date_commande` = date du jour (pas la date du devis)

### Référence affaire
- `bdc_ref_affaire` = dernière ligne non vide juste avant la date du devis

### Client
- Bloc client entre `Code client : ...` et `Contact commercial :`
- `bdc_client_nom` = première ligne non numérique du bloc
- `bdc_client_adresse` = lignes suivantes (multi-lignes OK)

### Commercial
- `bdc_commercial_nom` = ligne juste après "Contact commercial" (fallback : "BUCHE Kevin")

### Détection de pose
- Détecter la pose vendue **uniquement** si une ligne contient `Pose au ...` avec un montant
  (sur la même ligne ou la ligne adjacente).
- Si le texte est illisible, statut **À vérifier** et valeur par défaut = non (log affiché).
- Colonne **Origine** :
  - **Auto** : détection automatique.
  - **Forcé** : l'utilisateur a modifié le checkbox.
  - **À vérifier** : texte illisible, vérifier manuellement.

### Si pose vendue
- `bdc_livraison_bloc` = adresse dépôt configurée dans l'UI
- checkbox `bdc_chk_livraison_poseur` cochée
- checkbox `bdc_chk_livraison_client` décochée
- `bdc_montant_pose_ht` rempli (autoliquidation cochée si non vide)

### Si pas de pose
- `bdc_livraison_bloc` = "idem"
- checkbox `bdc_chk_livraison_client` cochée
- checkbox `bdc_chk_livraison_poseur` décochée
- `bdc_montant_pose_ht` vide

### Montants extraits
- Montants avant libellés :
  - `PRIX DE LA FOURNITURE HT`
  - `PRIX PRESTATIONS ET SERVICES HT`
  - `TOTAL HORS TAXE`
- Remplissage:
  - `bdc_montant_fourniture_ht = fourniture_ht`
  - `bdc_total_ht = total_ht`

### Champs techniques
- `bdc_esc_gamme` = valeur de `-Modèle : ...`
- `bdc_esc_finition_marches` = valeur de `-Marche : ...`
- `bdc_esc_essence` = texte avant le premier `-` dans la finition marche

### Poteau / TPA
- Si ligne `-Poteau ... (TPA)` :
  - `bdc_esc_tete_de_poteau = "TPA"`
- `bdc_esc_poteaux_depart` vide si poteau standard (`Poteau droit ...`)

### Nom des fichiers BDC
- Format : `CDE {NOM_CLIENT} Ref {REF_AFFAIRE}.pdf`
- Remplacement des caractères interdits Windows `\ / : * ? " < > |`
- Normalisation des espaces
- Longueur totale max : 150 caractères
- Si ref affaire vide : `Ref INCONNUE`

### Debug
- Variable d'environnement `BDC_DEBUG=1` pour tracer les valeurs extraites dans l'UI

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
