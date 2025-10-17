Authentication
==============

Because CLIrrus interacts directly with AWS resources via the AWS python API
with the boto3 library, you will have to be authenticated with AWS.  We
recommend folllowing your organization's best practice recommendations for
authentication. One way you could do so is to use the `AWS CLI tool`_.

Look `here`_ for an in depth explanation of authentication options with the AWS
command line tool and how to configure SSO login.

CLIrrus will only need to be installed once, but authenticatig with AWS
will be necessary for each new session as AWS credentials expire and must be
refreshed every so often.  This can be easily accomplished with the AWS CLI
single sign on (SSO) option.

After you have built your config file according to organizational or personal
preference you can login with

.. code-block:: bash

    aws sso login --profile your-named-profile

One you have successfully SSO'd setup will be complete for CLIrrus

.. _AWS CLI tool: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html
.. _AWS config file: https://docs.aws.amazon.com/cli/v1/userguide/cli-configure-files.html
.. _here: https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html
