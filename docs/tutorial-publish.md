# Workflow Tutorial: publish-only

In this tutorial the AWS CLI will be used, which can be installed via pip:

```
$ pip install awscli
```

The Cirrus `publish-only` workflow only does one thing: it takes all the Input STAC Items and "publishes" each one. If the publishing task is successful then the workflow ends. If it fails it will invoke other error handling tasks, as can be seen in the Step Function diagram:

![](images/workflow-publish-only.png)

In Cirrus publishing means:

- A message is published to the SNS topic `cirrus-<stage>-publish`
- The STAC Item is written to the s3 bucket named `cirrus-<stage>-data-<random-string>` (`random-string` is string assigned by the Serverless framework during deploy)

## Run the workflow

To run the example workflow:

- copy the [publish-only example Input Catalog](examples/publish-only.json) locally and name it `payload.json`
- get the ARN (Amazon Resource Name) for the SNS topic. In AWS Console navigate to SNS and look for topic named `cirrus-<stage>-queue`, where `<stage>` is the stage specified during deployment (defaults to `dev`). Copy provided ARN for that topic
- Run the following AWS command:

```
$ aws sns publish --topic-arn <queue-topic-arn> --message file://payload.json
```

If successful, the CLI will return JSON indicating a unique identifier for the message, you don't need to keep this.

## What happened?

Look at the `payload.json` file. Under `features` it has a single STAC Item for a Sentinel-2 scene. The `process` block looks like:

```json
{
    "workflow": "publish-only",
    "output_options": {
        "path_template": "${collection}/${year}/${month}/${id}",
        "collections": {
            "my-collection": ".*"
        }
    },
    "tasks": {
        "publish": {
            "public": true
        }
    }
}
```

In addition to specifying the `publish-only` workflow, this `process` block says to:

- set the collection on the Item to `my-collection`. The value `.*` is a regex expression used against the `id` of the Item. In this case all items are assigned the `my-collection` collection
- save the output STAC Items in the data bucket using a templated path where the components are retrieved from the STAC Item. 
- Pass the parameter `publish=true` to the `publish function (this will make the item publicly available over https from s3)

To verify operation, look at the contents of the `cirrus-<stage>-data-<random-string>` bucket:

```
$ aws s3 ls s3://cirrus-<stage>-data-<random-string>
```

which should show the file published:

```
s3://cirrus-<stage>-data-<random-string>/my-collection/2020/07/S2B_26PPC_20200728_0_L2A/S2B_26PPC_20200728_0_L2A.json
```

The output STAC Item was also published to SNS, but if no subscription is set up it would not have been delivered anywhere. Use the AWS Console to also explore:

- Step Functions should indicate 1 execution in the `publish-only` Step Function
- The `cirrus-<dev>-state` DynamoDB should show a single Item where `cirrus_state` starts with `COMPLETED`
- The `/aws/lambda/cirrus-<stage>-publish` CloudWatch Log Group should contain logs for the publishing and will indicate the STAC Item being added to s3 and published to SNS

## Subscribe to Cirrus SNS Publish Topic

To verify that the STAC Item was published to the SNS `cirrus-<dev>-publish` topic, a subscription first needs to be set up. SNS does not save messages, it is not a queue, so if there are no subscriptions that it means the message was not delivered anywhere.

Using the AWS Console set up an email subscription to the `cirrus-<dev>-publish` topic, then publish the payload again:

```
$ aws sns publish --topic-arn <queue-topic-arn> --message file://payload.json
```

It will appear to have been successfully run, however if you look at how many executions there are in the `publish-only` Step Function, there is still just one. This is because Cirrus checked the Input Catalog and saw that it had been run and completed successfully. We could either publish a different STAC Item, or indicate that Cirrus should replace the existing one, update the `process` block in `payload.json` with the `replace` field:

```json
{
    "workflow": "publish-only",
    "replace": true,
    "output_options": {
        "path_template": "${collection}/${year}/${month}/${id}",
        "collections": {
            "my-collection": ".*"
        }
    },
    "tasks": {
        "publish": {
            "public": true
        }
    }
}
```

Then republish the message. Now a second exucution will be seen, and the message should have been delivered to the email used in the subscription. Note that under normal operation it is not advisable to use email based subscriptions, as this can easily be overloaded and hit AWS limits. Instead the publish topic is useful for other services to subscribe to, such as an SQS Queue or a Lambda function.
