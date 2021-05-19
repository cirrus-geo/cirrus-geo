# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [v0.4.2] - 2021-01-12

### Added

- Query parameters that allow for results sorting.

### Fixed
- stac-api feeder (broken when providing STAC API URL)
- publish-test Lambda correctly logs

## [v0.4.1] - 2020-11-19

### Fixed
- Error when trying to parse non standardized logging error output
- Fixed `updated` index to allow for time filtering
- Rerunning of catalogs in process task
- Fixed creation of preview/thumbnails in add-preview task

## [v0.4.0] - 2020-11-13

### Added
- API root now returns child links to summaries if configured in the Cirrus root catalog
- `status` field added to attributes of published SNS messages, `created` if new STAC Item (not in Cirrus catalog), or `updated` if it already exists
- `created` and `updated` properties added to STAC Items when adding to Cirrus static catalog on s3

### Changed
- feeder.test Lambda moved to core/publish-test Lambda and defaults to being subscribed to the Cirrus Publish SNS. The Lambda only logs the payload
- API changes: get single catalog is now `/<catid>`, collection names now include collections + workflow, Item response updated as detailed in cirrus-lib 0.4
- State Schema changes, see `cirrus-lib`
- `publish-test` moved to core lambdas, and auto subscribes to Cirrus endpoint
- Feeders cleaned up, updated to cirrus-lib 0.4 where needed

## [v0.3.0] - 2020-10-26

### Added
- Structured logging, providing additional context to logs
- `add-collections` Lambda function for adding Collections to the Cirrus static STAC catalog
- `process` Lambda updated to accept `catids` as an argument which it will replace with that Catalog's original input file
- `process_update` parameter added to `rerun` to allow for partial updated of process definition in reruns
- Additional retry logic added in workflows, Unknown Lambda errors retried
- /catid/<catalog_id> endpoint added to Cirrus API
- Link relation type `via-cirrus` added to output items where title is the Catalog ID and the href links to that catalog ID in the Cirrus API

### Changed
- Update `cirrus-lib` to 0.3.3
- Lambda code files renamed from lambda_function.py to feeder.py for feeders and task.py for tasks, allowing better logging
- Lambda handler functions renamed from `lambda_handler` to `handler` since they could be Batch rather than lambdas
- Batch Compute Environment definitions moved to core/ directory
- API Lambda refactored to return collections in Cirrus static STAC catalog
- Handler function names changed for feeders to `feeder.handler`
- Handler function names changed for tasks to `task.handler`
- Logging refactored to do structured (JSON) logging

### Fixed
- Errors from batch now correctly reported to StateDB

### Removed
- `catids` no longer valid argument `rerun`  payload - publish array of `catids` directly to Cirrus queue instead

## [v0.2.1] - 2020-09-10

### Added
- Failed workflows publish state db info to new SNS topic: cirrus-<stage>-failed
- STAC Lambda added for adding collections to the Cirrus root catalog. This is not currently required, but is good practice
- s3 inventory feeder: added support for s3 orc inventory files

### Removed
- assigning of collections in the `copy-assets` and `publish` Lambdas - this is done in cirrus-lib when parsing for a payload so this was redundant

### Changed
- cirrus-lib version updated to 0.3.1
- VisibilityTimeout and maxReceiveCount fields changed on Cirrus process lambda

### Fixed
- Updated version of batch jobs `geolambda-as-batch` and `lambda-as-batch`
- bug in s3 inventory feeder when using regex to extract date from filename

## [v0.2.0] - 2020-09-08

### Added
- `process` Lambda that consumes from ProcessQueue that both validates the payload and starts the workflow.
- `stac` Lambda added for adding Collections to the Cirrus Catalog
- `s2-inventory` for creating partial STAC Items (i.e., JSON with assets) from s3 inventory files
- `feed-stac-crawl` for adding Items by crawling a STAC catalog (using PySTAC)
- Retries added to all tasks in workflows
- Added back "post-batch" steps to all workflows

### Changed
- Update cirrus-lib to 0.3.0
- IAM configuration (previously batch/iam.yml) combined into Core resources (core.yml)
- `pre-batch` and `post-batch` Lambda functions moved from `core` to `tasks` (since they are tasks that can be used in a workflow)
- `add-preview` now suffixes thumbnails with "_thumb.png" instead of "_preview.png"
- Batch processes now write output payload back to a new file rather than overwriting the input payload.

### Removed
- `validation` and `start-workflow` Lambdas (replace with new `process` Lambda)
- ValidationQueue (SQS), now only 1 queue (ProcessQueue)

### Fixed
- `feed-stac-api` Lambda fixed to split requests by hours, not days. Fixes issue where there are more scenes in 1 day than the per request limit
- `lambda-as-batch` and `geolambda-as-batch` Batch tasks fixed to properly return newly returned STAC Catalog rather than the original one (which may have been modified as it is passed by reference to handler)
- `convert-to-cog` now properly populates `derived_from` link in newly created STAC Item


## [v0.1.0] - 2020-08-07

Initial release

[Unreleased]: https://github.com/cirrus-geo/cirrus/compare/v0.4.2...main
[v0.4.2]: https://github.com/cirrus-geo/cirrus-lib/compare/v0.4.1...v0.4.2
[v0.4.1]: https://github.com/cirrus-geo/cirrus-lib/compare/v0.4.0...v0.4.1
[v0.4.0]: https://github.com/cirrus-geo/cirrus-lib/compare/v0.3.0...v0.4.0
[v0.3.0]: https://github.com/cirrus-geo/cirrus-lib/compare/v0.2.1...v0.3.0
[v0.2.1]: https://github.com/cirrus-geo/cirrus-lib/compare/v0.2.0...v0.2.1
[v0.2.0]: https://github.com/cirrus-geo/cirrus-lib/compare/v0.1.0...v0.2.0
[v0.1.0]: https://github.com/cirrus-geo/cirrus/cirrus/tree/legacy

