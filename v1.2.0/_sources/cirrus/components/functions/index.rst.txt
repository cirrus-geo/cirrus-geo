Functions
=========

The ``function`` component type refers to AWS Lambda functions.  These
functions are essential to the functioning of Cirrus by performing jobs that
wrap around the core analysis of workflows and tasks.

There are currently 5 lambdas, 2 of which can be considered essential to a
functioning Cirrus deployment, and 3 others that can be conditionally created
for more complex use cases.

Required
--------

* ``process``: Listens for payloads on the SQS queue and then transforms these payloads and kicks off a pre-defined workflows.  Performs state management by updating state as workflows are claimed and begin processing to place effective locks and prevent duplicate workflows, and updates state for step function executions that fail to start
* ``update-state``: Handles step function completion events, updating state database and sending notification to downstream systems.

Optional
--------

These lambda functions offer more advanced functionality for heavier use cases
like longer running jobs and Cirrus dashboards.

* ``pre-batch``: Runs only for batch tasks.  Takes input payloads and send them to S3 to then pass the S3 payload URL to the Step Function
* ``post-batch``: Runs only for batch tasks.  Takes batch output payloads from S3 and passes payloads to next task in the workflow.  Also retrieves and errors from failed batch tasks and re-raises them in the step-functon context.
* ``api``: Offers a read-only HTTP API clients can leverage to search and fetch data from state databse and event database.

Additional documentation on each lambda can be found in component READMEs
