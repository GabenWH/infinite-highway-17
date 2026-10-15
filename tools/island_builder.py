"""Offline conversion from an Elaborate triangle mesh to an InfMap heightfield."""

from __future__ import annotations

import argparse
import json
import math
import numbers
import shutil
import struct
from collections import Counter, deque
from pathlib import Path


FORMAT_NAME = "elaborate-island-mesh"
FORMAT_VERSION = 1
MAX_SAMPLE_COUNT = 2_000_000
INFMAP_CHUNK_SIZE = 20000
LUA_DATA_CHUNK_BYTES = 2048


def _finite_number(value, label):
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ValueError(f"{label} must be a finite number")
    try:
        value = float(value)
    except (OverflowError, TypeError, ValueError) as error:
        raise ValueError(f"{label} must be a finite number") from error
    if not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return value


def _validate_mesh(document):
    if not isinstance(document, dict) or document.get("format") != FORMAT_NAME:
        raise ValueError(f"format must be {FORMAT_NAME!r}")
    if document.get("version") != FORMAT_VERSION:
        raise ValueError(f"version must be {FORMAT_VERSION}")
    if not isinstance(document.get("generator"), dict) or document["generator"].get("name") != "Elaborate":
        raise ValueError("generator.name must be 'Elaborate'")

    raw_vertices = document.get("vertices")
    raw_triangles = document.get("triangles")
    if not isinstance(raw_vertices, list) or len(raw_vertices) < 3:
        raise ValueError("mesh must contain at least three vertices")
    if not isinstance(raw_triangles, list) or not raw_triangles:
        raise ValueError("mesh must contain at least one triangle")

    vertices = []
    for index, vertex in enumerate(raw_vertices):
        if not isinstance(vertex, dict):
            raise ValueError(f"vertex {index} must be an object")
        is_sea = vertex.get("is_sea")
        if not isinstance(is_sea, bool):
            raise ValueError(f"vertex {index}.is_sea must be a boolean")
        vertices.append({
            "x": _finite_number(vertex.get("x"), f"vertex {index}.x"),
            "y": _finite_number(vertex.get("y"), f"vertex {index}.y"),
            "height": _finite_number(vertex.get("height"), f"vertex {index}.height"),
            "is_sea": is_sea,
        })

    triangles = []
    for index, triangle in enumerate(raw_triangles):
        if not isinstance(triangle, list) or len(triangle) != 3:
            raise ValueError(f"triangle {index} must contain three vertex indices")
        if any(isinstance(vertex_id, bool) or not isinstance(vertex_id, int) for vertex_id in triangle):
            raise ValueError(f"triangle {index} indices must be integers")
        if any(vertex_id < 0 or vertex_id >= len(vertices) for vertex_id in triangle):
            raise ValueError(f"triangle {index} has an out-of-range vertex index")
        if len(set(triangle)) != 3:
            raise ValueError(f"triangle {index} is degenerate")
        a, b, c = (vertices[vertex_id] for vertex_id in triangle)
        area2 = (b["x"] - a["x"]) * (c["y"] - a["y"]) - (b["y"] - a["y"]) * (c["x"] - a["x"])
        if abs(area2) <= 1e-12:
            raise ValueError(f"triangle {index} is degenerate")
        triangles.append(triangle)

    land_heights = [vertex["height"] for vertex in vertices if not vertex["is_sea"]]
    if not land_heights:
        raise ValueError("mesh must contain at least one land vertex")
    return vertices, triangles, land_heights


def build_heightfield(
    document,
    *,
    world_width=524288,
    grid_step=2048,
    max_height=16384,
    sea_floor=-4096,
    padding_cells=2,
):
    """Rasterize a triangulated mesh into row-major signed integer samples.

    The longest input axis is scaled to ``world_width`` Hammer units. Land
    elevations are normalized from their minimum to ``max_height``; sea-marked
    vertices are placed at ``sea_floor`` so the ocean surface can be rendered
    separately at sea level.
    """
    vertices, triangles, land_heights = _validate_mesh(document)
    world_width = _finite_number(world_width, "world_width")
    grid_step = _finite_number(grid_step, "grid_step")
    max_height = _finite_number(max_height, "max_height")
    sea_floor = _finite_number(sea_floor, "sea_floor")
    if world_width <= 0 or grid_step <= 0:
        raise ValueError("world_width and grid_step must be greater than zero")
    if max_height < 0:
        raise ValueError("max_height must be non-negative")
    if isinstance(padding_cells, bool) or not isinstance(padding_cells, int) or padding_cells < 0:
        raise ValueError("padding_cells must be a non-negative integer")
    if int(sea_floor) != sea_floor:
        raise ValueError("sea_floor must be an integer Hammer height")
    sea_floor = int(sea_floor)

    xs = [vertex["x"] for vertex in vertices]
    ys = [vertex["y"] for vertex in vertices]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max_x - min_x
    span_y = max_y - min_y
    if span_x <= 0 or span_y <= 0:
        raise ValueError("mesh must have non-zero width and height")

    scale = world_width / max(span_x, span_y)
    scaled_span_x = span_x * scale
    scaled_span_y = span_y * scale
    grid_ratio_x = scaled_span_x / grid_step
    grid_ratio_y = scaled_span_y / grid_step
    if not math.isfinite(grid_ratio_x) or not math.isfinite(grid_ratio_y):
        raise ValueError("grid resolution is too fine for finite dimension calculation")
    inner_width = max(2, int(round(grid_ratio_x)) + 1)
    inner_height = max(2, int(round(grid_ratio_y)) + 1)
    step_x = scaled_span_x / (inner_width - 1)
    step_y = scaled_span_y / (inner_height - 1)
    width = inner_width + 2 * padding_cells
    height = inner_height + 2 * padding_cells
    sample_count = width * height
    if sample_count > MAX_SAMPLE_COUNT:
        raise ValueError(
            f"heightfield requires {sample_count} samples, above the sample limit "
            f"of {MAX_SAMPLE_COUNT}; increase --grid-step or reduce --world-width"
        )
    origin_x = -scaled_span_x / 2 - padding_cells * step_x
    origin_y = -scaled_span_y / 2 - padding_cells * step_y

    low_land = min(land_heights)
    high_land = max(land_heights)
    land_range = high_land - low_land
    vertex_heights = [
        sea_floor if vertex["is_sea"] else (
            0 if land_range == 0 else (vertex["height"] - low_land) * max_height / land_range
        )
        for vertex in vertices
    ]
    samples = [sea_floor] * sample_count
    covered = bytearray(sample_count)
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2

    grid_vertices = []
    for vertex in vertices:
        scaled_x = (vertex["x"] - center_x) * scale
        scaled_y = (vertex["y"] - center_y) * scale
        grid_vertices.append(((scaled_x - origin_x) / step_x, (scaled_y - origin_y) / step_y))

    for triangle_index, triangle in enumerate(triangles):
        points = [grid_vertices[vertex_id] for vertex_id in triangle]
        heights = [vertex_heights[vertex_id] for vertex_id in triangle]
        (x0, y0), (x1, y1), (x2, y2) = points
        denominator = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(denominator) <= 1e-12:
            raise ValueError(f"triangle {triangle_index} is degenerate after scaling")

        col_start = max(0, math.floor(min(x0, x1, x2) - 1e-9))
        col_end = min(width - 1, math.ceil(max(x0, x1, x2) + 1e-9))
        row_start = max(0, math.floor(min(y0, y1, y2) - 1e-9))
        row_end = min(height - 1, math.ceil(max(y0, y1, y2) + 1e-9))
        for row in range(row_start, row_end + 1):
            for col in range(col_start, col_end + 1):
                weight0 = ((y1 - y2) * (col - x2) + (x2 - x1) * (row - y2)) / denominator
                weight1 = ((y2 - y0) * (col - x2) + (x0 - x2) * (row - y2)) / denominator
                weight2 = 1 - weight0 - weight1
                if min(weight0, weight1, weight2) < -1e-9 or max(weight0, weight1, weight2) > 1 + 1e-9:
                    continue
                offset = row * width + col
                value = round(weight0 * heights[0] + weight1 * heights[1] + weight2 * heights[2])
                if covered[offset] and samples[offset] != value:
                    raise ValueError(
                        f"overlapping triangles produce conflicting heights at "
                        f"column {col}, row {row}"
                    )
                samples[offset] = value
                covered[offset] = 1

    # Elaborate's jagged outer mesh does not cover its rectangular bounds.
    # Only accept missing cells connected to the exterior of a sea-bounded
    # mesh. Interior holes and incomplete land boundaries remain errors.
    edges = Counter(tuple(sorted((t[i], t[(i + 1) % 3])))
                    for t in triangles for i in range(3))
    boundary = {v for edge, count in edges.items() if count == 1 for v in edge}
    exterior = bytearray(sample_count)
    if boundary and all(vertices[v]['is_sea'] for v in boundary):
        queue = deque()
        def enqueue(index):
            if not covered[index] and not exterior[index]:
                exterior[index] = 1
                queue.append(index)
        for col in range(width):
            enqueue(col)
            enqueue((height - 1) * width + col)
        for row in range(height):
            enqueue(row * width)
            enqueue(row * width + width - 1)
        while queue:
            index = queue.popleft()
            row, col = divmod(index, width)
            if row: enqueue(index - width)
            if row + 1 < height: enqueue(index + width)
            if col: enqueue(index - 1)
            if col + 1 < width: enqueue(index + 1)

    for row in range(padding_cells, padding_cells + inner_height):
        for col in range(padding_cells, padding_cells + inner_width):
            if not covered[row * width + col] and not exterior[row * width + col]:
                raise ValueError(f"uncovered interior sample at column {col}, row {row}")

    # Validate the full supported height range before bytes are produced.
    encode_heightfield(samples)
    metadata = {
        "format": "infmap-island-heightfield",
        "version": 1,
        "sample_format": "int16le",
        "width": width,
        "height": height,
        "sample_count": len(samples),
        "step_x": step_x,
        "step_y": step_y,
        "origin_x": origin_x,
        "origin_y": origin_y,
        "world_width": world_width,
        "sea_level": 0,
        "sea_floor": sea_floor,
        "max_height": max_height,
        "padding_cells": padding_cells,
        "land_bounds": {
            "min_x": -scaled_span_x / 2,
            "max_x": scaled_span_x / 2,
            "min_y": -scaled_span_y / 2,
            "max_y": scaled_span_y / 2,
        },
    }
    return metadata, samples


def encode_heightfield(samples):
    """Encode an iterable of heights as signed 16-bit little-endian values."""
    values = list(samples)
    data = bytearray(2 * len(values))
    for index, value in enumerate(values):
        if isinstance(value, bool) or not isinstance(value, numbers.Integral):
            raise ValueError("height samples must be signed 16-bit integers")
        if value < -32768 or value > 32767:
            raise ValueError("height sample is outside the signed 16-bit range")
        struct.pack_into("<h", data, index * 2, int(value))
    return bytes(data)


def decode_heightfield(data):
    """Decode signed 16-bit little-endian samples."""
    if not isinstance(data, (bytes, bytearray, memoryview)) or len(data) % 2:
        raise ValueError("heightfield binary must contain an even number of bytes")
    return [value[0] for value in struct.iter_unpack("<h", data)]


def sample_height(metadata, samples, x, y):
    """Bilinearly sample row-major data, using seabed outside its bounds."""
    x = _finite_number(x, "sample x")
    y = _finite_number(y, "sample y")
    width = metadata["width"]
    height = metadata["height"]
    if len(samples) != width * height:
        raise ValueError("sample count does not match heightfield dimensions")
    fx = (x - metadata["origin_x"]) / metadata["step_x"]
    fy = (y - metadata["origin_y"]) / metadata["step_y"]
    if fx < 0 or fy < 0 or fx > width - 1 or fy > height - 1:
        return metadata["sea_floor"]

    x0 = min(int(math.floor(fx)), width - 2)
    y0 = min(int(math.floor(fy)), height - 2)
    tx = fx - x0
    ty = fy - y0
    top_left = samples[y0 * width + x0]
    top_right = samples[y0 * width + x0 + 1]
    bottom_left = samples[(y0 + 1) * width + x0]
    bottom_right = samples[(y0 + 1) * width + x0 + 1]
    top = top_left + (top_right - top_left) * tx
    bottom = bottom_left + (bottom_right - bottom_left) * tx
    return top + (bottom - top) * ty


def _lua_number(value):
    if isinstance(value, int):
        return str(value)
    return format(float(value), ".12g")


def write_addon(document, output_dir, **options):
    """Build a local InfMap2 addon directory from an exported mesh document."""
    output = Path(output_dir)
    if output.exists():
        if not output.is_dir():
            raise FileExistsError(f"output path exists and is not a directory: {output}")
        if any(output.iterdir()):
            raise FileExistsError(f"output directory is not empty: {output}")

    metadata, samples = build_heightfield(document, **options)
    binary = encode_heightfield(samples)
    # Even subdivisions align the centered chunk mesh and terrain queries.
    # 64 bounds the padded chunk mesh below GMod's 32768-vertex mesh limit.
    terrain_samples = min(64, max(2, 2 * math.ceil(
        INFMAP_CHUNK_SIZE / min(metadata['step_x'], metadata['step_y']) / 2)))
    metadata['infmap_chunk_size'] = INFMAP_CHUNK_SIZE
    metadata['infmap_samples'] = terrain_samples
    metadata['infmap_sample_spacing'] = INFMAP_CHUNK_SIZE / terrain_samples
    data_chunks = [binary[i:i + LUA_DATA_CHUNK_BYTES]
                   for i in range(0, len(binary), LUA_DATA_CHUNK_BYTES)]
    template_dir = Path(__file__).parent / "templates"
    project_root = Path(__file__).resolve().parents[1]
    main_template = (template_dir / "main.lua").read_text(encoding="utf-8")
    tokens = {
        "@@WIDTH@@": str(metadata["width"]),
        "@@HEIGHT@@": str(metadata["height"]),
        "@@SAMPLE_COUNT@@": str(metadata["sample_count"]),
        "@@ORIGIN_X@@": _lua_number(metadata["origin_x"]),
        "@@ORIGIN_Y@@": _lua_number(metadata["origin_y"]),
        "@@STEP_X@@": _lua_number(metadata["step_x"]),
        "@@STEP_Y@@": _lua_number(metadata["step_y"]),
        "@@SEA_LEVEL@@": _lua_number(metadata["sea_level"]),
        "@@SEA_FLOOR@@": _lua_number(metadata["sea_floor"]),
        "@@DATA_CHUNKS@@": str(len(data_chunks)),
        "@@CHUNK_SIZE@@": str(INFMAP_CHUNK_SIZE),
        "@@TERRAIN_SAMPLES@@": str(terrain_samples),
    }
    main_lua = main_template
    for token, value in tokens.items():
        main_lua = main_lua.replace(token, value)
    if "@@" in main_lua:
        raise ValueError("unexpanded token in main.lua template")

    map_dir = output / "lua" / "infmap2" / "gm_inf_island"
    map_dir.mkdir(parents=True, exist_ok=True)
    (map_dir / "main.lua").write_text(main_lua, encoding="utf-8")
    (map_dir / "terrain.bin").write_bytes(binary)
    # GMod automatically sends Lua via AddCSLuaFile, unlike arbitrary .bin
    # files. Fixed-width decimal escapes preserve all bytes, including NUL.
    data_dir = map_dir / "data"
    data_dir.mkdir()
    for index, chunk in enumerate(data_chunks, 1):
        escaped = ''.join('\\%03d' % byte for byte in chunk)
        (data_dir / f"part_{index:04d}.lua").write_text(
            'return "' + escaped + '"\n', encoding='ascii')
    (map_dir / "terrain.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    shutil.copyfile(template_dir / "addon.json", output / "addon.json")
    shutil.copyfile(project_root / "gmod" / "island_infmap2" / "README.md", output / "README.md")
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description="Convert an Elaborate island export into a Garry's Mod InfMap2 addon.")
    parser.add_argument("mesh_json", help="JSON file downloaded with tools/elaborate-export.js")
    parser.add_argument("--output", required=True, help="new or empty directory for the generated addon")
    parser.add_argument("--world-width", type=float, default=524288, help="longest island side in Hammer units (default: 524288, about 10 km)")
    parser.add_argument("--grid-step", type=float, default=2048, help="target horizontal sample spacing in Hammer units (default: 2048)")
    parser.add_argument("--max-height", type=float, default=16384, help="height of the highest land sample above sea level (default: 16384)")
    parser.add_argument("--sea-floor", type=int, default=-4096, help="height of the sea floor and fallback beyond the exported mesh")
    parser.add_argument("--padding-cells", type=int, default=2, help="flat-seabed samples added around the island bounds")
    args = parser.parse_args(argv)

    try:
        document = json.loads(Path(args.mesh_json).read_text(encoding="utf-8"))
        output = write_addon(
            document,
            args.output,
            world_width=args.world_width,
            grid_step=args.grid_step,
            max_height=args.max_height,
            sea_floor=args.sea_floor,
            padding_cells=args.padding_cells,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))

    metadata_path = output / "lua" / "infmap2" / "gm_inf_island" / "terrain.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    print(f"Built {output} ({metadata['width']} x {metadata['height']} samples, {metadata['sample_count'] * 2} terrain bytes).")
    print("Copy InfMap2's gm_inf_bliss BSP to this addon's maps/gm_inf_island.bsp before launching the map.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
