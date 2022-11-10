Configuration and Deployment
============================

Using the Cirrus CLI to create new project
------------------------------------------

Naming your deployment
----------------------

Required AWS deploy permissions
-------------------------------

Build and deploy
----------------

- Use of the AWS Timestream timeseries database can be turned off by removing the environment variable
  `CIRRUS_EVENT_DB_AND_TABLE: !Ref StateEventTimestreamTable` in cirrus.yml.

Test basic publish workflow
---------------------------

Required resources
------------------

Notes on using a VPC
--------------------

Deleting a deployment
---------------------
