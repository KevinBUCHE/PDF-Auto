import json
from pathlib import Path
import unittest

from services.devis_parser import DevisParser


class DevisParserTests(unittest.TestCase):
    def setUp(self):
        self.parser = DevisParser(debug=True)

    def _sample_lines(self):
        return [
            "DEVIS N° SRX2511AFF037501",
            "Réf affaire : AFF-42",
            "Code client",
            "RIAUX",
            "Client Maison",
            "12 rue Exemple",
            "77100 MAREUIL",
            "Contact commercial",
            "Jean Commercial",
            "FINITION",
            "- Contremarche : Sans",
            "- Structure : limon central",
            "- Marche : Chêne huilé",
            "- Remplissage rampant : Barreaudage",
            "-Modèle : DIZA",
            "PRIX DE LA FOURNITURE HT : 1 000,00",
            "PRIX PRESTATIONS ET SERVICES HT : 200,00",
        ]

    def test_client_name_skips_banned_and_uses_next_line(self):
        data = self.parser._parse_lines(self._sample_lines(), Path("dummy.pdf"))
        self.assertEqual(data["client_nom"], "Client Maison")
        self.assertEqual(data["client_cp"], "77100")
        self.assertEqual(data["client_ville"], "MAREUIL")
        self.assertFalse(data["client_nom"].lower().startswith("riaux"))

    def test_bdc_mapping_matches_fixture(self):
        expected_path = Path("tests/fixtures/basic/expected.json")
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        data = self.parser._parse_lines(self._sample_lines(), Path("dummy.pdf"))
        for key, value in expected.items():
            self.assertEqual(data.get(key), value, f"Mismatch on {key}")


if __name__ == "__main__":
    unittest.main()
