# api

An AWS Lambda intended to function as an HTTP API to facilitate querying general information about the Dynamo DB and TimeStream Event Tables.  This can be used for building Cirrus monitoring dashboards, like hourly or daily events aggregate statistics.

This differentiates it from the other lambdas which are more like traffic managers and handlers, while the `API` lambda exists outside of the standard cirrus workflow as laid out in the architecture diagram in :doc:`cirrus_overview <../../cirrus/10_intro.rst>`

## Trigger

Triggered by sending valid HTTTP requests.

Query parameters can be passed in to control the behavior of the response.  A query param not in the following list will have no effect as it goes un unanalzyed, only a specific set of params are examined.

### Query Params
- State: `State` to filter the StateDB items on.
- Since: A string field used to search the StateDB from this time forward to the present.  Takes the form of an integer follwed by a flag to indicate the time unit.  Acceptable flags are "d" (days), "h" (hours), and "m" (minutes)

## Response

A REST-like response containing a status_code, headers, and body that can be parsed like any REST response.

### "Endpoints"

### "GET" Root

Return a STAC-like object with links to all the outputs from the cirrus S3 data bucket.

### "GET" Stats

Return a summary statistics of events from the TimeStream database to get a picture of cirrus events on a daily, hourly, and hourly rolling basis

### "GET" Items

Return items from the DynamoDB state database based on query filters.  Can be filered on 'state', 'since', 'limit'. The results are paginated and the pagination key `NextKey` can be used by passing it as one of the query params when making the API call to the lambda.
