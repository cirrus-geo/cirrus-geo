# Cirrus Task: copy-assets

Copies specified Assets from Source STAC Item(s) and copies to s3 and updates Item Assets to point to new location.

## Configuration Parameters

Configuration parameters are passed in `payload['process']['tasks']['copy-assets']`:

| Field     | Type     | Description |
| --------- | -------- | ----------- |
| assets    | [string] | **REQUIRED** An array of asset keys to copy |
| drop_assets | [string] | Asset keys to remove from output STAC Item(s) (Default: [])  |

### Output Options

The `copy-assets` task also uses the following parameters supplied in `payload['process']['output_options']`:

| Field         | Type     | Description |
| ------------- | -------- | ----------- |
| public_assets | [string] | List of asset keys to make public (Default: []) |
| path_template | string   | A template path for the prefix when uploading assets, uses fields from STAC Item (Default: '${collection}/${id}') |
| s3_urls       | bool     | Use s3 URLs for Item Assets rathert than http (Default: False) |
| headers       | Map<string, string> | Additional headers to set when uploading Item Assets to s3 |
