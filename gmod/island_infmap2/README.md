# Generated InfMap2 Island Addon

The builder writes this package from an Elaborate mesh. It contains the InfMap2 map configuration and sampled terrain data; it does not include a BSP or any Half-Life 2 assets.

## Requirements

- Garry's Mod with its default Half-Life 2 content.
- InfMap2 by Def-Try: <https://github.com/Def-Try/infmap2>

## Install

1. Copy this addon folder into `garrysmod/addons/`.
2. Create this addon's `maps/` folder if needed. Copy InfMap2's `maps/gm_inf_bliss.bsp` into it and rename the copy `gm_inf_island.bsp`. InfMap2 uses the BSP as its base and requires `inf` as the second underscore-separated word in the map name.
3. Start Garry's Mod and run `map gm_inf_island` in the developer console.

The copied BSP remains an InfMap2 base map. The island terrain is sampled from this addon's generated data at runtime. GMod's bundled Half-Life 2 content supplies the referenced `nature/grassfloor001a` and `nature/water_coast01` materials.

## Multiplayer and Linux

The server sends `lua/infmap2/gm_inf_island/data/part_*.lua` through `AddCSLuaFile`. Keep all of these generated files together with `main.lua`. Builds made with `--coastal-road` also send `road.lua` and every `road_data/part_*.lua` file automatically. Clients do not need a manually copied `terrain.bin`; InfMap2 itself and `maps/gm_inf_island.bsp` still need normal client installation or server distribution.

All runtime filenames are lowercase. This map leaves InfMap2's optional grass-blade shader disabled. Compatibility was checked against InfMap2 0.41b source, including its doubled height-callback coordinates, but Linux gameplay has not been tested here.

## Coastal road (when enabled)

Build with `--coastal-road` to include a continuous coastal highway. In the developer console, `ih17_road_start` moves your player to its start. A terrain-only build does not register that command.

The road uses the HL2 coastline asphalt/gravel texture pair: `concrete/concretefloor037b` and `nature/gravelfloor004a`. The renderer references their original textures using model-compatible shader wrappers. The asphalt, gravel shoulders, and earth slopes have matching collision triangles attached to InfMap2's normal terrain chunks on both server and client. They do not depend on the coarse terrain mesh resolving the road width. Nearby road meshes stream in and distant ones are freed.

`road.json` contains the generated route and cross-sections for offline inspection. The road starts near sea level and has gentle rises; it has no broken bridges, tunnels, lane-paint overlays, or automatic roadside props. InfMap2 0.41b is the supported API target. Run an in-game vehicle and chunk-boundary check before relying on this experimental road for a server.

## Highway 17 set-dressing references

These Half-Life 2 models fit the rocky coast palette and can be spawned from GMod's prop browser:

- `models/props_wasteland/rockcliff01b.mdl` — large cliff outcrop.
- `models/props_wasteland/rockcliff_cluster02a.mdl` — broken rock cluster.

They are references only in this first build. InfMap2's virtual entity placement needs an in-game pass before the generator can scatter props reliably across the island.

## First-version limits

- One finite island is generated, with a camera-following 28,000-unit square ocean surface at sea level. Its edge may show from high viewpoints or beyond the expected render range. The ocean has no swimming or water physics.
- InfMap2 exposes one terrain material for its generated terrain, so the initial pass does not blend grass, beach, and cliff textures.
- A coastal road is included only when built with `--coastal-road`; roadside props are not automatically placed yet. Coarse terrain settings produce broad road cuts, and narrow bays may be rounded off by route smoothing.
- This package was not run inside GMod in the build environment; test the base BSP copy and water material on your installation.
