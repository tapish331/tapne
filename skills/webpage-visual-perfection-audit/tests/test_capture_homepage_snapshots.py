import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

try:
    from PIL import Image
except ImportError:  # pragma: no cover - dependency/environment specific
    Image = None  # type: ignore[assignment]


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "capture_homepage_snapshots.py"
)

SPEC = importlib.util.spec_from_file_location("capture_homepage_snapshots", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Could not load module from {SCRIPT_PATH}")

MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def require_pillow_image() -> Any:
    if Image is None:  # pragma: no cover - guarded by skipIf
        raise unittest.SkipTest("Pillow not installed")
    return Image


@unittest.skipIf(Image is None, "Pillow not installed")
class ChangedPixelRatioTests(unittest.TestCase):
    def test_identical_images_have_zero_diff_ratio(self) -> None:
        image_module = require_pillow_image()
        with tempfile.TemporaryDirectory() as tmp:
            p1 = Path(tmp) / "a.png"
            p2 = Path(tmp) / "b.png"
            image_module.new("RGBA", (20, 10), (20, 40, 60, 255)).save(p1)
            image_module.new("RGBA", (20, 10), (20, 40, 60, 255)).save(p2)
            ratio, reason = MODULE.changed_pixel_ratio(p1, p2)
            self.assertEqual(ratio, 0.0)
            self.assertEqual(reason, "ok")

    def test_size_mismatch_returns_full_diff_ratio(self) -> None:
        image_module = require_pillow_image()
        with tempfile.TemporaryDirectory() as tmp:
            p1 = Path(tmp) / "a.png"
            p2 = Path(tmp) / "b.png"
            image_module.new("RGBA", (20, 10), (20, 40, 60, 255)).save(p1)
            image_module.new("RGBA", (10, 20), (20, 40, 60, 255)).save(p2)
            ratio, reason = MODULE.changed_pixel_ratio(p1, p2)
            self.assertEqual(ratio, 1.0)
            self.assertIn("size_mismatch", reason)

    def test_one_pixel_change_reports_non_zero_ratio(self) -> None:
        image_module = require_pillow_image()
        with tempfile.TemporaryDirectory() as tmp:
            p1 = Path(tmp) / "a.png"
            p2 = Path(tmp) / "b.png"
            img_a = image_module.new("RGBA", (20, 10), (20, 40, 60, 255))
            img_b = image_module.new("RGBA", (20, 10), (20, 40, 60, 255))
            img_b.putpixel((0, 0), (255, 0, 0, 255))
            img_a.save(p1)
            img_b.save(p2)
            ratio, reason = MODULE.changed_pixel_ratio(p1, p2)
            self.assertGreater(ratio, 0.0)
            self.assertEqual(reason, "ok")


if __name__ == "__main__":
    unittest.main()
