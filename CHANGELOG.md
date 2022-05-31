# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Support for cli plugins ([#138])
- Documentation within the package for projects to build into their docs ([#138])
- `update-state` now supports `ABORTED` and `TIMED_OUT` step function events ([#85])


### Fixed

- Component README template missing space in header ([#138])


### Removed

- Cleaned up old docs ([#138])


## [v0.5.4] - 2022-02-10

### Fixed

- `process` bug due to variable name reuse ([#116])


## [v0.5.3] - 2022-02-10

### Fixed

- API `items` endpoint fixed ([#114])


## [v0.5.2] - 2022-02-09

### Fixed

- `update-state` needs to use step function output for workflow chaining ([#111])


## [v0.5.1] - 2022-01-28

### Fixed

- `post-batch` returns process payload when no batch error, not batch output ([#107])
- `publish` publishes items to `PUBLISH_SNS` topics again ([#108])
- node package pinning in default package.json using correct semantics ([#102])


## [v0.5.0] - 2022-01-12

This release includes a number of small internal changes and bugfixes not
listed below. Please refer to the full commit log for this release for
additional details about the changes included in this release.

### ⚠️ Breaking changes

- lambda `python_requirements` renamed `pythonRequirements` and nested under
  `lambda` key in lambda definition; requirements listed under `include` key

  Example `definition.yml`:

  ```
  description: example
  lambda:
    ...
    pythonRequirements:
      include:
        - 'a_package==1.2.3'
  ```
- now using `cirrus-lib>=0.6.0`; see the
  [breaking changes in the 0.6.0 release][cl0.6.0]
  and update lambda handlers accordingly
- all CloudFormation templates move from `resources/` and `outputs/` to
  `cloudformation/`
- the custom compute environment resources have been removed, so batch jobs
  using those need to declare their own; switching to batch tasks is recommended
- global IAM permissions have been removed; audit all IAM permissions and
  declare them as needed in the corresponding component's `definition.yml`
- `queue` topic renamed `process`
- if using the default S3 bucket configurations, the buckets will be recreated
  with the new default names ([#47]); redeclare with the current bucket names
  or migrate all data and delete the old buckets
- global env vars have been cleaned up; make sure all lambdas/batch jobs have
  the vars they require

Some of the above do not apply unless `cirrus.yml` is recreated from the new
default template. It is recommended to delete `cirrus.yml`, rerun `cirrus init`,
and then replace all custom `cirrus.yml` content that is still required.

### Added

- README badges and codecov support ([#88])
- workflow chaining support ([#74])
- item filter support for workflow chaining ([#99])
- CloudFormation support for all types beyond Resources and Outputs ([#64])
- `AWS_REGION` and `AWS_DEFAULT_REGION` env vars injected into batch job
  definitions by default ([44bebc5])

### Changed

- converted builtin tasks supporting batch to new "batch task" paradigm ([#65])
- documentation cleanup ([#62])
- builtins moved to `cirrus.builtins` ([#53])
- non-cli code moved to `cirrus.core` ([#53])
- `cirrus` package moved under `src` ([#87])
- rename `CollectionMeta` and `Collection` to `GroupMeta` and `Group` ([#54])
- `cirrus-lib` injected into lambda packages from python env rather than
  installed from pip ([#89])
- build test fixtures don't need to store copies of all files ([#90])
- test output stored locally in untracked dir to enable post-test inspection
  ([ba3e04b])
- `queue` topic renamed `process` ([#79])
- all uses of `cirrus-lib` `Catalog` renamed to `ProcessPayload` ([#79])
- default S3 buckets drop random postfix in names ([#47])
- files/dirs starting with `.` should be ignored by all tooling

### Fixed

- `post-batch` refactoring and bugfixes ([#75])
- issues with batch CloudFormation on tasks
- environment variable inheritence for lambdas and batch jobs now appropriately
  inherits from global env vars and task-level env vars, always preferring the
  more-specific context
- builtin tasks using geospatial libraries pinned to `python3.7` runtime due
  to lambda layer requirements
- `cirrus show` not showing yaml fn arguments ([#98])

### Removed

- custom compute environments and variables ([#65])
- `test` directory and contents ([#51])
- `publish-test` function


## [v0.5.0a5] - 2022-01-07

### Changed

- `cirrus-lib` dependency pinned strictly to v0.5.1 to prevent pulling in
  incompatiable newer release ([9f56981])


## [v0.5.0a4] - 2021-11-19

### Fixes

- Don't load step function definitions twice ([f25acd4])
- Add `__subclass__` hook to `CollectionMeta` to fix tests ([1b89611])
- Fix `enabled` support for workflows ([#82])


## [v0.5.0a3] - 2021-11-19

### Fixes

- ensure `enabled` is popped off component definitions ([85464f5])
- `update-state` premissions now allow getting step function execution
  history ([#73])


## [v0.5.0a2] - 2021-10-06

### Changed

- `post-batch` pulls batch job errors and re-raises, if necessary ([#72])
- Workflows always go to `post-batch` after batch jobs, even on error, to use
  the new behavior to pull and re-raise batch errors ([#72])

### Fixes

- builtin component linting/fixes ([#71])


## [v0.5.0a1] - 2021-10-05

### Changed

- Separate lambda packages only contain code/files specific to each respective
  lambda


## [v0.5.0a0] - 2021-10-05

### ⚠️ Notice

This repo is now a python package that installs a `cirrus` cli tool to manage
cirrus projects. Existing projects are supported with some manual migration
cleanup steps.

### Changed

- bumped rasterio version to 1.2.8 where applicable


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
- `add-preview` now suffixes thumbnails with `_thumb.png` instead of `_preview.png`
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



[Unreleased]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.5.4...main
[v0.5.3]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.5.3...v0.5.4
[v0.5.2]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.5.1...v0.5.2
[v0.5.1]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.5.0...v0.5.1
[v0.5.0]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.5.0a5...v0.5.0
[v0.5.0a5]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.5.0a4...v0.5.0a5
[v0.5.0a4]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.5.0a3...v0.5.0a4
[v0.5.0a3]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.5.0a2...v0.5.0a3
[v0.5.0a2]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.5.0a1...v0.5.0a2
[v0.5.0a1]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.5.0a0...v0.5.0a1
[v0.5.0a0]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.4.2...v0.5.0a0
[v0.4.2]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.4.1...v0.4.2
[v0.4.1]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.4.0...v0.4.1
[v0.4.0]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.3.0...v0.4.0
[v0.3.0]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.2.1...v0.3.0
[v0.2.1]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.2.0...v0.2.1
[v0.2.0]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.1.0...v0.2.0
[v0.1.0]: https://github.com/cirrus-geo/cirrus-geo/cirrus/tree/legacy

[#47]: https://github.com/cirrus-geo/cirrus-geo/issues/47
[#51]: https://github.com/cirrus-geo/cirrus-geo/issues/51
[#53]: https://github.com/cirrus-geo/cirrus-geo/issues/53
[#54]: https://github.com/cirrus-geo/cirrus-geo/issues/54
[#62]: https://github.com/cirrus-geo/cirrus-geo/issues/62
[#64]: https://github.com/cirrus-geo/cirrus-geo/issues/64
[#65]: https://github.com/cirrus-geo/cirrus-geo/issues/65
[#74]: https://github.com/cirrus-geo/cirrus-geo/issues/74
[#75]: https://github.com/cirrus-geo/cirrus-geo/issues/75
[#79]: https://github.com/cirrus-geo/cirrus-geo/issues/79
[#82]: https://github.com/cirrus-geo/cirrus-geo/issues/82
[#85]: https://github.com/cirrus-geo/cirrus-geo/issues/85
[#98]: https://github.com/cirrus-geo/cirrus-geo/issues/98
[#99]: https://github.com/cirrus-geo/cirrus-geo/issues/99
[#102]: https://github.com/cirrus-geo/cirrus-geo/issues/102
[#107]: https://github.com/cirrus-geo/cirrus-geo/issues/107
[#108]: https://github.com/cirrus-geo/cirrus-geo/issues/108
[#111]: https://github.com/cirrus-geo/cirrus-geo/issues/111
[#114]: https://github.com/cirrus-geo/cirrus-geo/issues/114
[#116]: https://github.com/cirrus-geo/cirrus-geo/issues/116

[#71]: https://github.com/cirrus-geo/cirrus-geo/pull/72
[#72]: https://github.com/cirrus-geo/cirrus-geo/pull/72
[#73]: https://github.com/cirrus-geo/cirrus-geo/pull/73
[#87]: https://github.com/cirrus-geo/cirrus-geo/pull/87
[#88]: https://github.com/cirrus-geo/cirrus-geo/pull/88
[#89]: https://github.com/cirrus-geo/cirrus-geo/pull/89
[#90]: https://github.com/cirrus-geo/cirrus-geo/pull/90
[#138]: https://github.com/cirrus-geo/cirrus-geo/pull/138

[f25acd4f]: https://github.com/cirrus-geo/cirrus-geo/commit/f25acd4f43e2d8e766ff8b2c3c5a54606b1746f2
[85464f5]: https://github.com/cirrus-geo/cirrus-geo/commit/85464f5a7cb3ef82bc93f6f1314e98b4af6ff6c1
[1b89611]: https://github.com/cirrus-geo/cirrus-geo/commit/1b89611125e2fa852554951343731d1682dd3c4c
[1e652f2]: https://github.com/cirrus-geo/cirrus-geo/commit/1e652f20ef38298f56ebc81aea0d61aaad135f67
[9f56981]: https://github.com/cirrus-geo/cirrus-geo/commit/9f569819d1c4a59fc71f15642b3ea0b30058c885
[44bebc5]: https://github.com/cirrus-geo/cirrus-geo/commit/44bebc5d1e2d802fc0e596be381fb3e1e1042170
[ba3e04b]: https://github.com/cirrus-geo/cirrus-geo/commit/ba3e04ba2c2ae554fecf9b80e22c71690a9eb518

[cl0.6.0]: https://github.com/cirrus-geo/cirrus-lib/releases/tag/v0.6.0
