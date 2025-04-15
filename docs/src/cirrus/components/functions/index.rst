Functions
=========

The ``function`` component type refers to AWS Lambda functions.  These functions are essential to the functioning of Cirrus by performing jobs that wrap around the core analysis of workflows and tasks.

There are currently 5 lambdas, 2 of which can be considered essential to a functioning Cirrus deployment, and 3 others that can be conditionally created for more complex use cases.

Required
--------

* Process: Listens for payloads on the SQS queue and then transforms these payloads and kicks off a pre-defined task or workflow.  Can also be directly triggered via CLIrrus CLI
* Update-State: Manages updating state.  Execution states are stored in DynamoDB and the update-state lambda ensures the state database is accurately managed and updated.

Optional
--------

These lambda functions offer more advanced functionality for heavier use cases like longer running jobs and Cirrus dashboards.

* Pre-batch: Runs only for batch tasks.  Takes input payloads and sends them to S3 to then pass the S3 payload URL to the Step Function
* Post-batch: Runs only for batch tasks.  After a batch task complete, retrieves output payload from S3 and send to the `update-state` lambda for state management.
* API: Offers a REST-like interface to offer aggregate statistics about cirrus events.

Additional documentation on each lambda can be found in component READMEs
