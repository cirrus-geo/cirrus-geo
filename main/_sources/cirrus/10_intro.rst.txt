Getting started with Cirrus
===========================
What is Cirrus?
---------------

Cirrus is a `STAC`_-based geospatial processing pipeline platform, built using a serverless
and scalable architecture deployed on AWS. Cirrus can scale from tiny workloads of tens of items
to massive workloads of millions of items in both a cost-efficient and
performance-efficient manner, regardless if processing takes
seconds, hours, or longer.

Cirrus consists of two primary pieces:
- `cirrus`, a CLI-based project management and deploy tool, and
- `cirrus-lib`, a Python library providing a number of useful
abstractions solving common needs for users writing their own Cirrus components.

The `cirrus` CLI is used to create a Cirrus Project that can be customized and deployed to AWS as
a running Cirrus system.

.. _STAC: https://stacspec.org/


Why Cirrus?
-----------


Concepts
--------

STAC-based workflows
^^^^^^^^^^^^^^^^^^^^

A core design aspect of Cirrus is the use of the `STAC`_ metadata specification as a
basis for the :doc:`Cirrus Process Payload <30_payload>` format. In this
way Cirrus, encourages a highly-interoperable, metadata-first approach for both
pipeline operators and end users alike.

Cirrus pipelines are, ideally, STAC-in and STAC-out, ensuring compatibility with
the full range of tooling and services available in the STAC ecosystem. Though
opinionated in this respect, Cirrus remains flexible to accommodate varied
use cases and data sources, such that input format requirements can be relaxed as
needed for a given workflow.


Cirrus Components
^^^^^^^^^^^^^^^^^

Cirrus is organized into reusable blocks called :doc:`Components
<60_components>`. There are four types of Components:

* :doc:`Feeders <components/feeders>` accept arbitrary input, and output a
  Cirrus Process Payload, which is enqueued for processing. These can be used to initiate
  processing from any source, for example, an SNS topic message indicating a new scene is
  available or an S3 Inventory of existing scenes.
* :doc:`Tasks <components/tasks/index>` are the basic unit of work in a Workflow and use a
  Cirrus Process Payload for both input and output. This is where specific processing,
  for example, transforming data to data (e.g., JPEG200 to COG), data to metadata
  (e.g., COG to STAC), or metadata to metadata (e.g., MTL to STAC).
* :doc:`Workflows <components/workflows/index>` are a composition of one or more Tasks
  implementing a processing pipeline that coordinate transforming a given input into one
  or more output STAC items
* :doc:`Functions <components/functions>` provide internal services that are used by
  Feeders, Tasks, and Workflows, and are less commonly extended by users.


Horizontal and vertical scaling
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Cirrus can scale both horizontally and vertically to match the requirements of
diverse workloads.

Cirrus supports scaling workflow execution capacity as-needed without requiring
expensive capacity reservations to support peak demands. This scaling can
accommodate anything from highly intermittent one-off executions to massively
parallel processing across hundreds of thousands of simultaneous workflow
executions.

Vertical scaling support allows compute resources to matched to different
workloads/requirements within a workflow execution. In other words, executions
are not tied to a specific instance for their duration, but can instead utilize
optimal instance sizes/types on a per-task basis.


Relationship with stac-server
-----------------------------

Cirrus Workflows create STAC items, which are stored in S3 for persistence and
can be published to `stac-server`_ (or any other STAC API) for indexing/search.
In other words, Cirrus generates the data, stac-server makes it
accessible to end-users through the robust ecosystem of STAC tooling.

.. _stac-server: https://github.com/stac-utils/stac-server


Example Earth Search use case
-----------------------------

One prominent use case of Cirrus is as the processing pipeline for `Earth Search`_.

- Landsat scenes are processed via Lambda Functions, triggered notifications from
  the USGS SNS topic.
- Sentinel-2 Collection 1 Level-2A scenes are processed via Batch, triggered by
  notifications from the ESA/Singergize SNS topic.
- Sentinel-1 GRD scenes are processed via Lambda, triggered by
  notifications from an SNS topic.
- NAIP scenes are processed using Lambda, and triggered manually
  once a year when released
- Copernicus DEM - Global and European Digital Elevation Model (COP-DEM) was
  processed with Lambda, and triggered once manually.

While triggering from SNS notifications is best practice, this is not always possible,
and there are numerous other ways to initiate ingest.  Previously, the Landsat
collection was populated by running a daily search against the LandsatLook
API and ingesting any new scenes. Similarly, the older Sentinel-2 Level-2A collection
is populated by receiving SNS messages from an older Cirrus pipeline that supported the
now-deprecated Earth Search v0 deployment.

.. _earth search: https://www.element84.com/earth-search/

AWS services used
-----------------

Cirrus is built on top of a number of AWS services that allow its serverless and
scalable architecture, including:

* Step Functions: workflow implementation
* Lambda: scalable compute for tasks, feeders, and functions
* Batch, ECS, and EC2 (spot or on-demand): supports longer runtimes and/or custom resource requirements for
  feeders and tasks
* DynamoDB: Payload state-tracking database
* SQS: message queuing for reliability
* SNS: messages to multiple subscribers
* S3: persistent storage for input payloads and generated items and their assets
* Timestream: event history
* ECR: image hosting for batch and lambda containers
* CloudFormation: infrastructure-as-code and deployment automation
* EventBridge: trigger processing on specific events, like workflow completion
* IAM: function roles and associated permissions/access policies


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
