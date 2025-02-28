Writing workflow definitions
============================

Cirrus workflows, being implemented via `AWS Step Functions`_, are written in
the `AWS States Language`_. Like all Cirrus components, workflows require both a
``definition.yml`` file and a ``README.md`` file. Cirrus uses the Serverless
plugin `serverless-step-functions`_ to underlay the workflow definitions and
therefore the ``definition.yml`` format is more or less as documented by the
plugin.

.. _AWS Step Functions:
   https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html
.. _AWS States Language:
   https://docs.aws.amazon.com/step-functions/latest/dg/concepts-amazon-states-language.html
.. _serverless-step-functions:
   https://www.serverless.com/plugins/serverless-step-functions


Simple example
--------------

We can use the built-in ``publish-only`` workflow as a simple example of a
minimal Cirrus workflow ``definition.yml``::

    name: '#{AWS::StackName}-publish-only
    enabled: true
    definition:
      Comment: Simple example that just publishes input Collections and items
      StartAt: publish
      States:
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

The top-level keys in this example are among those supported by the
serverless-step-functions plugin, with the exception of ``enabled``, which is a
Cirrus-specific parameter that controls whether this workflow definition should
be included or not when compiling the Serverless configuration.


Workflow naming
^^^^^^^^^^^^^^^

How a workflow is named is important. Here we can see the name is
``#{AWS::StackName}-publish-only``, where ``#{AWS::StackName}`` is like
``${self:service}-${self:provider.stage}``. If our ``service`` is ``cirrus``
(the default) and our stage is, say, ``dev``, then the resulting step function
will be created with the name ``cirrus-dev-publish-only``.

The ``process`` Lambda function which handles all incoming payloads and
dispatches them to the specified workflow does so via building the specified
workflow name into a full step function ARN, which it can then execute with the
input payload. ``process`` builds step function ARNs by appending the workflow
name to the string given by
``arn:aws:states:#{AWS::Region}:#{AWS::AccountId}:stateMachine:#{AWS::StackName}-``.
As ``process`` is part of the same CloudFormation stack as workflow step
functions, the prefix string above is common to all workflows. Thus, a payload
only needs to specify a workflow name of ``publish-only``, and ``process`` can
derive the step function ARN and execute the workflow.

The important takeaway here is that for workflows to be compatible with
``process``'s ARN builder they must be named using the format
``#{AWS::StackName}-<workflow_name>``, as in the example.


Basic step function structure
-----------------------------

All workflows share some common structure within the state machine definition:

* A ``Comment`` provides a short description of the workflow
  processing/operations

* At least one ``Task`` state defined

* ``StartAt`` set to the first state in the in the step function

* At least one state with ``End: True`` representing a successful completion of
  the workflow

* A state of type ``Fail`` to which all workflow states will go on fatal error

  * Doing so necessitates that each state properly catches all error states, as
    in the example, to define a the ``Fail`` state as the next step in the event
    of an error (with some exceptions, like Batch tasks, which are part of a
    larger block of connected tasks)

* While not *strictly* required, most every workflow should use the built-in
  ``publish`` task to push all output items into S3 for canonical storage, and
  to the ``cirrus-<stage>-publish`` topic to trigger any downstream systems
  accepting output items (e.g., stac-server ingest)

Review the built-in workflows for additional examples of how to structure a more
complex workflow. Also see how to use :doc:`Batch tasks in a workflow <batch>`
for details related to that specific scenario.


Triggering workflows off one another
------------------------------------

It is not uncommon to model a processing pipeline as a series of connected
workflows. Cirrus allows several means of building such multi-stage pipelines:

* **Workflow chaining**: a pre-defined chain can be specified in an input
  process payload, where all workflows/process definitions can be generated
  ahead of time. Alternatively, steps within a workflow can add additional
  workflows to the chain in the payload being processed, where dynamic chains
  are required.

  Chaining is most useful where a single input payload will generate one or more
  outputs for one or more successive workflows. That is, chaining supports one
  or more branches, but does not have any facilities to accommodate merging
  branches together.

  See the :doc:`workflow chaining documentation <chaining>` for further details.

* **Workflow callbacks**: allow workflows to wait on one or more sub-workflows.
  Callbacks can be used to model something like chains in the form of an outer
  workflow, but can also model merging the output of multiple workflows
  together.

  Callbacks are most useful when a workflow has a dependency on the
  output items from multiple other workflow executions.

  See the :doc:`workflow callback documentation <callbacks>` for further details.

* **Publish topic subscriptions**: custom Lambda functions or other such
  listeners can be subscribed to the ``cirrus-<stage>-publish`` SNS topic to
  process workflow output items. These functions can be used as feeders,
  performaing any custom logic on output items before triggering any additional
  workflow executions required.

  While chaining and callbacks solve most common cases where workflows need to
  trigger off one another, reach for this solution when custom trigger
  conditions don't quite fit with the in-the-box approaches.


Error handling
--------------

A critical aspect of scalable workflows is the ability to tolerate and properly recover
from errors.

Some errors can occur prior to even executing a task, for example,
a Lambda.TooManyRequestsException occurs when too many Lambda requests are being made
(a quota that defaults to 1,000 and can be set to tens of thousands) or an AWSBatchException
can occur when the AWS Batch API SubmitJob quota of 50/sec is breached. In both cases, these
steps should be retried; however, they are likely to fail again if retried immediately, and
the accumulating load will result in an increased failure rate.

Because of this, it is important
to have a well-designed retry definition for each task in a workflow.

A robust retry definition looks like the following::

  IntervalSeconds: 600
  MaxDelaySeconds: 86400
  BackoffRate: 2.0
  MaxAttempts: 20
  JitterStrategy: FULL

The `JitterStrategy` setting of `FULL` indicates that the next retry should be a random
amount of time between 0 and the current delay interval. The `JitterStrategy` of `NONE`
(which is also the default if undefined) simply multiplies the current delay interval by
the `BackoffRate` parameter on each attempt. `IntervalSeconds` defines what the first
delay period should be, and then for each retry, this is multiplied by the `BackoffRate`.
Without jitter, in our example above, the retry would simply wait 600 seconds, then 1200,
then 2400, etc. With jitter, retry will wait a random amount of time between 0 and 600,
0 and 1200, 0 and 2400, etc. This randomness means that sudden spike of requests that results
in errors won't continue to create a periodic spike of errors as they all retry on exactly
the same cycle. `MaxAttempts` defines the total number of attempts to run the task, and
`MaxDelaySeconds`` puts a reasonable cap on the delay period, for example, making the
maximum delay one 1 day instead of 10 years (600 * 2 ^ 19 seconds).

Also see the AWS documentation for `error handling in Step Functions`_.

.. _error handling in Step Functions:
  https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html


Workflow best practices
-----------------------

Cirrus has a few guardrails, but generally aims to stay out of the way and
retain as much flexibility as possible to ensure arbitrary constraints cannot
get in the way and prevent any legitimate use-cases. This is particularly true
for Cirrus workflow features and AWS step functions, and this flexibility can
sometimes work against users. That said, following certain guidelines can help
ensure a Cirrus deployment remains easy to manage and administer.

Keep in mind the rules on this list are not hard and fast, but it's recommended
to understand the how and why behind a rule before deciding to break it.


AWS step function best practices
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

AWS maintains their own list of `best practices for step functions`_. Review this
list for general step function considerations.

One such example from the list is to be sure to handle lambda quota limits. The
``publish-only`` example has an ``Retry`` error handler for that purpose.

.. _best practices for step functions:
   https://docs.aws.amazon.com/step-functions/latest/dg/sfn-best-practices.html


Try to use only one input item per workflow
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

State tracking and execution management is much easier to follow if workflows
have only a single input item. While this is not always possible, trying to keep
to this guideline is worthwhile.

In some cases, using a synthetic item (an "AOI" item, a list item) that can
query for or in some other way resolve the full set of input items is a great
way to achieve this goal when needing multiple items in a workflow. It is best
to try to ensure the synthetic item will always resolve the same set of input
items.


Keep workflows short and focused
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Generally speaking, a workflow should model a single level of processing.
Conflating multiple levels of processing into a single worflow should be a good
indication that a workflow is doing too much and should be split up.

If modeling a single level of processing requires one or more set of
intermediate outputs to be persisted, that is also a good indication that the
workflow should be further broken down into a set of workflows modeling the
deriviation of each set of intermediate outputs, with one final workflow
creating the actual outputs for the processing level.

In short, it is often best to defer to more short workflows than fewer long
ones.


.. _one-output-set:

Workflows should not produce different outputs from the same set of inputs
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

See the :doc:`Cirrus Process Payload docs <../../30_payload>` for additional details on
how Cirrus's idempotency check works. Generally speaking, cirrus will use the
set of input items as a proxy for the outputs produced by a given workflow.
Don't rely on workflow/task parameters to change the set outputs, as those
settings are not referenced as part of the idempotency check.

This also leads into the next best practice...


Make workflows specific, not flexible
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

It is tempting to make workflows as flexible as possible, having them use
parameters in the process definition to control all sorts of dynamic behavior.
While certain types of dynamism can be advantageous (picking resource
requirements for a batch job depending on input data properties, for example),
generally dynamism in workflows is best avoided, for a few reasons:

^ Dynamism within a workflow means one cannot simply assume different
  executions of the same workflow did similar things. This makes
  troubleshooting harder and raises the cognitive load of pipeline management.
^ Dynamic workflows can lead to needing to run the workflow multiple times to
  create different sets of outputs. See :ref:`above <one-output-set>`.

In other words, restricting dynamic parameters to those that do not affect the
type/contents of the output items is best.


Don't use workflows for side effects
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Given that workflows are intended to be functional processing units that
transform a given input(s) into a fixed set of outputs, using workflows for side
effects is a Cirrus anti-pattern. If needing to trigger some action for every
input payload--already processed, in processing, or brand new--reach for a
different event-based solution.
