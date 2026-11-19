# Changelog

## 0.4.0
- First public release, installable from the `mwiorek/ha-addons` repository. Home Assistant pulls a
  prebuilt image instead of building it.
- Built in: The World (W1). The regional maps are side-loaded: unzip a map pack into
  `addon_configs/…_atlas_frame/maps`, or point `maps_folder` at a NAS share. A map joins the
  rotation as soon as all four of its files are there, without a restart.
- New option `maps_source`: `auto` (side-loaded maps first) or `templates` (built-in maps only).
- `sensor.atlas_frame` reports `maps_available` and which chosen maps are not installed.
