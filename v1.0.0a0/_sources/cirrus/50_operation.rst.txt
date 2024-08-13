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

One of the most common actions to to re-run failed tasks. For example, it it common when
running the task to discover code bugs that cause the task to fail, fix them, and then want
to re-run the task.

The can be done with the `feed-rerun` feeder lambda. This should be invoked with a JSON body
like::

  {
    "collections": "roda-sentinel-2-c1-l2a",
    "workflow": "sentinel-2-c1-l2a-to-stac",
    "state": "FAILED",
    "error_begins_with": "Exception: Unable to get error log",
    "limit": 1000,
    "since": "1d"
  }

The fields `collections` and `workflow` are mandatory. The `state` indicates the state that items
in the the state database should have to be re-run, which will typically be `FAILED`. The
field `error_begins_with` can restrict the items within those that are `FAILED` to only those
where the error message matches, e.g., you had many scenes fail with the same bug (now fixed)
and only want to re-run those. If there are many items that match, the `limit` can be used to
only run a subset of these. If there are more than 20,000, this should be set so that the
item can be retrieved and then rerun with the 15 minute lambda time limit. The `since` field
takes an integer and then a value of 'd' for days, 'h' for hours, or 'm' for minutes and
only runs items that were last updated in the state database within that time period.


Using the stac-api feeder
-------------------------
