# pre-batch

A lambda related to running Batch tasks, required to work around limitations of AWS Batch.

This lambda exists due to how AWS Batch tasks are called.  `Batch` tasks do not support large JSONs being passed directly in the 'submit task' call, and STAC payloads can be large.   To work around this limitation the `pre-batch` lambda will take the input payload, push it to an intermediate location (S3) and the URL of this location will be passed to the step function.

A batch task will execute the defined workflow and will dump the output to S3, where it is picked up by the `post-batch` lambda

## Trigger

Any cirrus workflow or task that is an `Batch` job.
