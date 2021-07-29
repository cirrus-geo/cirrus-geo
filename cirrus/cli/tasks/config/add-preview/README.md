# Cirrus Task: add-preview

Adds a byte-scaled Cloud-Optimized GeoTiff, with internal tiles optimized for web viewing, and in EPSG:3857.  Adds an optional thumbnail from the preview image.

## Configuration Parameters

Configuration parameters are passed in `payload['process']['tasks']['add-preview']`:

| Field     | Type     | Description |
| --------- | -------- | ----------- |
| assets    | [string] | **REQUIRED** An array of asset keys to generate the preview from, in order of preference. The first asset that exists will be used |
| thumbnail | bool     | Create thumbnail from generated preview image (Default: False) |
| preproj   | bool     | Preproject asset to EPSG:4326, required if data file is unprojected and uses GCPs (Default: False) |
| ccc       | [number, number] | Low and high Cumuluative Count Percentage cutoffs for stretching image to Byte (Default: [2.0, 98.0]) |
| exp       | number   | If provided, use exponential stretch instead of `ccc` method (Default: None) |
| nodata    | number   | Nodata value for input image to creating preview (Default: 0)

### Output Options

The `add-preview` task also uses the following parameters supplied in `payload['process']['output_options']`:

| Field         | Type     | Description |
| ------------- | -------- | ----------- |
| public_assets | [string] | List of asset keys to make public (Default: []) |
| path_template | string   | A template path for the prefix when uploading assets, uses fields from STAC Item (Default: '${collection}/${id}') |
| s3_urls       | bool     | Use s3 URLs for Item Assets rathert than http (Default: False) |
| headers       | Map<string, string> | Additional headers to set when uploading Item Assets to s3 |