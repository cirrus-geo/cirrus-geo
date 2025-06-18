Batch tasks in workflows
========================

Using Batch tasks in workflows requires a few additional steps than using Lambda tasks.
Lambdas integrate more directly with Step Functions than Batch, which has
additional layer of infrastructure in-between. As a result, users must keep a few
more things in mind when using to Batch tasks.


``pre-batch`` and ``post-batch``
--------------------------------

Because Batch tasks cannot take the input payload natively like Lambda and must
redirect through S3, Cirrus provides a built-in Lambda task to assist. The
``pre-batch`` task takes an input payload, uploads it to S3, and returns an
output JSON payload with a ``url`` key with the S3 payload URL as its value.
``pre-batch`` should always be run immediately proceeding a Batch task for this
purpose.

Similarly, Batch does not integrate returned payloads with step functions nearly
as well as Lambda, so Cirrus has a built-in ``post-batch`` task to help with,
well, post-batch operations. Specifically, ``post-batch`` can pull the Batch
payload from S3 and return that in the case of a successful Batch execution. In
the case of a Batch error, ``post-batch`` will scrape the execution logs for an
exception or other error message, and raise it within the step function. This
helps "bubble" Batch task errors up to the step function. Errors can then be
handled within the step function semantics or used to fail the step function
execution with error context that can ultimately be pushed into the state
database, increasing error visibility and assisting with troubleshooting.

Therefore, like ``pre-batch``, a ``post-batch`` step should always immediately
follow a Batch task step.


Put it all together with a ``parallel`` block
---------------------------------------------

Instead of simply being able to have a single step in a step function for a
Batch task, we end up with three steps. Because of the way they operate
together, we can think of the ``pre-batch`` -> Batch task -> ``post-batch``
triad as a single step from the perspective of error handling and retries. That
is, if we encounter an error anywhere in that set of three, we either want to
fail them all or retry them all together.

Enter the step function ``parallel`` block. Step functions provide this control
primative to allow users to define one or more branches in a workflow that can
execute in parallel. Interestly for us, ``parallel`` supports both ``Catch`` and
``Retry`` policies for error handling, which provides us with the control we
need for Batch.


Error handling
^^^^^^^^^^^^^^

It is essential that workflows properly handle errors when using Batch, as there are
more things that can go wrong than when using Lambda. For example, when too many Step
Functions are trying to create a new Batch Job, a AWSBatchException is thrown. When the
EC2 instance that a Batch Job is running on is reclaimed, as happens frequently with Spot
instances at scale, a retry should occur so the Batch Job is attempted again. This is why
it is recommended to use a Parallel block with retry to wrap the Batch steps.

Additional considerations
^^^^^^^^^^^^^^^^^^^^^^^^^

Batch does not perform well when there are many jobs that run quickly. For example, if
a task filters out a significant number of payloads quickly, the overhead of placing the jobs
onto compute resources will dominate the runtime, and will result in a slow and inefficient
pipeline. A few examples in Earth Search are:

- Landsat SNS topic (public-c2-notify-v2) that initiates ingest includes many "Real-Time" (RT)
  scenes that are ignored. These result in a runtime of only a few seconds. If these were run
  with Batch, there would be a few minute overhead for job placement (incurring the cost of
  the EC2 instances for that time) for only a few seconds of actual use.
- Even without the aforementioned RT scenes, Landsat ingest uses Lambda instead of Batch
  because the task is only performing a metadata-to-metadata conversion that takes tens of seconds
  per scene. The overhead for Batch is far greater than the actual runtime, and the task runtime
  is both low (much less than the Lambda maximum of 15 minutes) and consistent.
- The Sentinel-2 Collection 1 Level-L2A collection only includes items with a "processing baseline"
  value of 05.00 or higher. All newly-acquired scenes have this processing baseline, but when
  back-processing the catalog, about half of the scenes have an older baseline and are immediately
  ignored. This meant that half of the Batch Jobs ran for seconds and half ran for 5-10 minutes.
  The batch jobs that ran for seconds caused a signficant increase in cost and decrease in throughput.
  A better solution would have been to have an initial Lambda that checked only if the processing
  baseline was appropriate, and only allowed the Batch job to run if it was.

Another consideration is with error handing and InvalidInputs. Tasks that raise InvalidInput exceptions
are indicating that the payload can never be processed correctly. I trivial example of this would be a
process payload with only an ID value and no other information. This is contrasted with a valid payload
that fails because of something that can be corrected, such as a code bug or a


Minimal example
^^^^^^^^^^^^^^^

Let's see an example of a workflow using a ``Parallel`` block to group the set of Batch
operations together. Notice how the example uses ``parallel`` with only a single
branch defined, but that fits the Batch use-case perfectly.

Example::

    name: '#{AWS::StackName}-batch-example
    definition:
      Comment: "Example workflow using parallel to make a 'batch group'"
      StartAt: batch-group
      States:
        batch-group:
          Type: Parallel
          Branches:
            - StartAt: pre-batch
              States:
                pre-batch:
                  Type: Task
                  Resource: !GetAtt pre-batch.Arn
                  Next: batch-task
                  Retry:
                    - ErrorEquals: ["Lambda.TooManyRequestsException", "Lambda.Unknown"]
                      IntervalSeconds: 10
                      MaxDelaySeconds: 86400
                      BackoffRate: 2.0
                      MaxAttempts: 20
                      JitterStrategy: FULL
                batch-task:
                  Type: Task
                  Resource: arn:aws:states:::batch:submitJob.sync
                  Parameters:
                    JobName: some-batch-job
                    JobQueue: "#{ExampleJobQueue}"
                    JobDefinition: "#{ExampleBatchJob}"
                    # Note that this passes the value of the `url` key in the step's
                    # input JSON to the job definition as the parameter `url`i.
                    Parameters:
                      url.$: "$.url"
                  Next: post-batch
                  Retry:
                    - ErrorEquals: ["Batch.AWSBatchException"]
                      IntervalSeconds: 600
                      MaxDelaySeconds: 86400
                      BackoffRate: 2.0
                      MaxAttempts: 20
                      JitterStrategy: FULL
                  Catch:
                    # Ensures we always go to post-batch to pull errors
                    - ErrorEquals: ["States.ALL"]
                      ResultPath: $.error
                      Next: post-batch
                post-batch:
                  Type: Task
                  Resource: !GetAtt post-batch.Arn
                  # End of the branch, not the step function
                  End: True
                  Retry:
                    - ErrorEquals: ["Lambda.TooManyRequestsException", "Lambda.Unknown"]
                      IntervalSeconds: 10
                      MaxDelaySeconds: 86400
                      BackoffRate: 2.0
                      MaxAttempts: 20
                      JitterStrategy: FULL
          Next: publish
          # Parallel output is always an array of the outputs from each branch.
          # We can use the OutputPath selector to get output index 0 as we only
          # have a single branch, so we don't pass an array as input to the
          # next task.
          OutputPath: $[0]
          Retry:
            # This policy will retry multiple times after any errors
            - ErrorEquals: ["States.ALL"]
              MaxAttempts: 3
              IntervalSeconds: 1200
              MaxDelaySeconds: 86400
              BackoffRate: 2.0
              JitterStrategy: FULL
          Catch:
            # If the branch fails more than twice we fail the workflow
            - ErrorEquals: ["States.ALL"]
              ResultPath: $.error
              Next: failure
        publish:
          Type: Task
          Resource: !GetAtt publish.Arn
          End: True
          Retry:
            - ErrorEquals: ["Lambda.TooManyRequestsException", "Lambda.Unknown"]
              IntervalSeconds: 10
              MaxDelaySeconds: 86400
              BackoffRate: 2.0
              MaxAttempts: 20
              JitterStrategy: FULL
          Catch:
            - ErrorEquals: ["States.ALL"]
              ResultPath: $.error
              Next: failure
        failure:
          Type: Fail


Batch retries vs step function retries
--------------------------------------

Whenver possible, using the step function retry semantics over those provided by
Batch is preferred. While Batch retries can be used without having to manage the
additional complexity of the ``parallel`` block, Batch retries regardless of
error type, while step function retries allow matching specific error types,
allowing users more granular control over when to retry or fail.

Additionally, retrying within the step function shows the retry as a separate
step than the first. This makes it much more obvious to users investigating
failures that a retry happened and what the initial error was. Batch retries
are more or less hidden from the step functions.

For these reasons, the overhead of the ``parallel`` block is worth the
investment.


Conditionally Using Batch or Lambda
--------------------------------------

Tasks can be configured to use either Batch or Lambda, and then the specific
one to use can be specified in the payload and selected by the workflow.

The payload should include a field like `batch` with a boolean indicating
if it's Batch or not (meaning Lambda)::

  {
    "process": {
    ...
    "tasks": {"foo-to-stac": {"batch": true}},
    ...
  }

Then in the workflow, this field can be used to drive a Choice block that selects either the
Batch or Lambda path::

  definition:
    StartAt: batch-or-lambda
    States:
      batch-or-lambda:
        Type: Choice
        Choices:
          - Variable: "$.process.tasks.foo-to-stac.batch"
            IsPresent: false
            Next: foo-to-stac-lambda
          - Variable: "$.process.tasks.foo-to-stac.batch"
            BooleanEquals: false
            Next: foo-to-stac-lambda
          - Variable: "$.process.tasks.foo-to-stac.batch"
            BooleanEquals: true
            Next: batch-group

In this case, `foo-to-stac-lambda` is a Task block that defines the Lambda path
and `batch-group` is a Task or Parallel block that defines the Batch path.
