import json
import tempfile
import unittest
from pathlib import Path

from tools.island_builder import write_addon


FIXTURE = Path(__file__).parent / "fixtures" / "elaborate-small.json"


class AddonPackageTests(unittest.TestCase):
    def build_package(self, output_dir):
        mesh = json.loads(FIXTURE.read_text(encoding="utf-8"))
        return write_addon(
            mesh,
            output_dir,
            world_width=2,
            grid_step=1,
            max_height=20,
            sea_floor=-100,
            padding_cells=1,
        )

    def test_writes_infmap2_config_and_matching_height_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = self.build_package(Path(temp_dir) / "gm_inf_island")
            map_dir = output / "lua" / "infmap2" / "gm_inf_island"
            self.assertTrue((map_dir / "terrain.json").exists())
            metadata = json.loads((map_dir / "terrain.json").read_text(encoding="utf-8"))
            data = (map_dir / "terrain.bin").read_bytes()
            lua = (map_dir / "main.lua").read_text(encoding="utf-8")
            addon = json.loads((output / "addon.json").read_text(encoding="utf-8"))

            self.assertEqual(metadata["format"], "infmap-island-heightfield")
            self.assertEqual(len(data), metadata["sample_count"] * 2)
            self.assertEqual(addon["title"], "Highway 17 Island (InfMap2)")
            self.assertIn("has_terrain = true", lua)
            self.assertIn("height_function = height_function", lua)
            self.assertIn('local DATA_PATH = "infmap2/"', lua)
            self.assertIn("nature/grassfloor001a", lua)
            self.assertIn("nature/water_coast01", lua)
            self.assertIn("if drawing_depth or drawing_skybox then return end", lua)
            self.assertIn("return SEA_FLOOR", lua)
            self.assertIn("gm_inf_bliss.bsp", (output / "README.md").read_text(encoding="utf-8"))
            self.assertFalse((output / "maps" / "gm_inf_island.bsp").exists())

    def test_refuses_to_replace_a_nonempty_output_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "existing"
            target.mkdir()
            (target / "keep.txt").write_text("user file", encoding="utf-8")
            with self.assertRaisesRegex(FileExistsError, "not empty"):
                self.build_package(target)
            self.assertEqual((target / "keep.txt").read_text(encoding="utf-8"), "user file")


if __name__ == "__main__":
    unittest.main()
