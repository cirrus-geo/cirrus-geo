State Database
==============

The state database (stateDB) is a serverless Amazon Web Services (AWS) Dynamo
DB table used to track the state of workflows and executions  It is a critical
component of cirrus that ensurse executions and execution state are properly
tracked.  Accurate state management is essential for monitoring pipeline
success, failures and errors.  State management is also essential for avoiding
duplicate workflows, tracking failed or aborted workflows, and flagging invalid
payloads.

The stateDB is accessed by cirrus at different stages of workflow execution.
Some non exhaustive examples are as follows:

    * ``process`` lambda: acesses the stateDB to check existing states and skip payloads that have successfully completed, and fire off TimeStream events in the event of encountering an already "failed" or "invalid" payload.  It will also make state updates if encountering an invalid payload or initializing a workflow execution.
    * ``api`` lambda: when queried for aggregate statistics, the lambada will call the stateDB to get execution summary counts based on query inputs.
    * ``update_state`` lambda: updates stateDB table after step function workflow execution termination

Why Dynamo DB?
--------------

- serverless
- scalability
- optimized for scalable read/write
- non-relational

Dynamo DB is a serverless non-relational (NoSQL) database provisioned and managed by AWS.

Unlike other common databases like Postgres or AWS RDS, DynamoDB is a
"key-value" database, NOT a relational database. In a relational database data
is stored as rows in tables with columnar attributes and relationships exist
between rows in different tables. In a NoSQL database like Dynamo DB there are
instead 'items' and each item has 'attributes'.

Additionally as a NoSQL database, Dynamo DB does not require a predefined
schema and in fact permits diferent items to have different attributes while
the rigid schema of relational databases means there can be no variaton of the
data stored in a given table.  At no point does cirrus state management
necessitate complex relational queries, we are simply reading or writing items
to the state DB instead of exploring complex relationships between items.  In
fact each entry and its attributes in the cirrus state DB is completely
independant of other items in the state DB.

Managed Serverless Service
--------------------------

As a managed AWS service Dynamo DB handles provisoning and maintaining   underlying storage and scaling infrastructure as your data scales up or down.  This allows cirrus to focus simply on the business logic of state management.  Additonally, Dynamo DB is optimized for rapid read/writes at any scale.


Schema
------
While Dynamo DB does not necessitate a predefined schema like a relational
databse, there are attributes that are required by cirrus functionality.
Users may add additional fields if necessary.  Because Dynamo DB does not
require a predefined schema users may add additonal attributes as needed.

Required Fields:
These fields are required for out of the box functionality of cirrus

* ``collections_workflow`` (*string*):  a unique "partition key" constructed from a CPP ``payload_id``
* ``itemIDs`` (*string*): a unique ID field extrated from a payload ID
* ``created`` (*string*): UTC time when record was created
* ``executions`` (*list[string]*): ARNs of state machine executions.  May have multiple records in this field if a payload is submitted multiple time, or part of chained workflows
* ``state_updated`` (*string*): Concatenated string of state + UTC of last updated
* ``updated`` (*string*): UTC time when the record was most recently updated


State DB and Cirrus CLI
-----------------------

Selected Cirrus CLI commands interact with the state DB.

The ``get-payloads`` command take in query parameters that can be used as query
filters against the state DB to retrieve records matching certain criteria, like
entires with a ``FAILED`` workflow status that occured in the past week.  These
returned state DB records are used to retrieve input payloads from the S3
payload bucket.  One common use for these returned bulk payloads is to pipe
them into another cirrus CLI command to rerun failed payloads, perhaps in the
event of a third party serice failure that resulted in failed executons.

Deleting items from database
----------------------------

There is a ``delete_item`` method in the "StateDB" class that can be used to
delete a given item based on using ``payload_id``.

However as the stateDB is the primary record keeping tool for cirrus, and is
used by almost all components, users are strongly discouraged from manually
altering/removing records in the state table
