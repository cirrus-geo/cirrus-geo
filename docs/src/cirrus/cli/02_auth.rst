CLIrrus Authentication
=========================

Because CLIrrus interacts directly with AWS resources via the
AWS python API with the boto3 library, you will have to be authenticated with AWS. The easiest way to do this will be to use the `AWS CLI tool`_.

CLIrrus will only need to be installed once, but authenticatig with AWS
will be necessary for each new session as AWS credentials expire and must be
refreshed every so often.  The best way to retrieve and store these credentials is with the AWS CLI single sign on (SSO) option.

To execute the AWS SSO command you will need to have an `AWS config file`_ so
that the AWS CLI SSO command can access the necessary account information in
that config file.

A config file needs to live in the discoverable ``.aws/config`` location. The
config file is broken into sections for different profiles that are assigned
names of your choice.

Required key value pairs are:

- sso_session: A user assigned name given to the session
- sso_account_id: AWS account ID to use to authenticate
- sso_role_name: A valid AWS role assigned to the account ID
- region: AWS Region to SSO into

After you have built your config file you can login with

.. code-block:: bash

    aws sso login --profile your-named-profile

One you have successfully SSO'd setup will be complete for CLIrrus

.. _AWS CLI tool: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html
.. _AWS config file: https://docs.aws.amazon.com/cli/v1/userguide/cli-configure-files.html
