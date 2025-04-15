Cirrus Components
=================

Cirrus features several component types, which each represent a specific role
within the Cirrus architecture.

These primary types of Cirrus components are:

* lambda functions: AWS Lambda functions used to manage payload flow into and out of cirrus, and accurately update state
* tasks: a unit of processing that can be executed on its own or composed together into a workflow.
* workflows: The 'pipe' in 'pipeline.'  Workflows are what transforms input into output using process definition blocks from input payloads and executed in a AWS Step Function.

Previously Cirrus was based on the `Serverless`_ framework but has been moved to a Terraform deployment.  These Terraform definitions can be found in the `Cirrus module`_ of the open source Filmdrop repository.  This module represents a fully realized Cirrus deployment that will work out of the box when deployed using Terraform.  Once you have cloned the repository you can make any changes to your cirrus deployment as your needs require.

The Cirrus infrastructure laid out in that module is a quick and easy way to get a Cirrus deployment up and running in your own AWS account.

.. toctree::
   :maxdepth: 2
   :caption: Component documentation:

   components/tasks/index
   components/workflows/index
   components/functions/index

.. _Cirrus module: https://github.com/Element84/filmdrop-aws-tf-modules/tree/main/modules/cirrus
.. _Serverless: https://www.serverless.com/
