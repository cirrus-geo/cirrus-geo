Tasks
=====

.. toctree::
   :hidden:
   :maxdepth: 2

   batch


Tasks in Cirrus implement a unit of processing, to be composed together into a
:doc:`Workflow <../workflows/index>`. Tasks are expected to support both input and
output formatted as a :doc:`Cirrus Process Payload <../../30_payload>`. As part of its
processing, a task can make any requisite modifications to its input payload
and/or derive any output assets, pushing them to the canonical storage location
in S3.

In other other words, to implement custom processing routines for a pipeline,
use a task. The best tasks are modular, simple, focused, and composable. Most
projects end up with more custom tasks than other component types, so it pays
to be familiar with the tasks ins and outs.

Tasks can make use of AWS Lambda and/or AWS Batch for execution. Lambda tasks
are simpler to manage and quicker to start up, but the Lambda runtime
constraints can be prohibitive or untenable for some task workloads. In those
cases, Batch allows for extended runtimes, greater resource limits, and
specialized instance types.

In a Cirrus project, tasks are stored inside the ``tasks/`` directory, each in a
subdirectory named for the task. Each task requires a ``definition.yml`` file with
the task's configuration, and a ``README.md`` file documenting the task's usage.


Anatomy of a task
-----------------

Generally speaking, every task should do a few key things:

* Take an input Cirrus Process Payload

  * In the case of Batch tasks and/or large payloads, tasks should support
    receiving a ``url`` input parameter pointing to a payload object in S3

* Instantiate a ``cirrus.lib.ProcessPayload`` instance from the input payload
  JSON
* Download all required assets from the items in the input payload
* Perform any asset metadata manipulation and/or derived product processing
* Update/replace payload items based on task outputs
* Upload any output assets to S3 for persistence
* Return the output Cirrus Process Payload

  * In the case of Batch tasks and/or large payloads, tasks should support
    uploading the output payload to S3 and returning an output ``url`` parameter
    pointing to that payload object in S3

Certain tasks may deviate from this pattern, but the vast majoity of tasks will
follow this flow. ``cirrus-lib`` provides convenince classes/methods to help with
these common needs.


Lambda tasks
^^^^^^^^^^^^

Lambda tasks use the `AWS Lambda`_ runtime to power executions. Lambda has the
advantage of quick startup and easy management, but has many restrictions like
short timeouts and significant resource limits.

Lambda-only tasks follow the specifications outlined in the :doc:`Lambda-based
components <../lambdas>` documentation. Refer there for specifics on what files
are requried for Lambda tasks and how to structure the ``definition.yml`` file.

.. _AWS Lambda: https://docs.aws.amazon.com/lambda/latest/dg/welcome.html


Batch tasks
^^^^^^^^^^^

Batch tasks use `AWS Batch`_ semantics to define `jobs`_ that execute within a
`compute environment`_ as determined by the `job queue`_ to which the job is
submitted.  Batch compute environments can make use of `Fargate`_ or `EC2`_ to
run jobs, allowing significantly more control over the execution environment
than Lambda allows, as well as much greater limits on resources.

Batch tasks are inherently just an abstraction around a set of CloudFormation
resources, minimally just a Batch `job definition`_, but commonly also the job
queue, compute environment, and any other requried resources.

For more infomation see the :doc:`Batch tasks <batch>` documentation.

.. _AWS Batch: https://docs.aws.amazon.com/batch/latest/userguide/what-is-batch.html
.. _jobs: https://docs.aws.amazon.com/batch/latest/userguide/jobs.html
.. _compute environment: https://docs.aws.amazon.com/batch/latest/userguide/compute_environments.html
.. _job queue: https://docs.aws.amazon.com/batch/latest/userguide/job_queues.html
.. _Fargate: https://docs.aws.amazon.com/eks/latest/userguide/fargate.html
.. _EC2: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts.html
.. _job definition: https://docs.aws.amazon.com/batch/latest/userguide/job_definitions.html


Lambda vs Batch
---------------

When to chose either
^^^^^^^^^^^^^^^^^^^^

* can be run as a Docker image


When to chose Lambda
^^^^^^^^^^^^^^^^^^^^

* short runtime, with a maximum of 15 minutes
* single vCPU is acceptable
* under 10GB of memory
* small code size / few dependencies
* need code to live in the cirrus project repository


When to chose Batch
^^^^^^^^^^^^^^^^^^^

* runtime always longer than 5 minutes
* larger package size / many dependencies
* need multiple vCPUs, more than 10GB memory, or the ability to more precisely specify a vCPU-to-memory ratio
* easier to manage code as separate container images
* need more than 10GB storage
* need special hardware resources (e.g., GPU)


..
    Omitting discussion of Batch Lambdas for the moment

    Or maybe both?
    ^^^^^^^^^^^^^^

    Sometimes both Lambda and Batch can fit the task requirements, depending on
    input. Other times, avoiding the overhead of managing/deploying a Batch
    container image makes Lambda attractive, but runtime constraints like max
    execution time mean that only Batch is viable.

    In each of these cases, one can specify a task as *both* Lambda and Batch,
    using the Cirrus Batch Lambda runner container to run the packaged Lambda code.
    Doing this allows the user to choose which execution mechanism is most
    appropriate in a given context. This could be parameterized in a workflow based
    on the input (like a ``batch`` flag in the task parameters), or on logic in an
    separate input inspection Lambda. Some workflows could always run the Lambda
    version of a task, and others the batch version. Or maybe the Batch version is
    the only ever actually used, taking advantage of the Lambda packaging support
    solely to make it easier to keep task code inside the Cirrus project.

    Using the Batch Lambda runner
    *****************************

    See the `cirrus-task-image`_ repo for more information.

    .. _cirrus-task-image: https://github.com/cirrus-geo/cirrus-task-images


Creating a new task
-------------------

Creating a new task involves creating a directory with the task name under
``tasks/`` and the required files inside it. Getting everything setup with all
the requisite boiler-plate takes some minor work. The ``cirrus`` cli includes
a convenience function to automate getting started with a new task.

Lambda-only
^^^^^^^^^^^

To create a lambda-only task, simply create a new task with a description and
the option ``--type lambda``::

    ❯ cirrus create task --has-lambda --no-batch <TaskName> "<task description>"

This command will create the task directory and required files from a minimal
template. The new task will obviously need to have the custom handler code
added, and the ``definition.yml`` configuration will need to be validated to
ensure it matches the task requirements. Any usage information should also be
added to the ``README.md`` file.

Batch-only
^^^^^^^^^^

To create a Batch-only task, simply create a new task with a description, but
add the ``--type batch`` option::

    ❯ cirrus create task --type batch <TaskName> "<task description>"

The task directory and required files will be created from a minimal template.
The templated Batch configuration in the ``definition.yml`` should be
considered a rough starting point, and will require fairly significant
modification for most uses. Be sure to also update the ``README.md`` file with
usage information.

Lambda and Batch
^^^^^^^^^^^^^^^^

For tasks that should support both Lambda and Batch, run the ``create``
command, this time using the options ``--type lambda`` and ``--type batch``::

    ❯ cirrus create task --type lambda --type batch <TaskName> "<task description>"

This command does the same as both of the above ``create`` command examples, so
the listed caveats of both apply here: ensure the handler code is completed,
and the batch configuration is updated to match the task requirements.

* :doc:`Conditionally Using Batch or Lambda <../workflows/batch>`

Docker Image
---------------

It is generally recommended to use a Docker image for tasks unless the task is only
intended to run in Lambda and has few dependencies, which is rarely the case with
geospatial processing.

The easiest way to do this is to create a Python class that extends stactask.task.Task
and implements the abstract method `def process(self, **kwargs: Any) -> List[Dict[str, Any]]`.
This class should be put in the file `src/task/task.py`, and can then be invoked by
Docker with directives::

  FROM public.ecr.aws/lambda/python:3.11

  # ENTRYPOINT ["/lambda-entrypoint.sh"] # set by base lambda image
  COPY src/task/task.py ${LAMBDA_TASK_ROOT}/task.py
  CMD [ "task.handler" ]

If you choose to use your own container that is not based on a standard Lambda image,
you must add the `lambda-entrypoint.sh` file to your image and set `ENTRYPOINT` explicitly.

Unfortuantely, the same Docker image cannot be used by both Batch and Lambda, as they
have slightly different requirements for the `CMD` and `ENTRYPOINT` parameters. The
solution to this is to have one base image definition that has all directives exception
`CMD` and `ENTRYPOINT`, and then create two image definitions that use the base image
but set `CMD` and `ENTRYPOINT`. For example, if we had a image that used a standard
AWS lambda image (public.ecr.aws/lambda/python:3.11), we would use these directives for
Batch and Lambda.

Batch::

  COPY src/task/task.py ${LAMBDA_TASK_ROOT}/task.py
  ENTRYPOINT []

(any prior `CMD` will be reset by the ENTRYPOINT change, and the command is set by the Batch Job Definition)

Lambda::

  COPY src/task/task.py ${LAMBDA_TASK_ROOT}/task.py
  CMD [ "task.handler" ]

(base image sets `ENTRYPOINT ["/lambda-entrypoint.sh"]`)

Thereby, an example base image that needed geospatial tools could look like this::

  FROM ghcr.io/lambgeo/lambda-gdal:3.8-python3.11 as gdal

  FROM public.ecr.aws/lambda/python:3.11

  # Bring C libs from lambgeo/lambda-gdal image
  COPY --from=gdal /opt/lib/ ${LAMBDA_TASK_ROOT}/lib/
  COPY --from=gdal /opt/include/ ${LAMBDA_TASK_ROOT}/include/
  COPY --from=gdal /opt/share/ ${LAMBDA_TASK_ROOT}/share/
  COPY --from=gdal /opt/bin/ ${LAMBDA_TASK_ROOT}/bin/

  ENV \
    GDAL_DATA=${LAMBDA_TASK_ROOT}/share/gdal \
    PROJ_LIB=${LAMBDA_TASK_ROOT}/share/proj \
    GDAL_CONFIG=${LAMBDA_TASK_ROOT}/bin/gdal-config \
    GEOS_CONFIG=${LAMBDA_TASK_ROOT}/bin/geos-config \
    PATH=${LAMBDA_TASK_ROOT}/bin:$PATH

  RUN yum update -y && \
      yum install -y libxml2-devel libxslt-devel python-devel gcc && \
      yum clean all && \
      rm -rf /var/cache/yum /var/lib/yum/history

  COPY requirements.txt ${LAMBDA_TASK_ROOT}

  RUN pip3 install --no-cache-dir -r requirements.txt

  COPY src/task/task.py ${LAMBDA_TASK_ROOT}/task.py

That could be built and tagged as the base image, and then the Lambda and/or Batch images
based on it.

Batch::

  FROM my_base_task

  ENTRYPOINT []

Lambda::

  FROM my_base_task

  CMD [ "task.handler" ]

Of course, if only one of the Batch or Lambda is needed, these commands can be combined into
a single definition.


Task parameters
---------------

Tasks can take arguments at runtime via process definition parameters. See the
:doc:`Cirrus Process Payload <../../30_payload>` docs for more information. When
authoring a task, be sure to document all supported task parameters in the
task's ``README.md``. In using an existing task, the task README can always be
view via the cli::

    ❯ cirrus show task <TaskName> readme

This will dump the ``README.md`` contents to the terminal with appropriate
markup applied.


Running tasks locally
---------------------

We are working to standardize task code and ``cirrus`` cli tooling to provide
an easy and consistent means to execute tasks locally. This feature is still
under development, so for now please consult the project or task documentation
for further information (if available).
