# Cutomizing Cirrus

## Per-bucket credentials

Some workflows will require accessing s3 buckets with a different set of
AWS credentials. In these cases all that is required is to add an AWS Secret
with the name `cirrus-creds-<bucketname>` and add in key-value pairs for
`aws_access_key_id`, `aws_secret_access_key`, and `region_name`. Any additional
parameters accepted by
[boto3.Session](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/core/session.html)
can also be included. As long as the `cirrus-lib` transfer module is used to
create an s3 session, the credentials from the secret will be used.
