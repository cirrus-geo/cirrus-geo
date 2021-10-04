# STAC Feeder

Crawls bucket for STAC records and feeds them to Cirrus



# Process configuration
'''
{
    "url": "https://stac-api-endpoint",
    "search": {
        <stac-api-search-params>
    },
    "sleep": 10,
    "process": {
        <process-block>
    }
}
'''