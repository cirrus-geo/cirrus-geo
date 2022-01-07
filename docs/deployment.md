# Cirrus Deployment

Cirrus uses the [serverless](https://www.serverless.com/) framework for
packaging and deployment. The `cirrus` CLI tooling provides a veneer over
top of serverless to allow the Cirrus project structure and reduce boiler
plate.

Running `cirrus init` in a directory will initialize a new project within.
As part of that initialization, a `cirrus.yml` config file will be created,
along with a `package.json` file containing the serverless and serverless
plugin versions required by Cirrus. An `npm install` will install serverless
and the requried plugins in the project directory.


## Cirrus Configuration

The `cirrus.yml` configuration file is, more or less, a serverless configuration
file minus all the pieces that get assembled at build time. Out of the box, it
is almost ready to go, but some minor customization is required.

```yaml
service: cirrus

provider:
  stage: ${opt:stage, 'dev'}
  region: ${opt:region, 'us-west-2'}
  ...

custom:
  batch:
    SecurityGroupIds:
      - ${env:SECURITY_GROUP_1}
      - ${env:SECURITY_GROUP_2}
      - ...
    Subnets:
      - ${env:SUBNET_1}
      - ${env:SUBNET_2}
      - ...
```

The `service` name defaults to `cirrus`, but can be updated as required for
a given deployment.

The default `stage` and `region` in the `provider` block can be changed from
`dev` and `us-west-2`. They can also be specified at deploy time as options to
the `cirrus serverless` command.

The deployed CloudFormation stack will be named `<service>-<stage>`, so the
`service` and/or `stage` need to be changed if multiple Cirrus deployments will
exist within the same account.

The `custom` section contains some additional user defined variables.
`SecurityGroupIds` and `Subnets` reference Environment Variables.
Define 1 or more environment variables `SECURITY_GROUP_X` and `SUBNET_X`
and edit the `cirrus.yml` file accordingly (the number defined in the
environment in the config must be equal). `SECURITY_GROUP_X` is an
AWS Security Group (EC2->Security Groups in AWS Console).
Every AWS account should have a default Security Group which can be used,
or SecurityGroup(s) from a custom VPC. `Subnets` are the IDs of 1 or more
(preferably 4 or more) Subnets (VPC->Subnets in AWS Console).


## Deploy!

Once `cirrus.yml` has been edited, you are ready to package and deploy.
To use `serverless` it must be installed via the `npm install` command
previously mentioned.

The `serverless` framework will build/package all the Lambda functions before
deploying using the `serverless-python-requirements` plugin. Note that
the common dependency `cirrus-lib` will be automaticall injected into all
Lambdas packaged in a Cirrus project, along with its dependencies.

```
# Deploy the project
$ cirrus serverless deploy

# Just build/package, don't deploy anything
# Note that serverless is also aliased to sls
$ cirrus sls package

# Specify a stage
$ cirrus sls deploy --stage myStage
```

Deployment can take several minutes or more due to the Lambda packaging.
Once completed there should be a CloudFormation stack named `<service>-<stage>`,
along with all the resources: DynamoDB, SQS, SNS, Lambda, Batch Compute
Environments, Batch Jobs, and Step Functions, all named starting with
`<service>-<stage>`.


## Using a STAC API

Cirrus does not include a STAC API, it only writes static files.
It is recommended to use a STAC API, such as
[stac-server](https://github.com/stac-utils/stac-server),
to index the metadata so it can be searched. If using stac-server,
the ingest SQS can subscribe to the Cirrus Publish SNS to add published
items to the index. A Filter can be added to the subscription
(AWS Console SNS->Subscriptions) to only index certain Items, if desired.
