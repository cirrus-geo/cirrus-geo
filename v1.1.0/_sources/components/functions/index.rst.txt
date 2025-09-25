Functions
=========

The ``function`` component type is mainly used by the Cirrus built-ins required
to implement the core Cirrus functionality. Examples include the ``process``
lambda function, which processes all incoming Cirrus Payloads and
dispatches them to their specified workflows, or the ``update-state`` lambda
function that updates the :doc:`state database <../../cirrus/70_statedb>` on
workflow completion events.

In typical use, most Cirrus projects will not require any additional
function-type components. However, they can be occasionally be useful for
lambda utility functions required to manage a given deployment.

The :doc:`Lambdas component documentation <../../cirrus/components/functions/index>` component
documentation contains relevant information for this and other Lambda
components.

.. toctree::
   :maxdepth: 1
   :glob:
   :titlesonly:

   api <api.md>
   process <process.md>
   update-state <update-state.md>
   post_batch <post_batch.md>
   pre_batch <pre_batch.md>
