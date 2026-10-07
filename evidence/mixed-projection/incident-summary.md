# Item 7 – Failed mosaic logs from the mixed-projection problem

## Status

**Unavailable.** No log of the failed mosaic operation was found in any retained log on the server. No substitute log has been created.

## What was searched

Search terms: `not identified as EPSG`, `gdalwarp failed`, `harvest failed`, `mismatch`, `crs` (case-insensitive), plus `projection`.

| Source | Period covered | Result |
|---|---|---|
| `/var/log/nexgen_mosaic_updater.log` | 2026-08-05 → 2026-10-07 | No failure lines (only routine "Bypassing GDAL reprojection" messages) |
| `/var/lib/geoserver_data/logs/geoserver*.log` | 2026-10-07 08:06 → 12:30 only (size-based rotation) | No failure lines |
| `/var/lib/geoserver_data_backup_1778785403/logs/geoserver.log`, `/var/lib/geoserver_data_backup_1778785925/logs/geoserver.log` | Backups dated 2026-05-14 | No failure lines |

Inference: if the failure was logged on this server, it occurred outside the retained periods, most likely before 2026-08-05, and GeoServer's log rotation has since overwritten it.

## Remediation evidence – what does exist

- **Direct (source code):** [update_nexgen_mosaic.py](../ingestion/update_nexgen_mosaic.py) checks every source image's CRS with `gdalsrsinfo` / `gdalinfo` (`inspect_gdalinfo()`) and reprojects anything not in EPSG:3857 with `gdalwarp -t_srs EPSG:3857` before it enters the mosaic (`create_cog()`).
- **Direct (configuration):** [nexgen_site_mosaic.properties](../imagemosaic/nexgen_site_mosaic.properties) sets `MosaicCRS=EPSG:3857` and `HeterogeneousCRS=false`. The mosaic is configured for one CRS only.
- **Supporting (catalog):** the `nexgen` workspace still holds individually published layers delivered in EPSG:2956 (NAD83(CSRS) / UTM zone 13N), e.g. `SK_25-1408-2_NexGen_KM1.5_202060621_EPSG2956_Ortho_0.05m`, `SK_25-1408-2_NexGen_AOI5_20260626_EPSG2956_Ortho_0.05m`. This shows source imagery arrived in projections other than the mosaic's CRS.

## Possible other sources (not on this server)

Tickets, emails or chat messages from the time of the incident, if they exist, would be the remaining place a record of the original error might be found.
