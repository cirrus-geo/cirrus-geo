Functions
=========

The ``function`` component type is mainly used by the Cirrus built-ins required
to implement the core Cirrus functionality. Examples include the ``process``
lambda function, which processes all incoming Cirrus Process Payloads and
dispatches them to their specified workflows, or the ``update-state`` lambda
function that updates the :doc:`state database <../70_statedb>` on workflow
completion events.

In typical use, most Cirrus projects will not require any additional
function-type components. However, they can be occasionally be useful for
lambda utility functions required to manage a given deployment.

As a component with a Lambda base, the :doc:`Lambda-based components <lambdas>`
documentation contains relevant information for this and other Lambda
components.
