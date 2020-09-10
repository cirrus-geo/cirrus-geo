# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [v0.2.1] - 2020-09-10

### Fixed
- Updated version of batch jobs `geolambda-as-batch` and `lambda-as-batch`

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

[Unreleased]: https://github.com/cirrus-geo/cirrus/compare/master...develop
[v0.2.0]: https://github.com/cirrus-geo/cirrus-lib/compare/v0.1.0...v0.2.0
[v0.1.0]: https://github.com/cirrus-geo/cirrus/cirrus/tree/legacy

