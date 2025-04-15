# Process

The process lambda is a core piece of Cirrus infrastructure.  It processes messages, extracts and prepares Cirrus Process Payloads (CPP) from these messages and then uses these payloads to trigger execution of pre-defined AWS Step Function workflows.  This process can also involve simple administrative work like setting payload ids, and updating the state db to avoid duplicative executions.

## Trigger

There are multiple ways to trigger the Process lambda.

* Listens for messages on the `Process` SQS queue.
* Send a message to an SNS topic which the SQS queue is subscribed to
* Direct invocation - you can send a payload directly to the lambda using the CLIrrus CLI tool `invoke-lambda` command
* Indirect invocation: send a message to the SQS queue using te CLIrrus CLI tool `process` command.

The SQS message can be used to send a single payload, or batch payloads to trigger workflows at volume with a single message (e.g. bulk image processing).  Once these lambda has ingested a payload it begins the processing pipeline.

## Payload

The Process lambda message from SQS is NOT required to itself be a Cirrus Payload.  The message can itself contain the payload to be run, or can have an S3 URl for a payload for the lambda to retrieve.  However direct invocation not require a CPP payload.

## Workflow Kick Off

The core function of the process lambda is to handle and process inputs and to then trigger AWS Step Function execution of predefined cirrus tasks and workflows.  Payloads are also stored in the cirrus deployment S3 bucket.

## State Management

The Process lambda also makes select updates the state table when workflows are claimed and started to prevent duplicate workflows running the same payload.  Failure to trigger a step function execution is also logged in the state table.

### CLI

This lambda can be invoked using the included CLIrrus CLI tool using either the `process` or `invoke` commands.
