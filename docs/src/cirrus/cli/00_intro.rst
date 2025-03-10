Cirrus CLI management Tool - CLIrrus
==========================

Introduction
------------
Cirrus itself is `STAC`_-based geospatial processing pipeline platform deployed on AWS and the pieces of a Cirrus deployment like the lambdas, SQS, S3 buckets and other can be managed and interacted with using common AWS management tools, either from the AWS GUI or AWS CLI.  However the nature of a Cirrus deployment can make direct management via AWS tools difficult to do things like batch reruns, manage deployments, individual invokations, and more.  There can be multiple cirrus deployments, and Cirrus infrastructure like SQS queues, S3 buckets, and lambdas may co-exist in an AWS account with non Cirrus resources.

What Is CLIrrus?
----------------
To ease the management of a cirrus deployment, the cirrus-geo library comes out of the box with a command line tool (CLIrrus!) designed to streamline the developer experience when using and managing a Cirrus deployment.

CLIrrus is a python CLI tool built using the `click`_ library with commmands specific to Cirrus.  Example use cases would be to list all available cirrus deployments, list lambdas in a given deployment, and even directly trigger a workflow with an input Payload by sending the payload directly to the SQS queue monitored by the Process lambda.

How To Use CLIrrus?
-------------------
Get quick steps are required to set up CLIrrus for use.

1. Install
2. Authenticatie
3. Run commands

Quick Start
-----------
If you understand the broader background and structure of Cirrus, cirrus deployments and the cirrus CLI tool and you want to jump right into using the CLI tool here is what an example workflow might look like:

1. Install requirements
```
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```
2. Authenticate
```
aws sso login --profile your-config-profile-here
```
3. Use CLIrrus
```
cirrus mgmt deployment-name-here list-lambdas
```
If your cirrus resources are in a different region from the account sso region you can use a region flag
```
cirrus --region us-west-2 mgmt deployment-name-here list-lambdas
```

And thats it!  If you would like more in depth explanations on how to use the tool, please proceed.




The tool is accessed immediatel

How to install?
---------------
Run the following commands from the project root to install all related tools for the `cirrus-geo` library.  This installation of project requirements will also install the necessary requirements for the cirrus CLI management tool
```
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt requirements.dev.txt
```

Once the libraries are installed, you can move onto authentication.





MOVE TO AUTH DOCS




Install reqs in virtual env to gain access to click lib functionality

How to perform auth?
Need to have the aws CLI installed as the mgmnt tool interacts directly with AWS infrastructure resources like step functins, lambdas, and parameter stored

Run aws sso sigin to refresh creds and ensure you are calling to the correct AWS environment in your AWS org


How deployments Configs

.. _STAC: https://stacspec.org/
