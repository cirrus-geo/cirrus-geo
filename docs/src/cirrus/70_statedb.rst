State Database
==============



The state database (DB) is a Amazon Web Services (AWS) Dynamo DB table used to track the state of workflows and executions.  It is a critical component of cirrus, ensuring that executions are properly tracked, duplicate runs are not executing, ensuring duplicate payloads are skipped, and a place to query.  This
state tracking is also critical to tracking failed or aborted workflows, or
flagging invalid payloads, as essential tool for monitoring pipeline success
and failures.

Why Dynamo DB?
--------------

Dynamo DB is what is commonly known as a NoSQL database provided by AWS.  Unlike
other common databases like Postgres or AWS, it is NOT a relational database.
As a non-relational database, and never having to caluclate complex query and
joins it has enhanced performance for read and write, critical when running
large pipelines with potentially tens of thousands of runs simultaneously.

The ``cirrus-geo`` Dynamo DB instanced is designed on a ``key-value`` principle.
This enable quick and efficent look ups on a given key-value, or combining
multiple key value pairs into a query.

Schema
------

Using cirrus-lib to interact with state database
------------------------------------------------

Using the Cirrus CLI
--------------------

Selected Cirrus CLI commands interact with the state database.

The ``get-payloads`` command take in query parameters that can be used as query
filters against the DB to retrieve records matching certain criteria, like
entires with a ``FAILED`` workflow status that occured in the past week.  These
returned records are then transformed to extract the payloads from the S3
payload bucket.  These returned payloads can be handled as desired, for example
usig other CLI commands to rerun these failed payloads.

Deleting items from database
----------------------------
