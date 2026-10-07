# Item 6 – How only newly downloaded images were processed

## Summary

`update_nexgen_mosaic.py` runs from root's crontab every 30 minutes. For each site it selects only the newest downloaded image, and skips reprojection and conversion when that image has already been processed. Unchanged images are logged as skipped.

Three limitations are disclosed below. The most important is that the reprojection/conversion step is incremental, but the GeoServer index registration is repeated for all granules on every run.

## Schedule – Direct

[root-crontab.txt](root-crontab.txt):

```text
*/30 * * * * /usr/bin/python3 /home/geoadmin/nexgen/update_nexgen_mosaic.py >> /home/geoadmin/nexgen/nexgen_mosaic_cron.log 2>&1
```

## Decision logic – Direct (source code)

[update_nexgen_mosaic.py](update_nexgen_mosaic.py):

| Step | Function | Behaviour |
|---|---|---|
| Find downloads | `scan_latest_sites()` | Reads `/mnt/nas_storage/data/nexgen/<site>_YYYYMMDDHHMMSS/` folders; keeps only the newest timestamp per site, logs older ones as ignored |
| New vs. already processed | `needs_processing()` | Processes only if the output file is missing from the mosaic folder or the source is newer than the output; otherwise logs `ALREADY published and up-to-date … Skipping` |
| Avoid needless work | `create_cog()` | Skips reprojection if the source is already EPSG:3857; skips all GDAL work and copies directly if it is already a Cloud Optimized GeoTIFF |
| Replace | `cleanup_old_versions()` | Removes the superseded image from the index and disk (see item 3) |
| Concurrency | `ProcessLock` | File lock prevents overlapping cron runs |

## Log evidence – Direct

Main log `/var/log/nexgen_mosaic_updater.log`, retained from **2026-08-05 19:14:06** to collection date. Full copy: [nexgen_mosaic_updater.log.gz](nexgen_mosaic_updater.log.gz). Decision lines extracted to [incremental-decisions.log](incremental-decisions.log).

Unchanged images skipped:

```text
[2026-10-07 12:30:38] Latest image for 'rock_garden_20261005151021.tif' is ALREADY published and up-to-date in mosaic folder. Skipping.
[2026-10-07 12:30:38] Latest image for 'septic_absorption_field_20261005220543.tif' is ALREADY published and up-to-date in mosaic folder. Skipping.
[2026-10-07 12:30:38] Latest image for 'temporary_airstrip_access_road_20261003220123.tif' is ALREADY published and up-to-date in mosaic folder. Skipping.
[2026-10-07 12:30:38] Latest image for 'topsoil_stockpile_20261004220423.tif' is ALREADY published and up-to-date in mosaic folder. Skipping.
[2026-10-07 12:30:38] Latest image for 'waste_management_20260903140056.tif' is ALREADY published and up-to-date in mosaic folder. Skipping.
```

New image already in the target format, processed without reprojection:

```text
[2026-08-05 20:06:18] Image '.../construction_facility_pad_20260804160238.tif' is ALREADY in EPSG:3857 and COG format! Bypassing GDAL reprojection/translation and performing fast direct copy ...
```

## Current state – Supporting

[imagery-inventory.txt](imagery-inventory.txt): directory listing of `/mnt/nas_storage/data/nexgen_site_mosaic` (22 TIFFs, one per site name) and the shapefile index summary (22 features, EPSG:3857). File timestamps and counts alone do not prove incremental processing; they are consistent with the logic above.

## Limitations – disclosed

1. **The index is re-registered every run (Direct, source code).** After the per-site step, `sync_and_cleanup_orphans()` deletes all granules except one from the ImageMosaic index, re-harvests every TIFF in the mosaic folder, and then calls `/rest/reload`. This runs every 30 minutes whether or not anything changed. Only the reprojection/conversion step is incremental. The `nexgen_site_mosaic.properties` header was observed as `#Wed Oct 07 12:00:42 MDT 2026` and, when collected after the next run, `#Wed Oct 07 12:30:42 MDT 2026` – rewritten about 40 seconds after each 30-minute cron run started. This is consistent with the index being rebuilt every run (Inference).
2. **One image is re-copied every run (Direct, log).** Because the `airstrip` site name is a prefix of `airstrip_access_road`, the script deletes and then re-adds `airstrip_access_road` on every run. Logged every 30 minutes on 2026-08-17 (16:00–19:30) and on 2026-10-07 (12:00, 12:30). The source is already EPSG:3857 COG, so this is a file copy, not a reprojection.
3. **Site key spelling (Direct, inventory + code).** `1.5_km_crusher_20260812124309.tif` and `1_5_km_crusher_20261002141254.tif` are treated as two different sites, so the older one was not replaced.
