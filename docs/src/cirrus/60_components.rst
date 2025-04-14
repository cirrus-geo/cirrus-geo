Cirrus Components
=================

Cirrus features several component types, which each represent a specific role
within the Cirrus architecture.

Components are defined in a terraform deployment, an example of which can be found here https://github.com/Element84/filmdrop-aws-tf-modules/tree/main/modules/cirrus

The cirrus infrastructure laid out in that module is a quick and easy way to get a cirrus deployment up and running in your own AWS account.

Each component types has in-depth documentation detailing functionality, how-to use. :doc:`Lambda-based
components <components/lambdas>`.

.. toctree::
   :maxdepth: 2
   :caption: Component documentation:

   components/lambdas
   components/tasks/index
   components/workflows/index
