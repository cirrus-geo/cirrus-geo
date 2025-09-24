Cirrus Components
=================

Cirrus features several component types, which each represent a specific role
within the Cirrus architecture.

These primary types of Cirrus components are:

* **lambda functions**: AWS Lambda functions used to manage payload flow into and out of cirrus, and manage state updates
* **tasks**: a unit of processing that can be executed on its own or composed together into a workflow.
* **workflows**: The 'pipe' in 'pipeline.'  Workflows are what transforms input into output using process definition blocks from input payloads and executed in an AWS Step Function.

There is one more component type, that while not explicitly defined in ``cirrus-geo``, is critical to a cirrus deployment - feeders

* **feeders**: Conceptually, anything that generates a :doc:`Cirrus Payload <../30_payload>` and queues it for processing. In practice this is open ended and could be anything from a user pasting JSON into the AWS console to an automated process that turns external events into process payloads and publishes them to the Cirrus process topic.

Additonal documentation on each compoent type is available.

.. toctree::
   :maxdepth: 2
   :caption: Component documentation:

   components/tasks/index
   components/workflows/index
   components/functions/index
   components/feeders/index
