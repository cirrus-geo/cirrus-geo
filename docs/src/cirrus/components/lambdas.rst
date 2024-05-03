Lambda-based components
=======================

Components that use Lambda (feeders, functions, and some tasks) share a common
set of required files and ``definition.yml`` format.


Required files
--------------

In addition to the ``definition.yml`` and ``README.md`` files required by all
components, Lambda-based components also require a ``lambda_function.py`` Python
file implementing a ``lambda_handler`` function, which serves as the Lambda
execution entry point. Like all components, these files are contained within a
directory named for the component within its component type's directory.

For example, if we have a Lambda task component named ``reproject``, we would
end up with a directory structure that looks like this::

    <project_dir>/
        tasks/
            reproject/
                definition.yml
                README.md
                lambda_function.py

The contents of a Lambda-based component's directory--minus the
``definition.yml`` file--will be packaged into a Lambda deployment zip file and
uploaded to AWS on project deploy. Any additional files added by the user will
also be included in the Lambda zip.


Definition file
---------------

The ``definition.yml`` contains a Lambda component's configuration. The format
is similar to that used by the Serverless Framework, which underlies cirrus's
deployment mechanism, but is subtly different.

Here is an example ``definition.yml`` file for a Lambda component::

    description: A sample lambda description string
    environment:
      COMPONENT_LEVEL_VAR: some value
      OVERRIDDEN_VAR: another_value
    enabled: true
    lambda:
      enabled: true
      memorySize: 1024
      timeout: 60
      runtime: python3.7
      environment:
        LAMBDA_LEVEL_VAR: 13
        OVERRIDDEN_VAR: new_value
      layers:
        - arn:aws:lambda:${self:provider.region}:552188055668:layer:geolambda:2
      pythonRequirements:
        include:
          - rasterio==1.2.8
          - rio-cogeo~=1.1.10
      iamRoleStatements:
        - Effect: "Allow"
          Action:
            - "s3:PutObject"
          Resource:
            - !Join
              - ''
              - - 'arn:aws:s3:::'
                - ${self:provider.environment.CIRRUS_DATA_BUCKET}
                - '*'
        - Effect: "Allow"
          Action:
            - "s3:ListBucket"
            - "s3:GetObject"
            - "s3:GetBucketLocation"
          Resource: "*"
        - Effect: "Allow"
          Action: secretsmanager:GetSecretValue
          Resource:
            - arn:aws:secretsmanager:#{AWS::Region}:#{AWS::AccountId}:secret:cirrus-creds-*

Generally speaking, the ``lambda`` key's value supports the same configuration
parameters as `Serverless Functions`_, with a few key differences. Consult that
Serverless documentation for a full list of supported parameters, along with
the following list of Cirrus-specific properties/behaviors.

.. _Serverless Functions: https://www.serverless.com/framework/docs/providers/aws/guide/functions

Description
***********

The top-level ``description`` value is used for the component's description
within Cirrus, as is also added to the ``lambda`` configuration during the
``cirrus build`` configuration compiliation process. So there's no need to
specify it twice.

Enabled state
*************

Components can be disabled within Cirrus, which will exclude them from the
compiled configuration. All components support a top-level ``enabled`` parameter
to completely enable/disable the component. Lambda-based components also support
an ``enabled`` parameter under the ``lambda`` key, which will enable/disable
just the Lambda portion of the component.

For Lambda-only components these ``enabled`` controls function more or less
identically. For components that support additional modes of operation (such as
tasks, which also support Batch), the specific ``lambda.enabled`` parameter can
be more useful.

Environment variables
*********************

Lambda-based components support top-level ``environment`` variable
specifications, which they inherit, along with any environment variables defined
globally in the ``cirrus.yml`` file under the ``provider.environment`` key. In
the case of conflicts, inheritence will perfer a value in the Lambda environment
varaibles over one from the task, and one from the task varaibles over that from
the globals.

If, along with the example ``definition.yml`` above, we had a ``cirrus.yml``
defining::

    provider:
      environment:
        GLOBAL_LEVEL_VAR: global_value
        OVERRIDDEN_VAR: first_value

we would end up with the following environment variables/values defined for the
Lambda function::

    GLOBAL_LEVEL_VAR: global_value
    COMPONENT_LEVEL_VAR: some value
    LAMBDA_LEVEL_VAR: 13
    OVERRIDDEN_VAR: new_value

Generally, we recommend using the top-level environment variables for all
variable definitions whenever possible. Global variables in the ``cirrus.yml``
are useful for values shared amongst most or all Lambda or Batch components,
allowing a single place for updates. Values used by only one or a handful of
components, however, are best specified in those respective component
definitions.

We recommend using the top-level variable specification over the ``lambda``
level for consistency, as that is also preferred for tasks that use Batch (both
to allow sharing the environment values between Batch and Lambda, where
required, and because the Batch environment specification uses a different and
more verbose format).

If ever in doubt about the final environment variables/values (or the values of
any other parameters) used in a Lambda definition, the ``cirrus`` cli provides
a ``show`` command that runs the full configuration interpolation to generate
the "complete" definition as it appears in the compiled configuration generated
by the ``build`` command.  Run it like this::

    ❯ cirrus show task <TaskName>

IAM permissions
***************

Lambda's each get a unique role created via the `serverless-iam-roles-per-function
plugin`_. While this plugin supports the specification of global permissions in
the ``cirrus.yml`` file under ``provider.iamRoleStatments`` or
``provider.iam.role.statements`` (depending on serverless version), using global
permissions is highly discourgaed.

Instead, each function should have a specific set of IAM permissions listed in
its ``definition.yml``, limited to most restrictive set possible. The default
set of permissions, as shown in the example, may or may not be that set,
depending on the functionality of the Lambda components. Let's break each of
those default permissions down to see what they do.

::

    - Effect: "Allow"
      Action:
        - "s3:PutObject"
      Resource:
        - !Join
          - ''
          - - 'arn:aws:s3:::'
            - ${self:provider.environment.CIRRUS_DATA_BUCKET}
            - '*'

This first action allows the Lambda to add/update an object in a the bucket
referenced by the S3 bucket ARN provided via the global environment variable
``CIRRUS_DATA_BUCKET``. This permission is useful for all tasks that need to
write assets/items to the data bucket.

::

    - Effect: "Allow"
      Action:
        - "s3:ListBucket"
        - "s3:GetObject"
        - "s3:GetBucketLocation"
      Resource: "*"

This next action allow Cirrus components to retrieve data from any S3 bucket
that allows access. Task and other components that need to access assets or
other files across a potentially unknown set of S3 buckets should get this
permsission.

::

    - Effect: "Allow"
      Action: secretsmanager:GetSecretValue
      Resource:
        - arn:aws:secretsmanager:#{AWS::Region}:#{AWS::AccountId}:secret:cirrus-creds-*

Some buckets require credentials for access (such as those using KMS
encryption). The underlying ``cirrus-lib`` utility functions for accessing S3
objects implicitly supports accessing all secrets named like
``cirrus-creds-<bucket_name>`` to get and use credentials as requred for
accessing such buckets. An IAM statement like this one allows this Cirrus
component access to any such secrets as needed.

.. _serverless-iam-roles-per-function plugin: https://github.com/functionalone/serverless-iam-roles-per-function

Python dependencies
*******************

Cirrus uses a Serverless plugin `serverless-python-requirements`_ to bundle any
necessary Python dependencies into the Lambda deployment zip file when
packaging. Unlike the stock plugin, however, Cirrus does not use a
``requirements.txt`` file for dependency specifiction. Instead, Cirrus supports
a list of all requirements under ``lambda.pythonRequirements.include``.

The items in that list support the normal ``requirements.txt`` file format and
all version specification operators/options.

Global requirements supported by all Lambda components are supported via
configuration in the ``cirrus.yml`` file under
``custom.pythonRequirements.include``, but using this mechanism is highly
discouraged in favor of explicitly listing pinned requirements for every Lambda
component, as required.

Note that a dependency specification for ``cirrus-lib`` is injected into every
Lambda. Cirrus does this by updating each Lambda component's requirements list
with the ``cirrus-lib`` requirements. ``cirrus-lib`` itself is copied into each
Lambda deployment zip from the version installed to the current Python
environment.

.. _serverless-python-requirements: https://www.serverless.com/plugins/serverless-python-requirements

Different module/handler names
******************************

Serverless function definitions require the specification of a ``handler``
property to set the Lambda entry point module and function. Indeed, if
``lambda.handler`` is set, that value will be used to set the Lambda entry point.

However, Cirrus does not require this parameter to be specified, and will
instead default it to ``lambda_function.lambda_handler``, in line with AWS
convention and the expected handler file name.
