# Changelog

## 0.5.15
- The snow maps (W1S, R1S) keep the political maps' own panels: the World's most populous nations, Europe's flags by day and largest cities by night. The snow key is gone; the chart's date and the day's snow and ice areas are on `sensor.atlas_frame` (`live`: `stamp`, `snow_km2`, `ice_km2`, `snow_share`). Needs a snow pack built from the new sheets; an older pack still shows its key.
- The snow maps' data is credited in the add-on's NOTICE and in every map pack's NOTICE.txt: U.S. National Ice Center (2008), IMS Daily Northern Hemisphere Snow and Ice Analysis (NSIDC G02156, Version 1), doi:10.7265/N52R3PMC.

## 0.5.14
- The moon on the regional maps now sits where you see it. On a map it is not over, it stands on its arc along the horizon it crosses: the **bottom** edge where it crosses the sky to the south (Europe), the **top** edge where it crosses to the north (Australia). East is on the right, as on the map, and the higher it stands, the further in from the edge. Before, it stood along the top with east on the left (as if facing south), so a moon rising in the north-east was drawn in the map's north-west corner.
- Fix: the moon's lit side on the regional maps is now the side you see lit in the sky. It was aimed at where the sun fell on the moon's strip, which drew the crescent or gibbous moon the wrong way round (lit on the right for a moon whose left is lit, and the reverse).
- New switch `input_boolean.atlas_frame_moon` (on by default, also without it; copy `atlas_frame_package.yaml` again to get it): off leaves the moon and its track off every map. The moon is drawn over any panel it lands on.

## 0.5.13
- New maps: **The World (snow and ice now)**, `W1S`, and **Europe (snow and ice now)**, `R1S`: the political maps with the day's snow on the land and ice on the sea and lakes laid over them, from NOAA's daily IMS chart of the Northern Hemisphere (4 km, about 450 KB a day, via NSIDC). A new chart is looked for every three hours and laid once; one chart serves both maps. Mountains show through the snow; borders and names stay on top. The key gives the snow area, its share of the northern land, the ice area and the chart's date; with no chart for a week the map shows no snow and says so. Both come as a map pack (W1S is not built in); this release has the code that reads and colours them, so a pack with them needs 0.5.13 or later.
- In the rotation: `W1S`, `R1S`, the word `snow` for both, or the letter **S** in a matrix row (`W1:BS R1:BS`). The maps card has a *Snow* column.

## 0.5.12
- Fix: the legend's temperature now comes from your own sensor. With `home_sensors` set, the legend showed the weather entity's value (a forecast model for your area) while the home dot showed the sensor, so the two disagreed with each other and with the sensor. Now the sensors win for temperature, pressure and wind, in the legend and at the home dot alike; the weather entity fills only what you have no sensor for, and *feels like* is worked out from your sensor's temperature.
- Fix: home sensors are read in their own unit. A sensor in °F, inHg, km/h or mph was taken as °C, hPa or m/s (34.5 °F showed as 34.5°); each is now converted from its `unit_of_measurement`. A wind direction given as N, NW, … works too.
- The barometer's three-hour trend follows the pressure the legend shows (your sensor when you have one) and starts again when that changes, so it never compares two instruments.

## 0.5.11
- New built-in map: **The World (GDP per person)**, `W1C`, the per-person companion of W1G. GDP per person at purchasing power parity, by district, 2024 (Kummu et al. 2025, CC BY 4.0), from slate blue through sand to deep red; land where nobody lives stays plain paper, so empty provinces do not borrow their capital's figure. By night under the city lights. Its own legend in the bottom-left box. Ships lossless (PNG).
- In the rotation: add `W1C`, or the new word `gdp` for W1G and W1C together, or the letter **C** in a matrix row (`W1:BGC`). The maps card has a *GDP/p.* column.

## 0.5.10
- Fix: the add-on no longer stops at start when the TV does not answer. It connects to the TV on first use instead of at start, and afresh after any failure; until the TV answers, the log says *TV not answering; waiting* and the output files are still written.
- Known: on a 2026 Frame (LS03H) the TV's control API (ports 8001/8002) accepted connections but never replied, in Art Mode, in TV mode and after a power cycle, so nothing reached the TV. Check that the TV's software is up to date and allow *Atlas* when the TV asks.

## 0.5.9
- Fix: the add-on stopped at start with `No module named 'samsungtvws'`. The `samsungframetv` package installs its module as `samsungframetv`; the connection to the TV now imports it under that name.

## 0.5.8
- **The maps card**: a dashboard card that shows the rotation as a matrix, places by versions, each cell a toggle that also shows whether the map is installed. Turn a whole row or column on or off from its heading; *Only installed* hides the rest. The add-on copies the card to `/local/atlas-frame-card.js` when it starts; add it once as a dashboard resource (DOCS, The maps card).
- The add-on now maps Home Assistant's config folder, to put the card in its `www` folder.
- Matrix rows in `input_text.atlas_frame_maps`: `W1:BL R7:BPT` (W1 and W1L; R7, R7P and R7T). The whole matrix fits in the helper's 255 characters.
- `sensor.atlas_frame` lists the matrix under `maps_matrix` (versions, places, each cell's map and where it comes from).

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
