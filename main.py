import os
import re
import shutil
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from services.rule_based_parser import RuleBasedParser
from services.bdc_filler import BdcFiller
from services.data_normalizer import normalize_extracted_data
from services.gemini_extractor import DEFAULT_GEMINI_MODEL, GeminiExtractor
from services.address_sanitizer import has_riaux_pollution
from services.validator import validate_and_fix
from utils.logging_util import append_log
from utils.paths import (
    get_log_file_path,
    get_template_path,
    get_user_templates_dir,
)
from utils.settings_service import SettingsService

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
            ["Fichier devis", "Pose vendue", "Forcer", "Auto pose", "Statut"]
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
        self.settings = QtCore.QSettings("PDF-Auto", APP_NAME)
        self.parser = DevisParser(debug=bool(os.getenv("BDC_DEBUG")))
        self.pose_detector = PoseDetector()
        self.bdc_filler = BdcFiller(logger=self.log)
        self.base_dir = self._resolve_base_dir()
        self.templates_dir = get_user_templates_dir(APP_NAME)
        self.template_path = get_template_path(APP_NAME)
        self.bundled_template_path = self.base_dir / "Templates" / "bon de commande V1.pdf"
        self.log_file_path = get_log_file_path(APP_NAME)
        self.settings_service = SettingsService(APP_NAME)
        self.settings = self.settings_service.load()
        self.gemini_api_key = self.settings.get("gemini_api_key", "")
        self.gemini_model = self.settings.get("gemini_model", DEFAULT_GEMINI_MODEL)
        self.gemini_enabled = bool(self.settings.get("gemini_enabled"))
        self.gemini_extractor: GeminiExtractor | None = None
        self._loading_table = False

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)

        template_layout = QtWidgets.QHBoxLayout()
        self.template_status = QtWidgets.QLabel()
        self.open_templates_button = QtWidgets.QPushButton("Ouvrir le dossier Templates")
        self.choose_template_button = QtWidgets.QPushButton("Choisir un template…")
        self.open_log_button = QtWidgets.QPushButton("Ouvrir le log")
        self.gemini_settings_button = QtWidgets.QPushButton("Paramètres Gemini")
        self.gemini_toggle = QtWidgets.QLabel()
        self.open_templates_button.clicked.connect(self.open_templates_folder)
        self.choose_template_button.clicked.connect(self.choose_template_file)
        self.open_log_button.clicked.connect(self.open_log_file)
        self.gemini_settings_button.clicked.connect(self.open_gemini_settings)
        template_layout.addWidget(self.template_status)
        template_layout.addStretch()
        template_layout.addWidget(self.open_templates_button)
        template_layout.addWidget(self.choose_template_button)
        template_layout.addWidget(self.open_log_button)
        template_layout.addWidget(self.gemini_settings_button)
        template_layout.addWidget(self.gemini_toggle)
        layout.addLayout(template_layout)

        info_label = QtWidgets.QLabel(
            "Glissez-déposez vos devis PDF SRX*. La pose est détectée automatiquement "
            "(colonne Auto pose). Cochez “Forcer” pour ajuster la pose."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        depot_layout = QtWidgets.QHBoxLayout()
        depot_label = QtWidgets.QLabel("Adresse dépôt (utilisée si pose vendue)")
        depot_label.setMinimumWidth(250)
        self.depot_text = QtWidgets.QPlainTextEdit()
        self.depot_text.setPlaceholderText("Ex: Dépôt ...")
        self.depot_text.setFixedHeight(80)
        depot_layout.addWidget(depot_label)
        depot_layout.addWidget(self.depot_text)
        layout.addLayout(depot_layout)

        self.table = DropTable()
        self.table.files_dropped.connect(self.handle_files_dropped)
        self.table.itemChanged.connect(self.handle_item_changed)
        layout.addWidget(self.table)

        buttons_layout = QtWidgets.QHBoxLayout()
        self.generate_button = QtWidgets.QPushButton("Générer les BDC")
        self.clear_button = QtWidgets.QPushButton("Vider la liste")
        self.export_debug_button = QtWidgets.QPushButton("Exporter debug")
        self.generate_button.clicked.connect(self.generate_bdcs)
        self.clear_button.clicked.connect(self.clear_list)
        self.export_debug_button.clicked.connect(self.export_debug)
        buttons_layout.addWidget(self.generate_button)
        buttons_layout.addWidget(self.clear_button)
        buttons_layout.addWidget(self.export_debug_button)
        layout.addLayout(buttons_layout)

        self.logs = QtWidgets.QTextEdit()
        self.logs.setReadOnly(True)
        layout.addWidget(self.logs)

        self.setCentralWidget(central)
        self.refresh_template_status(log_missing=True)
        self._load_settings()

    def log(self, message):
        self.logs.append(message)
        append_log(self.log_file_path, message)

    def log_to_file(self, message):
        append_log(self.log_file_path, message)

    def _load_settings(self):
        depot_value = self.settings.value("depot_adresse", "")
        if depot_value:
            self.depot_text.setPlainText(str(depot_value))

    def _save_settings(self):
        self.settings.setValue("depot_adresse", self.depot_text.toPlainText())

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

    def export_debug(self):
        row = self.table.currentRow()
        if row < 0:
            self.log("Sélectionnez un devis pour exporter le debug.")
            return
        file_item = self.table.item(row, 0)
        if not file_item:
            self.log("Impossible de trouver le devis sélectionné.")
            return
        path = Path(file_item.text())
        exported_path = self.parser.export_debug(path)
        if not exported_path:
            self.log(f"Aucune donnée debug disponible pour {path.name}.")
            return
        self.log(f"Debug exporté: {exported_path}")

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

    def _load_gemini_settings(self):
        self.settings = self.settings_service.load()
        self.gemini_api_key = str(self.settings.get("gemini_api_key", "") or "")
        self.gemini_model = str(
            self.settings.get("gemini_model", DEFAULT_GEMINI_MODEL) or DEFAULT_GEMINI_MODEL
        )
        self.gemini_enabled = bool(self.settings.get("gemini_enabled"))
        self.gemini_extractor = None
        state = "activé" if self.gemini_enabled and self.gemini_api_key else "désactivé"
        self.gemini_toggle.setText(f"Gemini: {state}")

    def _get_gemini_extractor(self) -> GeminiExtractor | None:
        if self.gemini_extractor is not None:
            return self.gemini_extractor
        if not self.gemini_api_key:
            return None
        try:
            self.gemini_extractor = GeminiExtractor(
                api_key=self.gemini_api_key,
                model=self.gemini_model,
                logger=self.log,
            )
        except Exception as exc:  # pylint: disable=broad-except
            self.log(f"Erreur initialisation Gemini: {exc}")
            self.gemini_extractor = None
        return self.gemini_extractor

    def _merge_data(self, base: dict, override: dict | None) -> dict:
        if not override:
            return base
        merged = dict(base)
        for key, value in override.items():
            if value in ("", None, []):
                continue
            merged[key] = value
        return merged

    def _extract_data(self, path: Path) -> tuple[dict, str]:
        data = self.parser.parse(path)
        pose_status = "rule"
        data, validation_warnings = validate_and_fix(data)
        for warning in validation_warnings:
            self.log(f"Validation: {warning}")
        if validation_warnings:
            existing = data.get("parse_warning", "")
            data["parse_warning"] = " ".join([existing, *validation_warnings]).strip()

        extractor = self._get_gemini_extractor() if self.gemini_enabled else None
        critical_keys = ["client_nom", "ref_affaire", "devis_num", "devis_annee_mois", "fourniture_ht", "prestations_ht", "total_ht"]
        needs_fallback = extractor and any(not data.get(key) for key in critical_keys)
        if needs_fallback and self.gemini_api_key:
            try:
                text = "\n".join(data.get("lines", []))
                result = extractor.extract_from_text(text)
                candidate = self._merge_data(data, result.data)
                if has_riaux_pollution(candidate):
                    self.log("Gemini a renvoyé une adresse RIAUX: relance avec avertissement.")
                    result = extractor.extract_from_text(
                        text,
                        retry_note="Tu as inclus l’adresse RIAUX, recommence sans aucune donnée RIAUX côté client.",
                    )
                    candidate = self._merge_data(data, result.data)
                candidate, val_w = validate_and_fix(candidate)
                data = candidate
                for warning in val_w:
                    self.log(f"Validation: {warning}")
                if val_w:
                    existing = data.get("parse_warning", "")
                    data["parse_warning"] = " ".join([existing, *val_w]).strip()
                pose_status = "gemini"
            except Exception as exc:  # pylint: disable=broad-except
                self.log(f"Gemini ignoré pour {path.name}: {exc}")

        data = normalize_extracted_data(data)
        if data.get("parse_warning"):
            self.log(f"{path.name}: {data['parse_warning']}")
        return data, pose_status

    def _origin_text(self, pose_status: str) -> str:
        if pose_status == "gemini":
            return "Gemini"
        if pose_status == "auto":
            return "Auto"
        return "À vérifier"

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
                data, pose_status = self._extract_data(path)
                pose_sold = bool(data.get("pose_sold"))
                self.add_row(path, pose_sold, pose_status)
                self.devis_items[path] = DevisItem(
                    path=path,
                    data=data,
                    pose_sold=pose_sold,
                    pose_source=pose_status,
                    auto_pose_sold=pose_sold,
                    auto_pose_status=pose_status,
                )
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

        origin_item = QtWidgets.QTableWidgetItem(self._origin_text(pose_status))
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
                devis_item.pose_source = devis_item.auto_pose_status
                devis_item.data["pose_sold"] = devis_item.auto_pose_sold
                origin_text = self._origin_text(devis_item.auto_pose_status)
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

    def clear_list(self):
        self.table.setRowCount(0)
        self.devis_items = {}
        self.log("Liste vidée.")

    def generate_bdcs(self):
        if not self.template_path.exists():
            self.refresh_template_status(log_missing=True)
            return
        output_dir = Path.home() / "Desktop" / "BDC_Output"
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
                item.data["depot_adresse"] = self.depot_text.toPlainText().strip()
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
        ref_affaire = self._clean_ref_affaire(data.get("ref_affaire", ""))
        ref_affaire = ref_affaire.strip() or "Ref INCONNUE"
        base = f"CDE {client_nom} Ref {ref_affaire}"
        base = re.sub(r'[\\/:*?"<>|]', " ", base)
        base = re.sub(r"\s+", " ", base).strip()
        max_base = 150 - len(".pdf")
        if len(base) > max_base:
            base = base[:max_base].rstrip()
        return f"{base}.pdf"

    def closeEvent(self, event):
        self._save_settings()
        super().closeEvent(event)


def main():
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
