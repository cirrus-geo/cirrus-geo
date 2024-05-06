Workflow chaining
=================

Workflow chaining is a mechanism to allow multiple workflow executions to be
chained together in a declarative fashion, such that the output of one becomes
the inputs of the next. Chaining is implemented as an extension to the Cirrus
Process Payload format via support for an array of process definitions under the
payload ``process`` key, where each element in that ``process`` array represents
a link in the chain. The payload for the simple case of two chained workflows
would have a ``process`` array something like this::

    process = [
        { <workflow 1 definition> },
        { <workflow 2 definition> }
    ]

This example models a simple chain:

.. mermaid::

   flowchart LR
     1(Workflow 1)
     2(Workflow 2)
     1 --> 2

In this case, the Cirrus Process Payload output from ``workflow 1`` is passed as
the input to ``workflow 2`` after

* popping the ``workflow 1`` process definition from the array.
* deleting the payload ``id`` (as the ``id`` necessarily has to be different for
  the ``workflow 2`` execution).

Each step in the workflow chain additionally supports a nested array, to model
branching within the chain. For example, the following would branch into two
separate workflow executions after the end of ``workflow 1``::

    process = [
        { <workflow 1 definition> },
        [{ <workflow 2a definition> }, { <workflow 2b definition> }],
        { <workflow 3 definition> }
    ]

This example would result in an execution chain that looks like this:

.. mermaid::

   flowchart LR
     1(Workflow 1)
     2a(Workflow 2a)
     2b(Workflow 2b)
     3a(Workflow 3)
     3b(Workflow 3)
     1  --> 2a
     1  --> 2b
     2a --> 3a
     2b --> 3b

Note that chaining alone can effectively model one-to-one and one-to-many
dependency relationships. If needing to model many-to-one or many-to-many
relationships, see :doc:`workflow callbacks <callbacks>` for an effective way
to consolidate the outputs of multiple workflows together.


Filtering output items
----------------------

In cases where a successive workflow in a chain does not need all items produced
by an multi-output-item proceeding workflow, chaining supports an output item
filter via a `JSONPath`_ filter expression. To set such a filter, specify it in
the successive workflow's process definition using the `chain_filter` key. For
example, if we only wanted items with an ``id`` starting with ``SWE`` that had a
``confidence`` property greater than 80, we could do something like this::

    process = [
        { <workflow 1 definition> },
        {
            <workflow 2 definition>,
            "chain_filter": "@.id =~ 'SWE*' & @.properties.confidence > 80"
        }
    ]

The ``chain_filter`` string is specifically a JSONPath filter expression string
to apply to the output payload features. In other words, the above filter
expression example actually results in the following JSONPath query applied
against the JSON ``workflow 1`` output payload::

    $.features[?(@.id =~ 'SWE*' & @.properties.confidence > 80)]

.. _JSONPath: https://goessner.net/articles/JsonPath/index.html
