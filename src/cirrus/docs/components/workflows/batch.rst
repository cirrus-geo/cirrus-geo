Batch tasks in workflows
========================

Using Batch tasks in workflows is a little more involved than with Lambda tasks.
Lambdas integrate a more natively with step functions than batch, which has
additional layer of infrastructure between. As a result, users must keep a few
more things in mind when wanting to use Batch tasks.


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

Now, instead of simply being able to have a single step in a step function for a
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


Minimal example
^^^^^^^^^^^^^^^

Let's see an example of a workflow using ``parallel`` to group the set of Batch
operations together. Notice how the example uses ``parallel`` with only a single
branch defined, but that fits the Batch use-case perfectly.

::

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
                      IntervalSeconds: 1
                      BackoffRate: 2.0
                      MaxAttempts: 5
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
                      IntervalSeconds: 1
                      BackoffRate: 2.0
                      MaxAttempts: 5
          Next: publish
          # Parallel output is always an array of the outputs from each branch.
          # We can use the OutputPath selector to get output index 0 as we only
          # have a single branch, so we don't pass an array as input to the
          # next task.
          OutputPath: $[0]
          Retry:
            # This policy will retry any errors a second time
            - ErrorEquals: ["States.ALL"]
              IntervalSeconds: 3
              MaxAttempts: 2
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
              IntervalSeconds: 1
              BackoffRate: 2.0
              MaxAttempts: 5
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
