import math
import json
import tempfile
import unittest
from pathlib import Path

from tools import island_builder


def coastal_field():
    size, step = 49, 1024
    meta = {"width": size, "height": size, "step_x": step, "step_y": step,
            "origin_x": -24576, "origin_y": -24576, "sea_floor": -4096,
            "sea_level": 0}
    samples = []
    for row in range(size):
        for col in range(size):
            x, y = meta["origin_x"] + col * step, meta["origin_y"] + row * step
            r, angle = math.hypot(x, y), math.atan2(y, x)
            coast = 15500 + 1500 * math.cos(angle * 3)
            samples.append(round(max(-4096, min(6000, (coast - r) * 0.6))))
    return meta, samples


def coastal_mesh():
    meta, samples = coastal_field()
    vertices = []
    for row in range(meta["height"]):
        for col in range(meta["width"]):
            z = samples[row * meta["width"] + col]
            vertices.append({"x": col, "y": row, "height": max(0, z), "is_sea": z < 0})
    triangles = []
    for row in range(meta["height"] - 1):
        for col in range(meta["width"] - 1):
            a = row * meta["width"] + col
            triangles.extend([[a, a + 1, a + meta["width"]],
                              [a + meta["width"], a + 1, a + meta["width"] + 1]])
    return {"format": "elaborate-island-mesh", "version": 1,
            "generator": {"name": "Elaborate"}, "vertices": vertices, "triangles": triangles}


class CoastalRoadTests(unittest.TestCase):
    def generate(self, meta=None, samples=None):
        self.assertTrue(hasattr(island_builder, "build_coastal_road"),
                        "builder has no coastal road generation")
        if meta is None:
            meta, samples = coastal_field()
        return island_builder.build_coastal_road(meta, samples, terrain_spacing=2000)

    def test_closed_coastal_route_has_continuous_width_and_mild_grades(self):
        road, graded = self.generate()
        line = road["centerline"]
        self.assertGreater(len(line), 100)
        self.assertEqual(line[0][:3], line[-1][:3])
        for a, b, section in zip(line, line[1:], road["sections"]):
            length = math.dist(a[:2], b[:2])
            self.assertGreater(length, 0)
            self.assertLessEqual(length, 512.01)
            self.assertLessEqual(abs(a[2] - b[2]) / length, 0.08)
            self.assertGreater(a[2], 0)
            self.assertAlmostEqual(math.dist(section[2][:2], section[3][:2]), 512)
        self.assertEqual(road["sections"][0], road["sections"][-1])

    def test_road_tracks_the_shore_and_clears_underlying_collision_grid(self):
        meta, original = coastal_field()
        road, graded = self.generate(meta, original)
        for x, y, z, _ in road["centerline"]:
            self.assertLess(abs(island_builder.sample_height(meta, original, x, y) - 768), 350)
            self.assertLess(island_builder.sample_height(meta, graded, x, y), z - 20)
        self.assertEqual(graded[0], original[0])
        self.assertNotEqual(graded, original)

    def test_largest_landmass_wins_and_generation_is_deterministic(self):
        meta, samples = coastal_field()
        # An isolated little island in a corner must not take over the route.
        for row in range(3, 6):
            for col in range(3, 6):
                samples[row * meta["width"] + col] = 1500
        road, graded = self.generate(meta, samples)
        self.assertTrue(all(x > -20000 or y > -20000 for x, y, _, _ in road["centerline"]))
        self.assertEqual((road, graded), self.generate(meta, samples))

    def test_missing_coast_is_an_explicit_error(self):
        meta, samples = coastal_field()
        with self.assertRaisesRegex(ValueError, "coastal contour"):
            self.generate(meta, [6000] * len(samples))

    def test_erosion_cusps_do_not_fold_road_or_shoulder_triangles(self):
        meta, _ = coastal_field()
        samples = []
        for row in range(meta['height']):
            for col in range(meta['width']):
                x, y = meta['origin_x'] + col * 1024, meta['origin_y'] + row * 1024
                r, angle = math.hypot(x, y), math.atan2(y, x)
                samples.append(round(max(-4096, min(6000, (15500 + 3000 * math.cos(angle * 18) - r) * .6))))
        road, _ = self.generate(meta, samples)
        for a, b in zip(road['sections'], road['sections'][1:]):
            for band in range(5):
                for p, q, r in ((a[band], b[band], a[band+1]), (b[band], b[band+1], a[band+1])):
                    cross = (q[0]-p[0])*(r[1]-p[1]) - (q[1]-p[1])*(r[0]-p[0])
                    self.assertLess(cross, 0, 'coastal cusp folded a road triangle')

    def test_addon_includes_road_geometry_in_transfer_safe_lowercase_lua(self):
        with tempfile.TemporaryDirectory() as temp:
            output = island_builder.write_addon(coastal_mesh(), Path(temp) / "addon",
                world_width=49152, grid_step=1024, max_height=6000, coastal_road=True)
            road_dir = output / "lua/infmap2/gm_inf_island"
            road = json.loads((road_dir / "road.json").read_text())
            self.assertGreater(road["length"], 50000)
            self.assertEqual(road["materials"], ["nature/gravelfloor004a", "concrete/concretefloor037b"])
            self.assertTrue((road_dir / "road.lua").exists())
            self.assertIn('include("infmap2/" .. MAP_NAME .. "/road.lua")', (road_dir / "main.lua").read_text())
            chunks = list((road_dir / "road_data").glob("*.lua"))
            self.assertGreater(len(chunks), 1)
            for chunk in chunks:
                self.assertLess(chunk.stat().st_size, 60000)
                self.assertEqual(chunk.name, chunk.name.lower())


if __name__ == "__main__":
    unittest.main()
