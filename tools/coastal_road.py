"""Deterministic coastal road geometry, generated entirely outside GMod."""

import math


def _contour(metadata, heights, elevation):
    """Trace closed contours of the same triangle split used by InfMap2."""
    width, height = metadata["width"], metadata["height"]
    positions, neighbours = {}, {}
    # Avoid branching contours through samples exactly equal to the level.
    level = elevation + 0.125
    for row in range(height - 1):
        for col in range(width - 1):
            a = row * width + col
            for triangle in ((a, a + 1, a + width),
                             (a + width, a + 1, a + width + 1)):
                crossings = []
                for first, second in zip(triangle, triangle[1:] + triangle[:1]):
                    if (heights[first] > level) == (heights[second] > level):
                        continue
                    key = tuple(sorted((first, second)))
                    if key not in positions:
                        t = (level - heights[first]) / (heights[second] - heights[first])
                        r0, c0 = divmod(first, width)
                        r1, c1 = divmod(second, width)
                        positions[key] = (
                            metadata["origin_x"] + (c0 + (c1 - c0) * t) * metadata["step_x"],
                            metadata["origin_y"] + (r0 + (r1 - r0) * t) * metadata["step_y"],
                        )
                    crossings.append(key)
                if len(crossings) == 2:
                    a, b = crossings
                    neighbours.setdefault(a, []).append(b)
                    neighbours.setdefault(b, []).append(a)
    seen, loops = set(), []
    for start in sorted(neighbours):
        if start in seen:
            continue
        path, current, previous = [], start, None
        while current not in seen and len(neighbours[current]) == 2:
            seen.add(current)
            path.append(positions[current])
            following = next(n for n in neighbours[current] if n != previous)
            previous, current = current, following
        if current == start and len(path) >= 3:
            area = sum(a[0] * b[1] - b[0] * a[1]
                       for a, b in zip(path, path[1:] + path[:1]))
            loops.append((abs(area), path if area > 0 else list(reversed(path))))
    if not loops:
        raise ValueError("no closed coastal contour; lower --road-elevation or omit --coastal-road")
    return max(loops, key=lambda item: item[0])[1]


def _smooth_and_resample(loop, spacing=256):
    for _ in range(3):
        loop = [point for a, b in zip(loop, loop[1:] + loop[:1])
                for point in ((a[0] * .75 + b[0] * .25, a[1] * .75 + b[1] * .25),
                              (a[0] * .25 + b[0] * .75, a[1] * .25 + b[1] * .75))]
    return _resample(loop, spacing)


def _resample(loop, spacing=256):
    lengths = [math.hypot(b[0] - a[0], b[1] - a[1])
               for a, b in zip(loop, loop[1:] + loop[:1])]
    total = sum(lengths)
    count = max(3, math.ceil(total / spacing))
    result, segment, start = [], 0, 0
    for index in range(count):
        distance = total * index / count
        while segment + 1 < len(loop) and start + lengths[segment] < distance:
            start += lengths[segment]
            segment += 1
        a, b = loop[segment], loop[(segment + 1) % len(loop)]
        t = (distance - start) / max(lengths[segment], 1e-12)
        result.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return result


def _fair_route(loop, minimum_radius):
    """Remove erosion cusps before offsetting the road's wide earth shoulders."""
    weights = [math.exp(-i * i / 32) for i in range(-12, 13)]
    weight_sum = sum(weights)
    for _ in range(64):
        tight = False
        for index, b in enumerate(loop):
            a, c = loop[index - 1], loop[(index + 1) % len(loop)]
            cross = abs((b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0]))
            if cross < 1e-8:
                continue
            radius = math.dist(a, b) * math.dist(b, c) * math.dist(a, c) / (2 * cross)
            if radius < minimum_radius:
                tight = True
                break
        if not tight:
            return loop
        loop = _resample([
            tuple(sum(loop[(index + offset) % len(loop)][axis] * weight
                      for offset, weight in zip(range(-12, 13), weights)) / weight_sum
                  for axis in range(2))
            for index in range(len(loop))])
    raise ValueError("coastal contour is too tight for this road width; reduce --road-width or omit --coastal-road")


def engine_height(metadata, heights, x, y, spacing):
    """Sample InfMap2's actual triangle surface, rather than the source grid."""
    from .island_builder import sample_height
    gx, gy = math.floor(x / spacing), math.floor(y / spacing)
    tx, ty = x / spacing - gx, y / spacing - gy
    a = sample_height(metadata, heights, gx * spacing, gy * spacing)
    b = sample_height(metadata, heights, (gx + 1) * spacing, gy * spacing)
    c = sample_height(metadata, heights, gx * spacing, (gy + 1) * spacing)
    if tx + ty <= 1:
        return a * (1 - tx - ty) + b * tx + c * ty
    d = sample_height(metadata, heights, (gx + 1) * spacing, (gy + 1) * spacing)
    return b * (1 - ty) + c * (1 - tx) + d * (tx + ty - 1)


def build_coastal_road(metadata, samples, *, terrain_spacing,
                       road_width=512, elevation=768):
    """Return road geometry and graded terrain; never mutate the input samples.

    A smoothed low-elevation contour surrounds the largest landmass. The deck
    has gentle closed-loop vertical undulations. Each cross-section has six
    points: ground, shoulder, asphalt, asphalt, shoulder, ground.
    """
    from .island_builder import _finite_number
    road_width = _finite_number(road_width, "road_width")
    elevation = _finite_number(elevation, "road_elevation")
    if road_width < 128 or road_width > 2048:
        raise ValueError("road_width must be between 128 and 2048 Hammer units")
    if elevation < metadata["sea_level"] + 128 or elevation > 30000:
        raise ValueError("road_elevation must be 128..30000 Hammer units above sea level")
    loop = _fair_route(_smooth_and_resample(_contour(metadata, samples, elevation)), road_width / 2 + 1400)
    lengths = [math.hypot(b[0] - a[0], b[1] - a[1])
               for a, b in zip(loop, loop[1:] + loop[:1])]
    total = sum(lengths)
    if total < road_width * 20:
        raise ValueError("coastal contour is too small for a highway; omit --coastal-road")
    # Approximately 300 m between gentle rises, with <= 3% longitudinal grade.
    waves = max(1, int(total / 16000))
    centerline, distance = [], 0
    for point, length in zip(loop, lengths):
        z = elevation + 64 * (1 - math.cos(distance / total * math.tau * waves))
        centerline.append([point[0], point[1], z, distance])
        distance += length
    centerline.append(centerline[0][:3] + [total])

    graded = list(samples)
    width, height = metadata["width"], metadata["height"]
    sx, sy = metadata["step_x"], metadata["step_y"]
    # Include all source-grid vertices supporting all engine triangles below
    # the deck. This avoids grass/terrain protruding through a narrow road.
    radius = road_width / 2 + 96 + math.sqrt(2) * (max(sx, sy) + terrain_spacing)
    for a, b in zip(centerline, centerline[1:]):
        x0 = max(0, math.floor((min(a[0], b[0]) - radius - metadata["origin_x"]) / sx))
        x1 = min(width - 1, math.ceil((max(a[0], b[0]) + radius - metadata["origin_x"]) / sx))
        y0 = max(0, math.floor((min(a[1], b[1]) - radius - metadata["origin_y"]) / sy))
        y1 = min(height - 1, math.ceil((max(a[1], b[1]) + radius - metadata["origin_y"]) / sy))
        dx, dy = b[0] - a[0], b[1] - a[1]
        length2 = dx * dx + dy * dy
        ceiling = math.floor(min(a[2], b[2]) - 64)
        for row in range(y0, y1 + 1):
            y = metadata["origin_y"] + row * sy
            for col in range(x0, x1 + 1):
                x = metadata["origin_x"] + col * sx
                t = max(0, min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / length2))
                if (x - a[0] - dx * t) ** 2 + (y - a[1] - dy * t) ** 2 <= radius * radius:
                    index = row * width + col
                    graded[index] = min(graded[index], ceiling)

    sections = []
    half = road_width / 2
    offsets = (half + 1120, half + 96, half, -half, -half - 96, -half - 1120)
    for index, (x, y, z, _) in enumerate(centerline[:-1]):
        a, b = loop[index - 1], loop[(index + 1) % len(loop)]
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        nx, ny = -(b[1] - a[1]) / length, (b[0] - a[0]) / length
        section = []
        for band, offset in enumerate(offsets):
            px, py = x + nx * offset, y + ny * offset
            pz = engine_height(metadata, graded, px, py, terrain_spacing) if band in (0, 5) else z
            section.append([px, py, pz])
        sections.append(section)
    sections.append([point[:] for point in sections[0]])
    return {"format": "infmap-coastal-road", "version": 1,
            "width": road_width, "elevation": elevation, "length": total,
            "materials": ["nature/gravelfloor004a", "concrete/concretefloor037b"],
            "centerline": centerline, "sections": sections}, graded
