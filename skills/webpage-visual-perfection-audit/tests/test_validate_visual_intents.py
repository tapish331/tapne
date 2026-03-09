import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "validate_visual_intents.py"
)

SPEC = importlib.util.spec_from_file_location("validate_visual_intents", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Could not load module from {SCRIPT_PATH}")

MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RegexParsingTests(unittest.TestCase):
    def test_default_regex_when_empty(self) -> None:
        pattern, flags = MODULE.parse_regex_pattern_flags("")
        self.assertEqual(pattern, "view\\s+all")
        self.assertEqual(flags, "i")

    def test_python_inline_case_insensitive_regex(self) -> None:
        pattern, flags = MODULE.parse_regex_pattern_flags("(?i)view\\s+all")
        self.assertEqual(pattern, "view\\s+all")
        self.assertEqual(flags, "i")

    def test_js_slash_style_regex_with_flags(self) -> None:
        pattern, flags = MODULE.parse_regex_pattern_flags("/view\\s+all/im")
        self.assertEqual(pattern, "view\\s+all")
        self.assertIn("i", flags)
        self.assertIn("m", flags)

    def test_unknown_inline_flags_do_not_break(self) -> None:
        pattern, flags = MODULE.parse_regex_pattern_flags("(?L)view all")
        self.assertEqual(pattern, "view all")
        self.assertEqual(flags, "i")


if __name__ == "__main__":
    unittest.main()
