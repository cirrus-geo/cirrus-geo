State Database
==============

The state database (StateDB) is a serverless Amazon Web Services (AWS) Dynamo
DB table used by Cirrus to track the state of workflows and executions  It is a
critical of Cirrus that ensurse workflow executions and execution state are
properly tracked.  Accurate state management is essential for monitoring
pipeline success, failure, errors, avoiding duplicate workflows, and flagging
invalid payloads.

The StateDB is accessed by Cirrus at different stages of workflow execution.

    * ``process`` lambda: acesses the StateDB to check existing states and skip payloads that have successfully completed, and fire off TimeStream events in the event of encountering an already "failed" or "invalid" payload.  It will also make state updates upon initializing a workflow execution.
    * ``api`` lambda: when queried for aggregate statistics, the lambada will call the StateDB to get execution summary counts based on query inputs.
    * ``update_state`` lambda: updates StateDB table after step function workflow execution termination, successful or not.
    * ``management`` cli: directly connects to the StateDB to get workflow status, inputs, and outputs.

Why DynamoDB?
--------------

- serverless
- optimized for scalable read/write
- non-relational

DynamoDB is a serverless non-relational (NoSQL) database provisioned and
managed by AWS.  This means that unlike other common databases like Postgres or
AWS RDS, DynamoDB is a "key-value" database, NOT a relational database. In a
relational database data in tables is stored as rows with columnar attributes
and relationships are understood by shared attributes across tables.  In a
NoSQL database like DynamoDB there are instead 'items' and each item has
'attributes', and items are independant of each other.

While relational databases are optimized for understanding and exploring
relationships between data, NoSQL databases are often optimized for specific
requirements, in this case rapid read/write operations.  At no point does
Cirrus state management necessitate complex relational queries, Cirrus is only
reading or writing items to the state DB instead of exploring complex
relationships between between executions.

Additionally as a NoSQL database, DynamoDB does not require a predefined
schema and permits diferent items to have different attributes while the rigid
schema of relational databases means there can be no variaton of the data
stored in a given table.  In fact each entry and its attributes in the Cirrus
state DB is completely independant of other items in the state DB.

Managed Serverless Service
--------------------------

As a managed AWS service DynamoDB handles provisoning and maintaining the
underlying storage and scaling infrastructure for your tables as your data
scales up or down.  This allows Cirrus to focus on the business logic of state
management.  Additonally, DynamoDB is optimized by AWS for rapid read/writes
at any scale.

Schema
------
While DynamoDB does not necessitate a predefined schema like a relational
databse, there are attributes that are required for core Cirrus functionality.
Users may add additional fields if necessary.  Because DynamoDB does not
require a predefined schema users may add additonal attributes as needed.

Required Fields:
These fields are required for out of the box functionality of Cirrus

* ``collections_workflow`` (*string*):  a unique "partition key" constructed from a Cirrus payload's ``payload_id``
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
Cirrus CLI command to rerun failed payloads, perhaps in the event of a third
party service failure that resulted in failed workflow executons.

More information about the ``get-payloads`` command can be found in the CLI
documentation

Deleting state DB items
-----------------------

There is a ``delete_item`` method in the "StateDB" class that can be used to
delete a given item based on using ``payload_id``.

However as the StateDB is the primary record keeping tool for Cirrus, and is
used by almost all components, users are strongly discouraged from manually
altering/removing records in the state table
