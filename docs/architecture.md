# Cirrus Architecture

This is the basic architecture for Cirrus, a pipeline to process and
publish geospatial data based on the
[SpatioTemporal Asset Catalog](https://stacspec.org/) (STAC) specification.
Cirrus uses STAC metadata as the primary message throughout a workflow,
from input to output. See [usage](./usage.md) for a more thorough definition
of Cirrus payloads.


The diagram below shows how users interact with Cirrus and what Cirrus outputs.
# TODO: update bits on input payload format

![](images/highlevel.png)



## Feeders

Users operate *feeders*, programs that create STAC input catalogs and
add them to Cirrus. Feeders could be AWS Lambda or AWS Batch operations
that are user-initiated or scheduled.  The most simple version of a
*feeder* is simply passing a JSON payload from the users local computer.
Feeders are responsible for generating proper STAC metadata for the desired
workflow, providing information on the workflow to run along workflow
specific parameters, as desired.

Cirrus feeders are the most likely component of Cirrus to be customized
by a user. Several general use Lambda feeders are included with Cirrus.


### Batch feeders

The included feeders are all Lambdas, however they can also be run as
Batch processes instead, if they require more time or storage that what
a Lambda can provide. If the feeder accepts a `batch` parameter and it is
set to `true`, the feeder will spawn a Batch process from the Lambda using
the same Lambda function code and the same payload. The Lambda will then exit.
See documentation for the indvidual feeders for more information on accepeted
parameters.

See the `utils.submit_batch_job` function in `cirrus-lib` if interested in
supporting Batch in custom feeders.



## Cirrus Pipeline

The Cirrus Geospatial Pipeline black cloud above consists of a series of AWS
services that orchestrate and manage the flow of data through the system, as
shown here:

![](images/architecture.png)

From the standpoint of a user, who is using *feeders* to add data to Cirrus,
the entrypoint is an SNS topic named `process`. Feeders should publish Cirrus
ProcessPayloads using the
[ARN](https://docs.aws.amazon.com/general/latest/gr/aws-arns-and-namespaces.html)
of the that `process` topic.

The `process` SQS queue, subscribed to that `process` topic, is consumed by
the `process` Lambda function, which does two things, in this order:

1. Invoke the correct AWS Step Function based on the specified `workflow` in the Input Catalog
2. Update the Input Catalog in the StateDB to `PROCESSING`



## Workflows

Cirrus workflows are AWS Step Functions and are made up of a series of Tasks.
Tasks can be either AWS Lambda functions or AWS Batch operations. An example
workflows is shown here:

![](images/example-workflow.png)

This example workflow includes several Tasks:

- `Preprocess`: Performs some pre-processing on the Cirrus ProcessPayload
  metadata and pass to `Batch`.
- `Batch`: Runs an AWS Batch process that generates some data that is added
  to the s3 Data bucket. The ProcessPayload is updated and passed to
  `Create Preview`.
- `Create Preview`: Create a Preview Cloud-Optimized GeoTIFF from existing
  data and, optionally, a thumbnail image. Add these to the STAC Item assets
  and pass to `Publish`.
- `Publish`: Add all resulting STAC Items to the s3 Data bucket (alongside
  any data if there is some) and publishes each STAC Item to the Cirrus
  `publish` SNS topic.
- `Failure`: If any of the above fail, fail the Step Function execution.

Not pictured is `update-state`, a Lambda triggered by AWS EventBridge on
Cirrus Workflow Step Function success or failure, which updates the state
database ProcessPayload records with `COMPLETED`, `FAILED`, or `INVALID`,
as appropriate.



## Tasks

Cirrus includes several tasks by default:

- `add-preview`: Generates a byte-scaled Cloud-Optimized GeoTIFF (COG) from
  an asset, copy to bucket and add new asset for preview. Optionally also
  generates a thumbnail from preview image.
- `copy-assets`: Copies 1 or more assets from source to the Cirrus data bucket
  and updates STAC Asset URLs.
- `convert-to-cogs`: Converts 1 or more assets of the source to Cloud-Optimized
  GeoTIFFs, copies to Cirrus data bucket and replaces assets with new COG assets.
- `publish`: A Lambda function that takes the input STAC catalog and publishes
  all included STAC Items to s3 and to the Cirrus `publish` SNS topic.


### Batch Tasks

The included tasks are all Lambda functions, however if a workflow supports it,
they can optionally be run as a Batch task instead. This is useful if the
processing requirements are too much for a Lambda (e.g., takes more than 15
minutes, requires more storage, etc.).

A task can also be written solely as a Batch task with no corresponding Lambda.
Such tasks support CloudFormation in their `definition.yml` to create all Batch
resources (compute environment, job queue, job definition, etc.) required for
the job.

Container images for such tasks should be maintained in a separate repository
with some facility for publishing as a Docker image. The image should contain a
Command Line Interface that accepts a URL argument and is responsible for
fetching the input ProcessPayload and uploading the output ProcessPayload
from/to S3.

The Docker image URL is set in the
[definition for the batch job](../batch/jobs.yml).



## STAC

Cirrus uses [STAC ](https://stacspec.org/) as the message specification
for geospatial data through the pipeline. At the end of every workflow
Cirrus outputs one or more STAC Items to it's internal static STAC, saved
by default in the s3 bucket s3://cirrus-<stage>-data. The STAC root catalog
is located at s3://cirrus-<stage>-data/catalog.json.
