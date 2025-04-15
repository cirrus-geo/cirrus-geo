Functions
=========

The ``function`` component type refers to AWS Lambda functions.  These functions are essential to the functioning of Cirrus by performing essential tasks that wrap around the core analysis of workflows and tasks.

There are currently 5 lambdas, 2 of which can be considered essential to a minimally functioning Cirrus deployment, and 3 others that can be conditionally created for more robust/complex use cases.

Required
--------

These are the lambda functions that are essential to a minimally functional cirrus deployment.

* Process: Listens for payloads on the SQS queue and then transforms these payloads and kicks off a pre-defined task or workflow.
* Update-State: Manages updating state.  Execution states are stored in DynamoDB and the Update-State lambda focuses on ensures state is accurately managed and updated.

Optional
--------

These lambda functions offer more advanced functionality for heavier use cases like longer processing and Cirrus dashboards.

* Pre-batch: Runs only for batch tasks that takes input payloads and sends them to S3 to then pass the S3 payload URL to the Step Function
* Post-batch: Only runs after batch tasks to retrieve output payload from S3 and send to the `update-state` lambda for state management.
* API: Offers a REST-like interface for collecting aggregate statistics about cirrus events.

Additional documentation on each lambda can be found in coponent READMEs
