# Cirrus

Cirrus is a [STAC](https://stacspec.org/)-based processing pipeline. As input, Cirrus takes a GeoJSON FeatureCollection with 1 or more STAC Items. This input is run through workflows that generate 1 or more STAC Items as output. These output Items are added to the Cirrus static STAC catalog, and are also broadcast via an SNS topic that can be subscribed to for triggering additional workflows, such as keeping a dynamic STAC catalog up to date (for example, [STAC-server](https://github.com/stac-utils/stac-server)).

Cirrus workflows can be as simple as containing no processing at all, where the input is passed through and published. It could be more complex where the STAC Items and underlying data are transformed, and then those are published.  The current state (QUEUED, PROCESSING, COMPLETED, FAILED) is tracked during processing, preventing inputs from getting ingested more than once and allows for a user to follow the state of any input through the pipeline.

![](docs/images/highlevel.png)

As shown in this high-level overview of Cirrus, users input data to Cirrus through the user of *feeders*. Feeders are simply programs that get/generate some type of STAC metadata, combine it with processing parameters and passes it into Cirrus in the format Cirrus expects.

Because Cirrus output is published via SNS, a Feeder can be configured to subscribe to that SNS and thus workflows can be chained, such that the output of one workflow becomes the input to another workflow and creates multiple levels of products, all with published STAC metadata and clear links showing data provenance.

## Cirrus Repositories

Cirrus is divided up into several repositories, all under the [cirrus-geo](https://github.com/cirrus-geo) organization on GitHub, with this repository (`cirrus`) the main one of interest to users.

| Repository         | Purpose |
|:------------------ |---------|
| cirrus             | Main Cirrus repo containing serverless config and deployment files, along with the standard set of Lambda functions |
| [cirrus-lib](https://github.com/cirrus-geo/cirrus-lib) | A Python library of convenience functions to interact with Cirrus. Lambda functions are kept lightweight |
| [cirrus-task-images](https://github.com/cirrus-geo/cirrus-task-images)  | Dockerfiles and code for publishing Cirrus Docker images to Docker Hub that are used in Cirrus Batch tasks |

The `cirrus` repository is what users would clone, modify and deploy. The pip-installable python library `cirrus-lib` is used from all Cirrus Lambdas and tasks and is available to developers for writing their own tasks.

## Cirrus Repository Structure

This repository, `cirrus` contains  all the files for deploying a Cirrus instance including all the core Lambda functions, workflows (AWS Step Functions), State database (AWS DynamoDB), Compute Environments (AWS Batch), and API (API Gateway + Lambda).

Users may need to edit the deployment YAML files as needed for their Cirrus instance, and may also wish to add new tasks, Lambda functions, and workflows.

| Folder    | Purpose |
|:----------|---------|
| core      | Core lambda functions for validating and orchestrating workflows |
| deploy    | yaml files used for deployment with Serverless (referenced from [serverless.yml](serverless.yml)) |
| docs      | Keeping details documentation for this application in a single place |
| feeders   | Feeder Lambda functions used to add data to Cirrus |
| lambdas   | Code for lambdas |
| tasks     | Lambda tasks |
| test      | All test files for the application, including test fixtures, are kept here |
| workflows | Definitions for AWS Step Functions and schemas |

## Documentation

Documentation for deploying, using, and customizing Cirrus is contained within the [docs](docs/) directory:

- Understand the [architecture](docs/architecture.md) of Cirrus and key concepts
- [Deploy](docs/deployment.md) Cirrus to your own AWS account
- [Use](docs/usage.md) Cirrus to process input data and publish resulting STAC Items
- [Customize](docs/customize.md) Cirrus by adding tasks, workflows, and compute environments

## About
Cirrus is an Open-Source pipeline for processing geospatial data in AWS. Cirrus was developed by [Element 84](https://element84.com/) originally under a [NASA ACCESS project](https://earthdata.nasa.gov/esds/competitive-programs/access).
