import builtins
import importlib
import sys
import unittest

import services.devis_parser as devis_parser


class OptionalFitzImportTest(unittest.TestCase):
    def test_import_without_fitz(self):
        original_import = builtins.__import__

        def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "fitz":
                raise ModuleNotFoundError("No module named 'fitz'")
            return original_import(name, globals, locals, fromlist, level)

        builtins.__import__ = blocked_import
        try:
            sys.modules.pop("fitz", None)
            reloaded = importlib.reload(devis_parser)
            self.assertFalse(reloaded.FITZ_AVAILABLE)
            self.assertIsNone(reloaded.fitz)
            parser = reloaded.DevisParser()
            self.assertIsNotNone(parser)
        finally:
            builtins.__import__ = original_import
            importlib.reload(devis_parser)


if __name__ == "__main__":
    unittest.main()
