State Database
==============

The state database (StateDB) is a serverless Amazon Web Services (AWS) DynamoDB
table used by Cirrus to track the state of workflows and executions.  It is a
critical component of Cirrus that ensures workflow state and executions are
properly tracked.  Accurate state management is essential for monitoring
pipeline success, failure, errors, avoiding duplicate workflows, and flagging
invalid payloads.

The StateDB is accessed by Cirrus at different stages of workflow execution.

* ``process`` lambda: acesses the StateDB to check existing states and skip
  payloads that have successfully completed, and fire off TimeStream events in
  the event of encountering an already "failed" or "invalid" payload.  It will
  also make state updates upon initializing a workflow execution.
* ``api`` lambda: when queried for aggregate statistics, the lambada will call
  the StateDB to get execution summary counts based on query inputs.
* ``update_state`` lambda: updates StateDB table after step function workflow
  execution termination, successful or not.
* ``management`` cli: directly connects to the StateDB to get workflow status,
  inputs, and outputs.

What is DynamoDB?
-----------------

DynamoDB is a serverless non-relational (NoSQL) database provisioned and
managed by AWS.  This means that DynamoDB is a "key-value" database, not a relational database like Postgres or
AWS RDS.  In a
NoSQL database like DynamoDB there are 'items' and each item has
'attributes', and items are independant of each other.  This simplified
structures allows DynamoDB to be optimized for read/writing at any scale.

Additionally as a NoSQL database, DynamoDB does not require a predefined
schema and permits diferent items to have different attributes unlike the rigid schemas of relational databases.  In fact each entry and its attributes in the Cirrus state DB is completely independant of other items in the state DB.


Why DynamoDB?
--------------

- serverless
- optimized for scalable read/write
- non-relational

Cirrus itself handles business logic of when and how to make updates to the StateDB, and thus the StateDB only needs a "key-value" store for lookup.  DynamoDB is the fast, scalable managed AWS service that best meets Cirrus needs.

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

* ``collections_workflow`` (*string*):  a unique "partition key" constructed
  from a Cirrus payload's ``payload_id``
* ``itemIDs`` (*string*): a unique ID field extrated from a payload ID
* ``created`` (*string*): UTC time when record was created
* ``executions`` (*list[string]*): ARNs of state machine executions.  May have
  multiple records in this field if a payload is submitted multiple time, or
  part of chained workflows
* ``state_updated`` (*string*): Concatenated string of state + UTC of last
  updated
* ``updated`` (*string*): UTC time when the record was most recently updated

State DB and Cirrus CLI
-----------------------

Selected Cirrus CLI commands interact with the state DB.

The ``get-payloads`` command takes in query parameters to retrieve input
payloads in bulk, returned as new line delimited JSON.

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

The deletion of records from the StateDB is strongly discouraged, and almost
certainly unnecessary.  For the unlikely case it is required, there is a
``delete_item`` method of the ``StateDB`` class.  That can be used to delete
a record, based on its ``payload_id``.
