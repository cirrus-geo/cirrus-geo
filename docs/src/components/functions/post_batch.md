# post-batch

A lambda related to running Batch tasks, required to work around limitations of AWS Batch.

* Post-batch: Runs only for batch tasks.  Takes batch output payloads from S3 and passes payloads to next task in the workflow.

The `post-batch` lambda preforms a function similar to that of the `pre-batch` lambdas.  A `Batch` task will execute the predefined workflow and push the output to S3.  The `post-batch` lambda will take outputs from S3 and passes the payloads to the next task in the workflow.

It also handles errors that come out of the `Batch` workflow, errors that can be related to either the Batch job itself or cirrus task related errors.

## Trigger

The completion of any cirrus `Batch` task
