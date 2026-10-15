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

    def test_irregular_sea_boundary_leaves_exterior_as_seabed(self):
        mesh = square_mesh()
        mesh['vertices'] = [
            {'x': x, 'y': y, 'height': h, 'is_sea': sea}
            for x, y, h, sea in [(0, 1, 0, True), (1, 0, 0, True),
                                  (2, 1, 0, True), (1, 2, 0, True),
                                  (1, 1, 10, False), (1, .5, 5, False)]
        ]
        mesh['triangles'] = [[0, 1, 5], [1, 2, 5], [2, 4, 5],
                             [4, 0, 5], [0, 4, 3], [4, 2, 3]]
        metadata, samples = self.build(mesh, grid_step=.25)
        self.assertEqual(sample_height(metadata, samples, -1, -1), -100)
        self.assertEqual(sample_height(metadata, samples, 0, 0), 20)

    def test_enclosed_hole_is_not_filled_as_exterior_seabed(self):
        mesh = square_mesh()
        mesh['vertices'] = [
            {'x': x, 'y': y, 'height': 0, 'is_sea': True}
            for x, y in [(0, 0), (4, 0), (4, 4), (0, 4),
                         (1, 1), (3, 1), (3, 3), (1, 3)]
        ] + [{'x': 2, 'y': .5, 'height': 1, 'is_sea': False}]
        mesh['triangles'] = [[0, 1, 8], [1, 5, 8], [5, 4, 8], [4, 0, 8],
                             [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6],
                             [3, 0, 4], [3, 4, 7]]
        with self.assertRaisesRegex(ValueError, 'uncovered'):
            self.build(mesh, world_width=4, grid_step=.5)

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
