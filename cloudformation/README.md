# Cirrus CloudFormation Infrastructure

This directory contains CloudFormation templates for deploying **cirrus-geo**
infrastructure on AWS. This implementation provides a canonical Infrastructure as Code
(IaC) definition for the **cirrus-geo** project and provides a means for sandbox
deployments for development and testing.

## Overview

The CloudFormation implementation consists of:

- **Base Infrastructure**: S3 buckets, DynamoDB state table, Timestream database, SQS
  queues, SNS topics
- **Lambda Functions**: 5 core functions (API, Process, Update State, Pre-Batch,
  Post-Batch) with IAM roles
- **API Gateway**: REST API (EDGE) with Lambda integration and CloudWatch logging

The CloudFormation templates are modular and use nested stacks for organization.

## Directory Structure

```bash
cloudformation/
├── cirrus-bootstrap.yaml        # Bootstrap template (S3 bucket for deployment artifacts)
├── cirrus-main.yaml             # Main template (entry point)
├── core/                        # Core stack templates
│   ├── cirrus-base.yaml         # Base infrastructure (S3, DynamoDB, Timestream, SQS, SNS)
│   ├── cirrus-functions.yaml    # Lambda functions with IAM roles
│   ├── cirrus-api.yaml          # API Gateway and related resources
│   └── cirrus-vpc.yaml          # VPC and networking (2-AZ setup)
├── parameters.json              # Parameter file with sensible defaults
└── deployment-artifacts/        # Directory for packaged Lambda code (created by build script)
```

## Quick Start

### Prerequisites

1. **AWS CLI** installed and configured
2. **Python 3.12+** for Lambda function packaging
3. AWS credentials with appropriate permissions

### Basic Deployment

1. **Deploy bootstrap stack** (creates S3 bucket for deployment artifacts):

   ```bash
   aws cloudformation create-stack \
     --stack-name cirrus-bootstrap \
     --template-body file://cloudformation/cirrus-bootstrap.yaml \
     --parameters file://cloudformation/parameters.json

   # Wait for bootstrap to complete
   aws cloudformation wait stack-create-complete --stack-name cirrus-bootstrap
   ```

2. **Package Lambda functions**:

   ```bash
   ./bin/build-lambda-dist.bash
   ```

   Copy the `cirrus-lambda-dist.zip` file that was created into the
   `cloudformation/lambda-packages/` directory.

3. **Package and deploy the main stack**:

   ```bash
   # Get the S3 bucket for packaging
   S3_BUCKET=$(aws cloudformation describe-stacks --stack-name cirrus-bootstrap \
     --query 'Stacks[0].Outputs[?OutputKey==`CirrusDeploymentArtifactsBucket`].OutputValue' --output text)

   # Package templates and Lambda code
   aws cloudformation package \
     --template-file cloudformation/cirrus-main.yaml \
     --s3-bucket $S3_BUCKET \
     --output-template-file packaged-template.yaml

   # Deploy the packaged stack
   aws cloudformation create-stack \
     --stack-name cirrus-sandbox \
     --template-body file://packaged-template.yaml \
     --parameters file://cloudformation/parameters.json \
     --capabilities CAPABILITY_NAMED_IAM
   ```

4. **Wait for deployment to complete**:

   ```bash
   aws cloudformation wait stack-create-complete --stack-name cirrus-sandbox
   ```

5. **Get deployed resource information**:

   ```bash
   aws cloudformation describe-stacks --stack-name cirrus-sandbox \
     --query 'Stacks[0].Outputs | sort_by(@, &OutputKey)' \
     --output table
   ```

## Cleanup

1. **Empty S3 buckets** (required before stack deletion):

   ```bash
   # Get bucket names
   DATA_BUCKET=$(aws cloudformation describe-stacks --stack-name cirrus-sandbox \
     --query 'Stacks[0].Outputs[?OutputKey==`CirrusDataBucket`].OutputValue' --output text)

   PAYLOAD_BUCKET=$(aws cloudformation describe-stacks --stack-name cirrus-sandbox \
     --query 'Stacks[0].Outputs[?OutputKey==`CirrusPayloadBucket`].OutputValue' --output text)

   ARTIFACT_BUCKET=$(aws cloudformation describe-stacks --stack-name cirrus-bootstrap \
     --query 'Stacks[0].Outputs[?OutputKey==`CirrusDeploymentArtifactsBucket`].OutputValue' --output text)

   # Empty buckets
   aws s3 rm s3://$DATA_BUCKET --recursive
   aws s3 rm s3://$PAYLOAD_BUCKET --recursive
   aws s3 rm s3://$ARTIFACT_BUCKET --recursive
   ```

2. **Delete the stacks** (main stack first, then bootstrap):

   ```bash
   # Delete main stack
   aws cloudformation delete-stack --stack-name cirrus-sandbox
   aws cloudformation wait stack-delete-complete --stack-name cirrus-sandbox

   # Delete bootstrap stack
   aws cloudformation delete-stack --stack-name cirrus-bootstrap
   aws cloudformation wait stack-delete-complete --stack-name cirrus-bootstrap
   ```
