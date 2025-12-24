"""
Unit tests for devis_parser.py

Tests the robust extraction of CLIENT / COMMERCIAL / RÉF AFFAIRE / MONTANTS from SRX PDFs,
and validates that RIAUX information is never injected into client fields.
"""

import unittest
from pathlib import Path

from services.devis_parser import DevisParser
from services.sanitize import is_riaux_contaminated, validate_client_extraction


class TestDevisParser(unittest.TestCase):
    """Test cases for DevisParser"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.parser = DevisParser(debug=False)
        self.repo_root = Path(__file__).resolve().parents[1]
        
    def test_parser_initialization(self):
        """Test that parser initializes correctly"""
        parser = DevisParser()
        self.assertIsNotNone(parser)
        self.assertFalse(parser.debug)
        
        parser_debug = DevisParser(debug=True)
        self.assertTrue(parser_debug.debug)
    
    def test_normalize_amount(self):
        """Test amount normalization"""
        # Test various amount formats
        self.assertEqual(self.parser._normalize_amount("1 234,56"), "1 234,56")
        self.assertEqual(self.parser._normalize_amount("1234,56"), "1234,56")
        self.assertEqual(self.parser._normalize_amount("1.234,56"), "1234,56")  # Dot removed when both present
        self.assertEqual(self.parser._normalize_amount("1234.56"), "1234,56")  # Dot converted to comma
    
    def test_clean_line(self):
        """Test line cleaning"""
        # Test whitespace normalization
        self.assertEqual(self.parser._clean_line("  test   line  "), "test line")
        self.assertEqual(self.parser._clean_line("test\u202fline"), "test line")
        self.assertEqual(self.parser._clean_line(""), "")
    
    def test_has_letters(self):
        """Test letter detection"""
        self.assertTrue(self.parser._has_letters("Test"))
        self.assertTrue(self.parser._has_letters("Test123"))
        self.assertFalse(self.parser._has_letters("123"))
        self.assertFalse(self.parser._has_letters(""))
    
    def test_extract_after_colon(self):
        """Test value extraction after colon"""
        self.assertEqual(self.parser._extract_after_colon("Label: Value"), "Value")
        self.assertEqual(self.parser._extract_after_colon("Label:Value"), "Value")
        self.assertEqual(self.parser._extract_after_colon("No colon"), "")
    
    def test_detect_pose(self):
        """Test pose detection in lines"""
        lines_with_pose = [
            "PRIX DE LA FOURNITURE HT : 5000,00",
            "PRESTATIONS",
            "Pose escalier"
        ]
        self.assertTrue(self.parser._detect_pose(lines_with_pose))
        
        lines_without_pose = [
            "PRIX DE LA FOURNITURE HT : 5000,00",
            "PRESTATIONS",
            "Livraison"
        ]
        self.assertFalse(self.parser._detect_pose(lines_without_pose))
    
    def test_no_riaux_contamination(self):
        """Test that parser never returns RIAUX information in client fields"""
        # Mock data that might contain RIAUX info
        test_lines = [
            "Code client : 12345",
            "CLIENT TEST",
            "12 rue de Test",
            "75000 PARIS",
            "Contact commercial : BUCHE Kevin",
            "RIAUX SAS",
            "VAUGARNY",
            "35560 BAZOUGES LA PEROUSE"
        ]
        
        client_details = self.parser._find_client_details(test_lines)
        
        # Verify no RIAUX contamination in client fields
        for key, value in client_details.items():
            if value:
                self.assertFalse(
                    is_riaux_contaminated(value),
                    f"RIAUX contamination detected in {key}: {value}"
                )
    
    def test_fixture_parsing(self):
        """Test parsing of fixture PDF if available"""
        fixture_dir = self.repo_root / "fixtures" / "SRX2507AFF046101"
        if not fixture_dir.exists():
            self.skipTest("Fixture directory not found")
        
        pdfs = list(fixture_dir.glob("*.pdf"))
        if not pdfs:
            self.skipTest("No PDF found in fixture")
        
        pdf_path = pdfs[0]
        data = self.parser.parse(pdf_path)
        
        # Basic structure checks
        self.assertIn("client_nom", data)
        self.assertIn("commercial_nom", data)
        self.assertIn("ref_affaire", data)
        self.assertIn("devis_num", data)
        self.assertIn("fourniture_ht", data)
        self.assertIn("prestations_ht", data)
        
        # Validate no RIAUX contamination
        warnings = validate_client_extraction(data)
        self.assertEqual(len(warnings), 0, f"RIAUX contamination warnings: {warnings}")


class TestSanitization(unittest.TestCase):
    """Test cases for RIAUX sanitization"""
    
    def test_riaux_patterns_detected(self):
        """Test that RIAUX patterns are correctly detected"""
        # Test RIAUX address detection
        self.assertTrue(is_riaux_contaminated("VAUGARNY"))
        self.assertTrue(is_riaux_contaminated("35560 BAZOUGES LA PEROUSE"))
        self.assertTrue(is_riaux_contaminated("BAZOUGES-LA-PÉROUSE"))
        
        # Test RIAUX phone detection
        self.assertTrue(is_riaux_contaminated("02 99 98 04 50"))
        self.assertTrue(is_riaux_contaminated("02.99.98.04.50"))
        
        # Test company identifiers
        self.assertTrue(is_riaux_contaminated("RCS RENNES 123456"))
        self.assertTrue(is_riaux_contaminated("SIRET 12345678901234"))
        self.assertTrue(is_riaux_contaminated("GROUPE RIAUX"))
        
        # Test clean values
        self.assertFalse(is_riaux_contaminated("CLIENT TEST"))
        self.assertFalse(is_riaux_contaminated("75000 PARIS"))
        self.assertFalse(is_riaux_contaminated("01 23 45 67 89"))
    
    def test_validate_client_extraction(self):
        """Test client extraction validation"""
        # Clean data
        clean_data = {
            "client_nom": "BERVAL MAISONS",
            "client_cp": "77100",
            "client_ville": "MAREUIL LES MEAUX",
            "client_tel": "01 60 24 72 72"
        }
        warnings = validate_client_extraction(clean_data)
        self.assertEqual(len(warnings), 0)
        
        # Contaminated data
        contaminated_data = {
            "client_nom": "RIAUX SAS",
            "client_cp": "35560",
            "client_ville": "BAZOUGES LA PEROUSE",
        }
        warnings = validate_client_extraction(contaminated_data)
        self.assertGreater(len(warnings), 0)


if __name__ == "__main__":
    unittest.main()
