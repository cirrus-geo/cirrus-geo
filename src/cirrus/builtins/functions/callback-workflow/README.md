#callback-workflow

Function to receive events from the Workflow Callback DynamoDB table stream.
Notifies waiting workflows of success/failures via associated callback tokens.

Useful as part of a workflow model that requires a workflow to wait for others
to complete in order to provide inputs.
