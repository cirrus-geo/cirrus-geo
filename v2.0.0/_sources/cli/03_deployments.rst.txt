CLIrrus and Cirrus Deployments
==============================

CLIrrus is designed around interacting with a different cirrus deployments. Many
of the commands are focused on interacting with a specific cirrus 'deployment',
like invoking a specific workflow to run in a specific deployment.  A 'cirrus
deployment' can be considered to be the collection of related AWS resources for
a single cirrus deployment.   For CLIrrus, a 'deployment' is represented as a
collection of essential environment variables that are necessary to interact
with the correct AWS resources for a deployment, like relevant ARNs or SQS queue
URLs.  These environment variables for connecting to the correct resources are
stored in the `AWS Parameter Store`_

Deployments and Parameter Store
-------------------------------

As previously mentined, using CLIrrus requires knowing deployment specific
environment variables to make AWS API calls to the correct resources.  These
environment variables are stored in the AWS Parameter Store.  For example, the
``process`` lambda requires the "CIRRUS_PAYLOAD_BUCKET" environment variable to
know what bucket to dump payloads into for storage.  When running commands on a
specific deployment CLIrrus will automatically retrieve these environment
variables based on the deployment name you pass.

Parameter Store
---------------

The parameter store has a hierarchical storage system centered around the use of
``/`` in parameter names. More information on parameter hierachies can be found
on the `AWS parameter store documentation`_.  This hierarchial organization is
used to ensure deployments can be found under common prefixes, and enables for
easy use if you wish to directly search the parameter store yourself.

CLIrrus utilizes the parameter store to store these critical environment
variables for different deployments.  When you run a command on a specific
named cirrus deployment CLIrrus first retrieves the environmental variables for
that cirrus deployment from the parameter store and then uses them to execute
commands like ``list-lambdas``

A pointer system is used to identify the parameter store prefix for a given
deployment to ensure that we can search and retrieve only the enviroment
variables for a given deployment without having to parse a large amount of
returned parameters.  Using this pointer CLIrrus can then retrieve the related
environment variables.

.. _AWS Parameter Store: https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html
.. _AWS Parameter store documentation: https://docs.aws.amazon.com/systems-manager/latest/userguide/sysman-paramstore-hierarchies.html
