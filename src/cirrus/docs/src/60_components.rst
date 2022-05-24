Cirrus Components
=================

Cirrus features several component types, which each represent a specific role
within the Cirrus architecture.

A single component is made up of a collection of files, minimally a
``definition.yml`` file containing the component configuration, and a
``README.md`` file outlining the component usage and any other necessary
documentation for the component. Additional required files vary per component
type. All the files for a given component are stored in a single directory named for the component instance::

    <component_name>/
        definition.yml
        README.md
        ...

Within a Cirrus project directory, components are organized in subdirectories
named for their respective component types, like so::

    <project_dir>/
        feeders/
            feeder1/
            feeder2/
        functions/
        tasks/
            atask/
        workflows/
            aworkflow/

Each component types has in-depth documentation detailing any supported files
and the ``definition.yml`` format. Some components share a common set of
required files and configuration format, such as all :doc:`Lambda-based
components <components/lambdas>`.

.. toctree::
   :maxdepth: 2
   :caption: Component documentation:

   components/lambdas
   components/feeders
   components/tasks/index
   components/workflows/index
   components/functions
