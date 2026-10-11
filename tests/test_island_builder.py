import unittest

from tools.island_builder import build_heightfield, decode_heightfield, encode_heightfield, sample_height


def square_mesh():
    return {
        "format": "elaborate-island-mesh",
        "version": 1,
        "generator": {"name": "Elaborate"},
        "vertices": [
            {"x": 0, "y": 0, "height": 0, "is_sea": False},
            {"x": 2, "y": 0, "height": 10, "is_sea": False},
            {"x": 2, "y": 2, "height": 20, "is_sea": False},
            {"x": 0, "y": 2, "height": 10, "is_sea": False},
        ],
        "triangles": [[0, 1, 2], [0, 2, 3]],
    }


class HeightfieldTests(unittest.TestCase):
    def build(self, mesh=None, **overrides):
        options = {
            "world_width": 2,
            "grid_step": 1,
            "max_height": 20,
            "sea_floor": -100,
            "padding_cells": 1,
        }
        options.update(overrides)
        return build_heightfield(mesh or square_mesh(), **options)

    def test_rasterizes_mesh_and_interpolates_the_center(self):
        metadata, samples = self.build()
        self.assertEqual(metadata["width"], 5)
        self.assertEqual(metadata["height"], 5)
        self.assertEqual(sample_height(metadata, samples, 0, 0), 10)

    def test_sea_vertices_become_seabed_and_horizontal_scale_is_recorded(self):
        mesh = square_mesh()
        mesh["vertices"][2]["is_sea"] = True
        metadata, samples = self.build(mesh, world_width=200, grid_step=100)
        self.assertEqual(metadata["world_width"], 200)
        self.assertEqual(sample_height(metadata, samples, 100, 100), -100)

    def test_rejects_unsupported_format_and_empty_mesh(self):
        mesh = square_mesh()
        mesh["version"] = 9
        with self.assertRaisesRegex(ValueError, "version"):
            self.build(mesh)
        mesh = square_mesh()
        mesh["triangles"] = []
        with self.assertRaisesRegex(ValueError, "triangle"):
            self.build(mesh)

    def test_rejects_uncovered_interior_samples(self):
        mesh = square_mesh()
        mesh["triangles"] = [[0, 1, 2]]
        with self.assertRaisesRegex(ValueError, "uncovered"):
            self.build(mesh)

    def test_rejects_degenerate_triangles(self):
        mesh = square_mesh()
        mesh["triangles"] = [[0, 1, 1], [0, 2, 3]]
        with self.assertRaisesRegex(ValueError, "degenerate"):
            self.build(mesh)

    def test_rejects_heightfields_over_the_sample_limit_before_allocating(self):
        with self.assertRaisesRegex(ValueError, "sample limit"):
            self.build(world_width=1_000_000, grid_step=1)

    def test_rejects_overlapping_triangles_with_conflicting_heights(self):
        mesh = square_mesh()
        mesh["vertices"].extend([
            {"x": 0, "y": 0, "height": 20, "is_sea": False},
            {"x": 2, "y": 0, "height": 0, "is_sea": False},
            {"x": 2, "y": 2, "height": 0, "is_sea": False},
        ])
        mesh["triangles"].append([4, 5, 6])
        with self.assertRaisesRegex(ValueError, "overlap"):
            self.build(mesh)

    def test_rejects_numbers_too_large_for_finite_float_conversion(self):
        mesh = square_mesh()
        mesh["vertices"][0]["x"] = 10**10000
        with self.assertRaisesRegex(ValueError, "finite number"):
            self.build(mesh)

    def test_rejects_grid_steps_that_overflow_dimension_calculation(self):
        with self.assertRaisesRegex(ValueError, "grid resolution"):
            self.build(grid_step=1e-320)

    def test_binary_round_trip_is_signed_little_endian(self):
        values = [-32768, -1, 0, 32767]
        encoded = encode_heightfield(values)
        self.assertEqual(encoded, b"\x00\x80\xff\xff\x00\x00\xff\x7f")
        self.assertEqual(decode_heightfield(encoded), values)
        with self.assertRaisesRegex(ValueError, "signed 16-bit"):
            encode_heightfield([32768])


if __name__ == "__main__":
    unittest.main()
