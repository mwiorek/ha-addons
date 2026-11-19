# Atlas Frame (Home Assistant add-on)

Shows the atlas on The Frame's Art Mode: one map at a time, lit by the sun of that moment, with the
moon, cut to the next map every few minutes. Controlled from Home Assistant; reports back on
`sensor.atlas_frame`.

## What it does
Every few seconds it reads its controls. While the Frame is in Art Mode it pushes the next map when
one is due, when Art Mode comes on, when you press "next map", or when you change a control. Each
push: render (about 1 s), upload, select, delete its own previous upload. It never wakes a TV in
standby, never pushes while the TV shows anything but Art Mode, and never touches pictures it did
not upload. If the TV or a data source does not answer, it waits or leaves that layer out.

## Install
1. **Add the repository:** Settings, Add-ons, Add-on Store, the three dots, Repositories, add
   `https://github.com/mwiorek/ha-addons`.
2. **Install** "Atlas Frame" from the store. Home Assistant downloads a ready-made image, so this
   takes moments; updates appear like any other add-on's.
3. **Controls:** copy `atlas_frame_package.yaml` (in the repository's `atlas_frame` folder) to
   `config/packages/atlas_frame.yaml`, make sure `configuration.yaml` has
   `homeassistant: packages: !include_dir_named packages`, and restart Home Assistant. Without them
   the add-on runs on defaults: follow the sun, 2 minutes, every installed map.
4. **Start** the add-on. It begins in **preview** mode: no TV needed, each picture is written to
   `/share/atlas_frame/latest.jpg` (the `share` folder on the Samba share). Watch it change.

## When the Frame is on the wall
1. Give the Frame a fixed IP address in the router.
2. Add-on Configuration: `tv_host` = that address, `preview_only` off. Restart the add-on.
3. Put the TV in Art Mode. The first time, the TV asks to allow "Atlas": allow it. The add-on keeps
   the permission in its own storage.
4. **Watch the first push**: the map should change while staying in Art Mode. If the TV accepts the
   upload but the picture does not change, the select call needs `show=True` (the `ATLAS_SHOW`
   setting in `artmode/frame.py`).

## Maps
The add-on comes with **The World** (W1). The regional maps are added beside it, without
rebuilding or updating the add-on, from either of two folders:

- **My maps:** the add-on's own folder, `addon_configs/<…>_atlas_frame/maps` on the Samba share
  (`/config/maps` inside the add-on; it is made on first start). Unzip a map pack there.
- **A maps folder on the NAS:** Settings, System, Storage, Add network storage. Usage **Share**,
  a name such as `atlas`, the NAS address and folder. It appears to the add-on as `/share/atlas`;
  set the option `maps_folder: /share/atlas` and restart the add-on once.

Both take the same layout, which map packs and the atlas renderer write:

```
R7_4k.jpg  R7N_4k.jpg     the day and night maps, 3840 x 2160
places/R7.json            the map's places, label boxes and legend spot
grids/R7.npz              the map's globe grid
```

A map joins the rotation at its next turn once all four of its files are there; until then it is
skipped. `sensor.atlas_frame` lists `maps_available`, and `maps_missing` names the chosen maps that
are not installed. The same folders also **update** a map: a newer copy of a built-in or
side-loaded file is used at the map's next turn.

For each file the add-on uses the first good copy: the maps folder, then my maps, then the built-in
one. A file that is incomplete or not 3840 x 2160 is skipped, with a note, so a half-copied map
never breaks a push; if the NAS is offline the other maps carry on. `files_from` on the sensor
shows where the map on the wall came from.

**Back to the built-in maps:** set the option `maps_source: templates` and restart. Side-loaded files
are left where they are and ignored until you set it back to `auto`.

## Controls (Home Assistant helpers)
| Helper | What |
|---|---|
| `input_boolean.atlas_frame_on` | Pushing on or off |
| `input_select.atlas_frame_mode` | Follow the sun, Home light, Hold day, Hold dark |
| `input_number.atlas_frame_minutes` | Minutes per map, 1 to 30 |
| `input_text.atlas_frame_maps` | Maps in the rotation, in order, e.g. `R1,R7,R15,W1`; maps not installed are skipped |
| `input_button.atlas_frame_next` | Next map now |
| `input_boolean.atlas_frame_legend` | The weather legend in a free corner (on by default) |
| `input_boolean.atlas_frame_weather` | Temperature and wind at each map's cities (first draft look) |
| `input_boolean.atlas_frame_home_readings` | Your own sensors at home, where home is on the map |

Map ids: W1 The World, R1 Europe, R2 Asia, R3 Africa, R4 North America, R5 South America,
R6 Oceania, R7 Scandinavia, R8 Northern Africa, R9 The Middle East, R10 East Asia, R11 United
States, R12 Southern Europe, R13 Southern Africa, R14 Indian Subcontinent, R15 British Isles,
R16 Central America.

`sensor.atlas_frame`: the map on the wall, with mode, when it was pushed, when the next is due,
whether Art Mode is on, and the last error or note.

A dashboard card:
```yaml
type: entities
title: Atlas Frame
entities:
  - sensor.atlas_frame
  - input_boolean.atlas_frame_on
  - input_select.atlas_frame_mode
  - input_number.atlas_frame_minutes
  - input_button.atlas_frame_next
  - input_boolean.atlas_frame_weather
  - input_boolean.atlas_frame_home_readings
```

## Data on the map
- **The weather legend** (`atlas_frame_legend`, on by default): an engraved cartouche in each map's
  freest corner or edge (clear of the title, flags and scale bar, covering the least lettering),
  headed "Observations at" your Home Assistant location's name (or `legend_place` in the options),
  with the local time. It shows:
  - a barometer dial with the old words (Stormy, Rain, Change, Fair, Very Dry), the pressure in hPa
    and whether it is rising, falling or steady over three hours (the add-on samples the pressure
    every 5 minutes, even with the TV off; the word appears once it has three hours of samples);
  - the air temperature and what it feels like: the weather entity's own apparent temperature if
    it has one, otherwise wind chill in the cold and the heat index in the heat, as weather
    services report it;
  - a compass rose with a fletched arrow flying downwind, longer with more feathers as the wind
    rises, the Beaufort name and point it blows from, and the speed in m/s.
  Data: the `weather_entity` option, `weather.forecast_home` (Met.no, built into Home Assistant)
  by default. Units are converted from whatever the entity reports.
- **Weather at cities** (`atlas_frame_weather`): current temperature and wind from Open-Meteo (free,
  no key) for each map's largest labelled cities, refreshed at most every 15 minutes per map. Only
  the cities' public coordinates are sent. Figures keep off the map's lettering; a city with no
  free space nearby is left out (about 78 % of cities get one). Options, `weather_show`: any of
  temperature, pressure, wind.
- **Home readings** (`atlas_frame_home_readings`): your own sensors, set in the add-on options under
  `home_sensors` (temperature in deg C, pressure in hPa, wind speed in m/s, wind direction in
  degrees it blows from). Drawn at home (Home Assistant's location) on maps that show it.
- **Adding a data type:** a source in `app/artmode/sources.py` that returns readings, and a layer
  in `app/artmode/layers.py` that draws them, then a switch here.

## Building it yourself
To change the code and run your own build, copy the `atlas_frame` folder to Home Assistant's
`/addons` folder and delete the `image:` line from its `config.yaml`. It then shows under Local
add-ons, and Home Assistant builds it from the Dockerfile.

## Not yet tested
- Talking to the Frame (`artmode/frame.py`): written from the `samsungframetv` README, not run
  against a TV. The Frame Pro 2026 is not listed as tested by that library.
- The service was run end to end from `app/` against a stand-in Home Assistant, in preview mode.
