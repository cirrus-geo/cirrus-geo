# update-state

Updates the dynamoDB state database with the State Function execution results.

Completion of a State Function execution can also be used to chain additonal
workflow steps with pushing messages to SQS or SNS for additional steps beyond
the core cirrus workflow, like triggering a lambda to push an output STAC Item
to a STAC API.

## Trigger

The `update-state` lambda listens for terminal events output by a State Function
that is executing a cirrus workflow/task.  These terminal states are not an
exclusive list of possible states in the StateDB.

- "SUCCEEDED": the successful completion of a cirrus workflow
- "FAILED": A failed execution.  This can occur for a variety of reasons
- "ABORTED": The state machinea was forced to abort execution.  Can be triggered
    by manual termination of a workflow.
- "TIMED OUT": State machine terminated due to time out.  Can occur if a third
    party resource involved in a task hangs, or a workflow configuration did not
    allow sufficient time for a task to complete.

## StateDB Updates

Updating the DynamoDB state database is the core functionality of the
`update-state` lambda.

In addition to updating DynamoDB the `update-state` lambda also fires off events
to AWS TimeStream with each state update.

The `update-state` lambda additionally logs any errors that come from the
StateMachine so they can be captured and anlyzed in the log stream.

`update-state` can send messages to configured SNS topics to provide
notifications to users or downstream services when events and/or output items
are produced.  It may also be used to facilitate workflow chaining by
requeuing payloads in the `process` queue.
