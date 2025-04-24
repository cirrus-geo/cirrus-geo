Basic Operation
===============

Process definition
------------------

Process definition
------------------

Workflow
^^^^^^^^

upload_options
^^^^^^^^^^^^^^

Output collections
^^^^^^^^^^^^^^^^^^

Task parameters
^^^^^^^^^^^^^^^

Managing Secrets for Bucket access
----------------------------------

Submit a job for processing
---------------------------

Check statedb
-------------

Go to workflow (Step Function execution)
----------------------------------------

Inspect output STAC Items
-------------------------

Rerun tasks
-----------

One of the most common actions to to re-run failed tasks. For example, it it
common when running the task to discover code bugs that cause the task to fail,
fix them, and then want to re-run the task.

This can be done with the ``get-payloads`` CLIrrus command. This command offers
a way to retrieve payloads in bulk based on user supplied query parameters.
The output of ``get-payloads`` can then be passed into the ``process`` command
to rerun the tasks that meet your conditions.  The ``--rerun`` flag can be
passed to ``get-payloads`` to add the ``.process.replace: true`` parameter.

Adding this parameter when queuing a payload will result in the payload being
rerun if the payload is in the following states in the StateDB: ``COMPLETED``,
``FAILED``, ``ABORTED``, or ``CLAIMED``.  Checks are in place so that a state of
``PROCESSING`` will result in the payload being skipped.

like::

  cirrus manage deployment-name get-payloads --collectons-workflow "sar-test_workflow" --state "FAILED" --rerun | xargs -0 -L 1 echo | cirrus manage deployment-name process

Under the hood CLIrrus searches the AWS DynamoDB state database for records
matching the query parameters.  Using these state database records, the
original payloads are retrieved from the Cirrus deployment S3 bucket.
The ``--rerun`` flag adds a flag to the process block of the payload.  These
payloads are returned as new line delimited JSONs for easier stream
processing.

The available query parameters are:

* ``collections-workflow`` (string): collections workflow field in StateDB
* ``since`` (string): takes an integer and then a value of 'd' for days, 'h' for
  hours, or 'm' for minutes and only runs items that were last updated in the
  state database within that time period.  e.g. "10 h" looks back 10 hours.
* ``limit`` (int): limit how many records are returned from stateDB query
* ``error-prefix`` (string): a string prefix in an error string.  Useful if
  multiple records failed as a result of the same bug.
* ``state`` (string): the state of the record.  Must be one of the following:
  ``PROCESSING``, ``COMPLETED``, ``FAILED``, ``INVALID``, ``ABORTED``
