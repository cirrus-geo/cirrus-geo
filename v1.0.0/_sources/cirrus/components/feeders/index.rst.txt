Feeders
=======

Conceptually, a feeder is anything that generates a :doc:`Cirrus Process
Payload <../30_payload>` and queues it for processing.

In practice this could be anything from a user manually building a JSON and
pasting it into the AWS console, an AWS Lambda function, or any other process
that turns external events into process payloads and publishes them to the
Cirrus process topic.

Cirrus does not include out-of-the-box feeders.  Feeder design and implementation are left to users to build feeders that meet project needs.

Lambda, Batch, Local?
---------------------

Anatomy of a Feeder
-------------------

Process definition
^^^^^^^^^^^^^^^^^^

Creating new feeder
-------------------
