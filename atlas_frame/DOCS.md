# Atlas Frame (Home Assistant add-on)

Shows the atlas on The Frame's Art Mode, or on any screen that can show a picture file: one map at a
time, lit by the sun of that moment, with the moon, cut to the next map every few minutes.
Controlled from Home Assistant; reports back on `sensor.atlas_frame`.

## What it does
Every few seconds it reads its controls. While the Frame is in Art Mode it pushes the next map when
one is due, when Art Mode comes on, when you press "next map", or when you change a control. Each
push: render (about 1 s), write the picture to its output files (see Other screens), then upload,
select and delete its own previous upload on the Frame. The files are updated even while the Frame
is away. It never wakes a TV in
standby, never pushes while the TV shows anything but Art Mode, and never touches pictures it did
not upload. If the TV or a data source does not answer, it waits or leaves that layer out.

## Install
1. **Add the repository:** Settings, Add-ons, Add-on Store, the three dots, Repositories, add
   `https://github.com/mwiorek/ha-addons`.
2. **Install** "Atlas Frame" from the store. Home Assistant downloads a ready-made image, so this
   takes moments; updates appear like any other add-on's.
3. **Check the weather entity.** The add-on's Configuration option `weather_entity` defaults to
   `weather.forecast_home`, which does not exist on every system. Open Developer Tools, States,
   search "weather.", and if that name is not there, set `weather_entity` to the one you have. With a
   wrong name the weather cartouche and city weather are left out.
4. **Controls:** copy `atlas_frame_package.yaml` (in the repository's `atlas_frame` folder) to
   `config/packages/atlas_frame.yaml`, and make sure `configuration.yaml` has
   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```
   The `packages:` line goes **under your existing `homeassistant:` key**. Do not add a second
   `homeassistant:` block: that breaks the configuration. Restart Home Assistant. Without the
   package the add-on runs on defaults: follow the sun, 2 minutes, every installed map.
5. **Switch on the layers you want.** The helpers `atlas_frame_weather` (temperature and wind at
   the cities) and `atlas_frame_home_readings` (your own sensor at home) start **off**, and those
   layers only draw once they are on. The weather cartouche (`atlas_frame_legend`) starts on.
6. **Home sensors (optional):** in the add-on options, `home_sensors` takes your own Home Assistant
   sensors: `temperature`, `pressure`, `wind_speed`, and `wind_from` (the direction the wind blows from,
   in degrees or as N, NW, …). Any unit Home Assistant shows works (°C or °F; hPa, inHg, mmHg …; m/s,
   km/h, mph, knots): each sensor is converted from its own unit. Empty fields are fine. A sensor you set
   here is what the legend and the home dot show; the weather entity fills only the rest.
7. **Maps:** **The World** and **The World (population)** are built in; there is nothing to set up.
8. **Start** the add-on. It begins in **preview** mode: no TV needed, each picture is written to
   `/share/atlas_frame/latest.jpg` (the `share` folder on the Samba share). To watch it without
   opening the share, add a *Local File* camera or a *Picture* card pointing at that file. That
   file stays on when the Frame is set up; it is also how other TVs show the maps (Other screens).

### How to tell it is working
- The add-on's Log shows `Atlas Frame started: preview pictures in /share/atlas_frame, ...`.
- `sensor.atlas_frame` appears under Developer Tools, States. **Look at its `maps_missing`
  first**: it names chosen maps that are not installed (an empty maps folder shows up here).
- `latest.jpg` changes every few minutes, or at once when you press `input_button.atlas_frame_next`.

## When the Frame is on the wall
Not tested on a real TV yet (see the end of this page). Start in preview mode first.
1. Give the Frame a fixed IP address in the router.
2. Add-on Configuration: `tv_host` = that address, `preview_only` off. Restart the add-on.
   (`preview_only` on means: leave the Frame alone and only write the output files.)
3. Put the TV in Art Mode. The first time, the TV asks to allow "Atlas": allow it. The add-on keeps
   the permission in its own storage.
4. **Watch the first push**: the map should change while staying in Art Mode. If the TV accepts the
   upload but the picture does not change, turn on the add-on option `select_show` and restart.

## Maps
The add-on comes with **The World** (W1), **The World (population)** (W1P: the same sheet with
where people live in place of the countries' colours, by day the density as a heat, by night the
lights of the cities) and **The World (temperature)** (W1T: the mean annual temperature of land and
sea, 1970 to 2000, with the real city lights by night) and **The World (economic output)** (W1G: what
the people round each place produce, estimated from where people live and their country's GDP per person,
red in the rich city centres and blue on land with little or none; by night under dimmed city lights) and
**The World (GDP per person)** (W1C: how much each person produces, by district, 2024, at purchasing power
parity, from Kummu et al. 2025; land where nobody lives stays plain paper; by night under the city lights).
**The World (temperature now)** (W1L) is the
same sheet coloured by the current temperature: every two hours the add-on fetches the NOAA GFS model's
air temperature over land and sea surface temperature (about 2 MB, from the PacIOOS ERDDAP server at
pae-paha.pacioos.hawaii.edu, so Home Assistant needs internet access) and recolours the map once; the
pushes in between cost no more than any other map. Its legend shows the hour's values at a few places
and the model time. If the server cannot be reached the last data is kept; after 12 hours without
data the map shows the 1970 to 2000 average instead, and its legend says so.
**The World (snow and ice now)** (W1S, not built in) and **Europe (snow and ice now)** (R1S, in a map
pack) are the political maps with the day's snow on the land and ice on the sea and lakes laid over them,
from NOAA's daily snow and ice chart of the Northern Hemisphere (IMS, 4 km, about 450 KB a day from
noaadata.apps.nsidc.org). The add-on looks for a new chart every three hours (it comes out once a day,
early afternoon UTC) and lays the snow once per chart; mountains show through the snow, and borders and
names stay on top. The key gives the day's snow area, its share of the northern land, the sea and lake
ice area, and the chart's date. With no chart, or none for a week, the map shows no snow and the key
says so. Each data map carries its
own legend in the bottom-left box. **The World (land cover)** (W1U: forest, cropland, pasture, towns
and desert, blended where they share the ground) is known to the add-on but not shipped with it: it
joins the rotation once its files are installed beside the add-on. **The World (clock)** (W1Z: how far
the clock runs ahead of the sun, each time zone shaded west to east, its borders in red) likewise: it comes in three
versions for the three states of the world's clocks, W1ZW (northern winter), W1ZS (northern summer) and W1ZM (the
mixed weeks in March and around 1 November, when North America is on summer time and Europe is not). Put `W1Z` in the
rotation and the add-on shows the version that matches today's clocks; the option `clock_version` (`current`,
`winter`, `summer`, `mixed`) pins one instead. Any version that is installed can be shown; W1Z is skipped until one
is. More maps can be added beside them, without
rebuilding or updating the add-on, from either of two folders:

- **My maps:** the add-on's own folder, `addon_configs/e353e52e_atlas_frame/maps` on the Samba share
  (`/config/maps` inside the add-on; it is made on first start). Put a map's files there. The first
  part of the name comes from the repository address; look at the `addon_configs` folder on your
  share if yours differs.
- **A maps folder on the NAS:** Settings, System, Storage, Add network storage. Usage **Share**,
  a name such as `atlas`, the NAS address and folder. It appears to the add-on as `/share/atlas`;
  set the option `maps_folder: /share/atlas` and restart the add-on once.

Both take the same layout, which the atlas renderer writes:

```
R7_4k.png  R7N_4k.png     the day and night maps, 3840 x 2160, lossless (.jpg also works)
places/R7.json            the map's places, label boxes and legend spot
grids/R7.npz              the map's globe grid
```

A map joins the rotation at its next turn once all four of its files are there; until then it is
skipped. `sensor.atlas_frame` lists `maps_available`, `maps_missing` names the maps you named one
by one that are not installed, and `maps_catalog` lists every map id with its name and whether it is
built in, which pack carries it, or not installed. The same folders also **update** a map: a newer copy of a built-in or
side-loaded file is used at the map's next turn.

**Lossless maps:** the map pictures can be `.png` or `.jpg`. Use PNG: every picture the add-on
makes starts from these, so a JPEG base map's softness (colour stored at half resolution, which
blurs thin coloured lettering) is in every render after it. Within a folder the `.png` is used
before the `.jpg`, so dropping a PNG beside a JPEG upgrades that map at its next turn.
`files_from` on the sensor says which kind was used, e.g. `my maps (png)`.

For each file the add-on uses the first good copy: the maps folder, then my maps, then the built-in
one. A file that is incomplete or not 3840 x 2160 is skipped, with a note, so a half-copied map
never breaks a push; if the NAS is offline the other maps carry on. `files_from` on the sensor
shows where the map on the wall came from.

**Which clock map:** the option `clock_version` decides what `W1Z` shows: `current` (default) the version whose
clocks match today's, so it changes by itself in March, April, October and November; `winter`, `summer` or `mixed`
always that one (or today's, if that one is not installed).

**Back to the built-in maps:** set the option `maps_source: templates` and restart. Side-loaded files
are left where they are and ignored until you set it back to `auto`.


### Map packs

Further maps come as **map packs**: one `.atlaspack` file per purchase, licensed to you.

1. Copy the file, as it is (do not unzip it), into `share/atlas_frame/packs` on Home Assistant
   (over Samba: `\\homeassistant\share\atlas_frame\packs`; the folder appears once the add-on has started).
2. Within a minute the add-on checks the pack's licence, installs its maps into its own storage and
   lists the pack under `map_packs` on `sensor.atlas_frame`, with the name it is licensed to.
3. Add `pack:<pack id>` (or the pack's map ids, or `installed`) to `input_text.atlas_frame_maps` to put them in the rotation.

Delete the file to remove the pack; replace it to update it. A pack whose licence does not check out,
or whose files were changed, is not installed and is listed under `map_packs: refused` with the reason.
A map that is not built into the add-on is shown only while an installed pack's licence covers it.

## Other screens
Every push also writes the picture (3840 x 2160) to each path in the option `output_files`, the
Frame or not. The extension picks the encoding:

| Extension | Encoding | Size |
|---|---|---|
| `.png` | lossless | about 11 MB |
| `.jpg` | JPEG at the option `jpeg_quality` (default 95), colour at full resolution | about 3.5 MB at 95 |

To compare them on a screen, list both (`latest.jpg` and `latest.png`) and switch between them in
the player. The Frame always gets the JPEG. The file is replaced in one step, so a player never reads half a picture. Default:
`/share/atlas_frame/latest.jpg`. Add or change paths to suit the screen; remove them all if only the
Frame should get the maps. A path must be a full path ending in `.jpg`; the folder is made if needed.

Where to put a file:
| Path starts with | Reached as |
|---|---|
| `/share/` | the `share` folder on the Samba share, or a NAS share added under Settings, System, Storage (usage Share) |
| `/media/` | Home Assistant's media folder: Media in the sidebar, and `media-source://media_source/local/...` for casting |
| `/config/maps/..` | not for output: that is my maps |

**A TV with a media player that loops a file** (VLC, Kodi, a Philips or Android TV's own player):
open `latest.jpg` over the Samba share and set it to repeat. It reloads the file as it changes.

**Chromecast, Google TV, DLNA and other cast targets:** add a path in the media folder, e.g.
`/media/atlas_frame/latest.jpg`, and let an automation cast each new picture. After every push
the add-on fires the event `atlas_frame_rendered` with `map_id`, `map`, `mode`, `pushed_at`,
`files`, `media_ids` (the `media-source://` ids of files in the media folder) and `tv` (whether
the Frame got it):
```yaml
automation:
  - alias: Atlas on the living-room TV
    triggers:
      - trigger: event
        event_type: atlas_frame_rendered
    conditions:
      - condition: template
        value_template: "{{ trigger.event.data.media_ids | count > 0 }}"
    actions:
      - action: media_player.play_media
        target:
          entity_id: media_player.living_room_tv
        data:
          media:
            media_content_id: "{{ trigger.event.data.media_ids[0] }}"
            media_content_type: image/jpeg
```
Add a condition on the TV's state if it should only get maps while it is idle; the add-on cannot
tell whether another TV is showing something else. The same event can drive anything else that
takes a picture: a notification, a wall tablet, an upload.

## Controls (Home Assistant helpers)
| Helper | What |
|---|---|
| `input_boolean.atlas_frame_on` | Pushing on or off |
| `input_select.atlas_frame_mode` | Follow the sun, Home light, Hold day, Hold dark |
| `input_number.atlas_frame_minutes` | Minutes per map, 1 to 30 |
| `input_text.atlas_frame_maps` | Maps in the rotation, in order: map ids and words (below), e.g. `R1,R7,R15,W1` or `installed,-R11`; maps not installed are skipped |
| `input_button.atlas_frame_next` | Next map now |
| `input_boolean.atlas_frame_legend` | The weather legend in a free corner (on by default) |
| `input_boolean.atlas_frame_weather` | Temperature and wind at each map's cities (first draft look) |
| `input_boolean.atlas_frame_home_readings` | Your own sensors at home, where home is on the map |

Map ids: W1 The World, W1P The World (population), W1T The World (temperature), W1L The World (temperature now), W1G The World (economic output), W1C The World (GDP per person), W1U The World (land cover, not built in), W1Z The World (clock, not built in: today's version of W1ZW, W1ZS, W1ZM), R1 Europe, R2 Asia, R3 Africa, R4 North America, R5 South America,
R6 Oceania, R7 Scandinavia, R8 Northern Africa, R9 The Middle East, R10 East Asia, R11 United
States, R12 Southern Europe, R13 Southern Africa, R14 Indian Subcontinent, R15 British Isles,
R16 Central America. Each region also comes as population (`P`), temperature (`T`) and temperature
now (`L`), e.g. `R7P` Scandinavia (population), when installed. W1S The World (snow and ice now, not
built in) and R1S Europe (snow and ice now) show the day's snow and ice. `maps_catalog` on `sensor.atlas_frame`
lists them all.

**Words for sets of maps**, so the list need not spell out every id. Separate with commas or spaces,
in any case; ids and words can be mixed, and the rotation keeps the order they come in, each map once.

| Word | Maps |
|---|---|
| `installed` | Every map whose files are installed now; a pack added later joins by itself |
| `all` | Every map (the clock as W1Z) |
| `world` | W1, W1P, W1T, W1L, W1S, W1G, W1C, W1U, W1Z |
| `gdp` | W1G and W1C, the two economic Worlds |
| `regions` | R1 to R16 |
| `population`, `temperature`, `live` | That form of The World and of every region (W1P, R1P … R16P) |
| `snow` | W1S and R1S, snow and ice now |
| `clock` | W1Z |
| `pack:<id>` | The maps of an installed map pack (its id is under `map_packs`) |
| `-<id or word>` | Leave those out, wherever they are in the list: `regions,-R11` |
| `<place>:<versions>` | A row of the matrix, as the maps card writes it: `R7:BPT` is R7, R7P and R7T (see The maps card) |

Maps that come from a word and are not installed are skipped without a note; only ids named one by one
are reported under `maps_missing`. A word or id the add-on does not know is named under `maps_unknown`.
`map_words` on the sensor repeats this table.

`sensor.atlas_frame`: the map on the wall, with mode, when it was pushed, when the next is due,
whether Art Mode is on, and the last error or note. After a push of W1L, `live` says where its
colours came from (`live` or `climate`), the model time on its legend, when it last fetched, and the
last fetch error; after W1S or R1S, `live` is `live` (the chart's date on the key) or `none` (no snow
shown).

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

### The maps card
A card for choosing the maps without typing ids: a matrix with a row per place (The World, R1 to R16) and a
column per version (the map itself, population, temperature, temperature now, snow now, economic output,
land cover, clock). Each cell is a toggle and shows whether that map is installed; a row's or column's heading turns the
whole row or column on or off, so live temperature can be on for The World alone. *Only installed* hides the
places that have nothing installed.

1. The add-on puts the card in Home Assistant's `www` folder when it starts (`/local/atlas-frame-card.js`).
2. Once: **Settings, Dashboards, ⋮, Resources, Add resource**: URL `/local/atlas-frame-card.js`, type
   *JavaScript module*. Reload the browser.
3. Add the card to a dashboard (it is listed as *Atlas Frame maps*), or in YAML:
```yaml
type: custom:atlas-frame-card
```
It writes the rotation to `input_text.atlas_frame_maps` as matrix rows, e.g. `W1:BL R7:BPT` (W1 and W1L; R7,
R7P and R7T), so the helpers package must be installed. Rows can be typed by hand too: `B` the map, `P`
population, `T` temperature, `L` temperature now, `S` snow and ice now, `G` economic output, `U` land cover,
`Z` clock. Maps chosen
another way that have no cell (W1ZW, say) are kept when the card saves.

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
  Data: the `weather_entity` option. The default, `weather.forecast_home` (Met.no), is only there on
  systems that set it up: check the name under Developer Tools, States and change the option if it
  is missing. Units are converted from whatever the entity reports. **Your home sensors win:** for each
  of temperature, pressure and wind that has a sensor under `home_sensors`, the legend shows the sensor,
  not the weather entity (a forecast model's value for your area), and *feels like* is worked out from
  it; the barometer's trend is then the sensor's own. The legend works from the sensors alone if there
  is no weather entity.
- **Weather at cities** (`atlas_frame_weather`): current temperature and wind from Open-Meteo (free,
  no key) for each map's largest labelled cities, refreshed at most every 15 minutes per map. Only
  the cities' public coordinates are sent. Figures keep off the map's lettering; a city with no
  free space nearby is left out (about 78 % of cities get one). Options, `weather_show`: any of
  temperature, pressure, wind.
- **Home readings** (`atlas_frame_home_readings`): your own sensors, set in the add-on options under
  `home_sensors`, each converted from its own unit. Drawn at home (Home Assistant's location) on maps
  that show it, with the same values as the legend.
- **Adding a data type:** a source in `app/artmode/sources.py` that returns readings, and a layer
  in `app/artmode/layers.py` that draws them, then a switch here.

## Troubleshooting
- **A map you added does not show:** the maps folder is empty or one of the map's four files is
  missing. `sensor.atlas_frame` lists `maps_missing`. Add the missing files (see Maps); the map joins
  at its next turn.
- **The TV does not change:** the Frame must be on and in **Art Mode**; the add-on never wakes a TV
  in standby or pushes over other content. If it is in Art Mode and the TV accepted the upload but
  the picture stays, turn on `select_show`.
- **No weather on the map:** the `weather_entity` name is wrong. Check Developer Tools, States, and
  set the option. City weather and home readings also need their helpers switched on.
- **The output file does not change:** `sensor.atlas_frame` shows `output_files` and, if one could
  not be written, the `error`. A file that fails never stops the others or the Frame.
- **Nothing happens at all:** check `atlas_frame_on` is on, and read the add-on's Log.

## Building it yourself
To change the code and run your own build, copy the `atlas_frame` folder to Home Assistant's
`/addons` folder and delete the `image:` line from its `config.yaml`. It then shows under Local
add-ons, and Home Assistant builds it from the Dockerfile. **Uninstall the store version first, or
remove your old local copy before copying a new one**: otherwise both appear in the list.

## Not yet tested
- Talking to the Frame (`artmode/frame.py`): written from the `samsungframetv` README, not run
  against a TV. The Frame Pro 2026 is not listed as tested by that library.
- The service was run end to end from `app/` against a stand-in Home Assistant, in preview mode.
