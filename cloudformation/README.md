# Cirrus CloudFormation Infrastructure

This directory contains CloudFormation templates for deploying **cirrus-geo**
infrastructure on AWS.

## Overview

The CloudFormation implementation consists of:

- **Base Infrastructure**: S3 buckets, DynamoDB state table, SQS queues, SNS topics
- **VPC**: Virtual Private Cloud with public/private subnets
- **Lambda Functions**: 5 core functions (API, Process, Update State, Pre-Batch,
  Post-Batch) with IAM roles
- **API Gateway**: REST API (EDGE) with Lambda integration and CloudWatch logging
- **CLI Configuration**: Parameter Store setup for cirrus CLI deployment discovery

The CloudFormation templates are modular and use nested stacks for organization.

## Directory Structure

```bash
cloudformation/
├── main.yaml                   # Main template (entry point)
├── parameters.json             # Parameter file with default values
├── bootstrap/
│   └── bootstrap.yaml          # Bootstrap template (S3 bucket for deployment artifacts)
├── core/
│   ├── base.yaml               # Base infrastructure template (S3, DynamoDB, SQS, SNS)
│   ├── functions.yaml          # Lambda function template (functions, roles, security group)
│   ├── api.yaml                # API Gateway template (for Cirrus API)
│   ├── vpc.yaml                # VPC and networking template
│   └── lambda-packages/        # Zipped Python code for Lambda functions
├── cli/
│   └── ssm_parameters.yaml     # CLI template (for deployment discovery via Parameter Store)
└── workflows/
    └── minimal/                # Minimal test workflow
        ├── state_machine.yaml
        └── payload.json
```

## Quick Start

### Prerequisites

1. **AWS CLI** installed and configured
2. **Python 3.12+** for Lambda function packaging
3. AWS credentials with appropriate permissions

### Basic Deployment

1. **Set parameters and stack names**

   - Change parameters in `cloudformation/parameters.json` as needed.
   - Choose names for the bootstrap, main, and workflow CloudFormation stacks and
     export as environment variables. For example:

     ```bash
     export BOOTSTRAP_STACK="cirrus-bootstrap"
     export MAIN_STACK="cirrus-sandbox"
     export MINIMAL_WORKFLOW_STACK="cirrus-sandbox-minimal-workflow"
     ```

   - Export the location for the Lambda deployment packages. This is used by the
     `build/lambda-dist.bash` script.

     ```bash
     export CIRRUS_LAMBDA_ZIP_DIR="./cloudformation/core/lambda-packages"
     ```

2. **Deploy bootstrap stack** (creates S3 bucket for deployment artifacts):

   ```bash
   aws cloudformation deploy \
     --stack-name "$BOOTSTRAP_STACK" \
     --template-file cloudformation/bootstrap/bootstrap.yaml \
     --parameter-overrides file://cloudformation/parameters.json
   ```

   Note: This command is using CloudFormation's deploy operation, which is a
   "create-or-update" style of operation. It will modify an existing $BOOTSTRAP_STACK,
   if one exists.

3. **Package Lambda functions**:

   ```bash
   ./bin/build-lambda-dist.bash
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
     --parameter-overrides file://cloudformation/parameters.json \
     --capabilities CAPABILITY_NAMED_IAM
   ```

5. **Get deployed resource information**:

   ```bash
   aws cloudformation describe-stacks --stack-name "$MAIN_STACK" \
     --query 'Stacks[0].Outputs | sort_by(@, &Description)' \
     --output table
   ```

## Deploying Workflows

Workflows are deployed as separate stacks to allow rapid iteration without affecting the
main infrastructure.

### Minimal Workflow

Deploy the minimal test workflow:

```bash
aws cloudformation deploy \
  --template-file cloudformation/workflows/minimal/state_machine.yaml \
  --stack-name "$MINIMAL_WORKFLOW_STACK" \
  --parameter-overrides file://cloudformation/parameters.json \
  --capabilities CAPABILITY_NAMED_IAM
```

The minimal workflow contains a single `ChoiceState` that checks for a particular value
in the `workflow` field in the payload. Use `workflows/minimal/payload.json` for
testing. You can change the `workflow` value to something other than "minimal" to make
the workflow fail.

## Cleanup

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
