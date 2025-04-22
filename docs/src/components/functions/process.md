# process

The `process` lambda is a core piece of Cirrus infrastructure.  It processes messages, extracts and prepares Cirrus process Payloads (CPP) from these messages and then uses these payloads to trigger execution of pre-defined AWS Step Function workflows.  This lambda can also involve simple administrative work like setting payload ids, and updating the state db to avoid duplicative executions.

## Trigger

There are multiple ways to trigger the `process` lambda.

* Send a prepared CPP message to the SQS `process` queue
* Indirect invocation: send a message to the SQS queue using te CLIrrus CLI tool `process` command.

The SQS message can be used to send a single payload, or batch payloads to trigger workflows at volume with a single message (e.g. bulk image processing).  Once these lambda has ingested a payload it begins the processing pipeline.

## Payload

It is preferable that a message sent to the SQS queue is a CPP, but that is not essential.  The message may contain the CPP to be run, or can have an S3 URl for a payload for the lambda to retrieve.

## Workflow Kick Off

The core function of the `process` lambda is to handle and process inputs and to then trigger AWS Step Function execution of predefined cirrus tasks and workflows.  Payloads are also stored in the cirrus deployment S3 bucket.

## State Management

The `process` lambda also updates the state table when workflows are initiated or fail to be initiated.  This is intended to prevent duplicate workflows running the same payload.

### CLI

This lambda can be invoked using the included CLIrrus CLI tool using either the `process` or `invoke` commands.
