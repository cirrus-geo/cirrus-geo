# Cirrus CloudFormation Infrastructure

This directory contains CloudFormation templates for deploying **cirrus-geo**
infrastructure to AWS or LocalStack.

## Overview

The CloudFormation implementation consists of:

- **Base Infrastructure**: S3 buckets, DynamoDB state table, SQS queues, SNS topics
- **VPC** (optional): Virtual Private Cloud with public/private subnets
- **Lambda Functions**: 5 core functions (API, Process, Update State, Pre-Batch,
  Post-Batch) with IAM roles
- **API Gateway**: REST API (EDGE) with Lambda integration and CloudWatch logging
- **CLI Configuration**: Parameter Store setup for cirrus CLI deployment discovery

The CloudFormation templates use nested stacks for organization.

## Directory Structure

```bash
cloudformation/
├── main.yaml                   # Main template (entry point)
├── bootstrap/
│   └── bootstrap.yaml          # Bootstrap template (S3 bucket for deployment artifacts)
├── core/
│   ├── base.yaml               # Base infrastructure template (S3, DynamoDB, SQS, SNS)
│   ├── functions.yaml          # Lambda function template (functions, roles, security group)
│   ├── api.yaml                # API Gateway template (for Cirrus API)
│   ├── vpc.yaml                # VPC and networking template (optional)
│   └── lambda-packages/        # Zipped Python code for Lambda functions
├── cli/
│   └── ssm_parameters.yaml     # CLI template (for deployment discovery via Parameter Store)
└── workflows/
    └── minimal/                # Minimal test workflow
        ├── state_machine.yaml
        └── payload.json
```

## AWS Deployment

### Prerequisites

1. **AWS CLI** installed and configured
2. **Python 3.12+** for Lambda function packaging
3. AWS credentials with appropriate permissions in your environment

### Bootstrap and Main Stack Deployment

1. **Configure deployment**

   - Copy `.env.aws.example` to `.env.aws` (in the project root)
   - Edit `.env.aws` to customize stack names and deployment parameters
   - Source the environment file: `source .env.aws`

2. **Deploy bootstrap stack** (creates S3 bucket for deployment artifacts):

   ```bash
   aws cloudformation deploy \
     --stack-name "$BOOTSTRAP_STACK" \
     --template-file cloudformation/bootstrap/bootstrap.yaml \
     --parameter-overrides \
       "ResourcePrefix=$RESOURCE_PREFIX"
   ```

   > [!NOTE]
   > The use of CloudFormation's `deploy` operation here and elsewhere, which is a
   > "create-or-update" style of operation, will modify an existing stack, if one
   > exists.

3. **Package Lambda functions**:

   ```bash
   ./bin/build-lambda-dist.py \
       -p "$LAMBDA_PYTHON_VERSION" \
       -a "$LAMBDA_ARCH" \
       -o "cloudformation/core/lambda-packages/cirrus-lambda-dist.zip"
   ```

4. **Package and deploy the main stack**:

   ```bash
   # Get the S3 bucket for packaging
   ARTIFACT_BUCKET=$(aws cloudformation describe-stacks \
     --stack-name "$BOOTSTRAP_STACK" \
     --query 'Stacks[0].Outputs[?OutputKey==`CirrusDeploymentArtifactsBucket`].OutputValue' \
     --output text)

   # Package templates and Lambda code
   aws cloudformation package \
     --template-file cloudformation/main.yaml \
     --s3-bucket "$ARTIFACT_BUCKET" \
     --output-template-file packaged-template.yaml

   # Deploy the packaged stack
   aws cloudformation deploy \
     --stack-name "$MAIN_STACK" \
     --template-file packaged-template.yaml \
     --parameter-overrides \
       "ResourcePrefix=$RESOURCE_PREFIX" \
       "LambdaPythonVersion=$LAMBDA_PYTHON_VERSION" \
       "LambdaArch=$LAMBDA_ARCH" \
       "LogLevel=$LOG_LEVEL" \
       "EnableVpc=$ENABLE_VPC" \
       "VpcCidr=$VPC_CIDR" \
       "PrivateSubnetCidr=$PRIVATE_SUBNET_CIDR" \
       "PublicSubnetCidr=$PUBLIC_SUBNET_CIDR" \
     --capabilities CAPABILITY_NAMED_IAM
   ```

5. **Get deployed resource information**:

   ```bash
   aws cloudformation describe-stacks --stack-name "$MAIN_STACK" \
     --query 'Stacks[0].Outputs | sort_by(@, &Description)' \
     --output table
   ```

### Workflow Deployment

Workflows are deployed as separate stacks to allow rapid iteration without affecting the
main infrastructure. A minimal example workflow is provided in
`cloudformation/workflows/minimal` and is deployed with:

```bash
aws cloudformation deploy \
  --template-file cloudformation/workflows/minimal/state_machine.yaml \
  --stack-name "$MINIMAL_WORKFLOW_STACK" \
  --parameter-overrides \
    "ResourcePrefix=$RESOURCE_PREFIX" \
  --capabilities CAPABILITY_NAMED_IAM
```

The minimal workflow contains a single `ChoiceState` that checks the `succeed`
field in the first entry of the payload `process` block for a boolean `true`
value. Use `cloudformation/workflows/minimal/payload.json.template` for
testing:

```bash
<cloudformation/workflows/minimal/payload.json.template cirrus payload template \
    | cirrus management $RESOURCE_PREFIX run-workflow
```

Set the `succeed` field to `false` to generate a failed state machine
execution via the cirrus cli payload templating function:

```bash
<cloudformation/workflows/minimal/payload.json.template cirrus payload template \
    -x succeed false \
    | cirrus management $RESOURCE_PREFIX run-workflow
```

The `replace` flag can also be set to `true` if desired (default false), and a
unique ID can be created by setting the `id_suffix` var (default is not set a
suffix).

```bash
<cloudformation/workflows/minimal/payload.json.template cirrus payload template \
    -x succeed false \
    -x replace true \
    -x id_suffix "-$(uuidgen)" \
    | cirrus management $RESOURCE_PREFIX run-workflow
```

### Stack Cleanup

1. **Empty S3 buckets** (required before stack deletion):

   ```bash
   # Get bucket names
   DATA_BUCKET=$(aws cloudformation describe-stacks \
     --stack-name "$MAIN_STACK" \
     --query 'Stacks[0].Outputs[?OutputKey==`CirrusDataBucket`].OutputValue' \
     --output text)

   PAYLOAD_BUCKET=$(aws cloudformation describe-stacks \
     --stack-name "$MAIN_STACK" \
     --query 'Stacks[0].Outputs[?OutputKey==`CirrusPayloadBucket`].OutputValue' \
     --output text)

   ARTIFACT_BUCKET=$(aws cloudformation describe-stacks \
     --stack-name "$BOOTSTRAP_STACK" \
     --query 'Stacks[0].Outputs[?OutputKey==`CirrusDeploymentArtifactsBucket`].OutputValue' \
     --output text)

   # Empty buckets
   aws s3 rm s3://$DATA_BUCKET --recursive
   aws s3 rm s3://$PAYLOAD_BUCKET --recursive
   aws s3 rm s3://$ARTIFACT_BUCKET --recursive
   ```

2. **Delete the stacks** (workflows first, then main stack, then bootstrap):

   ```bash
   # Delete workflow stacks (if deployed). Example for the minimal workflow:
   aws cloudformation delete-stack --stack-name "$MINIMAL_WORKFLOW_STACK"
   aws cloudformation wait stack-delete-complete --stack-name "$MINIMAL_WORKFLOW_STACK"

   # Delete main stack:
   aws cloudformation delete-stack --stack-name "$MAIN_STACK"
   aws cloudformation wait stack-delete-complete --stack-name "$MAIN_STACK"

   # Delete bootstrap stack:
   aws cloudformation delete-stack --stack-name "$BOOTSTRAP_STACK"
   aws cloudformation wait stack-delete-complete --stack-name "$BOOTSTRAP_STACK"
   ```

## LocalStack Deployment

Deploying **cirrus-geo** to LocalStack is scripted for convenience. The script
`bin/localstack-provision.bash` handles packaging and deployment of the bootstrap,
main, and minimal workflow stacks and can also delete the stacks via command line
arguments.

```bash
./bin/localstack-provision.bash [bootstrap|debootstrap|deploy|delete]
```

### Prerequisites

1. **AWS CLI** installed and configured
2. **Python 3.12+** for Lambda function packaging
3. **Docker** to run LocalStack via compose

### Stack Deployment

1. **Configure deployment**

   - Copy `.env.localstack.example` to `.env.localstack` (in the project root)
   - Edit `.env.localstack` to customize stack names, Lambda configuration, and other
     deployment parameters
   - Source the environment file: `source .env.localstack`

2. **Start LocalStack**

   ```bash
   docker compose up -d -V
   ```

3. **Deploy the bootstrap stack**

   ```bash
   ./bin/localstack-provision.bash bootstrap
   ```

4. **Deploy the main and minimal workflow stacks**

   ```bash
   ./bin/localstack-provision.bash deploy
   ```

The `deploy` command can be used repeatedly as an idempotent way to apply stack
updates.

> [!NOTE]
> Sometimes LocalStack can get into a broken state when trying to
> apply/rollback bad CloudFormation, such as when using LocalStack to test
> CloudFormation changes during development. If the `deploy` command results in
> the system entering an unrecoverable state, restarting LocalStack by
> re-running `docker compose up -d -V`  and redeploying from the bootstrap
> stage will be required.

### Interacting with LocalStack-deployed Infrastructure

You can use standard AWS CLI commands to interact with the LocalStack-deployed
infrastructure. For example, to list S3 buckets:

```bash
aws s3 ls
```

To call the API Gateway endpoint, you will need the API ID:

```bash
API_ID=$(aws cloudformation describe-stacks \
  --stack-name "$MAIN_STACK" \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayId`].OutputValue' \
  --output text)
```

Then:

```bash
curl "http://localhost:4566/restapis/${API_ID}/dev/_user_request_/<desired_path>"
```

For example, to list items in the state database for the minimal workflow:

```bash
curl "http://localhost:4566/restapis/${API_ID}/dev/_user_request_/collection/workflow-minimal/items"
```

### Stack Cleanup

1. **Delete the main stack**

   ```bash
   ./bin/localstack-provision.bash delete
   ```

2. **Delete the bootstrap stack**

   ```bash
   ./bin/localstack-provision.bash debootstrap
   ```
