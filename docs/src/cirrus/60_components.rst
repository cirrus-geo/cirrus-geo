Cirrus Components
=================

Cirrus features several component types, which each represent a specific role
within the Cirrus architecture.

These primary types of Cirrus components are:
- lambda functions
- tasks
- workflows

Previously Cirrus was based on the `Serverless`_ framework but has been moved to a Terraform deployment.

These Terrafrm definitions can be found in the `Cirrus module`_ of the open source Filmdrop repository.  This module represents a fully realized Cirrus deployment that will work out of the box when deployed with Terraform.  Once you have cloned the repository you can make any changes to your cirrus deployment as your needs require.

The Cirrus infrastructure laid out in that module is a quick and easy way to get a Cirrus deployment up and running in your own AWS account.

.. toctree::
   :maxdepth: 2
   :caption: Component documentation:

   components/functions/index
   components/tasks/index
   components/workflows/index

.. _Cirrus module: https://github.com/Element84/filmdrop-aws-tf-modules/tree/main/modules/cirrus
.. _Serverless: https://www.serverless.com/
