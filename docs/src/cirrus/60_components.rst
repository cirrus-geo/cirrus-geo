Cirrus Components
=================

Cirrus features several component types, which each represent a specific role
within the Cirrus architecture.

These primary types of Cirrus components are:

* lambda functions: AWS Lambda functions used to manage payload flow into and out of cirrus, and manage state updates
* tasks: a unit of processing that can be executed on its own or composed together into a workflow.
* workflows: The 'pipe' in 'pipeline.'  Workflows are what transforms input into output using process definition blocks from input payloads and executed in an AWS Step Function.

There is one more component type and while not explicitly instantiated by the Terraform that generates the Cirrus components, is essential to a cirrus deployment - `feeders`

* feeders: Conceptually, anything that generates a :doc:`Cirrus Process Payload <../30_payload>` and queues it for processing. In practice this is open ended and could be anything from a user pasting JSON into the AWS console to an automated process that turns external events into process payloads and publishes them to the Cirrus process topic,

Previously Cirrus was based on the `Serverless`_ framework but has been changed to a Terraform deployment framework.  These Terraform definitions can be found in the `Cirrus module`_ of the open source Filmdrop repository.  This module represents a fully realized Cirrus deployment that can be deployed and built out of the box when deployed using Terraform.  Once you have cloned the repository you can make any changes to your cirrus deployment as your needs require prior to deployment.

Additonal documentation on each compoent type is available.

.. toctree::
   :maxdepth: 2
   :caption: Component documentation:

   components/tasks/index
   components/workflows/index
   components/functions/index

.. _Cirrus module: https://github.com/Element84/filmdrop-aws-tf-modules/tree/main/modules/cirrus
.. _Serverless: https://www.serverless.com/
