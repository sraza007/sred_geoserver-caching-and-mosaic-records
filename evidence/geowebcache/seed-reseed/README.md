# Item 2 – Cache-seeding and reseeding logs

**Status: Unavailable.** No seeding or reseeding records exist for `nexgen:nexgen_site_mosaic`. No substitute has been created.

## What was searched

| Source | Result |
|---|---|
| GeoServer logs `/var/lib/geoserver_data/logs/geoserver.log`, `geoserver-1.log` … `geoserver-3.log`, searched for `seed` / `truncat` | No matches |
| GWC REST `/gwc/rest/seed/nexgen:nexgen_site_mosaic.json` ([../gwc_seed_status_nexgen.json](../gwc_seed_status_nexgen.json)) | HTTP 200, no running or pending tasks. This endpoint only reports current tasks and keeps no history. |
| Ingestion script [update_nexgen_mosaic.py](../../ingestion/update_nexgen_mosaic.py) | Contains no GWC REST calls (`/gwc/rest/seed`, `truncate`, `masstruncate`) |
| Root crontab ([root-crontab.txt](../../ingestion/root-crontab.txt)), `/etc/cron.d`, `/etc/cron.daily`, `/etc/cron.hourly`, systemd timers | No seeding job |

## Limits of the search

- GeoServer rotates its log at about 20 MB and keeps 3 old copies. On 2026-10-07 the oldest retained GeoServer log started at 08:06 the same day. Any seeding activity before that is no longer recorded by GeoServer.
- **Conclusion (inference):** there is no scheduled or scripted seeding for this layer, and no retained record of manual seeding. It cannot be shown from available records whether manual seeding was ever performed.
