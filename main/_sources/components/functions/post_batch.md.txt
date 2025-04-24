# post-batch

A lambda related to running Batch tasks, required to work around limitations of AWS Batch and facilitates batch tasks to have the same step-function API as a lambda based task

The `post-batch` lambda preforms a function similar to that of the `pre-batch` lambdas.  A `Batch` task will execute the predefined workflow and push the output to S3.  The `post-batch` lambda will take outputs from S3 and passes the payloads to the next task in the workflow.

It also handles errors that come out of the `Batch` workflow, errors that can be related to either the Batch job itself or cirrus task related errors, and re-raises these errors in the step-function context.

## Trigger

The completion of any cirrus `Batch` task
