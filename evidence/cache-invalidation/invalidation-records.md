# Item 3 – Cache invalidation after imagery replacement

## Summary

When a site receives newer imagery, the ingestion script removes the superseded granule from the ImageMosaic index through the GeoServer REST API and deletes the superseded file. These events are logged.

There is **no record of GeoWebCache tile truncation** after replacement. The script makes no GWC calls (see [../geowebcache/seed-reseed/README.md](../geowebcache/seed-reseed/README.md)).

## Mechanism – Direct (source code)

[update_nexgen_mosaic.py](../ingestion/update_nexgen_mosaic.py):

1. `harvest_new_granule()` – adds the new image via `POST /rest/workspaces/nexgen/coveragestores/NexGen_Sites/external.imagemosaic`.
2. Only if the harvest succeeds, `cleanup_old_versions()` runs.
3. `delete_old_granule()` – finds the old granule with `GET …/index/granules.json?filter=location LIKE '%<old file>%'` and removes it with `DELETE …/index/granules/<id>.json`.
4. The old file is then deleted from `/mnt/nas_storage/data/nexgen_site_mosaic`.

`nexgen_site_mosaic.properties` has `Caching=false`, so GeoServer does not keep an in-memory copy of the granule index; index changes take effect without a separate cache flush (Supporting).

## Replacement events – Direct (log)

Full extract: [replacement-events.log](replacement-events.log) (from `/var/log/nexgen_mosaic_updater.log`).

Genuine replacements:

```text
[2026-10-05 09:02:29] Found obsolete processed TIFF for site 'topsoil_stockpile': 'topsoil_stockpile_20261001215556.tif'. Purging old version...
[2026-10-05 19:01:39] Found obsolete processed TIFF for site 'aoi5_crusher': 'aoi5_crusher_20261004172737.tif'. Purging old version...
[2026-10-05 19:31:39] Found obsolete processed TIFF for site 'rock_garden': 'rock_garden_20260927224521.tif'. Purging old version...
```

Supporting: the current mosaic contains only the newer files for these sites – `topsoil_stockpile_20261004220423.tif`, `aoi5_crusher_20261005170242.tif`, `rock_garden_20261005151021.tif` ([imagery-inventory.txt](../ingestion/imagery-inventory.txt)).

## Entries that are NOT genuine replacements

`replacement-events.log` also contains repeated entries such as:

```text
[2026-10-07 12:30:02] Found obsolete processed TIFF for site 'airstrip': 'airstrip_access_road_20260913151439.tif'. Purging old version...
```

These come from a name-matching defect: the script treats any file starting with `airstrip_` as an older `airstrip` image, so it removes `airstrip_access_road` on each run and re-adds it straight afterwards. They are not replacements and should not be read as invalidation evidence. See [incremental-processing.md](../ingestion/incremental-processing.md).

## Not available

- GWC tile truncation or reseed records after replacement.

The layer **is** tile-cached by GWC (`enabled: true`, PNG, `Esri_Compatible_Mercator`, blob store `nas_geoserver_cache`) with `expireCache: 0`, meaning tiles do not expire on their own ([../geowebcache/configuration.md](../geowebcache/configuration.md)). Because the ingestion script makes no GWC truncate call and no truncation is recorded, the available records do not show that cached tiles were invalidated after imagery was replaced (Inference).
