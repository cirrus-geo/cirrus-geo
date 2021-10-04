# Cirrus Task: convert-to-cog

Converts Item assets to Cloud-Optimized GeoTiff

## Configuration Parameters

Configuration parameters are passed in `payload['process']['tasks']['convert-to-cog']`:

| Field       | Type     | Description |
| ----------- | -------- | ----------- |
| assets      | Map<string, ConvertAsset Object> | **REQUIRED** Dictionary of Asset keys to convert with parameters for each asset |
| drop_assets | [string] | Asset keys to remove from output STAC Item(s) (Default: [])  |

### ConvertAsset Object

| Field       | Type     | Description |
| ----------- | -------- | ----------- |
| nodata      | number   | If provided, use as input NoData value, otherwise get from data file (Default: None) |
| web_optimized | bool   | Use rio-cogeo option to create web-optimized COG (Default: False)  |
| blocksize   | number   | Size (both x and y) of internal tiles (Default: 256) |
| overview_blocksize | number | Size (both x and y) of internal tiles for overviews |
| overview_resampling | string | Resampling to use when creating overviews: ‘nearest’, ‘bilinear’, ‘cubic’, ‘cubic_spline’, ‘lanczos’, ‘average’, ‘mode’, and ‘gauss’ (Default: 'nearest') |

### Output Options

The `convert-to-cog` task also uses the following parameters supplied in `payload['process']['output_options']`:

| Field         | Type     | Description |
| ------------- | -------- | ----------- |
| public_assets | [string] | List of asset keys to make public (Default: []) |
| path_template | string   | A template path for the prefix when uploading assets, uses fields from STAC Item (Default: '${collection}/${id}') |
| s3_urls       | bool     | Use s3 URLs for Item Assets rathert than http (Default: False) |
| headers       | Map<string, string> | Additional headers to set when uploading Item Assets to s3 |