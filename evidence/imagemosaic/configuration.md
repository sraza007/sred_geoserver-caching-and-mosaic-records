# Items 4 and 5 – Mosaic property file and GeoServer ImageMosaic configuration

## Files – Direct

| File | Source |
|---|---|
| [nexgen_site_mosaic.properties](nexgen_site_mosaic.properties) | `/mnt/nas_storage/data/nexgen_site_mosaic/nexgen_site_mosaic.properties` (copied unchanged) |
| [NexGen_Sites.json](NexGen_Sites.json) | `GET /geoserver/rest/workspaces/nexgen/coveragestores/NexGen_Sites.json` |
| [nexgen_site_mosaic.json](nexgen_site_mosaic.json) | `GET /geoserver/rest/workspaces/nexgen/coveragestores/NexGen_Sites/coverages/nexgen_site_mosaic.json` |

## Key settings

**Mosaic property file**

| Setting | Value | Meaning |
|---|---|---|
| `MosaicCRS` | `EPSG:3857` | Mosaic CRS |
| `HeterogeneousCRS` | `false` | Granules in other CRSs are not accepted |
| `Heterogeneous` | `true` | Granules may differ in resolution |
| `Caching` | `false` | No in-memory granule index cache |
| `LevelsNum` | `10` | Resolution levels recorded |
| `LocationAttribute` / `PathType` | `location` / `RELATIVE` | Granule paths stored relative to the mosaic folder |
| `SuggestedFormat` | `GeoTiffFormat` | Granules are GeoTIFF |

**Coverage (`nexgen_site_mosaic`)**

| Setting | Value |
|---|---|
| SRS / native CRS | EPSG:3857 |
| Projection policy | `REPROJECT_TO_DECLARED` |
| Bands | RGBA, 8-bit unsigned |
| `cachingEnabled` | `false` |
| `MergeBehavior` | `FLAT` |
| `OVERVIEW_POLICY` | `QUALITY` |
| `SUGGESTED_TILE_SIZE` | `512,512` |
| `AllowMultithreading` | `false` |
| `SkipDuplicates` | `false` |
| `FootprintBehavior` | `None` |
| Default interpolation | Nearest neighbour |

**Index (shapefile `nexgen_site_mosaic.shp`)** – 22 polygon features, EPSG:3857, attribute `location`. See [imagery-inventory.txt](../ingestion/imagery-inventory.txt).

## Note

The coverage's stored native bounding box (minx −12164882) is smaller than the index extent (minx −12175952). GeoServer did not recalculate the advertised bounding box after granules were added. Recorded here so a reviewer comparing the two files is not surprised.
