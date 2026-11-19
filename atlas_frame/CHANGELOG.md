# Changelog

## 0.4.1
- New option `select_show` for the TV picture-select call (was a code setting).
- Setup guide rewritten from first-install feedback: checking `weather_entity`, the helpers that start off, the packages line, sensor units, regional maps and where map packs come from, how to tell it works, and a troubleshooting list.

## 0.4.0
- First public release, installable from the `mwiorek/ha-addons` repository. Home Assistant pulls a
  prebuilt image instead of building it.
- Built in: The World (W1). The regional maps are side-loaded: put a map's files into
  `addon_configs/…_atlas_frame/maps`, or point `maps_folder` at a NAS share. A map joins the
  rotation as soon as all four of its files are there, without a restart.
- New option `maps_source`: `auto` (side-loaded maps first) or `templates` (built-in maps only).
- `sensor.atlas_frame` reports `maps_available` and which chosen maps are not installed.
