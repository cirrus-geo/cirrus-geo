# Tests





## Testing with Payloads

There is a test payload in the payloads/ directory for each workflow. These tests require you have the [sentinel-s2-l2a](https://raw.githubusercontent.com/sat-utils/sat-stac-sentinel/develop/stac_sentinel/sentinel-s2-l2a.json) collection in your deployed STAC API.

The Payload scan be tested by publishing them to the Cirrus SNS topic:

```
$ aws sns publish --topic-arn <full-arn> --message file://payloads/publish-only.json