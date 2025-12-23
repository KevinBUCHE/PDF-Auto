import os
import re
import shutil
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from services.devis_parser import DevisParser
from services.pose_detector import PoseDetector
from services.bdc_filler import BdcFiller
from utils.logging_util import append_log
from utils.paths import (
    get_log_file_path,
    get_template_path,
    get_user_templates_dir,
)

APP_NAME = "BDC Generator"


@dataclass
class DevisItem:
    path: Path
    data: dict
    pose_sold: bool
    pose_source: str
    auto_pose_sold: bool
    auto_pose_status: str


class DropTable(QtWidgets.QTableWidget):
    files_dropped = QtCore.Signal(list)

    def __init__(self, parent=None):
        super().__init__(0, 5, parent)
        self.setAcceptDrops(True)
        self.setHorizontalHeaderLabels(
            ["Fichier devis", "Pose vendue", "Forcer", "Origine", "Statut"]
        )
        header = self.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.Stretch)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            paths = []
            for url in event.mimeData().urls():
                path = Path(url.toLocalFile())
                if path.suffix.lower() == ".pdf":
                    paths.append(path)
            if paths:
                self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(900, 600)

        self.devis_items = {}
        debug_mode = bool(os.getenv("BDC_DEBUG"))
        self.parser = DevisParser(debug=debug_mode)
        self.pose_detector = PoseDetector()
        self.bdc_filler = BdcFiller(logger=self.log, debug=debug_mode)
        self.base_dir = self._resolve_base_dir()
        self.templates_dir = get_user_templates_dir(APP_NAME)
        self.template_path = get_template_path(APP_NAME)
        self.bundled_template_path = self.base_dir / "Templates" / "bon de commande V1.pdf"
        self.log_file_path = get_log_file_path(APP_NAME)
        self._loading_table = False

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)

        template_layout = QtWidgets.QHBoxLayout()
        self.template_status = QtWidgets.QLabel()
        self.open_templates_button = QtWidgets.QPushButton("Ouvrir le dossier Templates")
        self.choose_template_button = QtWidgets.QPushButton("Choisir un template…")
        self.open_log_button = QtWidgets.QPushButton("Ouvrir le log")
        self.open_templates_button.clicked.connect(self.open_templates_folder)
        self.choose_template_button.clicked.connect(self.choose_template_file)
        self.open_log_button.clicked.connect(self.open_log_file)
        template_layout.addWidget(self.template_status)
        template_layout.addStretch()
        template_layout.addWidget(self.open_templates_button)
        template_layout.addWidget(self.choose_template_button)
        template_layout.addWidget(self.open_log_button)
        layout.addLayout(template_layout)

        info_label = QtWidgets.QLabel(
            "Glissez-déposez vos devis PDF SRX*. La pose est détectée automatiquement "
            "(colonne Origine). Cochez “Forcer” pour ajuster la pose."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self.table = DropTable()
        self.table.files_dropped.connect(self.handle_files_dropped)
        self.table.itemChanged.connect(self.handle_item_changed)
        layout.addWidget(self.table)

        buttons_layout = QtWidgets.QHBoxLayout()
        self.generate_button = QtWidgets.QPushButton("Générer les BDC")
        self.generate_button.clicked.connect(self.generate_bdcs)
        buttons_layout.addWidget(self.generate_button)
        layout.addLayout(buttons_layout)

        self.logs = QtWidgets.QTextEdit()
        self.logs.setReadOnly(True)
        layout.addWidget(self.logs)

        self.setCentralWidget(central)
        self.refresh_template_status(log_missing=True)

    def log(self, message):
        self.logs.append(message)
        append_log(self.log_file_path, message)

    def log_to_file(self, message):
        append_log(self.log_file_path, message)

    def _resolve_base_dir(self) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).parent
        return Path(__file__).resolve().parent

    def _template_status_text(self, exists: bool) -> str:
        if exists:
            return "Template: OK"
        return "Template: MANQUANT (utilisez 'Choisir un template…')"

    def refresh_template_status(self, log_missing: bool = False):
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        if not self.template_path.exists() and self.bundled_template_path.exists():
            try:
                shutil.copy2(self.bundled_template_path, self.template_path)
                self.log(f"Template copié depuis l'application: {self.template_path}")
            except Exception as exc:  # pylint: disable=broad-except
                self.log(f"Erreur copie template embarqué: {exc}")
        exists = self.template_path.exists()
        self.template_status.setText(self._template_status_text(exists))
        color = "#1b8f1b" if exists else "#b00020"
        self.template_status.setStyleSheet(f"font-weight: 600; color: {color};")
        self.generate_button.setEnabled(exists)
        if not exists and log_missing:
            self.log(
                "Template manquant: placez 'bon de commande V1.pdf' dans le dossier Templates utilisateur "
                "ou utilisez 'Choisir un template…'."
            )

    def open_templates_folder(self):
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        opened = QtGui.QDesktopServices.openUrl(
            QtCore.QUrl.fromLocalFile(str(self.templates_dir))
        )
        if not opened:
            self.log("Impossible d'ouvrir le dossier Templates.")

    def open_log_file(self):
        self.log_file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_file_path.exists():
            self.log_file_path.touch()
        opened = QtGui.QDesktopServices.openUrl(
            QtCore.QUrl.fromLocalFile(str(self.log_file_path))
        )
        if not opened:
            self.log("Impossible d'ouvrir le fichier log.")


    def choose_template_file(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Choisir un template",
            str(self.templates_dir),
            "PDF (*.pdf)",
        )
        if not file_path:
            return
        self.install_template(Path(file_path))

    def _is_template_file(self, path: Path) -> bool:
        normalized = re.sub(r"[\s_-]+", "", path.name.lower())
        return normalized == "bondecommandev1.pdf"

    def _is_srx_pdf(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf" and path.name.upper().startswith("SRX")

    def handle_files_dropped(self, paths):
        for path in paths:
            if self._is_template_file(path):
                self.install_template(path)
                continue
            if not self._is_srx_pdf(path):
                self.log(f"Fichier ignoré (attendu SRX*.pdf): {path.name}")
                continue
            if path in self.devis_items:
                self.log(f"Déjà ajouté: {path}")
                continue
            try:
                data = self.parser.parse(path)
                if data.get("parse_warning"):
                    self.log(f"{path.name}: {data['parse_warning']}")
                pose_sold, pose_amount, pose_status = self.pose_detector.detect_pose(data["lines"])
                if pose_amount:
                    data["pose_amount"] = pose_amount
                data["pose_sold"] = pose_sold
                self.add_row(path, pose_sold, pose_status)
                self.devis_items[path] = DevisItem(
                    path=path,
                    data=data,
                    pose_sold=pose_sold,
                    pose_source="auto" if pose_status == "auto" else "unreadable",
                    auto_pose_sold=pose_sold,
                    auto_pose_status=pose_status,
                )
                if pose_status == "unreadable":
                    self.log(f"{path.name}: détection pose impossible, valeur par défaut = non.")
                self.log(f"Ajouté: {path.name} (pose: {'oui' if pose_sold else 'non'})")
                if "SRX2511AFF037501" in path.name:
                    self.log(
                        "[TEST] SRX2511AFF037501 client_nom="
                        f"{data.get('client_nom')!r} (attendu 'BERVAL MAISONS')"
                    )
                    self.log(
                        "[TEST] SRX2511AFF037501 ref_affaire="
                        f"{data.get('ref_affaire')!r}"
                    )
                    self.log(
                        "[TEST] SRX2511AFF037501 fourniture_ht="
                        f"{data.get('fourniture_ht')!r} (attendu '4 894,08')"
                    )
                    self.log(
                        "[TEST] SRX2511AFF037501 prestations_ht="
                        f"{data.get('prestations_ht')!r} (attendu '1 159,12')"
                    )
                for entry in data.get("debug", []):
                    self.log(f"[debug] {path.name}: {entry}")
            except Exception as exc:  # pylint: disable=broad-except
                self.log(f"Erreur lecture {path.name}: {exc}")

    def install_template(self, source: Path):
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(source, self.template_path)
            self.log(f"Template copié: {self.template_path}")
            self.refresh_template_status()
        except Exception as exc:  # pylint: disable=broad-except
            self.log(f"Erreur copie template: {exc}")

    def add_row(self, path, pose_sold, pose_status):
        row = self.table.rowCount()
        self._loading_table = True
        self.table.insertRow(row)
        file_item = QtWidgets.QTableWidgetItem(str(path))
        file_item.setFlags(file_item.flags() ^ QtCore.Qt.ItemIsEditable)
        self.table.setItem(row, 0, file_item)

        pose_item = QtWidgets.QTableWidgetItem()
        pose_item.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
        pose_item.setCheckState(QtCore.Qt.Checked if pose_sold else QtCore.Qt.Unchecked)
        self.table.setItem(row, 1, pose_item)

        force_item = QtWidgets.QTableWidgetItem()
        force_item.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
        force_item.setCheckState(QtCore.Qt.Unchecked)
        self.table.setItem(row, 2, force_item)

        self._set_pose_editable(row, False)

        origin_item = QtWidgets.QTableWidgetItem(
            "Auto" if pose_status == "auto" else "À vérifier"
        )
        origin_item.setFlags(origin_item.flags() ^ QtCore.Qt.ItemIsEditable)
        origin_item.setToolTip(origin_item.text())
        self.table.setItem(row, 3, origin_item)

        status_item = QtWidgets.QTableWidgetItem("En attente")
        status_item.setFlags(status_item.flags() ^ QtCore.Qt.ItemIsEditable)
        self.table.setItem(row, 4, status_item)
        self._loading_table = False

    def _set_pose_editable(self, row: int, enabled: bool):
        pose_item = self.table.item(row, 1)
        if not pose_item:
            return
        flags = pose_item.flags()
        if enabled:
            pose_item.setFlags(flags | QtCore.Qt.ItemIsEnabled)
        else:
            pose_item.setFlags(flags & ~QtCore.Qt.ItemIsEnabled)

    def handle_item_changed(self, item):
        if self._loading_table:
            return
        if item.column() not in (1, 2):
            return
        file_item = self.table.item(item.row(), 0)
        origin_item = self.table.item(item.row(), 3)
        force_item = self.table.item(item.row(), 2)
        if not file_item or not origin_item:
            return
        path = Path(file_item.text())
        devis_item = self.devis_items.get(path)
        if not devis_item:
            return
        if item.column() == 2:
            forced = item.checkState() == QtCore.Qt.Checked
            self._set_pose_editable(item.row(), forced)
            if forced:
                origin_item.setText("Forcé")
                origin_item.setToolTip("Forcé")
            else:
                pose_item = self.table.item(item.row(), 1)
                if pose_item:
                    pose_item.setCheckState(
                        QtCore.Qt.Checked
                        if devis_item.auto_pose_sold
                        else QtCore.Qt.Unchecked
                    )
                devis_item.pose_sold = devis_item.auto_pose_sold
                devis_item.pose_source = "auto"
                devis_item.data["pose_sold"] = devis_item.auto_pose_sold
                origin_text = (
                    "Auto"
                    if devis_item.auto_pose_status == "auto"
                    else "À vérifier"
                )
                origin_item.setText(origin_text)
                origin_item.setToolTip(origin_text)
            return
        if force_item and force_item.checkState() != QtCore.Qt.Checked:
            return
        pose_sold = item.checkState() == QtCore.Qt.Checked
        devis_item.pose_sold = pose_sold
        devis_item.pose_source = "forced"
        devis_item.data["pose_sold"] = pose_sold
        origin_item.setText("Forcé")
        origin_item.setToolTip("Forcé")

    def generate_bdcs(self):
        if not self.template_path.exists():
            self.refresh_template_status(log_missing=True)
            return
        output_dir = self.base_dir / "BDC_Output"
        output_dir.mkdir(exist_ok=True)

        for row in range(self.table.rowCount()):
            file_item = self.table.item(row, 0)
            pose_item = self.table.item(row, 1)
            status_item = self.table.item(row, 4)
            if not file_item:
                continue
            path = Path(file_item.text())
            item = self.devis_items.get(path)
            if not item:
                continue
            pose_sold = pose_item.checkState() == QtCore.Qt.Checked
            item.pose_sold = pose_sold
            item.data["pose_sold"] = pose_sold
            try:
                output_name = self._build_output_name(item.data)
                output_path = output_dir / output_name
                self.bdc_filler.fill(self.template_path, item.data, output_path)
                status_item.setText("OK")
                self.log(f"BDC généré: {output_path}")
            except Exception as exc:  # pylint: disable=broad-except
                short_message = str(exc).strip() or exc.__class__.__name__
                status_item.setText(f"Erreur: {short_message}")
                self.log(
                    f"Erreur génération {path.name}: {exc.__class__.__name__}: {short_message}"
                )
                self.log_to_file(traceback.format_exc())

    def _build_output_name(self, data: dict) -> str:
        client_nom = data.get("client_nom", "").strip() or "CLIENT"
        ref_affaire = data.get("ref_affaire", "").strip() or "Ref INCONNUE"
        base = f"CDE {client_nom} Ref {ref_affaire}"
        base = re.sub(r'[\\/:*?"<>|]', " ", base)
        base = re.sub(r"\s+", " ", base).strip()
        max_base = 150 - len(".pdf")
        if len(base) > max_base:
            base = base[:max_base].rstrip()
        return f"{base}.pdf"


def main():
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
