# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [v1.1.1] - 2025-10-01

### Changed

- Switch build system to hatchling. ([#337])
- Relax stac-task dependency version. ([#337])

### Fixed

- Fix README rendering on PyPI. ([#337])
- Add `--no-editable` flag to force non-editable install in bash build script. ([#339])

## [v1.1.0] - 2025-09-25

### Added

- Adds the functionality from the cirrus api lambda to the `Deployment` class and
  the CLI. ([#324])
- Adds a `CirrusPayload` model that extends `stac-task`'s `Payload` model with
  Cirrus-specific validation and ID generation. ([#331])

### Changed

- Switch to `uv` for package management. ([#330])
- Internal `ProcessPayload` class renamed to `PayloadManager` to better reflect its
  purpose. ([#331])

### Fixed

- The update state lambda was not correctly parsing the error and cause from
  the Step Functions event. This caused the lambda to fail on certain errors,
  leaving payloads with incorrect states in the state database. ([#326])

## [v1.0.2] - 2025-08-26

### Fixed

- StepFunctions Execution ARN stored in `StateDB` was incorrect, but format was
  unchecked.  Moto mock testing did not complain that the State Machine ARN
  provided was invalid for StepFunctions execution. ([#317])
- Dynamo DB fails to update with extraneous parameters in the
  `ExpressionAttributeValues` argument.  Issue not surfaced by Moto. ([#319])

## [v1.0.1] - 2025-06-18

### Added

- `pymarkdownlnt` via pre-commit hook

### Fixed

- `SNSPublisher.send` being used directly with more than 10 messages in a call was
  failing at the SNS API.  As direct usage of `send` was not intended, that method
  has been moved to `_send`, for alignment with its purpose as an internal message
  sending function. ([#315])

### Removed

- `markdownlint-cli` pulled due to dependency bitrot

## [v1.0.0] - 2025-04-25

This release rebuilds cirrus-geo to support a "bring-your-own-IaC" deployment model.
The changeset is extensive. Refer to the following PRs:

- Initial work for v1 ([#268])
- Build a dist zip for all cirrus lambdas ([#276])
- Fix package build and switch to trusted publishers ([#277])

This is a breaking change, as documented below.

### ⚠️ Breaking changes

- MAJOR: cirrus v1.0.0 no longer includes the idea of a project
  or the project-based CLI--it is just a collection of lambda definitions
  disconnected from a deployment mechanism. Serverless Framework is gone
  entirely. Existing projects will need to  migrate to a new externally-managed
  deployment mechanism--such as the [FilmDrop Terraform
  modules](https://github.com/Element84/filmdrop-aws-tf-modules/tree/main),
  which includes a cirrus module--or will need stick with the v0 releases.
  Note that support for v0 is not guaranteed, so consider that branch
  effectively deprecated.
- `update-state` lambda now retrieves error messages from FAIL state output payload
  instead of searching step function execution history ([#311])

### Added

- `CLAIMED` state to StateDB, along with associated `ALREADY_CLAIMED`
  WorkflowEvent. ([#281])
- `get-payloads` command added to CLI module to bulk retrieve input payloads
  based on user-supplied filters ([#305])
- documentation for setup, authorization, and commands for CLI tool ([#300])

### Changed

- StepFunctions executions now use a deterministic UUID5, derived from the
  payload ID and execution history ([#281])
- Upgrade `moto` to enable testing of `process` lambda race conditions ([#281])
- CLI required env vars are stored/retrieved from AWS Parameter Store ([#295])
- CLI tool may now assume an IAM role and update session with IAM credentials
  if IAM role is available in parameter store config ([#303])
- Updated documentation for default cirrus lambda functions, documenting each
  current lambda-function ([#306])
- The `update_state` lambda now pushes each Item in output Cirrus Process
  Payloads to the `CIRRUS_PUBLISH_TOPIC_ARN`, if set, with SNS messages derived
  from the Item.  ([#294])
- Workflow events of type `SUCCEEDED` now include the step function execution
  ARN in the event. ([#297])

## [v0.15.4] - 2024-12-03

### Fixed

- Pass payload, not string version of payload, when string version is larger
  than `MAX_PAYLOAD_LENGTH` is exceeded. ([#292])

## [v0.15.3] - 2024-11-15

### Fixed

- Fixed issue [#225] where default string is treated as a list when input
  collection is specified neither via `payload.collections` nor on the items in
  `payload.features[].collection`. ([#279])
- Fixed issue [#255] for the `release/v0` branch by using a heuristic to select
  only the libs that cirrus.lib2 needs for injection into the python lambda
  requirements files. ([#283])
- Use `importlib.resources._legacy` module for compatiblity with python version
  3.12. ([#290])

### Changed

- Loosened requirement `rich~=10.6` to `rich`, and bumped python-dateutil from
  `~2.8.2` to `~2.9.0`. Note, the sum total of `rich` usage is printing
  escaped character sequences to the console. ([#283])

### Removed

- Removed slimPatterns for `boto*` and `dateutil` packages, per [#242]. ([#283])

## [v1.0.0a1] - 2025-02-28

### Fixed

- Errors in `build-lambda-dist.bash` ([#278])
- Fixed issue [#225] where default string is treated as a list when input
  collection is specified neither via `payload.collections` nor on the items in
  `payload.features[].collection`. ([#280])

### Changed

- The `update_state` lambda now pushes each Item in output Cirrus Process
  Payloads to the `CIRRUS_PUBLISH_TOPIC_ARN`, if set, with SNS messages derived
  from the Item.  ([#294])
- Workflow events of type `SUCCEEDED` now include the step function execution
  ARN in the event. ([#297])

## [v0.15.2] - 2024-11-08

Deleted due to github release workflow misconfiguration.

## [v1.0.0a0] - 2024-08-13

### ⚠️ Breaking changes

- This release rebuilds cirrus-geo to support a "bring-your-own-IaC" deployment model.
  The changeset is extensive. Refer to the following PRs:

  - Initial work for v1 ([#268])
  - Build a dist zip for all cirrus lambdas ([#276])
  - Fix package build and switch to trusted publishers ([#277])

## [v0.15.1] - 2024-05-09

### Fixed

- Stop `SNSPublisher` and `SQSPublisher` from overwriting `dest_name`. ([#274])

## [v0.15.0] - 2024-05-06

### ⚠️ Deprecations

- Both the `CIRRUS_FAILED_TOPIC_ARN` and `CIRRUS_INVALID_TOPIC_ARN` SNS Topics
  have been deprecated, and the `CIRRUS_WORKFLOW_EVENT_TOPIC_ARN` Topic should
  be used by subscriptions which need to act on failed or invalid workflows.

### Fixed

- Incorrect function `already_processing` corrected to
  `skipping(state="PROCESSING",...)`. ([#267])
- `payload_id` was not passed properly to `StateDB` for logging, via the state
  change decorator. Updated the decorator to be a Descriptor, which may make
  type checking happier. ([#270])
- added function `cirrus.lib2.utils.cold_start` to move overhead of boto
  client/resource cache instantiation out of lambda function execution. ([#272])

### Added

- `cirrus-<stage>-workflow-event` SNS topic, and
  `WorkflowEventManager` class for managing workflow event actions. ([#261])
  The actions managed by this class include:

  - updating state of workflows in `StateDB`
  - announcing interactions cirrus has with a payload to the
    `cirrus-<stage>-workflow-event`
    Note: To use this topic, existing deployments will need to add the following
    to their environment in both their `cirrus.yml` file:

    ```yaml
    CIRRUS_WORKFLOW_EVENT_TOPIC_ARN: !Ref WorkflowEventTopic
    ```

- Testing of python 3.12. ([#261])
- `SfnStatus` string enum added for StepFunctions execution status
  strings. ([#261])
- Added check of status returned from AWS calls to update the `StateDB` table,
  which raises a `RuntimeError` including the response if the write fails.
  This addresses Issue [#202]. ([#263])

### Changed

- Moved `StateEnum` to `cirrus.lib2.enums` module for use across `lib2` and
  `builtins`. ([#261])
- Migrated management of timeseries (`EventDB`) events from `StateDB` to
  `WorkflowEventManager`. ([#263])
- Provide option to pass in timestamp to `WorkflowEventManager` state-change
  functions. ([#263])

## [v0.14.0] - 2024-04-26

### Changed

- Prevent `cirrus.lib2.logging` logger messages from being duplicated by the
  root logger. ([#264])
- Collections are not assigned by any of the built-in functions or tasks. ([#266])

### Removed

- `ProcessPayload.assign_collections()` removed in favor of having tasks assign
  collections to items themselves (which happens automatically when using
  stac-task. ([#266])

## [v0.13.0] - 2024-03-04

### Added

- SNS and SQS publisher classes to manage batching of messages. ([#249])
- Added markdownlint-cli to pre-commit hooks. ([#259])

## [v0.12.1] - 2024-02-15

### Fixed

- Restore `InvalidInput` exception, which only existed in `cirrus-lib` (and
  `stactask`). ([#256])

## [v0.12.0] - 2024-02-14

### Fixed

- Re-add default dependencies to lambdas. ([#254])

## [v0.11.4] - 2024-02-13

### Fixed

- Fix IAM perms for timestream:DescribeEndpoints to be '\*'. ([#253])

## [v0.11.3] - 2024-02-13

### Fixed

- Fix IAM perms on Timestream resources to be a valid ARN. ([#248])

## [v0.11.2] - 2024-02-13

### Fixed

- Only assign IAM perms to Timestream resources if the region supports them. ([#247])

## [v0.11.1] - 2024-02-12

### Changed

- ProcessQueue SQS queue visibility timeout increased from 60 to 180([#245])
- Only create Timestream resources if the region supports them. ([#246])

## [v0.11.0] - 2024-02-05

### ⚠️ Breaking changes

- Users relying on the automatic packaging of cirrus.lib into lambdas will need
  to explicitly add cirrus.lib to those function requirements. Additionally,
  cirrus.lib is no longer maintained it is recommended to migrate to using
  stac-task instead. ([#230])

### Removed

- Cleaned `cirrus.lib` (old separate package) from lambda templates and build
  process. ([#230])

## Changed

- `process` function definition now defines a maximumConcurrency of 16. This
  still results is relatively fast draining of the process queue, but unlike an
  unlimited concurrency, prevents too many step functions from being created
  too fast, which can result in Lambda or Batch overload.

## [v0.10.1] - 2024-01-10

### Fixed

- In post-batch, better handle errors with the task failing to run and/or the
  CloudWatch log not existing. ([#231])
- Ensure correct count returned from `process` lambda and resolve
  `UnboundLocalError` encountered on certain workflow failures. ([#224])
- Reduce `ProcessPayload.assign_collections` iteration from `N*M` to
  `N*log(M)` by exiting the inner loop on first match. ([#226])

## [v0.10.0] - 2023-07-19

### ⚠️ Breaking changes

- Remove support for Python 3.8

### Fixed

- Include `requirements.txt` for install from source distribution. This was
  missing and prevented install from pypi source. - For Batch tasks in
  workflows, the output payload URL is now explicitly set in the pre-batch
  lambda so that the URL is in the Parameters list of the output, rather than
  the post-batch function having to infer the output payload URL. This fixes
  Batch tasks when using stac-task. Any JobDefinition using stac-task should
  specify `url` and `url_out` as Parameters and specify --output in the
  Command, e.g.:

```yaml
Parameters:
  url: ""
  url_out: ""
ContainerProperties:
  Command:
    - task
    - run
    - Ref::url
    - --output
    - Ref::url_out
```

## [v0.9.0] - 2023-01-26

### ⚠️ Breaking changes

- An AWS Timestream timeseries database has been added to track workflow state
  change events. The environment variable
  `CIRRUS_EVENT_DB_AND_TABLE: !Ref StateEventTimestreamTable`
  must be added to the cirrus.yml file if you wish to use this functionality.
- The Cirrus Process SNS topic has been removed, and the Process SQS queue is
  used directly now. This requires updating the cirrus.yml file to remove the
  environment variable `CIRRUS_PROCESS_TOPIC_ARN: !Ref ProcessTopic` and add
  the environment variable `CIRRUS_PROCESS_QUEUE_URL: !Ref ProcessQueue`.

### Fixed

- CLI warning and error outputs are again colorized ([#193])
- Error in rerun feeder due to using function removed from cirrus.lib2 ([#207])
- Update Step Functions State Machine execution url to v2 form.
- hash_tree was not skipping dot-dirs

## [v0.8.0] - 2022-11-02

### ⚠️ Breaking changes

- Serverless version >=3 is now required per the addition of a DLQ for the
  `update-state` events ([#182]).

  Note that upgrading to serverless v3 changes the type of EventBridge Rules
  resources. In testing we found that the existing `update-state` rule needed
  to be deleted by CloudFormation before adding the new rule. Manually
  deleting the existing rule before deployment was not sufficient, as
  CloudFormation ended up removing the new rule after it was created.

  In short, the simplest thing to do after upgrading serverless is to deploy
  twice, once with `update-state` disabled and again with it re-enabled.

  To disable it, it is easiest to run this from your project root:

  ```shell
  mkdir functions/update-state
  echo "description: temporarily disabled" > functions/update-state/definition.yml
  ```

  Then, run the deploy as normal. Once that is complete, remove the
  `update-state` override:

  ```shell
  rm -r functions/update-state
  ```

  Deploy again and `update-state` and its event should be re-created
  successfully.

  Note that state tracking/workflow chaining _will be broken_ between the first
  deploy and the second. It is _strongly_ recommended to do this only when your
  pipelines are not processing workflows.

- The `process` SNS topic has been removed ([#169]). All feeder/scripts/etc.
  should use the `process` SQS queue directly. If project needs require the SNS
  topic for migration or other use, the removed configuration can be
  reintroduced by adding the following CloudFormation template to your project:

  ```yaml
  # cloudformation/sns.yml
  Resources:
    ProcessTopic:
      Type: "AWS::SNS::Topic"
      Properties:
        TopicName: "#{AWS::StackName}-process"
    ProcessQueuePolicy:
      Type: AWS::SQS::QueuePolicy
      Properties:
        Queues:
          - !Ref ProcessQueue
        PolicyDocument:
          Statement:
            - Sid: allow-sqs-sendmessage
              Effect: Allow
              Principal:
                AWS: "*"
              Action: SQS:SendMessage
              Resource: !GetAtt ProcessQueue.Arn
              Condition:
                ArnEquals:
                  aws:SourceArn:
                    - !Ref ProcessTopic
    ProcessQueueSubsciption:
      Type: AWS::SNS::Subscription
      Properties:
        Endpoint: !GetAtt ProcessQueue.Arn
        Protocol: sqs
        Region: "#{AWS::Region}"
        TopicArn: !Ref ProcessTopic

  Outputs:
    CirrusQueueSnsArn:
      Value: !Ref ProcessTopic
  ```

### ⚠️ Deprecations

- cirrus-lib dependency injection will be removed in the next major release.
  Switch tasks now to the new `stac-task` class or be prepared to update task
  requirements to explicitly include cirrus-lib with the next release (see
  [#178] for context).

### Added

- `process` lambda now supports s3 URL payloads from feeders and partial
  success for message batches ([#103]).
- Code formatting and linting as a pre-commit hook ([#158]).
- `update-state` will match on `stactask.exceptions.InvalidInput` as an error
  triggering the `INVALID` state ([#180]).
- DLQ for `update-state` events ([#182]).

### Changed

- `process` lambda timeout reduced from 900s to 10s and the visibility timeout
  on the `process` queue reduced from 1000s to 60s ([#103]).
- Builtins no longer using cirrus-lib, but library methods built in to
  cirrus-geo, removing their strict dependency on cirrus-lib ([#177]).
- `feed-rerun` passes payloads one-by-one to `process` as URL payloads rather
  than depending on undocumented `process` behavior and increase the
  efficiency/reliabililty of `process` ([#120]).
- Payload validation has been loosed in all builtins as part of [#177],
  allowing cirrus uses previously unsupported by overly strict validation.
- Test coverage now considers builtins ([#172]).
- `publish` has permissions to write to and put object ACLs in all buckets
  (assuming the buckets allow; [#174])
- `update-state` and `feed-rerun` send messages directly to the `process` SQS
  rather than the now-removed SNS topic ([#169]).

### Fixed

- Avoid `States.DataLimitExceeded` error when `publish` or `post-batch` return
  large payloads by returning `payload.get_payload()` ([#160]).
- Bug in default batch task definition ([#154]).
- Batch-only tasks no longer template `lambda_function.py` on creation ([#155]).
- State DB bug in cirrus-lib 0.8.0 resolved in new builtin lib code ([#173]).

### Removed

- Undocumented behaviors in `process` lambda for things such as default
  processing configs, resolving payload IDs from the state database, and
  processing config updates ([#103]).
- `process` SNS topic ([#169]).

## [v0.7.0] - 2022-09-12

### ⚠️ Breaking changes

- Serverless versions through 3.x now supported. Minimum serverless of 2.3.0 is
  now required per pseudo parameters now being parsed within cirrus, rather
  than via the `serverless-pseudo-parameters` plugin. ([#139])

  Tested `package.json` dependency versions:

  ```yaml
    "serverless": "~3.18.0",
    "serverless-python-requirements": "~5.4.0",
    "serverless-step-functions": "~3.7.0",
    "serverless-iam-roles-per-function": "~3.2.0"
  ```

  Note that upgrading to serverless v3 changes the type of EventBridge Rules
  resources. In testing we found that the existing `update-state` rule needed
  to be deleted by CloudFormation before adding the new rule. Manually
  deleting the existing rule before deployment was not sufficient, as
  CloudFormation ended up removing the new rule after it was created.

  In short, the simplest thing to do after upgrading serverless is to deploy
  twice, once with `update-state` disabled and again with it re-enabled.

  To disable it, it is easiest to run this from your project root:

  ```shell
  mkdir functions/update-state
  echo "description: temporarily disabled" > functions/update-state/definition.yml
  ```

  Then, run the deploy as normal. Once that is complete, remove the
  `update-state` override:

  ```shell
  rm -r functions/update-state
  ```

  Deploy again and `update-state` and its event should be re-created
  successfully.

  Note that state tracking/workflow chaining _will be broken_ between the first
  deploy and the second. It is _strongly_ recommended to do this only when your
  pipelines are not processing workflows.

- All lambda component definitions need the `handler` populated if not already.
  Previously cirrus was defaulting `handler` to `lambda_function.lambda_handler`
  if it were omitted. Now the default lambda `definition.yml` includes
  `handler: lambda_function.lambda_handler`, allowing users to remove it if not
  compatible with their needs (i.e., specifying a container `image`). ([#139])

- S3 buckets `Data` and `Payload` are no longer defined as builtins. Projects that
  do not otherwise define their required S3 buckets should ensure they have both
  of these buckets defined in their cloudformation resource templates. The
  previously-default configuration looks like this ([#147]):

  ```yaml
  # cloudformation/s3.yml
  Resources:
    # Main data bucket
    Data:
      Type: AWS::S3::Bucket
      Properties:
        BucketName: "#{AWS::StackName}-data"
    # Bucket for storing input catalogs
    Payloads:
      Type: AWS::S3::Bucket
      Properties:
        BucketName: "#{AWS::StackName}-payloads"
        LifecycleConfiguration:
          Rules:
            - ExpirationInDays: 10
              Prefix: batch/
              Status: Enabled
            - ExpirationInDays: 10
              Prefix: payloads/
              Status: Enabled
  ```

  Note that if a bucket _not part your existing cirrus project_ already exists with
  the same name specified here, cloudformation will fail. Ensure you are only using
  these default bucket names if your project was previously relying on these
  built-in resources.

- Batch IAM role best practices have changed, and some builtin roles have changed
  or been removed. See [#149] for additional context. In summary:

  - Do not specify the service role on batch compute environments. The builtin
    `BatchServiceRole` has been removed from cirrus. The default role automatically
    provided by `AWS` automatically is sufficient.

    Note that existing compute environments have to be deleted and recreated
    using the new service role, as CloudFormation seems to be unable to update
    the service role and will instead leave all compute environments that have
    simply had the service role removed in an invalid state.

  - All non-standard permissions have been removed from the
    `BatchInstanceRole`. If you have been overriding that role with custom
    permissions review the new `BatchJobRole` and override with any further
    permissions instead. Better yet, create a unique role per batch task based
    on the `BatchJobRole`.
  - When using `BatchJobRole` or a custom role per batch task, ensure it is
    specified on the job definition as the `ContainerProperties` `JobRoleArn`.

- The cli command to create new tasks now uses `-t`/`--type` to specify the
  task type, instead of `--has-batch`/`--no-batch` and
  `--has-lambda`/`--no-lambda`. `-t`/`--type` has no default value and is
  required. It can be specified multiple times in the case of a task that uses
  both batch and lambda. ([#123])

### ⚠️ Deprecations

- `ProcessPayload.process['output_options']` has been renamed to
  `'upload_options'` ([#128])`

### Added

- experimental support for lambdas using container images ([#139])
- `init` creates a minimal .gitignore in the project root ([#140])
- `init` will now create cloudformation templates for the minimum set of resources
  not provided by builtins ([#147])
- explicit error message when lambda package requirements have duplicates ([#106])
- support for cirrus plugins providing components or cloudformation via the
  `cirrus.resources` entrypoint ([#104])
- support for cli plugins via the `cirrus.plugins` entrypoint ([#138])
- documentation within the package for projects to build into their docs ([#138])
- `update-state` now supports `ABORTED` and `TIMED_OUT` step function events ([#85])
- `rerun` feeder supports `error_begins_with` to search for payloads to rerun by
  the error message ([#143])

### Changed

- `BatchInstanceRole` no longer has cirrus-specific permissions. Specify a
  `JobRoleArn` on batch job definitions pointing to the builtin `BatchJobRole`
  or a custom role. ([#149])
- support for modern versions of serverless; minimum version supported is now
  2.3.0 ([#139])
- lambda components definitions require `handler` to be specified when not
  using container images (previous default: `handler:
  lambda_function.lambda_handler`) ([#139])

### Fixed

- `rerun` feeder has required permissions ([#131])
- cirrus.yml default template now has missing provider vpc configuration
  ([#132])
- `sls`/`serverless` command returns non-0 on errors ([#134])
- `update-state` lambda supports payload URLs ([#135])
- omit lambda block from batch-only task `definition.yml` on create ([#123])
- test payloads output to non-terminal FDs will not have lines broken by
  terminal width ([#145])
- component README templates missing space in header ([#138])

### Removed

- all non-core builtins ([#78]):
  - feed-s3-inventory (feeder)
  - feed-stac-api (feeder)
  - feed-stac-crawl (feeder)
  - add-preview (task)
  - convert-to-cog (task)
  - copy-assets (task)
  - cog-archive (workflow)
  - mirror-with-preview (workfow)
  - mirror (workflow)
- builtin S3 bucket resources ([#147])
- builtin `BatchServiceRole` resource ([#149])
- dependency on `servereles-pseudo-parameters` ([#139])
- old docs ([#138])

## [v0.6.0] - 2022-02-18

### Fixed

- `cirrus build` will now rmtree for build dirs on rebulids ([#105])

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

  ```yaml
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
- Fix `enabled` support for workflows ([#82], [1e652f2])

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

- API root now returns child links to summaries if configured in the Cirrus
  root catalog
- `status` field added to attributes of published SNS messages, `created` if
  new STAC Item (not in Cirrus catalog), or `updated` if it already exists
- `created` and `updated` properties added to STAC Items when adding to Cirrus
  static catalog on s3

### Changed

- feeder.test Lambda moved to core/publish-test Lambda and defaults to being
  subscribed to the Cirrus Publish SNS. The Lambda only logs the payload.
- API changes: get single catalog is now `/<catid>`, collection names now
  include collections + workflow, Item response updated as detailed in
  cirrus-lib 0.4.
- State Schema changes, see `cirrus-lib`
- `publish-test` moved to core lambdas, and auto subscribes to Cirrus endpoint
- Feeders cleaned up, updated to cirrus-lib 0.4 where needed

## [v0.3.0] - 2020-10-26

### Added

- Structured logging, providing additional context to logs
- `add-collections` Lambda function for adding Collections to the Cirrus static
  STAC catalog
- `process` Lambda updated to accept `catids` as an argument which it will
  replace with that Catalog's original input file
- `process_update` parameter added to `rerun` to allow for partial updated of
  process definition in reruns
- Additional retry logic added in workflows, Unknown Lambda errors retried
- /catid/<catalog_id> endpoint added to Cirrus API
- Link relation type `via-cirrus` added to output items where title is the
  Catalog ID and the href links to that catalog ID in the Cirrus API

### Changed

- Update `cirrus-lib` to 0.3.3
- Lambda code files renamed from lambda_function.py to feeder.py for feeders
  and task.py for tasks, allowing better logging
- Lambda handler functions renamed from `lambda_handler` to `handler` since
  they could be Batch rather than lambdas
- Batch Compute Environment definitions moved to core/ directory
- API Lambda refactored to return collections in Cirrus static STAC catalog
- Handler function names changed for feeders to `feeder.handler`
- Handler function names changed for tasks to `task.handler`
- Logging refactored to do structured (JSON) logging

### Fixed

- Errors from batch now correctly reported to StateDB

### Removed

- `catids` no longer valid argument `rerun` payload - publish array of `catids`
  directly to Cirrus queue instead

## [v0.2.1] - 2020-09-10

### Added

- Failed workflows publish state db info to new SNS topic: `cirrus-<stage>-failed`
- STAC Lambda added for adding collections to the Cirrus root catalog. This is
  not currently required, but is good practice
- s3 inventory feeder: added support for s3 orc inventory files

### Removed

- assigning of collections in the `copy-assets` and `publish` Lambdas - this is
  done in cirrus-lib when parsing for a payload so this was redundant

### Changed

- cirrus-lib version updated to 0.3.1
- VisibilityTimeout and maxReceiveCount fields changed on Cirrus process lambda

### Fixed

- Updated version of batch jobs `geolambda-as-batch` and `lambda-as-batch`
- bug in s3 inventory feeder when using regex to extract date from filename

## [v0.2.0] - 2020-09-08

### Added

- `process` Lambda that consumes from ProcessQueue that both validates the
  payload and starts the workflow.
- `stac` Lambda added for adding Collections to the Cirrus Catalog
- `s2-inventory` for creating partial STAC Items (i.e., JSON with assets) from
  s3 inventory files
- `feed-stac-crawl` for adding Items by crawling a STAC catalog (using PySTAC)
- Retries added to all tasks in workflows
- Added back "post-batch" steps to all workflows

### Changed

- Update cirrus-lib to 0.3.0
- IAM configuration (previously batch/iam.yml) combined into Core resources (core.yml)
- `pre-batch` and `post-batch` Lambda functions moved from `core` to `tasks`
  (since they are tasks that can be used in a workflow)
- `add-preview` now suffixes thumbnails with `_thumb.png` instead of `_preview.png`
- Batch processes now write output payload back to a new file rather than
  overwriting the input payload.

### Removed

- `validation` and `start-workflow` Lambdas (replace with new `process` Lambda)
- ValidationQueue (SQS), now only 1 queue (ProcessQueue)

### Fixed

- `feed-stac-api` Lambda fixed to split requests by hours, not days. Fixes
  issue where there are more scenes in 1 day than the per request limit
- `lambda-as-batch` and `geolambda-as-batch` Batch tasks fixed to properly
  return newly returned STAC Catalog rather than the original one (which may
  have been modified as it is passed by reference to handler)
- `convert-to-cog` now properly populates `derived_from` link in newly created
  STAC Item

## [v0.1.0] - 2020-08-07

Initial release

[Unreleased]: https://github.com/cirrus-geo/cirrus-geo/compare/v1.1.1...main
[v1.1.1]: https://github.com/cirrus-geo/cirrus-geo/compare/v1.1.0...v1.1.1
[v1.1.0]: https://github.com/cirrus-geo/cirrus-geo/compare/v1.0.2...v1.1.0
[v1.0.2]: https://github.com/cirrus-geo/cirrus-geo/compare/v1.0.1...v1.0.2
[v1.0.1]: https://github.com/cirrus-geo/cirrus-geo/compare/v1.0.0...v1.0.1
[v1.0.0]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.15.4...v1.0.0
[v0.15.4]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.15.3...v0.15.4
[v0.15.3]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.15.1...v0.15.3
[v1.0.0a1]: https://github.com/cirrus-geo/cirrus-geo/compare/v1.0.0a0...v1.0.0a1
[v0.15.1]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.15.0...v0.15.1
[v1.0.0a0]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.15.0...v1.0.0a0
[v0.15.0]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.14.0...v0.15.0
[v0.14.0]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.13.0...v0.14.0
[v0.13.0]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.12.1...v0.13.0
[v0.12.1]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.12.0...v0.12.1
[v0.12.0]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.11.4...v0.12.0
[v0.11.4]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.11.3...v0.11.4
[v0.11.3]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.11.2...v0.11.3
[v0.11.2]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.11.1...v0.11.2
[v0.11.1]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.11.0...v0.11.1
[v0.11.0]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.10.1...v0.11.0
[v0.10.1]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.10.0...v0.10.1
[v0.10.0]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.9.0...v0.10.0
[v0.9.0]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.8.0...v0.9.0
[v0.8.0]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.7.0...v0.8.0
[v0.7.0]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.6.0...v0.7.0
[v0.6.0]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.5.4...v0.6.0
[v0.5.4]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.5.3...v0.5.4
[v0.5.3]: https://github.com/cirrus-geo/cirrus-geo/compare/v0.5.2...v0.5.3
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
[#78]: https://github.com/cirrus-geo/cirrus-geo/issues/78
[#79]: https://github.com/cirrus-geo/cirrus-geo/issues/79
[#82]: https://github.com/cirrus-geo/cirrus-geo/issues/82
[#85]: https://github.com/cirrus-geo/cirrus-geo/issues/85
[#98]: https://github.com/cirrus-geo/cirrus-geo/issues/98
[#99]: https://github.com/cirrus-geo/cirrus-geo/issues/99
[#102]: https://github.com/cirrus-geo/cirrus-geo/issues/102
[#103]: https://github.com/cirrus-geo/cirrus-geo/issues/103
[#104]: https://github.com/cirrus-geo/cirrus-geo/issues/104
[#105]: https://github.com/cirrus-geo/cirrus-geo/issues/105
[#106]: https://github.com/cirrus-geo/cirrus-geo/issues/106
[#107]: https://github.com/cirrus-geo/cirrus-geo/issues/107
[#108]: https://github.com/cirrus-geo/cirrus-geo/issues/108
[#111]: https://github.com/cirrus-geo/cirrus-geo/issues/111
[#114]: https://github.com/cirrus-geo/cirrus-geo/issues/114
[#116]: https://github.com/cirrus-geo/cirrus-geo/issues/116
[#120]: https://github.com/cirrus-geo/cirrus-geo/issues/120
[#123]: https://github.com/cirrus-geo/cirrus-geo/issues/123
[#128]: https://github.com/cirrus-geo/cirrus-geo/issues/128
[#131]: https://github.com/cirrus-geo/cirrus-geo/issues/131
[#132]: https://github.com/cirrus-geo/cirrus-geo/issues/132
[#135]: https://github.com/cirrus-geo/cirrus-geo/issues/135
[#134]: https://github.com/cirrus-geo/cirrus-geo/issues/134
[#139]: https://github.com/cirrus-geo/cirrus-geo/issues/139
[#140]: https://github.com/cirrus-geo/cirrus-geo/issues/140
[#145]: https://github.com/cirrus-geo/cirrus-geo/issues/145
[#147]: https://github.com/cirrus-geo/cirrus-geo/issues/147
[#149]: https://github.com/cirrus-geo/cirrus-geo/issues/149
[#154]: https://github.com/cirrus-geo/cirrus-geo/issues/154
[#155]: https://github.com/cirrus-geo/cirrus-geo/issues/155
[#158]: https://github.com/cirrus-geo/cirrus-geo/issues/158
[#169]: https://github.com/cirrus-geo/cirrus-geo/issues/169
[#172]: https://github.com/cirrus-geo/cirrus-geo/issues/172
[#173]: https://github.com/cirrus-geo/cirrus-geo/issues/173
[#174]: https://github.com/cirrus-geo/cirrus-geo/issues/174
[#177]: https://github.com/cirrus-geo/cirrus-geo/issues/177
[#178]: https://github.com/cirrus-geo/cirrus-geo/issues/178
[#180]: https://github.com/cirrus-geo/cirrus-geo/issues/180
[#182]: https://github.com/cirrus-geo/cirrus-geo/issues/182
[#193]: https://github.com/cirrus-geo/cirrus-geo/issues/193
[#202]: https://github.com/cirrus-geo/cirrus-geo/issues/202
[#225]: https://github.com/cirrus-geo/cirrus-geo/issues/225
[#242]: https://github.com/cirrus-geo/cirrus-geo/issues/242
[#255]: https://github.com/cirrus-geo/cirrus-geo/issues/255
[#71]: https://github.com/cirrus-geo/cirrus-geo/pull/72
[#72]: https://github.com/cirrus-geo/cirrus-geo/pull/72
[#73]: https://github.com/cirrus-geo/cirrus-geo/pull/73
[#87]: https://github.com/cirrus-geo/cirrus-geo/pull/87
[#88]: https://github.com/cirrus-geo/cirrus-geo/pull/88
[#89]: https://github.com/cirrus-geo/cirrus-geo/pull/89
[#90]: https://github.com/cirrus-geo/cirrus-geo/pull/90
[#138]: https://github.com/cirrus-geo/cirrus-geo/pull/138
[#143]: https://github.com/cirrus-geo/cirrus-geo/pull/143
[#160]: https://github.com/cirrus-geo/cirrus-geo/pull/160
[#207]: https://github.com/cirrus-geo/cirrus-geo/pull/207
[#224]: https://github.com/cirrus-geo/cirrus-geo/pull/224
[#226]: https://github.com/cirrus-geo/cirrus-geo/pull/226
[#230]: https://github.com/cirrus-geo/cirrus-geo/pull/230
[#231]: https://github.com/cirrus-geo/cirrus-geo/pull/231
[#245]: https://github.com/cirrus-geo/cirrus-geo/pull/245
[#246]: https://github.com/cirrus-geo/cirrus-geo/pull/246
[#247]: https://github.com/cirrus-geo/cirrus-geo/pull/247
[#248]: https://github.com/cirrus-geo/cirrus-geo/pull/248
[#249]: https://github.com/cirrus-geo/cirrus-geo/pull/249
[#253]: https://github.com/cirrus-geo/cirrus-geo/pull/253
[#254]: https://github.com/cirrus-geo/cirrus-geo/pull/254
[#256]: https://github.com/cirrus-geo/cirrus-geo/pull/256
[#259]: https://github.com/cirrus-geo/cirrus-geo/pull/259
[#261]: https://github.com/cirrus-geo/cirrus-geo/pull/261
[#263]: https://github.com/cirrus-geo/cirrus-geo/pull/263
[#264]: https://github.com/cirrus-geo/cirrus-geo/pull/264
[#266]: https://github.com/cirrus-geo/cirrus-geo/pull/266
[#267]: https://github.com/cirrus-geo/cirrus-geo/pull/267
[#268]: https://github.com/cirrus-geo/cirrus-geo/pull/268
[#270]: https://github.com/cirrus-geo/cirrus-geo/pull/270
[#272]: https://github.com/cirrus-geo/cirrus-geo/pull/272
[#274]: https://github.com/cirrus-geo/cirrus-geo/pull/274
[#276]: https://github.com/cirrus-geo/cirrus-geo/pull/276
[#277]: https://github.com/cirrus-geo/cirrus-geo/pull/277
[#278]: https://github.com/cirrus-geo/cirrus-geo/pull/278
[#279]: https://github.com/cirrus-geo/cirrus-geo/pull/279
[#280]: https://github.com/cirrus-geo/cirrus-geo/pull/280
[#283]: https://github.com/cirrus-geo/cirrus-geo/pull/283
[#290]: https://github.com/cirrus-geo/cirrus-geo/pull/290
[#292]: https://github.com/cirrus-geo/cirrus-geo/pull/292
[#294]: https://github.com/cirrus-geo/cirrus-geo/pull/294
[#295]: https://github.com/cirrus-geo/cirrus-geo/pull/295
[#297]: https://github.com/cirrus-geo/cirrus-geo/pull/297
[#300]: https://github.com/cirrus-geo/cirrus-geo/pull/300
[#303]: https://github.com/cirrus-geo/cirrus-geo/pull/303
[#305]: https://github.com/cirrus-geo/cirrus-geo/pull/305
[#306]: https://github.com/cirrus-geo/cirrus-geo/pull/306
[#311]: https://github.com/cirrus-geo/cirrus-geo/pull/311
[#315]: https://github.com/cirrus-geo/cirrus-geo/pull/315
[#317]: https://github.com/cirrus-geo/cirrus-geo/pull/317
[#319]: https://github.com/cirrus-geo/cirrus-geo/pull/319
[#324]: https://github.com/cirrus-geo/cirrus-geo/pull/324
[#326]: https://github.com/cirrus-geo/cirrus-geo/pull/326
[#330]: https://github.com/cirrus-geo/cirrus-geo/pull/330
[#331]: https://github.com/cirrus-geo/cirrus-geo/pull/331
[#337]: https://github.com/cirrus-geo/cirrus-geo/pull/337
[#339]: https://github.com/cirrus-geo/cirrus-geo/pull/339
[f25acd4]: https://github.com/cirrus-geo/cirrus-geo/commit/f25acd4f43e2d8e766ff8b2c3c5a54606b1746f2
[85464f5]: https://github.com/cirrus-geo/cirrus-geo/commit/85464f5a7cb3ef82bc93f6f1314e98b4af6ff6c1
[1b89611]: https://github.com/cirrus-geo/cirrus-geo/commit/1b89611125e2fa852554951343731d1682dd3c4c
[1e652f2]: https://github.com/cirrus-geo/cirrus-geo/commit/1e652f20ef38298f56ebc81aea0d61aaad135f67
[9f56981]: https://github.com/cirrus-geo/cirrus-geo/commit/9f569819d1c4a59fc71f15642b3ea0b30058c885
[44bebc5]: https://github.com/cirrus-geo/cirrus-geo/commit/44bebc5d1e2d802fc0e596be381fb3e1e1042170
[ba3e04b]: https://github.com/cirrus-geo/cirrus-geo/commit/ba3e04ba2c2ae554fecf9b80e22c71690a9eb518
[cl0.6.0]: https://github.com/cirrus-geo/cirrus-lib/releases/tag/v0.6.0
