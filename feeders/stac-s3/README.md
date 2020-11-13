# STAC Feeder

Crawls bucket for STAC records and feeds them to Cirrus


# Process configuration
'''
{
    "s3urls": ["s3://bucket/key"],
    "suffix": "json",
    "process": {
        "collection": "<collectionId>",
        "workflow": "mirror"
        "tasks": {
            "copy-assets": {
                ...
            }
        }
    }
}
'''