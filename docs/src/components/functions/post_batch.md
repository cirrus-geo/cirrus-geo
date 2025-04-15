# Post Batch

A lambda related to running Batch tasks, required to work around limitations of AWS Batch.

The `post-batch` lambda preforms a function similar to that of the `pre-batch` lambdas.  A `Batch` task will execute the predefined workflow and push the output to S3 and return te URL.  The `post-batch` lambda will take in the S3 URL, retrieve the output payload, and pass it along to be captured and handled by the `update-state` lambda.

It also handles errors that come out of the `Batch` workflow, errors that can be related to either the Batch job itself or cirrus task related errors.

## Trigger

The completion of any cirrus `Batch` workflow
