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

## Highway 17 set-dressing references

These Half-Life 2 models fit the rocky coast palette and can be spawned from GMod's prop browser:

- `models/props_wasteland/rockcliff01b.mdl` — large cliff outcrop.
- `models/props_wasteland/rockcliff_cluster02a.mdl` — broken rock cluster.

They are references only in this first build. InfMap2's virtual entity placement needs an in-game pass before the generator can scatter props reliably across the island.

## First-version limits

- One finite island is generated, with a camera-following 28,000-unit square ocean surface at sea level. Its edge may show from high viewpoints or beyond the expected render range. The ocean has no swimming or water physics.
- InfMap2 exposes one terrain material for its generated terrain, so the initial pass does not blend grass, beach, and cliff textures.
- The map provides the terrain and coastal water foundation. Roadside props and a drivable Highway 17 road are not automatically placed yet.
- This package was not run inside GMod in the build environment; test the base BSP copy and water material on your installation.
