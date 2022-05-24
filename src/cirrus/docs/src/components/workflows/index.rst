Workflows
=========

Cirrus workflows are the component that puts the "pipe" in "pipeline".
Workflows model a transformation of an input item or set of input items with a
process definition into one or more output items via processing from one or
more tasks.

Cirrus also provides several mechanisms for modeling workflow dependencies.

The :doc:`state database <../../70_statedb>` tracks the state of items processed at
the workflow level.


.. toctree::
   :maxdepth: 2
   :caption: Workflow topics:

   definitions
   batch
   chaining
   callbacks
