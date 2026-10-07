# Item 1 – GeoWebCache configuration exports

## Files – Direct

| File | Source |
|---|---|
| [gwc_layer_nexgen_site_mosaic.json](gwc_layer_nexgen_site_mosaic.json) | `GET /geoserver/gwc/rest/layers/nexgen:nexgen_site_mosaic.json` (HTTP 200) |
| [gwc_layers_list.json](gwc_layers_list.json) | `GET /geoserver/gwc/rest/layers.json` (HTTP 200) – all GWC-configured layers |
| [gwc_seed_status_nexgen.json](gwc_seed_status_nexgen.json) | `GET /geoserver/gwc/rest/seed/nexgen:nexgen_site_mosaic.json` (HTTP 200) |

## GWC settings for `nexgen:nexgen_site_mosaic`

| Setting | Value | Meaning |
|---|---|---|
| `enabled` | `true` | Tile caching is active for this layer |
| `gridSubsets` | `Esri_Compatible_Mercator` | Single gridset (Web Mercator tiling scheme) |
| `mimeFormats` | `image/png` | Only PNG tiles are cached |
| `metaWidthHeight` | `[4, 4]` | 4×4 metatiling – tiles rendered in blocks of 16 |
| `gutter` | `0` | No gutter around metatiles |
| `blobStoreId` | `nas_geoserver_cache` | Tiles are stored in the named blob store `nas_geoserver_cache` |
| `inMemoryCached` | `true` | In-memory tile caching enabled in addition to the blob store |
| `expireCache` | `0` | Cached tiles never expire on the server |
| `expireClients` | `0` | No client-side cache expiry header set by GWC |
| `parameterFilters` | `STYLES` (default `""`) | Tiles cached per style; default style only unless requested |
| `id` | `LayerInfoImpl--136aaebf:19faa2ab0c0:-7e4d` | GeoServer catalog layer ID |

## Seed status

`gwc_seed_status_nexgen.json` = `{"long-array-array":[]}` – no seed, reseed or truncate task running at collection time. This endpoint reports only current tasks and holds no history (see [seed-reseed/README.md](seed-reseed/README.md)).
