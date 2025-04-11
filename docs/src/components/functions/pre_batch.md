# Pre Batch

A lambda specifically for wrapping cirrus tasks executing on an AWS Batch

This lambda is built to work around a limitation in how AWS Batch tasks are called.  `Batch` tasks do not support large JSONs being passed directly in the 'submit task' call, and STAC payloads can be large.   To work around this limitation the `pre-batch` lambda will take the input payload, push it to an intermediate location (S3) and the URL of this location will be passed to the step function.

A batch task will execute the defined workflow and will put the output to S3.


## Trigger

Any cirrus workflow or task that is an `Batch` job.
