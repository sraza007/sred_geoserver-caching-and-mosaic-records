# GeoServer Caching and Mosaic Records

Evidence package for the NexGen ImageMosaic layer.

Evidence collected on 2026-10-07 from the production Calgary GeoServer (`osgis.caltechgroup.com`) in response to reviewer comments on GeoServer caching and mosaic records.

Subject layer: `nexgen:nexgen_site_mosaic` (coverage store `NexGen_Sites`, type ImageMosaic, source `/mnt/nas_storage/data/nexgen_site_mosaic`).

## Background in plain words

- **GeoServer** is the map server that publishes aerial imagery of the NexGen sites to web maps.
- **ImageMosaic** is the GeoServer feature that stitches many separate site images into one seamless map layer. It keeps an **index** (a list of which image files belong to the mosaic and where each one sits on the map) and a **properties file** (its settings).
- **GeoWebCache (GWC)** is GeoServer's tile cache. It saves already-drawn map tiles so they can be served again without redrawing. **Seeding** means pre-drawing tiles in advance; **truncating** means deleting saved tiles so they are redrawn from fresh imagery.
- **Projection (CRS)** is the coordinate system an image is stored in. Images in different projections cannot be combined in one mosaic without first being converted to a common one. The NexGen mosaic uses EPSG:3857 (Web Mercator); some delivered imagery arrived in EPSG:2956 (UTM zone 13N).
- **The ingestion script** (`update_nexgen_mosaic.py`) runs automatically every 30 minutes. It finds newly downloaded site images, converts them to the mosaic's projection when needed, adds them to the mosaic, and removes the older image for the same site.

## Reviewer item → evidence map

| # | Reviewer item | Evidence | Status |
|---|---|---|---|
| 1 | GeoWebCache configuration exports | [evidence/geowebcache/](evidence/geowebcache/) – `gwc_layer_nexgen_site_mosaic.json`, `gwc_layers_list.json`, `gwc_seed_status_nexgen.json`, [configuration.md](evidence/geowebcache/configuration.md) | Direct |
| 2 | Cache-seeding and reseeding logs | [evidence/geowebcache/seed-reseed/README.md](evidence/geowebcache/seed-reseed/README.md) | **Not available** – explained |
| 3 | Cache invalidation records after imagery replacement | [evidence/cache-invalidation/](evidence/cache-invalidation/) – `replacement-events.log`, [invalidation-records.md](evidence/cache-invalidation/invalidation-records.md) | Direct for the ImageMosaic index; no GWC tile-truncation records |
| 4 | Mosaic property files | [evidence/imagemosaic/nexgen_site_mosaic.properties](evidence/imagemosaic/nexgen_site_mosaic.properties) | Direct |
| 5 | GeoServer ImageMosaic configuration | [evidence/imagemosaic/](evidence/imagemosaic/) – `NexGen_Sites.json`, `nexgen_site_mosaic.json`, [configuration.md](evidence/imagemosaic/configuration.md) | Direct |
| 6 | How only newly downloaded images were processed | [evidence/ingestion/](evidence/ingestion/) – `update_nexgen_mosaic.py`, `root-crontab.txt`, `incremental-decisions.log`, `nexgen_mosaic_updater.log.gz`, `imagery-inventory.txt`, [incremental-processing.md](evidence/ingestion/incremental-processing.md) | Direct, with disclosed limitations |
| 7 | Failed mosaic logs from the mixed-projection problem | [evidence/mixed-projection/incident-summary.md](evidence/mixed-projection/incident-summary.md) | **Failure log not available**; remediation evidence present |

## What each file is, in plain words

### `evidence/geowebcache/` – item 1 (and item 2)

| File | What it is |
|---|---|
| `gwc_layer_nexgen_site_mosaic.json` | The tile-cache settings for the NexGen mosaic, exported from GeoServer. Shows caching is switched on, tiles are PNG, drawn in 4×4 blocks, stored on the NAS, and never expire automatically. |
| `gwc_layers_list.json` | The list of every map layer that has a tile cache on this server. |
| `gwc_seed_status_nexgen.json` | GeoServer's answer to "are any pre-drawing or clearing jobs running for this layer right now?" – the answer was none. |
| `configuration.md` | Plain summary of the settings above. |
| `seed-reseed/README.md` | Explains that no seeding/reseeding records exist and lists everywhere that was searched. |

### `evidence/imagemosaic/` – items 4 and 5

| File | What it is |
|---|---|
| `nexgen_site_mosaic.properties` | The mosaic's own settings file, copied unchanged from the server. Shows the mosaic accepts only one projection (EPSG:3857). |
| `NexGen_Sites.json` | GeoServer's record of the mosaic data source (where the images live on disk). |
| `nexgen_site_mosaic.json` | GeoServer's record of the published mosaic layer: projection, bands, map extent and display settings. |
| `configuration.md` | Plain summary of the key settings in the three files above. |

### `evidence/ingestion/` – item 6

| File | What it is |
|---|---|
| `update_nexgen_mosaic.py` | The actual automation script running in production (password removed). Contains the logic that decides whether an image is new, already processed, or replacing an older one. |
| `root-crontab.txt` | The server schedule showing the script runs every 30 minutes. |
| `nexgen_mosaic_updater.log.gz` | The script's complete log, written automatically on every run from 2026-08-05 to 2026-10-07. Compressed; unedited. |
| `incremental-decisions.log` | Lines pulled from the full log showing each decision: "already processed – skipped", "new – processing required", and run summaries. |
| `imagery-inventory.txt` | Listing of the 22 image files currently in the mosaic, and a summary of the mosaic index (22 entries). |
| `incremental-processing.md` | Plain explanation of how the script processes only new images, with log examples and the known limitations. |

### `evidence/cache-invalidation/` – item 3

| File | What it is |
|---|---|
| `replacement-events.log` | Lines pulled from the script log every time an older image was removed from the mosaic because a newer one arrived. |
| `invalidation-records.md` | Plain explanation, with three genuine examples from 2026-10-05, and a note on entries that are not genuine replacements. |

### `evidence/mixed-projection/` – item 7

| File | What it is |
|---|---|
| `incident-summary.md` | Explains that the original failure log no longer exists, lists where it was searched, and shows the fix that is in place: every incoming image's projection is checked and converted to EPSG:3857 before entering the mosaic. |

### `source/` – how the evidence was collected

| File | What it is |
|---|---|
| `collection-notes.md` | Who collected what, when, and with which command. Also lists what was left out and why. |
| `SHA256SUMS.txt` | A fingerprint of every raw evidence file, taken on the server at collection time. Anyone can recompute them to confirm the files were not altered afterwards. |

## Key findings

1. **The mosaic and tile cache are configured as described** (items 1, 4, 5) – exported directly from production.
2. **Only new imagery is converted** (item 6). The script keeps the newest image per site and skips images it has already processed; the log records these skip decisions (e.g. the 2026-10-07 12:30 run).
3. **Older imagery is removed from the mosaic when a newer image arrives** (item 3) – logged, e.g. three sites on 2026-10-05.
4. **The projection problem is handled in code** (item 7). Images not in EPSG:3857 are automatically reprojected before entering the mosaic, and the mosaic is configured to reject mixed projections. The original failure log no longer exists.

### Limitations, stated openly

- **No tile-cache seeding or clearing records exist** (item 2). The script does not clear the tile cache after replacing imagery, and the cache is set never to expire, so the records do not show that old cached tiles were removed (item 3).
- **The mosaic index is rebuilt on every run.** Image conversion is incremental, but every 30 minutes the script re-registers all 22 images with GeoServer.
- **A name-matching defect** causes one image (`airstrip_access_road`) to be removed and re-added on every run, because its name starts with another site's name (`airstrip`).
- **Two spellings of one site** (`1.5_km_crusher` and `1_5_km_crusher`) are treated as separate sites, so the older crusher image was never replaced.
- **GeoServer's own logs are short-lived** – they rotate by size and covered only a few hours on the collection date.

## Time period covered by the records

| Record | Period | Nature |
|---|---|---|
| Ingestion script log | 2026-08-05 → 2026-10-07 | Written automatically by the system at the time of each run (contemporaneous) |
| Configuration exports, properties file, inventory, crontab, script | As of 2026-10-07 | Snapshot of the production state on the collection date |
| GeoServer logs (searched, not included) | 2026-10-07 08:06 → 12:30 | Contemporaneous, but very short retention |

## For the SR&ED reviewer

This package is the supporting technical record for the GeoServer caching and imagery-mosaic work. It shows, from production systems, what was built and how it behaves: automatic detection and conversion of image projections, selection of only the newest image per site, skipping of already-processed images, and replacement of superseded images in the mosaic. It also documents, without omission, the records that do not exist and the defects found during collection.

The project narrative (technological uncertainties, hypotheses, experiments and conclusions) belongs in the claim's project description and is not repeated here. No performance measurements are included; they were outside the scope of the reviewer's request.

## Evidence classification

Each summary document labels statements as:

- **Direct** – raw configuration, REST export, source code or log line captured from production.
- **Supporting** – real data that is consistent with a claim but does not prove it alone.
- **Inference** – a conclusion drawn from evidence, stated as such.
- **Unavailable** – searched for and not found; the search is documented.

## Integrity and handling

- SHA-256 checksums of the 12 raw evidence files (JSON, logs, properties, script, inventory, crontab): [source/SHA256SUMS.txt](source/SHA256SUMS.txt). The `.md` summaries were written afterwards and are not included.
- Collection method, commands and exclusions: [source/collection-notes.md](source/collection-notes.md)
- The GeoServer admin password has been replaced with `REDACTED` in `update_nexgen_mosaic.py`. No other credentials or IP addresses are present.
- This repository contains internal hostnames and storage paths and should remain **private**.
