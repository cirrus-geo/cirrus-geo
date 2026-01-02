State Database
==============

The state database (StateDB) is a serverless Amazon Web Services (AWS) DynamoDB
table used by Cirrus to track the state of workflows executions.  As seen
in the :doc:`architecture <20_arch>` the StateDB is an independant piece of AWS
infrastructure.  It is a critical component of Cirrus that ensures workflow
state and executions are properly tracked as part of :doc:`monitoring
<80_monitoring>` pipeline success, failure, errors, avoiding duplicate
workflows, and flagging invalid payloads.

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

DynamoDB is a serverless, highly scalable non-relational (NoSQL) database
provisioned and managed by AWS.  This means that DynamoDB is a "key-value"
database, not a relational database like Postgres or AWS RDS.  In a NoSQL
database like DynamoDB there are 'items' and each item has 'attributes', and
items are independant of each other.  This simplified structures allows
DynamoDB to be optimized for read/write at any scale.

Additionally as a NoSQL database, DynamoDB does not require a predefined
schema and permits different items to have different attributes unlike the
rigid schemas of relational databases, providing flexibility for users to add
attributes if needed.

Why DynamoDB?
--------------

- serverless
- optimized for scalable read/write
- non-relational

Cirrus itself handles business logic regarding when and how to make updates to
the StateDB and with no relationships between distinct workflow executions, the
StateDB only needs a "key-value" store for lookup.  As a managed, scalabale
"key-value" store DynamoDB is the AWS service that best meets Cirrus needs.

Managed Service
---------------

As a managed AWS service DynamoDB handles provisoning and maintaining the
underlying storage and scaling infrastructure as your data scales up or down.
This allows Cirrus to focus on the business logic of state management.
Additonally, DynamoDB is optimized by AWS for rapid read/writes at any scale.

Schema
------
While DynamoDB does not necessitate a predefined schema like a relational
databse, there are attributes that are required for core Cirrus functionality.

Required Fields:
These fields are required for out-of-the-box functionality of Cirrus

* ``collections_workflow`` (*string*):  a unique "partition key" constructed
  from a Cirrus payload's ``payload_id``
* ``itemIDs`` (*string*): a unique ID field extrated from a payload ID
* ``created`` (*string*): UTC time when record was created
* ``executions`` (*list[string]*): ARNs of state machine executions.  May have
  multiple records in this field if a payload is submitted multiple time, or
  part of chained workflows
* ``state_updated`` (*string*): Concatenated string of state + UTC time of last
  updated
* ``updated`` (*string*): UTC time when the record was most recently updated

StateDB and Cirrus CLI
-----------------------

Selected Cirrus CLI commands interact with the StateDB.

The ``get-payloads`` command takes in query parameters to retrieve input
payloads in bulk, returned as new line delimited JSON.

Input query parameters are used as filters against the StateDB to retrieve
records matching certain criteria, like entires with a ``FAILED`` workflow
status that occured in the past week.  These returned StateDB records are used
to retrieve input payloads from the S3 payload bucket which are returned to the
user.

More information about the ``get-payloads`` command can be found in the CLI
documentation

Deleting StateDB items
----------------------

The deletion of records from the StateDB is not generally necessary.  In the
unlikely case doing so required, the `cirrus.statedb.StateDB.delete_item()``
method can be used to delete a state record based on its ``payload_id``.
