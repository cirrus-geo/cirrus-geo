api
===

An AWS Lambda intended to function as an HTTP API to facilitate querying
general information about the Dynamo DB and TimeStream Event Tables.  This can
be used for building Cirrus monitoring dashboards, like hourly or daily events
aggregate statistics.

This differentiates it from the other lambdas, which are more like traffic
managers and handlers. The ``API`` lambda exists outside of the standard cirrus
workflow as laid out in the architecture diagram in :doc:``cirrus_overview
<../../cirrus/10_intro.rst>``

Supported event formats
-----------------------

The handler supports both Lambda event payload formats:

- **Payload format 1.0** — path read from ``event.path``
- **Payload format 2.0** — path read from ``event.rawPath``

When deployed with a route prefix (e.g. ``/cirrus``), set the
``CIRRUS_API_GATEWAY_BASE_PATH`` environment variable to the prefix (without leading
slash) so it is stripped before routing::

    CIRRUS_API_GATEWAY_BASE_PATH=cirrus

See `Lambda integration payload format versions
<https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-lambda.html>`_
for details on the differences between format 1.0 and 2.0. Lambda Function
URLs use `payload format version 2.0
<https://docs.aws.amazon.com/lambda/latest/dg/urls-invocation.html#urls-payloads>`_.

Trigger
-------

Triggered by sending valid HTTP requests.

Query parameters can be included in HTTP requests to control the behavior of
the response. A query param not in the following list will have no effect.

Query Params
~~~~~~~~~~~~

- State: ``State`` to filter the StateDB items on.
- Since: A string field used to search the StateDB from this time forward to
  the present. Takes the form of an integer followed by a flag to indicate the
  time unit. Acceptable flags are “d” (days), “h” (hours), and “m” (minutes)

Response
--------

A REST-like response containing a status_code, headers, and body that
can be parsed like any REST response.

Endpoints
---------

GET Root
~~~~~~~~

Return a STAC-like object with links to all the outputs from the cirrus
S3 data bucket.

GET Stats
~~~~~~~~~

Return a summary statistics of events from the TimeStream database to
get a picture of cirrus events on a daily, hourly, and hourly rolling
basis

GET Items
~~~~~~~~~

Return items from the DynamoDB state database based on query filters.
Can be filered on ‘state’, ‘since’, ‘limit’. The results are paginated
and the pagination key ``NextKey`` can be used by passing it as one of
the query params when making the API call to the lambda.
