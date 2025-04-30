State Database
==============

The state database (DB) is a Amazon Web Services (AWS) Dynamo DB table used to track the state of workflows and executions.  It is a critical component of cirrus, ensuring that executions are properly tracked, duplicate runs are not executing, ensuring duplicate payloads are skipped, and a place to query.  This
state tracking is also critical to tracking failed or aborted workflows, or
flagging invalid payloads, as essential tool for monitoring pipeline success
and failures.

Interactions are primarily conducted via the StateDB class, which handles transformations of CPP payloads and pipeline events into neccessary format for the Dynamo DB table.

The stateDB is accessed by cirrus at many different stages of workflow execution.  Some non exhaustive examples are as follows:

    * ``process`` lambda: accesses the stateDB to check existing states and skip payloads that have successfully completed, or fire off TimeStream events in the event of encountering an already "failed" or "invalid" payload.  It will also make state updates if say encountering an invalid payload or starting an execution.
    * ``api`` lambda: when queried for aggregate statistics, the lambada will call the stateDB to get counts based on query inputs.
    * ``update_state`` lambda: updates stateDB table after execution complete successfully or not.


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
There are core attributes that are required by existing cirrus functionality.
You may add additional fields if necessary.  A nice feature of Dynamo DB is that there is no predefined schema and you may simply add another attribute to a call when updating a record.

Required Fields:
These fields are required for out of the box
- ``collections_workflow`` (*string*):  a unique "partition key" constructed from a CPP ``payload_id``
- ``itemIDs`` (*string*): a unique ID field extrated from a payload ID
- ``created`` (*string*): UTC time when record was created
- ``executions`` (*list[string]*): ARNs of state machine executions.  May have multiple records in this field if a payload is submitted multiple time, or part of chained workflows
- ``state_updated`` (*string*): Concatenated string of state + UTC of last updated
- ``updated`` (*string*): UTC time when the record was most recently updated


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

There is a ``delete_item`` method in the "StateDB" class that can be used to delete a given item based on using ``payload_id``.

However as the stateDB is the primary record keeping tool for cirrus, and is used by almost all components, users are strongly discouraged from manually altering/removing records in the state table
