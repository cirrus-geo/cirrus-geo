post-batch
==========

A lambda related to running Batch tasks, required to work around limitations of
AWS Batch and facilitates batch tasks to have the same step-function API as a
lambda-based task.

In other words, the ``post-batch`` task performs a function similar to but
opposite that of the ``pre-batch`` task. A completed ``Batch`` task must push
its output to S3. The ``post-batch`` task will take said output from S3 and
pass it along to the next task in the workflow. The combination of
``pre-batch`` and ``post-batch`` with a batch task emulates how a lambda task
is able to consume and return the JSON payload directly.

It also handles errors that come out of the ``Batch`` workflow, errors that can
be related to either the Batch job itself or cirrus task related errors, and
re-raises these errors in the step-function context.
