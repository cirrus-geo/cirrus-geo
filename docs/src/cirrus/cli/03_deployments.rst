CLIrrus and Cirrus deployments
==============================

CLIrrus is designed around interacting with a different cirrus deployments.
Many of the commands are focused on interacting with a specific cirrus
'deployment', like invoking a specific workflow in a specific deployment.  A
'cirrus deployment' can be considered the collection of related AWS resources,
while for CLIrrus, a 'deployment' is represented as a collection of essential
environment variables that are necessary to interact with the correct AWS
resources for a deployment, like relevant ARNs or SQS queue URLs.  The
information for connecting to the correct rsources is stored in the `AWS
Parameter Store`_

Deployments and Parameter Store
-------------------------------

As previously mentined, using CLIrrus requires having the various information
necessary to make AWS API calls.  This information takes the form of environment
variables that are stored in the AWS Parameter Store.  For example, the Process
lambda requires the "CIRRUS_PAYLOAD_BUCKET" environment variable to know what
bucket to dump payloads into for storage.

Parameter Store
---------------

The parameter store has a hierarchical storage system centered around the use of
"/". More information on parameter hierachies can be found on the `AWS parameter store documentation`_

CLIrrus utilizes the parameter store to store these critical environment variables for different deployments.  When you run a command on a specific named cirrus deployment CLIrrus first goes to parameter store to retreive the environment variables for that cirrus deployments.

A pointer system is used to identify the parameter store prefix for a given deployment to ensure that we can search and retrieve only the enviroment variables for a given deployment without having to parse a large amount of returned parameters.  Using the pointer CLIrrus can then retrieve the related environment variables.

These environment variables are automatically created in the parameter store by the terraform that also deploys cirrus resources.

.. _AWS Parameter Store: https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html
.. _AWS Parameter store documentation: https://docs.aws.amazon.com/systems-manager/latest/userguide/sysman-paramstore-hierarchies.html
