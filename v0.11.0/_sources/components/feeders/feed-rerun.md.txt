# Rerun Feeder

Query the Cirrus State Database for items to rerun.

## Payload Parameters

| Field          | Type    | Description                                                                                                                          |
| -------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| collections    | string  | **REQUIRED** '/'-delimited string of the set of collections (alphanumeric order)                                                     |
| workflow       | string  | **REQUIRED** Workflow in state database to look up                                                                                   |
| state          | string  | The state of items to return (one of PROCESSING, COMPLETED, FAILED, INVALID, ABORTED)                                                |
| since          | string  | How long since present to retrun items. Conists of number and letter: XXu where `u` can be `m` (minutes), `d` (days), or `w` (weeks) |
| limit          | integer | Maximum number of items to return (default: no limit)                                                                                |
| batch          | bool    | Spawn batch job and run this handler (default: false)                                                                                |
| process_update | Dict    | A partial `process` definition that will be merged with original input, allowing user to override original parameters                |
