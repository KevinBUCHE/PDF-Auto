BDC Generator (build portable)

1) Télécharger l'archive `bdc-generator-portable.zip` produite par le workflow GitHub Actions.
2) Décompresser l'archive. Vous obtenez un dossier `BDC Generator` contenant l'exécutable et un dossier `Templates` vide.
3) Copier votre template utilisateur dans l'un des chemins suivants :
   - <dossier_exe>\Templates\bon de commande V1.pdf
   - %APPDATA%\BDC Generator\Templates\bon de commande V1.pdf
4) Lancer l'application :
   - Double-cliquez sur `BDC Generator.exe`
   - ou exécutez `RUN.bat`
5) Sélectionner un devis SRX et cliquer sur "Générer BDC". La sortie `<nom_devis>_BDC.pdf` est placée à côté du devis.

Dépendances : aucune DLL Qt. L'application est construite avec PyInstaller (Tkinter uniquement).
