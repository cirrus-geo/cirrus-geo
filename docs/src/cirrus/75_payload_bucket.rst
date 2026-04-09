Payload Bucket
==============

The Cirrus payload bucket is an S3 bucket used to store workflow payloads
that are either too large to pass inline through AWS service limits or
that need to be persisted for state tracking, debugging, and retrieval
after a workflow has finished executing.

Together with the :doc:`StateDB <70_statedb>`, the payload bucket forms
the record of a Cirrus deployment's work: where the StateDB tracks
*that* an execution happened and *what state* it's in, the payload
bucket stores the actual JSON payload content associated with each
execution.

Configuration
-------------

Cirrus does not manage the payload bucket itself. The bucket is supplied
to Cirrus code through the ``CIRRUS_PAYLOAD_BUCKET`` environment
variable, and any S3 bucket that the running code has permission to read
from and write to can serve as the payload bucket. A bucket provisioned
alongside Cirrus (for example, via the reference CloudFormation in this
repository) is one common way to satisfy this, but it is not a
requirement.

All Cirrus code that reads or writes payload objects goes through the
``cirrus.lib.payload_bucket.PayloadBucket`` class, which resolves the
bucket name from ``CIRRUS_PAYLOAD_BUCKET`` at construction time. If the
variable is not set when a ``PayloadBucket`` is created,
``UndefinedPayloadBucketError`` is raised.

The root prefix under which all payload objects are organized can be
customized via the optional ``CIRRUS_PAYLOAD_ROOT_PREFIX`` environment
variable. When not set, it defaults to ``cirrus``. This allows
deployments that share a payload bucket with other systems to use a
distinct namespace, avoiding key collisions.

Because Cirrus writes all of its objects under a single top-level
prefix (see :ref:`payload-bucket-layout`), the payload bucket can also
be shared with other, unrelated content without risk of key collisions.

.. _payload-bucket-layout:

Key Organization
----------------

All objects written by Cirrus live under a configurable top-level
prefix (default ``cirrus/``, controlled by
``CIRRUS_PAYLOAD_ROOT_PREFIX``). Within that, keys are split into two
distinct namespaces based on how long the data is expected to live:

* ``<root_prefix>/tmp/`` — **ephemeral** storage for transient payloads
  that the system does not need to retain once processing has moved on.
  Objects under this prefix are expected to be cleaned up by a bucket
  lifecycle rule (see :ref:`payload-bucket-lifecycle`).
* ``<root_prefix>/executions/`` — **persistent** storage for
  per-execution input and output payloads that Cirrus uses to link
  workflow runs to their payload content.

The full layout is as follows (using the default ``cirrus`` prefix)::

    s3://<payload-bucket>/
    └── cirrus/                               # configurable via CIRRUS_PAYLOAD_ROOT_PREFIX
        ├── tmp/                              # ephemeral
        │   ├── oversized/
        │   │   └── <uuid>.json               # overflow for oversized payloads
        │   ├── batch/
        │   │   └── <payload_id>/
        │   │       └── <uuid>.json           # payloads handed to batch tasks
        │   └── invalid/
        │       └── <uuid>.json               # payloads that failed validation
        └── executions/                       # persistent
            └── <payload_id>/
                └── <execution_id>/
                    ├── input.json            # payload as received
                    └── output.json           # payload after workflow completed

The prefix values are derived from the configured root prefix and are
exposed as instance attributes on ``PayloadBucket``. They are the
single source of truth for where each type of object is written.

.. note::

   Because a Cirrus ``payload_id`` has the form
   ``<collections>/workflow-<workflow_name>/<item_ids>`` and contains
   forward slashes, objects under ``<root_prefix>/executions/`` and
   ``<root_prefix>/tmp/batch/`` fan out into multiple levels of S3
   prefixes. This is intentional: it allows listing all executions for
   a given collection, workflow, or item grouping with ordinary S3
   prefix queries.

Execution Payloads
^^^^^^^^^^^^^^^^^^

When a workflow execution is claimed by the ``process`` lambda, the
input payload is written to::

    <root_prefix>/executions/<payload_id>/<execution_id>/input.json

On successful completion, the ``update-state`` lambda writes the output
payload to the sibling key::

    <root_prefix>/executions/<payload_id>/<execution_id>/output.json

The ``<execution_id>`` component is the Step Functions execution name,
which is deterministically derived from the payload ID and the current
list of executions in the StateDB record (see
``PayloadManagers.gen_execution_arn``). Because a single ``payload_id``
may be re-run — for example on ``FAILED`` or ``ABORTED`` states, or with
``replace=True`` — multiple ``<execution_id>`` children may exist under
the same ``payload_id`` prefix, one per attempt.

This layout is what makes the payload bucket and the StateDB addressable
together: given a StateDB record, its ``payload_id`` plus the relevant
entry from its ``executions`` list uniquely identify the corresponding
``input.json`` and ``output.json`` in the bucket. The management CLI's
``get-input-payload`` and ``get-output-payload`` commands rely on
exactly this correspondence.

Oversized Payloads
^^^^^^^^^^^^^^^^^^

Cirrus passes payloads between lambdas and Step Functions as JSON, but
AWS EventBridge embeds the Step Functions input and output as escaped
strings inside its own event envelope. To stay safely below the
EventBridge event size limit, ``PayloadManager`` enforces a conservative
``MAX_PAYLOAD_LENGTH`` (120 KB) on the JSON-escaped payload length.

When a payload exceeds that limit, its contents are uploaded to::

    <root_prefix>/tmp/oversized/<uuid>.json

and replaced in-flight by a small reference object of the form
``{"url": "s3://.../<root_prefix>/tmp/oversized/<uuid>.json"}``.
Downstream code in ``cirrus.lib.utils.payload_from_s3`` transparently
re-hydrates these references when the full payload is needed again.

Because oversized payloads are only used as an overflow mechanism
during a single execution, they live under ``<root_prefix>/tmp/`` and
are expected to be cleaned up by the bucket's lifecycle rule.

Batch Payloads
^^^^^^^^^^^^^^

Tasks that are dispatched to AWS Batch cannot receive their payload
inline, so ``PayloadBucket.upload_batch_payload`` writes the payload to::

    <root_prefix>/tmp/batch/<payload_id>/<uuid>.json

The Batch task is then invoked with a reference to this key. This path
is also ephemeral and cleaned up by the lifecycle rule.

.. note::

   The key format ``<payload_id>/<uuid>.json`` (rather than simply
   ``<uuid>/input.json``) is retained for backwards compatibility with
   earlier versions of ``cirrus-lib``.

Invalid Payloads
^^^^^^^^^^^^^^^^

When a payload fails validation in a way that Cirrus wants to preserve
for later inspection, it is uploaded to::

    <root_prefix>/tmp/invalid/<uuid>.json

This is intended as short-lived diagnostic storage, not a permanent
archive of invalid inputs, which is why it lives under
``<root_prefix>/tmp/``. If long-term retention of invalid payloads is
required for a particular deployment, the recommended approach is to
ship them out to a separate bucket or archive from the handling code
rather than to alter the lifecycle of ``<root_prefix>/tmp/``.

.. _payload-bucket-lifecycle:

Lifecycle and Retention
-----------------------

Cirrus assumes a simple retention model for the payload bucket:

* Everything under ``<root_prefix>/tmp/`` is **ephemeral** and should be
  removed by a bucket lifecycle rule. The reference CloudFormation in
  this repository configures a 10-day expiration on the
  ``<root_prefix>/tmp/`` prefix (derived from the configured
  ``PayloadRootPrefix``), which is a reasonable default that gives
  oversized and batch payloads enough lifetime to survive retries,
  backfills, and manual reprocessing.
* Everything under ``<root_prefix>/executions/`` is **persistent** and
  is not expired by any Cirrus-managed rule. These objects are the
  primary mechanism for reconstructing the history of a workflow run
  after the fact; losing them will break the ``get-input-payload`` and
  ``get-output-payload`` CLI commands and make post-hoc debugging
  significantly harder.

Operators bringing their own payload bucket should configure a
lifecycle rule on ``<root_prefix>/tmp/`` that matches this expectation.
A 10-day expiration is a reasonable starting point; shortening it risks
removing objects that are still in use by in-flight retries, and
extending it past ``<root_prefix>/tmp/`` into other prefixes will
silently delete execution history.

Operators who need different retention semantics for execution payloads
— for example, cost control on very high-throughput deployments — can
add their own lifecycle rules targeting the
``<root_prefix>/executions/`` prefix, keeping in mind that any payload
whose execution record is still referenced from the StateDB will become
unreachable through the CLI once expired.

Access Patterns
---------------

The payload bucket is accessed in a small number of well-defined
places:

* ``process`` lambda — uploads execution input payloads via
  ``PayloadBucket.upload_input_payload``, and uploads oversized
  payloads via ``PayloadBucket.upload_oversize_payload`` before
  invoking Step Functions.
* ``update-state`` lambda — uploads execution output payloads via
  ``PayloadBucket.upload_output_payload`` on successful completion.
* Task code — reads oversized payloads via
  ``cirrus.lib.utils.payload_from_s3`` and, for batch tasks, fetches
  payload content from the batch prefix.
* :doc:`Management CLI <../cli/04_commands>` — reads execution input
  and output payloads via ``PayloadBucket.get_input_payload_url`` and
  ``PayloadBucket.get_output_payload_url``, which reconstruct the
  deterministic S3 URL from a ``payload_id`` and ``execution_id`` pair
  looked up in the StateDB.

No Cirrus code writes directly to the bucket without going through
``PayloadBucket``, and the prefix attributes are not intended to be
re-implemented elsewhere. Downstream code that needs to locate a
payload object by key should import the helpers from
``cirrus.lib.payload_bucket`` rather than constructing prefixes by
hand, so that any future reorganization of the layout remains a
single-file change.
