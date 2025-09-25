CLIrrus Overview
====================

Introduction
------------
Cirrus itself is `STAC`_-based geospatial processing pipeline platform deployed
on AWS and is a constellation of associated pieces of AWS infrastructure.  The
pieces of a Cirrus deployment like the lambdas, SQS, S3 buckets and other can be
managed and interacted with using common AWS management tools like the AWS GUI
or AWS CLI.

However the nature of a Cirrus deployment can make direct
management via AWS tools difficult to do things like batch reruns, manage
deployments, individual lambda invocations, and more.  There can be multiple
cirrus deployments and Cirrus infrastructure may co-exist in an AWS account with non Cirrus resources further complicating this management.  The Cirrus CLI tool (CLIrrus) was built to simplify dealing with these issues.

What Is CLIrrus?
----------------
To ease the management of a cirrus deployment the cirrus-geo library has a
built in command line tool (CLIrrus) designed to streamline the developer
experience when using and interacting with a Cirrus deployment.

CLIrrus is a python CLI tool built using the `click`_ library with commmands
specific to Cirrus.  Example use cases would be to list all available cirrus
deployments, list lambdas in a given deployment, and even directly trigger a
workflow with an input Payload by sending the payload directly to the SQS queue
monitored by the ``process`` lambda, and more.

What if I'm using an older version of Cirrus?
---------------------------------------------

You can use the `older CLI tool`_ which is a standalone module and can be
installed via pip.

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
CLI tool here is what an example workflow might look like.  These are one way of accomplishing these steps, personal and organizatonal requirements may differ.

1. Install requirements

.. code-block:: bash

    python3.12 -m venv .venv
    source .venv/bin/activate
    pip install 'cirrus-geo[cli]>=1.0.0'

2. Authenticate (if necessary)

.. code-block:: bash

    aws sso login --profile your-config-profile-here

3. Use CLIrrus

.. code-block:: bash

    cirrus mgmt deployment-name-here list-lambdas

And thats it!  If you would like more in depth explanations on how to use the
tool, please proceed.

.. _click: https://click.palletsprojects.com/en/stable/
.. _STAC: https://stacspec.org/
.. _older CLI tool: https://pypi.org/project/cirrus-mgmt/
