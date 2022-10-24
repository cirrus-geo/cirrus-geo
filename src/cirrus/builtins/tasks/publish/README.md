# Cirrus Task: publish

Publishes output STAC Item(s) to s3 and SNS, optionally other targets.

## Configuration Parameters

Configuration parameters are passed in `payload['process']['tasks']['publish']`:

| Field  | Type     | Description                                                  |
| ------ | -------- | ------------------------------------------------------------ |
| public | bool     | Set ACL of STAC Item on s3 to `public-read` (Default: False) |
| sns    | [string] | Additional SNS topic ARNs to publish to (Default: [])        |

### Upload Options

The `publish` task also uses the following parameters supplied in `payload['process']['upload_options']`:

| Field         | Type   | Description                                                                                                                   |
| ------------- | ------ | ----------------------------------------------------------------------------------------------------------------------------- |
| path_template | string | A template path for the prefix when uploading STAC Item metadata, uses fields from STAC Item (Default: '${collection}/${id}') |
