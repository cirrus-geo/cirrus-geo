Cirrus CLI management Tool - CLIrrus
====================================

Introduction
------------
Cirrus itself is `STAC`_-based geospatial processing pipeline platform deployed
on AWS and the pieces of a Cirrus deployment like the lambdas, SQS, S3 buckets
and other can be managed and interacted with using common AWS management tools,
either from the AWS GUI or AWS CLI.  However the nature of a Cirrus deployment
can make direct management via AWS tools difficult to do things like batch
reruns, manage deployments, individual invokations, and more.  There can be
multiple cirrus deployments, and Cirrus infrastructure like SQS queues, S3
buckets, and lambdas may co-exist in an AWS account with non Cirrus resources.

What Is CLIrrus?
----------------
To ease the management of a cirrus deployment, the cirrus-geo library comes out
of the box with a command line tool (CLIrrus!) designed to streamline the
developer experience when using and managing a Cirrus deployment.

CLIrrus is a python CLI tool built using the `click`_ library with commmands
specific to Cirrus.  Example use cases would be to list all available cirrus
deployments, list lambdas in a given deployment, and even directly trigger a
workflow with an input Payload by sending the payload directly to the SQS queue
monitored by the Process lambda.

How To Use CLIrrus?
-------------------
A few simple steps are all it takes to set up CLIrrus for use.

1. Install
2. Authenticatie
3. Run commands

CLIrrus Quick Start
-------------------
If you understand the broader background and structure of Cirrus, cirrus
deployments and the cirrus CLI tool and you want to jump right into using the
CLI tool here is what an example workflow might look like:

1. Install requirements

.. code-block:: bash

    python3.12 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements-dev.txt -r requirements-cli.txt -r requirements.txt

2. Authenticate

.. code-block:: bash

    aws sso login --profile your-config-profile-here

3. Use CLIrrus

.. code-block:: bash

    cirrus mgmt deployment-name-here list-lambdas

If your cirrus resources are in a different region from the account sso region
you can use a region flag

.. code-block:: bash

    cirrus --region us-west-2 mgmt deployment-name-here list-lambdas


And thats it!  If you would like more in depth explanations on how to use the
tool, please proceed.

.. _click: https://click.palletsprojects.com/en/stable/
.. _STAC: https://stacspec.org/
