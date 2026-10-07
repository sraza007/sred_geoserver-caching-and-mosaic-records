# Collection notes

- **Collected:** 2026-10-07, by Shahid Raza
- **Server:** Calgary GeoServer, `osgis.caltechgroup.com`, data directory `/var/lib/geoserver_data` (from `-DGEOSERVER_DATA_DIR` of the running `geoserver.service`)
- **Method:** read-only. No production configuration, data or schedule was changed to produce this evidence.

## How each file was obtained

| File | Command |
|---|---|
| `evidence/geowebcache/gwc_layer_nexgen_site_mosaic.json` | `curl -u admin -H "Accept: application/json" $GS/gwc/rest/layers/nexgen:nexgen_site_mosaic.json` (HTTP 200) |
| `evidence/geowebcache/gwc_layers_list.json` | `curl … $GS/gwc/rest/layers.json` (HTTP 200) |
| `evidence/geowebcache/gwc_seed_status_nexgen.json` | `curl … $GS/gwc/rest/seed/nexgen:nexgen_site_mosaic.json` (HTTP 200) |
| `evidence/imagemosaic/NexGen_Sites.json` | `curl … $GS/rest/workspaces/nexgen/coveragestores/NexGen_Sites.json` |
| `evidence/imagemosaic/nexgen_site_mosaic.json` | `curl … $GS/rest/workspaces/nexgen/coveragestores/NexGen_Sites/coverages/nexgen_site_mosaic.json` |
| `evidence/imagemosaic/nexgen_site_mosaic.properties` | `cp` from `/mnt/nas_storage/data/nexgen_site_mosaic/` |
| `evidence/ingestion/imagery-inventory.txt` | `ls -la --time-style=full-iso` of the mosaic folder + `ogrinfo -so` of the index shapefile |
| `evidence/ingestion/root-crontab.txt` | `sudo crontab -l -u root` |
| `evidence/ingestion/update_nexgen_mosaic.py` | `cp` from `/home/geoadmin/nexgen/`; password default replaced with `REDACTED` |
| `evidence/ingestion/nexgen_mosaic_updater.log.gz` | `gzip -c /var/log/nexgen_mosaic_updater.log` (complete, unedited) |
| `evidence/ingestion/incremental-decisions.log` | `grep` extract of the above |
| `evidence/cache-invalidation/replacement-events.log` | `grep` extract of the above |

`$GS` = `https://osgis.caltechgroup.com/geoserver`. Credentials were entered interactively and are not stored anywhere in this repository.

## Integrity

`source/SHA256SUMS.txt` was generated on the server immediately after collection (`sha256sum` over `evidence/`), before any file left the server.

## Not included, and why

- **GeoServer logs** (`geoserver*.log`, ~65 MB): they cover only 2026-10-07 08:06–12:30, contain client IP addresses, and hold nothing relevant to the seven items. Their search results are documented in items 2 and 7.
- **NGINX access logs:** not relevant to the seven items. The log format has no `$request_time`, so it cannot show response times.

## Present on the server but not examined

- `nexgen_mosaic_updater_zone12.py` (hourly cron) and the `NexGen_Mosaic_Combined_Zone12` layer group
- `nexgen-watcher` systemd service (`/opt/nexgen-watcher`)
- `copy_tifs_to_cloud_geoserver.py` / `copy_missing_latest_tif.py` (sync to the Azure GeoServer)
