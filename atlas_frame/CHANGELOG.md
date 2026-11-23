# Changelog

## 0.5.7
- **Words in the rotation**: `input_text.atlas_frame_maps` takes words for sets of maps beside the ids: `installed`, `all`, `world`, `regions`, `population`, `temperature`, `live`, `clock`, `pack:<id>`, and `-<id or word>` to leave some out, e.g. `installed,-R11`. Commas or spaces, any case. A pack's maps no longer have to be typed out one by one, and the full list no longer runs into the helper's 255 characters.
- `sensor.atlas_frame` lists every map id it knows under `maps_catalog`, each with its name and whether it is built in, which pack carries it, or not installed; the words under `map_words`; and anything in the helper it did not understand under `maps_unknown` (it was dropped without a word before).
- `maps_missing` names only the maps named one by one, not every uninstalled map behind a word.

## 0.5.6
- The day/night line now sits on the real sunrise and sunset. The fade from night to day runs from the sun 6 deg below the horizon (end of civil twilight) to 4 deg above, in place of -8 to +2, which put the middle of the fade about 3 deg early: 10-20 minutes ahead of the real sunrise in most places, an hour in the far north in winter.
- **The World (economic output)**, `W1G`, toned down: land with little or no output is a quiet grey instead of slate blue, by day and by night, so the rich centres lead and the empty land no longer reads as water.

## 0.5.5
- New map id: **The World (clock)**, `W1Z`: how far the clock runs ahead of the sun, each time zone shaded from west to east, its borders in red. Not shipped with the add-on: it shows once its versions are installed, W1ZW (northern winter), W1ZS (northern summer) and W1ZM (the mixed weeks in March and around 1 November). `W1Z` in `input_text.atlas_frame_maps` shows the version that matches today's clocks.
- New option `clock_version`: `current` (default) follows today's clocks; `winter`, `summer` or `mixed` pins one version.

## 0.5.4
- **Map packs**: further maps come as one licensed `.atlaspack` file. Copy it into `share/atlas_frame/packs`; the add-on checks its licence and files, installs it into its own storage and lists it, with the licensee, under `map_packs` on `sensor.atlas_frame`. Delete the file to remove the pack.
- Maps that are not built in now need an installed pack whose licence covers them; maps copied loose into the maps folders without one are no longer shown.

## 0.5.3
- New map id: **The World (land cover)**, `W1U`. The add-on knows it but does not ship it: put its four files (`W1U_4k.png`, `W1UN_4k.png`, `places/W1U.json`, `grids/W1U.npz`) into the add-on's maps folder and add `W1U` to `input_text.atlas_frame_maps`.

## 0.5.2
- New built-in map: **The World (economic output)**, `W1G`. What the people round each place produce in a year, estimated from Natural Earth's places and each country's GDP per person, as a smooth gradient: deep red in the rich city centres, through sand, to blue on land with little or no output. By night the same colours under the real city lights, dimmed so the red still shows. Its own legend in the bottom-left box. Ships lossless (PNG). Add `W1G` to `input_text.atlas_frame_maps` to put it in the rotation.

## 0.5.1
- New built-in map: **The World (temperature)**, `W1T`. The mean annual temperature of land and sea surface (WorldClim 2.1, NOAA OI SST, 1970-2000) in place of the political colours; by night a dark tint under the real city lights. Ships lossless (PNG). Add `W1T` to `input_text.atlas_frame_maps` to put it in the rotation.
- New built-in map: **The World (temperature now)**, `W1L`. W1T's sheet coloured by the current temperature (NOAA GFS: air over land, surface over sea), fetched every two hours from the PacIOOS ERDDAP server and applied once per fetch, so the two-minute pushes cost the same as any map. The legend shows the hour's values at five places and the model time; without data for 12 hours it falls back to the 1970-2000 average and says so. `sensor.atlas_frame` reports the live data's source, time and last error. Needs internet access. Add `W1L` to `input_text.atlas_frame_maps`.
- The population and temperature Worlds carry their own legend (colour bar, scale, reference places) in the bottom-left box, in place of the table of nations.
- The World, W1, now ships lossless (PNG), and without the engraved lines along every coast.

## 0.5.0
- New built-in map: **The World (population)**, `W1P`. The same sheet with population density in place of the political colours by day, and city lights by night. Ships lossless (PNG). It joins the rotation by default; with the helpers package, add `W1P` to `input_text.atlas_frame_maps`.
- Lossless base maps: the map pictures can be `.png` (`R7_4k.png`), used before a `.jpg` in the same folder. Drop a PNG beside a map's JPEG to upgrade it. (The political World, W1, is still JPEG in this release.)
- Sharper output: JPEGs now keep colour at full resolution (4:4:4, was 4:2:0), at the new option `jpeg_quality` (default 95, was 90).
- An output file ending in `.png` is written lossless; one ending in `.jpg` as JPEG. List both to compare them.
- New option `output_files`: every push writes the picture to each of these paths, with or without the Frame, and keeps them updated while the Frame is away. For TVs that loop a file (VLC over Samba), Local File cameras and casting. Default `/share/atlas_frame/latest.jpg`, as before.
- The Frame and the files work side by side: `preview_only` now only means "leave the Frame alone".
- The add-on can write to Home Assistant's media folder (`/media`), for casting through media sources.
- New event `atlas_frame_rendered` after each push (map, files, media ids, whether the Frame got it), for automations that show the map elsewhere, e.g. `media_player.play_media`.

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
