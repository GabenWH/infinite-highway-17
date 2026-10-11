# Highway 17 Island for Garry's Mod

This project turns one island from the separate [Elaborate terrain generator](https://troido.nl/elaborate/) into a Garry's Mod map package. Its source is available at [jmdejong/elaborate](https://github.com/jmdejong/elaborate). Island generation and conversion run outside GMod. The generated addon samples a finite heightfield through [InfMap2](https://github.com/Def-Try/infmap2), with a camera-following ocean surface around it.

Garry's Mod includes Half-Life 2 content by default, so the addon refers to HL2 materials directly. It does not bundle HL2 textures or models and does not ask you to mount another game.

## What the first version makes

- One erosion-generated island per export, with a client-side ocean surface that follows the player.
- Default longest island side of 524,288 Hammer units, about 10 km. This is larger than the usual Source map footprint; InfMap2 supplies the virtual coordinates.
- A configurable heightfield, with a default target sample spacing of 2,048 units (about 39 m), maximum land height of 16,384 units, and seabed at -4,096 units.
- An InfMap2 Lua map config using `nature/grassfloor001a` for terrain and `nature/water_coast01` for the ocean surface.

The ocean is visual only; this version has no swimming or water physics. Its 28,000-unit square follows the player, and the edge may show from high viewpoints or beyond the expected render range. InfMap2's generated terrain uses one material, so it does not blend grass, sand, and cliff textures. The map provides an island and coast foundation; a drivable Highway 17 road and automatic roadside prop placement are follow-up work. The generated addon's README lists two HL2 cliff models for manual set dressing.

## Requirements

- Garry's Mod and its default Half-Life 2 content.
- The Def-Try InfMap2 addon installed separately.
- Python 3.8 or later for terrain conversion.
- A browser with developer tools for the Elaborate export step.

Node.js 18 or later is only needed to run the exporter tests.

## Build an island

1. Open Elaborate, generate an island, and wait for its mesh to finish.
2. Open the browser developer console. Paste the full contents of [`tools/elaborate-export.js`](tools/elaborate-export.js) and press Enter. Then run:

   ```js
   ElaborateIslandExporter.downloadCurrentWorld()
   ```

   The page downloads `elaborate-island-mesh.json`. The exporter reads the current `window.world.graph`; it does not change the generator or send data anywhere.

3. Convert that JSON into an addon folder:

   ```bash
   python3 tools/island_builder.py /path/to/elaborate-island-mesh.json --output build/gm_inf_island
   ```

   The output directory must be new or empty. The builder rejects malformed meshes, uncovered interior samples, invalid triangles, and height values outside signed 16-bit range.

4. Copy the generated `build/gm_inf_island` folder into your GMod `garrysmod/addons/` folder.
5. Copy InfMap2's `maps/gm_inf_bliss.bsp` into the generated addon's `maps/` folder and name it `gm_inf_island.bsp`.
6. Start GMod and run `map gm_inf_island` in the developer console.

The BSP is a small InfMap2 base. It is not generated from the island mesh, and this project does not include a copied third-party BSP. InfMap2's [map instructions](https://github.com/Def-Try/infmap2#creating-your-own-infmap) require `inf` as the second underscore-separated word; `gm_inf_island` follows that convention. The addon reads terrain data relative to GMod's [`LUA` search path](https://wiki.facepunch.com/gmod/File_Search_Paths).

## Scale and resolution

The default settings create a square island about 10 km across on a 2,048-unit grid. A square export produces 261 by 261 samples including the two-cell seabed border on each side. Change these options to trade detail for memory and build time:

The builder rejects heightfields above 2,000,000 samples before allocating their buffers. Increase the grid step or reduce the world width if a build exceeds that limit.

| Option | Default | Effect |
| --- | ---: | --- |
| `--world-width` | `524288` | Longest island side in Hammer units |
| `--grid-step` | `2048` | Target horizontal spacing between samples |
| `--max-height` | `16384` | Highest land point above sea level |
| `--sea-floor` | `-4096` | Underwater terrain and outside-field fallback |
| `--padding-cells` | `2` | Flat seabed cells around the exported mesh |

Example with a denser heightfield:

```bash
python3 tools/island_builder.py island.json --output build/gm_inf_island_detail --grid-step 1024
```

## Files

- `tools/elaborate-export.js` — browser-console exporter for Elaborate.
- `tools/island_builder.py` — JSON validation, mesh rasterization, heightfield encoding, and addon generation.
- `tools/templates/` — generated InfMap2 Lua config and addon metadata.
- `tests/fixtures/elaborate-small.json` — deterministic converter fixture.
- `gmod/island_infmap2/README.md` — instructions installed with the generated addon.

## Verify the toolchain

```bash
python3 -m unittest discover -s tests -v
node --test tests/elaborate-export.test.js
```

Run a small end-to-end fixture build:

```bash
python3 tools/island_builder.py tests/fixtures/elaborate-small.json \
  --output build/fixture-island \
  --world-width 2 --grid-step 1 --max-height 20 \
  --sea-floor -100 --padding-cells 1
```

The fixture is only for checking the conversion pipeline; it is not a playable island. GMod, Hammer, and VBSP are not installed in the build environment, so the final BSP copy, terrain loading, and water appearance still need an in-game check on a local GMod installation.

## Interchange format

The exporter writes JSON with `format: "elaborate-island-mesh"`, `version: 1`, vertex coordinates/heights/sea flags, and indexed triangles. The builder samples that triangle mesh into row-major signed 16-bit little-endian heights. The generated InfMap2 callback loads the binary data once and bilinearly samples it; points outside the field return the configured seabed height.
