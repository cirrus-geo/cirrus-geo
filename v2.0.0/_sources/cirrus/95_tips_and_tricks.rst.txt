Tips and Tricks
===============

Processing Queue Priority
-------------------------

By default, there is only one `process` queue. This can cause difficulty when doing
back-processing or failure re-run, as thousands of older, lower-priority payloads
can pile up in front of newly-generated, higher-priority payloads. A solution to this
is to create an addiitonal "bulk" queue and put all of the lower-priority payloads into it.

In the CloudFormation resources file, define a new queue named `ProcessBulkQueue` and
associated DLQ with the same settings as the default `ProcessQueue`.

Create an environment variable in cirrus.yml to reference this queue::

   CIRRUS_PROCESS_QUEUE_URL: !Ref ProcessQueue
   CIRRUS_PROCESS_BULK_QUEUE_URL: !Ref ProcessBulkQueue

Modify the `process` lambda definition to trigger on either of these queues with
`maximumConcurrency` set::

   lambda:
   memorySize: 128
   timeout: 30
   reservedConcurrency: 16
   handler: lambda_function.lambda_handler
   events:
      - sqs:
         arn: !GetAtt ProcessQueue.Arn
         maximumConcurrency: 4
      - sqs:
         arn: !GetAtt ProcessBulkQueue.Arn
         maximumConcurrency: 12


To use this "bulk" queue, replace uses of CIRRUS_PROCESS_QUEUE_URL with
CIRRUS_PROCESS_BULK_QUEUE_URL.
