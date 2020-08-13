# copy-assets

## Payload Parameters

| Key | Type | Description |
| --- | ---- | ----------- |
| assets | [string] | An array of asset keys to copy to the output_url |
| output_url | string | The URL prefix to copy the files to |
| public | bool | Make copied files public (Default: False) |
| s3urls | bool | Use s3 URLs instead of https (Default: False) |
| requester_pays | bool | Acknowledge source URLs are in a requester pays bucket and accept chargers (Default: False) |
| path_pattern | string | A templated string used to create the full path under `output_url` |


- **path_pattern**: The templated path parameter for generating the path to output files (e.g., "${platform}/${datetime})