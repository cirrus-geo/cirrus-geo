# Process

The process lambda is a core piece of Cirrus infrastructure.  It processes messages, extracts and prepares Cirrus Process Payloads from these messages and then uses these payloads to trigger execution of pre-defined AWS Step Function workflows.  This process can also involve simple administrative work like setting payload ids, and updating the state db to avoid duplicative executions.

## Trigger

The Process lambda listens for messages on the `Process` SQS queue.  These messages are ingested by the process lambda and used to trigger cirrus tasks/workflows.  The SQS message can be used to send a single payload, or batch payloads to trigger workflows at volume with a single message (e.g. bulk image processing)

## Payload

The Process lambda message from SQS is NOT required to itself be a Cirrus Payload.  The message can itself contain the payload to be run, or can have an S3 URl for a payload for the lambda to retrieve.

## Workflow Kick Off

The core function of the process lambda is to handle and process inputs and to then trigger AWS Step Function execution of predefined cirrus tasks and workflows.  Payloads are also stored in the cirrus deployment S3 bucket.   Large payloads are uploaded to S3 and the S3 URL is passed to the state machine, while

## State Management

The Process lambda also makes select updates the state table when workflows are claimed and started to prevent duplicate workflows running the same payload.  Failure to trigger a step function execution is also logged in the state table.

### CLI

This lambda can be invoked using the included CLIrrus CLI tools to send a payload to the `Process` queue.
