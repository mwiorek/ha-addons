# Licences and credits

## What is under which licence

| What | Where | Licence |
|------|-------|---------|
| Source code and documentation | everything not listed below | MIT, see `LICENSE` |
| The maps and artwork: map pictures, their places and globe grids, the moon, the icon and logo | `atlas_frame/app/maps/`, `atlas_frame/app/places/`, `atlas_frame/app/grids/`, `atlas_frame/app/moon.png`, `atlas_frame/icon.png`, `atlas_frame/logo.png` | Creative Commons Attribution-NonCommercial 4.0, see `LICENSE-CC-BY-NC-4.0.txt` |

To credit a map: "Antique Atlas Series by Martin Wiorek, CC BY-NC 4.0", with a link to this repository,
and keep the data credits below.

`atlas_frame/app/moon.png` was generated with Microsoft Copilot. It is offered under the same licence
as the maps, as far as any copyright in an AI-generated image exists.

## Files from others, not covered by the licences above

| File | Owner and terms |
|------|-----------------|
| `atlas_frame/app/fonts/IMFe*.ttf` | IM Fell types, (c) 2010 Igino Marini. SIL Open Font License 1.1, see `atlas_frame/app/fonts/OFL.txt` |

## Data credits for the maps

The credits are kept here, not printed on the maps. Anyone who shares a map should pass them on.

| Source | Used for | Terms |
|--------|----------|-------|
| Natural Earth, naturalearthdata.com | Coastlines, borders, rivers, lakes, places, Gray Earth relief, land cover, time zones; the countries' GDP and population figures behind the economic output map (W1G) | Public domain |
| NOAA NCEI ETOPO 2022 (60 arc-second), doi:10.25921/fd45-gt74 | Elevation, sea-floor relief, peaks | Public domain |
| IHO-IOC GEBCO Gazetteer of Undersea Feature Names, www.gebco.net | Undersea names | Free, with credit |
| OSCAR surface currents (Earth & Space Research), via NOAA CoastWatch ERDDAP `jplOscar` | Ocean currents | Free to use and redistribute |
| SCAR Antarctic Digital Database, rock outcrop (medium resolution, v7.11), British Antarctic Survey | The world map's corner discs | CC BY 4.0 |
| `flag-icons` 7.2.3, (c) Panayiotis Lipiridis | Flags in the flag panels | MIT |
| NASA Black Marble 2016 (VIIRS night lights), via NASA GIBS | Night maps | Free, with credit. Imagery provided by NASA's Global Imagery Browse Services (GIBS), part of NASA's Earth Science Data and Information System (ESDIS) |
| Kummu, M. et al. 2025, gridded GDP per capita by subnational area (Scientific Data 12:178), updated to 2024, doi:10.5281/zenodo.18429133 | The World (GDP per person), W1C | CC BY 4.0 |
| WorldClim 2.1 (Fick and Hijmans 2017), worldclim.org | The temperature maps (W1T; W1L when no live data is at hand): mean annual temperature over land, 1970-2000 | CC BY 4.0 |
| NOAA OI SST v2, NOAA PSL, psl.noaa.gov | The temperature maps: mean sea surface temperature, 1971-2000 | Public domain |

At run time the add-on reads current weather from Open-Meteo (open-meteo.com, CC BY 4.0) when the
city weather layer is on. For The World (temperature now), W1L, it reads the current air and
sea surface temperature of the NOAA GFS model (NCEP, public domain) every two hours from the PacIOOS
ERDDAP server (pae-paha.pacioos.hawaii.edu, dataset `ncep_global`). For the snow maps (W1S, R1S, from a map pack) it reads
the day's snow and ice chart: U.S. National Ice Center (2008), IMS Daily Northern Hemisphere Snow and Ice
Analysis at 1 km, 4 km, and 24 km Resolutions (G02156, Version 1), National Snow and Ice Data Center,
doi:10.7265/N52R3PMC (noaadata.apps.nsidc.org); free to use, with this credit.
