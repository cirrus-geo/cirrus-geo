Getting started with Cirrus
===========================

What is Cirrus?
---------------

Cirrus is a `STAC`_-based geospatial processing pipeline built using a serverless
and scalable architecture. Cirrus can scale from tiny workloads of tens of items
to massive workloads of millions of items in both a cost-efficient and
performance-efficient manner, regardless if your pipeline processing takes
seconds, hours, or longer.

Cirrus is made up of `cirrus-geo`_, a cli-based project management and deploy tool, as
well as `cirrus-lib`_, a Python library providing a number of useful
abstractions solving common needs for users writing their own Cirrus components.

.. _STAC: https://stacspec.org/
.. _cirrus-geo: https://cirrus-geo.github.com/cirrus-geo
.. _cirrus-lib: https://cirrus-geo.github.com/cirrus-lib


Why Cirrus?
-----------


Concepts
--------

STAC-based workflows
^^^^^^^^^^^^^^^^^^^^

A key principal of Cirrus is the use of the `STAC`_ metadata specification as a
central tenant of the :doc:`Cirrus Process Payload <30_payload>` format. In this
way Cirrus encourages a highly-interoperable, metadata-first focus for both
pipeline operators and end-users alike.

Cirrus pipelines are, ideally, STAC-in and STAC-out, ensuring compatibility with
the full range of tooling and services available in the STAC ecosystem. Though
opinionated in this respect, Cirrus remains flexible to accommodate varied
use-cases and data sources, such that input format requirements can be relaxed as
needed for a given workflow.


Cirrus Components
^^^^^^^^^^^^^^^^^

Cirrus is organized into reusable blocks called :doc:`Components
<60_components>`, which can be broken down into three main types:

* :doc:`Feeders <components/feeders>`: take arbitrary input in and create a
  Cirrus Process Payload, which is enqueue for processing
* :doc:`Tasks <components/tasks/index>`: the basic unit of work in a Workflow, uses a
  Cirrus Process Payload for both input and output
* :doc:`Workflows <components/workflows/index>`: a set of Tasks implementing a
  processing pipeline to transform a given input into one or more output STAC
  items

An additional component type is that of a :doc:`Function
<components/functions>`, though they are less commonly extended by end users.



Horizontal and vertical scaling
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Cirrus can scale both horizontally and vertically to match the requirements of
diverse workloads.

Cirrus supports scaling workflow execution capacity as-needed without requiring
expensive capacity reservations to support peak demands. This scaling can
accommodate anything from highly intermittent one-off executions to massively
parallel processing across hundreds of thousands of simultaneous workflow
executions (or more).

Vertical scaling support also allow compute resources to matched to different
workloads/requirements within a workflow execution. In other words, executions
are not tied to a specific instance for their duration, but can instead utilize
optimal instance sizes/types on a per-task basis.


Relationship with stac-server
-----------------------------

Cirrus Workflows create STAC items, which are stored in S3 for persistence and
can be published to `stac-server`_ (or any other STAC API) for indexing/search.
In other words, Cirrus generates the data, stac-server makes it easily
accessible to end-users and the whole world of STAC tooling.

.. _stac-server: https://github.com/stac-utils/stac-server


Example use cases
-----------------


AWS services used
-----------------

Cirrus is built on top of a number of AWS services that allow its serverless and
scalable architecture, including:

* Lambda: underlays tasks, feeders, and functions
* Batch: supports longer runtimes and/or custom resource requirements for
  feeders and tasks
* SNS: messages to multiple subscribers
* SQS: message queuing for reliability
* DynamoDB: State-tracking database
* Step Functions: multi-step functions underlying workflows
* ECR: image hosting for batch and lambda containers
* IAM: function roles and associated permissions/access policies
* S3: persistent storage for input payloads and generated items and their assets
* CloudFormation: infrastructure-as-code and deployment automation
* EventBridge: trigger processing on specific events, like workflow completion


Where to go next?
-----------------

New Cirrus users may want to progress through the Cirrus documentation
following different paths, depending on their role. We've broken down a few
tracks for key Cirrus user types: work through the list of docs for your role
in the order provided, before branching out to the rest of the docs as
necessary.


Infrastructure Engineers
^^^^^^^^^^^^^^^^^^^^^^^^

*Those that are deploying Cirrus and managing the Cirrus infrastructure.*


Framework Users
^^^^^^^^^^^^^^^

*Those that are configuring, operating, and monitoring pipeline workflows.*




Algorithm Developers
^^^^^^^^^^^^^^^^^^^^

*Those writing code to be run as Cirrus tasks within workflows.*

* :doc:`Components <60_components>`
* :doc:`Tasks <components/tasks/index>`
* :doc:`Cirrus Process Payload format <30_payload>`
* ``cirrus-lib`` documentation
