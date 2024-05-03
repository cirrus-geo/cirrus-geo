Feeders
=======

Conceptually, a feeder is anything that generates a :doc:`Cirrus Process
Payload <../30_payload>` and queues it for processing. In practice this could be
anything from a user hand-rolling JSON and pasting it into the AWS console, to
an automated process that turns external events into process payloads and
publishes them to the Cirrus process topic.

Within a Cirrus project instance, however, the term ``feeder`` refers
specifically to an AWS Lambda function that takes arbitrary input in, generates
one or more Cirrus Process Payloads, and publishes them to the Cirrus process
SNS topic.

As a component with a Lambda base, the :doc:`Lambda-based components <lambdas>`
documentation contains relevant information for this and other Lambda
components.

Lambda, Batch, Local?
---------------------

Anatomy of a Feeder
-------------------

Process definition
^^^^^^^^^^^^^^^^^^

Creating new feeder
-------------------

Spawning Batch feeders with a Lambda feeder
-------------------------------------------
