# S3 Inventory Feeder


## Payload Parameters

| Field           | Type     | Description |
| -----------     | -------- | ----------- |
| process         | Dict     | **REQUIRED** Process definition |
| inventory_url   | string   | URL |
| inventory_files | [string] | 
| keys            | [string] | |
| suffix          | string   | |
| batch_size      | Integer  | Number of invenotry files to run at once |



## Example payloads


payload = {
    "inventory_url": "s3://landsat-pds-inventory/landsat-pds/landsat-pds",
    "process": {}
}
payload = {
    "inventory_files": [
        "s3://landsat-pds-inventory/landsat-pds/landsat-pds/data/422f6969-87f5-4aa6-a159-3839f155bc88.orc",
        "s3://landsat-pds-inventory/landsat-pds/landsat-pds/data/2d676b49-2c57-452f-8677-9b0bdba0c79c.orc"
    ],
    "keys": ["bucket", "key", "size", "last_modified_date"],
    "suffix": "MTL.txt",
    "process": {
        "input_collections": ["landsat-l1-c1"],
        "workflow": "test"
    }
}