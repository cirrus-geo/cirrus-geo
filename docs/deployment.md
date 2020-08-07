# Cirrus Deployment

Cirrus uses the [serverless](https://www.serverless.com/) framework for packaging and deployment. Everything needed to deployed is within the `cirrus` repository:

```
$ git clone https://github.com/cirrus-geo/cirrus
```

## Serverless Configuration

Once cloned you will need to make a copy of the `serverless.yml.example`, save as `serverless.yml` and edit the files relevant sections are shown here:

#### serverless.yml

```yaml
provider:
  stage: ${opt:stage, 'dev'}
  region: ${opt:region, 'us-west-2'}
custom:
  batch:
    SecurityGroupIds:
      - <SECURITY_GROUP_1>
      - <SECURITY_GROUP_2>
      - ...
    Subnets:
      - <SUBNET_1>
      - <SUBNET_2>
      - ...
    BasicComputeEnvironments:
      MaxvCpus: 128
```

The default `stage` and `region` in the `provider` block can be changed from `dev` and `us-west-2` (they can also be specified at deploy time). The deployed CloudFormation stack will be named `cirrus-<stage>`, so the stage needs to be changed if there are multiple Cirrus deployments.

The `custom` section contains some additional user defined variables. `SecurityGroupIds` needs to be updated to include an AWS Security Group (EC2->Security Groups in AWS Console). Every AWS account should have a default Security Group which can be used, or a SecurityGroup from a custom VPC. `Subnets` needs to be updated to include 1 or more (preferably 4 or more) Subnets (VPC->Subnets in AWS Console)

The `BasicComputeEnvironments.MaxvCpus` controls the maximum number of Virtual CPUs that can run at one time in AWS Batch. The number of vCPUs, and required memory, for each Batch Job is specified in [jobs.yml](../batch/jobs.yml)


## Deploy!

Once `serverless.yml` has been edited, you are ready to package and deploy. To use `serverless` it must be installed. If `NVM` is used there is an `.nvmrc` file included, otherwise use NodeJS v12.13.

```
# If using NVM, this will switch to correct NodeJS version
$ nvm use

# Installs serverless and dependencies, must be run from the root directory of the repo
$ npm install
```

The `serverless` framework will build/package all the Lambda functions before deploying using the `serverless-python-requirements` plugin.

```
# Calls the `deploy` npm script
$ npm run deploy

# The above npm script effectively runs the following command to run serverless directly.  If running directly `serverless` will need to be installed globally with `npm install -g serverless`
$ sls deploy

# Just build/package, don't deploy anything
$ sls deploy --noDeploy

# Specify a stage
$ sls deploy --stage myStage
```

Deployment can take 20 minutes or more. Once completed there should be a CloudFormation stack named `cirrus-<stage>`, along with all the resources: DynamoDB, SQS, SNS, Lambda, Batch Compute Environments, Batch Jobs, and Step Functions, all starting with `cirrus-<stage>`


## Using a STAC API

Cirrus does not include a STAC API, it only writes static files. It is recommended to use a STAC API, such as [stac-server](https://github.com/stac-utils/stac-server), to index the metadata so it can be searched. If using stac-server, the SQS can be subscribed to the Cirrus Publish SNS to add published items to the index. A Filter can be added to the subscription (AWS Console SNS->Subscriptions) to only index certain Items.