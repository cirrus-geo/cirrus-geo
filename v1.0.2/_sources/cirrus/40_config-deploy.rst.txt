Configuration and Deployment
============================

Using the Cirrus CLI to create new project
------------------------------------------

Naming your deployment
----------------------

Required AWS deploy permissions
-------------------------------

AWS Service Quotas and Limits
-----------------------------

AWS provides highly-scalable cloud resources, but these are not infinitely scalable.
There are quotas on the number of resources of each type that you can create,
APIs have limits on how frequently they can be called, and there is significant
latency for allocating some types of resources (e.g., Spot EC2 instances).

Quotas
^^^^^^

Quotas are limits imposed per account that can usually be increased.

- Lambda Functions - defaults to 1,000 concurrent executions, should be increased to at least 10,000
- Step Functions - 1M open step function executions per account per region
  (see `AWS Step Functions - Quotas`_).
  Generally, this is sufficient, and if a higher volume of items is being processed that
  this, their ingress into the system should be throttled earlier in the flow.
- Step Functions - StartExecution throttle token bucket size: 2,500
- Step Functions - StartExecution throttle token refill rate per second: 300
- Step Functions - GetExecutionHistory throttle token bucket size: 2,000
- Step Functions - GetExecutionHistory throttle token refill rate per second: 100
- EC2 - Running On-Demand P instances: 64
- EC2 - Spot Instance requests per-instance type is set to a default of 5, and should increased at least into the hundreds.
- WAF Classic - Rules per region: 200
- S3 - General Purpose Buckets: 200

.. _AWS Step Functions - Quotas: https://docs.aws.amazon.com/step-functions/latest/dg/limits-overview.html

Limits
^^^^^^

- Batch API SubmitJob and DescribeJob API endpoints have a limit of 50 requests/sec
- There are no limits on the number of EC2 Spot instance vCPUs you can have like there are for On-Demand and Dedicated instances
- Lambda has a 15 minute execution time limit


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
