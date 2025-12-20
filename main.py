import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6 import QtCore, QtWidgets

from services.devis_parser import DevisParser
from services.pose_detector import PoseDetector
from services.bdc_filler import BdcFiller

APP_NAME = "BDC Generator"


@dataclass
class DevisItem:
    path: Path
    data: dict
    pose_sold: bool


class DropTable(QtWidgets.QTableWidget):
    files_dropped = QtCore.Signal(list)

    def __init__(self, parent=None):
        super().__init__(0, 3, parent)
        self.setAcceptDrops(True)
        self.setHorizontalHeaderLabels(["Fichier devis", "Pose vendue", "Statut"])
        header = self.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)

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
        self.parser = DevisParser(debug=bool(os.getenv("BDC_DEBUG")))
        self.pose_detector = PoseDetector()
        self.bdc_filler = BdcFiller()

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)

        info_label = QtWidgets.QLabel(
            "Glissez-déposez vos devis PDF ci-dessous. Chaque ligne propose un toggle AVEC/SANS pose."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self.table = DropTable()
        self.table.files_dropped.connect(self.handle_files_dropped)
        layout.addWidget(self.table)

        buttons_layout = QtWidgets.QHBoxLayout()
        self.generate_button = QtWidgets.QPushButton("Générer les BDC")
        self.clear_button = QtWidgets.QPushButton("Vider la liste")
        self.generate_button.clicked.connect(self.generate_bdcs)
        self.clear_button.clicked.connect(self.clear_list)
        buttons_layout.addWidget(self.generate_button)
        buttons_layout.addWidget(self.clear_button)
        layout.addLayout(buttons_layout)

        self.logs = QtWidgets.QTextEdit()
        self.logs.setReadOnly(True)
        layout.addWidget(self.logs)

        self.setCentralWidget(central)

    def log(self, message):
        self.logs.append(message)

    def handle_files_dropped(self, paths):
        for path in paths:
            if path in self.devis_items:
                self.log(f"Déjà ajouté: {path}")
                continue
            try:
                data = self.parser.parse(path)
                pose_sold, pose_amount = self.pose_detector.detect_pose(data["lines"])
                if pose_amount:
                    data["pose_amount"] = pose_amount
                data["pose_sold"] = pose_sold
                self.add_row(path, pose_sold)
                self.devis_items[path] = DevisItem(path=path, data=data, pose_sold=pose_sold)
                self.log(f"Ajouté: {path.name} (pose: {'oui' if pose_sold else 'non'})")
                for entry in data.get("debug", []):
                    self.log(f"[debug] {path.name}: {entry}")
            except Exception as exc:  # pylint: disable=broad-except
                self.log(f"Erreur lecture {path.name}: {exc}")

    def add_row(self, path, pose_sold):
        row = self.table.rowCount()
        self.table.insertRow(row)
        file_item = QtWidgets.QTableWidgetItem(str(path))
        file_item.setFlags(file_item.flags() ^ QtCore.Qt.ItemIsEditable)
        self.table.setItem(row, 0, file_item)

        checkbox = QtWidgets.QTableWidgetItem()
        checkbox.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
        checkbox.setCheckState(QtCore.Qt.Checked if pose_sold else QtCore.Qt.Unchecked)
        self.table.setItem(row, 1, checkbox)

        status_item = QtWidgets.QTableWidgetItem("En attente")
        status_item.setFlags(status_item.flags() ^ QtCore.Qt.ItemIsEditable)
        self.table.setItem(row, 2, status_item)

    def clear_list(self):
        self.table.setRowCount(0)
        self.devis_items = {}
        self.log("Liste vidée.")

    def generate_bdcs(self):
        template_path = Path("Templates") / "bon de commande V1.pdf"
        if not template_path.exists():
            self.log(
                "Template manquant: placez 'Templates/bon de commande V1.pdf' puis relancez."
            )
            return
        output_dir = Path("BDC_Output")
        output_dir.mkdir(exist_ok=True)

        for row in range(self.table.rowCount()):
            file_item = self.table.item(row, 0)
            pose_item = self.table.item(row, 1)
            status_item = self.table.item(row, 2)
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
                self.bdc_filler.fill(template_path, item.data, output_path)
                status_item.setText(f"OK -> {output_path}")
                self.log(f"BDC généré: {output_path}")
            except Exception as exc:  # pylint: disable=broad-except
                status_item.setText("Erreur")
                self.log(f"Erreur génération {path.name}: {exc}")

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
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
