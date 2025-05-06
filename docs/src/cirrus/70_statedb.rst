State Database
==============

The state database (stateDB) is a serverless Amazon Web Services (AWS) Dynamo
DB table used by cirrus to track the state of workflows and executions  It is a
critical of cirrus that ensurse workflow executions and execution state are
properly tracked.  Accurate state management is essential for monitoring
pipeline success, failure, errors, avoiding duplicate workflows, and flagging
invalid payloads.

The stateDB is accessed by cirrus at different stages of workflow execution.

    * ``process`` lambda: acesses the stateDB to check existing states and skip payloads that have successfully completed, and fire off TimeStream events in the event of encountering an already "failed" or "invalid" payload.  It will also make state updates upon initializing a workflow execution.
    * ``api`` lambda: when queried for aggregate statistics, the lambada will call the stateDB to get execution summary counts based on query inputs.
    * ``update_state`` lambda: updates stateDB table after step function workflow execution termination, successful or not.

Why Dynamo DB?
--------------

- serverless
- optimized for scalable read/write
- non-relational

Dynamo DB is a serverless non-relational (NoSQL) database provisioned and
managed by AWS.  This means that unlike other common databases like Postgres or
AWS RDS, DynamoDB is a "key-value" database, NOT a relational database. In a
relational database data in tables is stored as rows with columnar attributes
and relationships are understood by shared attributes across tables.  In a
NoSQL database like Dynamo DB there are instead 'items' and each item has
'attributes', and items are independant of each other.

While relational databases are optimized for understanding and exploring
relationships between data, NoSQL databases are often optimized for specific
requirements, in this case rapid read/write operations.  At no point does
cirrus state management necessitate complex relational queries, cirrus is only
reading or writing items to the state DB instead of exploring complex
relationships between between executions.

Additionally as a NoSQL database, Dynamo DB does not require a predefined
schema and permits diferent items to have different attributes while the rigid
schema of relational databases means there can be no variaton of the data
stored in a given table.  In fact each entry and its attributes in the cirrus
state DB is completely independant of other items in the state DB.

Managed Serverless Service
--------------------------

As a managed AWS service Dynamo DB handles provisoning and maintaining the
underlying storage and scaling infrastructure for your tables as your data
scales up or down.  This allows cirrus to focus on the business logic of state
management.  Additonally, Dynamo DB is optimized by AWS for rapid read/writes
at any scale.

Schema
------
While Dynamo DB does not necessitate a predefined schema like a relational
databse, there are attributes that are required for core cirrus functionality.
Users may add additional fields if necessary.  Because Dynamo DB does not
require a predefined schema users may add additonal attributes as needed.

Required Fields:
These fields are required for out of the box functionality of cirrus

* ``collections_workflow`` (*string*):  a unique "partition key" constructed from a cirrus payload's ``payload_id``
* ``itemIDs`` (*string*): a unique ID field extrated from a payload ID
* ``created`` (*string*): UTC time when record was created
* ``executions`` (*list[string]*): ARNs of state machine executions.  May have multiple records in this field if a payload is submitted multiple time, or part of chained workflows
* ``state_updated`` (*string*): Concatenated string of state + UTC of last updated
* ``updated`` (*string*): UTC time when the record was most recently updated

State DB and Cirrus CLI
-----------------------

Selected Cirrus CLI commands interact with the state DB.

The ``get-payloads`` command takes in query parameters to retrieve input payloads in bulk, returned as new line delimited JSON.

Input query parameters are used as filters against the state DB to retrieve
records matching certain criteria, like entires with a ``FAILED`` workflow
status that occured in the past week.  These returned state DB records are used
to retrieve input payloads from the S3 payload bucket which are returned to the
user.

One use for these returned bulk payloads is to pipe them into another
cirrus CLI command to rerun failed payloads, perhaps in the event of a third
party service failure that resulted in failed workflow executons.

More information about the ``get-payloads`` command can be found in the CLI
documentation

Deleting state DB items
-----------------------

There is a ``delete_item`` method in the "StateDB" class that can be used to
delete a given item based on using ``payload_id``.

However as the stateDB is the primary record keeping tool for cirrus, and is
used by almost all components, users are strongly discouraged from manually
altering/removing records in the state table
