# API

An AWS Lambda intended to function in a REST-like fashion for building Cirrus monitoring dashboards.

This differentiates it from the other lambdas which function more as traffic managers and handlers, the `API` lambda exists outside of the standard cirrus workflow as laid out in the architecture diagram in [cirrus_overview](/docs/src//cirrus/10_intro.rst)

## Trigger

A lambda intended to facilitate querying general information about the Dynamo DB and TimeStream Event Tables. This lambada is intended to respond in a REST-like fashion.  The result can be used to generate dashboards of cirrus statistics, like hourly or daily events or runs, or different filters.

Query parameters can be passed in to control the behavior of the response.  A query param not in the following list will have no effect as it goes un unanalzyed, only a specific set of params are examined.

### Query Params
- State: `State` to filter the StateDB items on.
- Since: A string field used to search the StateDB from this time forward to the present.  Takes the form of an integer follwed by a flag to indicate the time unit.  Acceptable flags are "d" (days), "h" (hours), and "m" (minutes)

## Response

A REST-like response containing a status_code, headers, and body that can be parsed like any REST response.

### "GET" Root

A call to the root 'endpoint' will return a STAC-like object with links to all the outputs from the cirrus S3 data bucket

### "GET" Stats

Return a summary of statistics of events from the TimeStream database to get a picture of cirrus events daily, hourly, and hourly rolling

### "GET" Items

Return items from the DynamoDB state database based on query filters.  Can be filered on 'state', 'since', 'limit'. The results are paginated and the pagination key `NextKey` can be used by passing it as one of the query params when making the API call to the lambda.
