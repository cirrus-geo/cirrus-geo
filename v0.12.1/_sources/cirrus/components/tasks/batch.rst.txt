Batch tasks
===========


Required files
--------------

Tasks that support Batch-only operation need just the standard
``definition.yml`` and ``README.md`` files. Tasks that support both Batch and
Lambda will additionally need all files required for :doc:`Lambda-based
components <../lambdas>`. In the Batch-only case specifically, the task
directory structure looks very similar to Lambda-based tasks::

    <project_dir>/
        tasks/
            BatchTask/
                definition.yml
                README.md


Definition file
---------------

The ``definition.yml`` contains a Lambda component's configuration. The format
is similar to that used by the Serverless Framework, which underlies cirrus's
deployment mechanism, but is subtly different.

Batch tasks include CloudFormation resource declarations in the
``definition.yml`` file for all resources required for the Batch execution
environment. At minimum, a Batch job definition resource is required, which
should specify a link to an ECR image managed/built via an external source.
Often Batch tasks include dedicated compute environment and job queue
resources. Other common resources found in Batch task definitions include
launch templates, IAM roles and profiles, and ECR repositories.

Here is an example ``definition.yml`` file for a fairly complex Batch-only task
named ``Reproject``::

    description: A sample Batch-only task definition
    environment:
      BATCH_VAR_1: some value
      OVERRIDDEN_VAR: another_value
    enabled: true
    batch:
      enabled: true
      resources:
          Resources:

            ReprojectBatchJob:
              Type: "AWS::Batch::JobDefinition"
              Properties:
                JobDefinitionName: '#{AWS::StackName}-Reproject'
                Type: Container
                Parameters:
                  url: ""
                ContainerProperties:
                  Command:
                    - cirrus-batch.py
                    - process
                    - Ref::url
                  Environment:
                    - Name: JOB_DEF_VAR
                      Value: 1234
                    - Name: OVERRIDDEN_VAR
                      Value: last_value
                  ResourceRequirements:
                    - Type: VCPU
                      Value: 32
                    - Type: MEMORY
                      Value: 240000
                    - Type: GPU
                      Value: 4
                  Image: '123456789012.dkr.ecr.#{AWS::Region}.amazonaws.com/some-image-name:${opt:stage}'

            ReprojectLaunchTemplate500GB:
              Type: AWS::EC2::LaunchTemplate
              Properties:
                LaunchTemplateName: '#{AWS::StackName}-Reproject-500GB'
                LaunchTemplateData:
                  BlockDeviceMappings:
                    - Ebs:
                        VolumeSize: 500
                        VolumeType: gp3
                        DeleteOnTermination: true
                        Encrypted: true
                      DeviceName: /dev/xvda

            ReprojectComputeEnvironment500GB:
              Type: AWS::Batch::ComputeEnvironment
              Properties:
                ComputeEnvironmentName: '#{AWS::StackName}-Reproject-500GB'
                Type: MANAGED
                ServiceRole: !GetAtt BatchServiceRole.Arn
                ComputeResources:
                  MaxvCpus: 2000
                  SecurityGroupIds: ${self:custom.batch.SecurityGroupIds}
                  Subnets: ${self:custom.batch.Subnets}
                  Type: EC2
                  AllocationStrategy: BEST_FIT_PROGRESSIVE
                  MinvCpus: 0
                  InstanceRole: !GetAtt ReprojectInstanceProfile.Arn
                  LaunchTemplate:
                    LaunchTemplateId: !Ref ReprojectLaunchTemplate500GB
                    Version: $Latest
                  Tags: {"Name": "Batch Instance - #{AWS::StackName}"}
                  DesiredvCpus: 0
                State: ENABLED

            ReprojectJobQueue500GB:
              Type: AWS::Batch::JobQueue
              Properties:
                JobQueueName: '#{AWS::StackName}-Reproject-500GB'
                ComputeEnvironmentOrder:
                  - Order: 1
                    ComputeEnvironment: !Ref ReprojectComputeEnvironment500GB
                State: ENABLED
                Priority: 1

            ReprojectInstanceRole:
              Type: AWS::IAM::Role
              Properties:
                AssumeRolePolicyDocument:
                  Version: '2012-10-17'
                  Statement:
                    - Effect: Allow
                      Principal:
                        Service:
                          - ec2.amazonaws.com
                      Action:
                        - sts:AssumeRole
                Path: /
                ManagedPolicyArns:
                  - arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role
                Policies:
                  - PolicyName: Cirrus
                    PolicyDocument:
                      Version: '2012-10-17'
                      Statement:
                        - Effect: Allow
                          Action:
                            - s3:PutObject
                          Resource:
                            - Fn::Join:
                                - ''
                                - - 'arn:aws:s3:::'
                                  - ${self:provider.environment.CIRRUS_DATA_BUCKET}
                                  - '*'
                            - Fn::Join:
                                - ''
                                - - 'arn:aws:s3:::'
                                  - ${self:provider.environment.CIRRUS_PAYLOAD_BUCKET}
                                  - '*'
                        - Effect: Allow
                          Action:
                            - s3:ListBucket
                            - s3:GetObject
                            - s3:GetBucketLocation
                          Resource: '*'
                        - Effect: Allow
                          Action: secretsmanager:GetSecretValue
                          Resource:
                            - arn:aws:secretsmanager:#{AWS::Region}:#{AWS::AccountId}:secret:cirrus*
                        - Effect: Allow
                          Action:
                            - lambda:GetFunction
                          Resource:
                            - arn:aws:lambda:#{AWS::Region}:#{AWS::AccountId}:function:#{AWS::StackName}-*

            ReprojectInstanceProfile:
              Type: AWS::IAM::InstanceProfile
              Properties:
                Path: /
                Roles:
                  - Ref: ReprojectInstanceRole


Let's break down the resources at play in this Batch example.


Description
^^^^^^^^^^^

The top-level ``description`` value is used for the component's description
within Cirrus. It has no further purpose in the case of Batch.


Enabled state
^^^^^^^^^^^^^

Components can be disabled within Cirrus, which will exclude them from the
compiled configuration. All components support a top-level ``enabled`` parameter
to completely enable/disable the component. Batch tasks also support
an ``enabled`` parameter under the ``batch`` key, which will enable/disable
just the Batch portion of the component.

For Batch-only components these ``enabled`` controls function more or less
identically. For tasks that support both Batch and Lambda, the
``lambda.enabled`` and ``batch.enabled`` paramters can prove useful in certain
circumstances. However, note that if the Lambda component of a dual
Lambda/Batch task is disabled, the Lambda deployment zip will not be
packaged/deployed and the Lambda will be deleted from AWS. This can leave the
Batch task unable to execute due to the missing code package.


Job definition
^^^^^^^^^^^^^^

The ``ReprojectBatchJob`` resource defines a CloudFormation resouce of job
definition type, and represents the job configuration used when running our
``Reproject`` job. The job definition includes such configuration settings as
the container image to run, the command to run inside that container, and the
resource requirements of the container. See the `AWS Job Definition
CloudFormation reference`_ for the full list of supported settings.

It is worth highlighting a few aspects of job definition resources.

.. _AWS Job Definition CloudFormation reference:
   https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-batch-jobdefinition.html


Job parameters
**************

The job definition ``Parameters`` key defines a list of parameter and optional
default values that can be passed in to a job instance when run. In the example
above, the ``url`` parameter is used to pass an S3 URL of the process payload
in to the executed command.

This is an important note: Batch has a rather low limit on the size of a job
sent to the SubmitJob API (`30KiB at current`_). To mitigate impacts from this
limit, use the ``pre-batch`` task immediately prior to any batch tasks to upload
the payload to S3 and return a ``url`` to that payload, which can then be
referenced when calling the batch job as the value to the ``url`` parameter.

In the ``ReprojectBatchJob`` example resource above, we can see that the ``url``
parameter is referenced in the executed command::

    Command:
      - cirrus-batch.py
      - process
      - Ref::url

which tells Batch to run a command like::

    ❯ cirrus-batch.py process <contents_of_url_parameter>

Exactly what command should be specified for a job definition is dependent on
the appropriate entry point inside the specified container image. Regardless,
that entry point should be expecting an S3 URL to a process payload, specified
in some manner. ``cirrus-lib`` provides convenince classes/methods to help with
this common need.

The Batch tasks should replace the payload in S3 at the end of execution after
any modifications. Follow the Batch task with the ``post-batch`` task to resolve
that S3 URL into a JSON payload to pass to successive tasks. ``post-batch`` will
also pull any Batch errors from the logs and raise them within the workflow, in
the event of an unsuccessful Batch execution.

See :doc:`Batch tasks in workflows <../workflows/batch>` for an example of how a
payload is passed to a job using this ``url`` parameter, how ``pre-batch`` and
``post-batch`` are used, and some other tips regarding Batch tasks in workflows.

Job parameters can also be used for other job settings, but are most commonly
used within the ``Command`` specification in Cirrus.

.. _30KiB at current:
   https://docs.aws.amazon.com/batch/latest/userguide/service_limits.html


Environment variables
*********************

Batch job definition resources support defining a list of environment variable
names and values, similar to Lambda functions, though with a slightly different
format. Like Lambda tasks, Batch tasks job definitions support the task
definition's top-level ``environment`` specification, which they inherit, along
with any environment variable defined globally in the ``cirrus.yml`` file under
the ``provider.environment`` key, with preference given to any duplicate
varaibles defined on the Batch job defintion.

Additionally, ``AWS_REGION`` and ``AWS_DEFAULT_REGION`` are added to the job
defintion's environment variables with the value derived from the stack's
deployment region.

If ever in doubt about the final environment variables/values (or the values of
any other parameters) used in a Batch task definition, the ``cirrus`` cli
provides a ``show`` command that runs the full configuration interpolation to
generate the "complete" definition as it appears in the compiled configuration
generated by the ``build`` command. Run it like this::

    ❯ cirrus show task <TaskName>


Resource requirements
*********************

The ``ResourceRequirements`` key allows specification of a list of all hardware
resources required by the job (unfortunately with the exception of disk space).
Note that the values provided here serve as defaults for spawned jobs, and can
be overriden when calling ``SubmitJob`` in the workflow. Again, see :doc:`Batch
tasks in workflows <../workflows/batch>` for an example of overriding resource
requirements.

The specified resource requirements are used by the compute environment to pick
an appropriate-sized instance type for the job, either by doing a best fit
across all available instance types, or by selecting the best fit instance type
from a user-provided list. Additional factors come into play with instance
selection such as whether the compute environment is using on-demand or spot
instance.

Optimizing task resource requirements to the minimum required is critical.
While doing so certainly provides an important cost savings, often the more
meaningful reason to do so is to ensure fast instance start up time. Larger
instances can take much longer to become available than small instance, delaying
instance provisioning and therefore job start.


Image specification
*******************

The ``Image`` key accepts an image name within a docker registry in the form
``repository-url/image:tag``. If omitted, the ``repository-url`` will point to
Docker Hub.

For Cirrus tasks, using the AWS Elastic Container Registry to store images is
common, as is show in the example ``Image`` value::

    123456789012.dkr.ecr.#{AWS::Region}.amazonaws.com/some-image-name:${opt:stage}

Note the use of the Serverless parameter ``${opt:stage}``, which allows
specification of an image tag based on the stage in a multi-stage deployment
pipeline. For example, if we have a deployment pipeline with the stages,
``dev``, ``staging``, and ``prod``, we will want to ensure we have image
versions in the ECR repo with tags of those same names.


Compute environments
^^^^^^^^^^^^^^^^^^^^

Compute environments are perhaps the most complex of the Batch resources. Users
are strongly encouraged to read through both the `Batch compute environment
documentation`_ and the `CloudFormation compute environment documentation`_ to
gain an understanding of the role of compute environments, how they can be
used, and what options are available for controlling how jobs are executed
within them.

Within the Cirrus context, it is recommended to use ``MANAGED`` compute
environments. Whether to make use of Fargate or EC2 for job execution is highly
dependent on the workload involved. Many geospatial processing tasks a
compute-intensive and make heavy, constant use of instance CPUs, which often
tips the balance in favor of EC2 for the cost savings. EC2 also allows great
flexibility, at the expense of having more complex configuration to manage.

.. _Batch compute environment documentation:
   https://docs.aws.amazon.com/batch/latest/userguide/compute_environments.html
.. _CloudFormation compute environment documentation:
   https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-batch-computeenvironment.html


Naming compute environments
***************************

Naming a compute environment is seemingly desirable as the autogenerated names
created when a name is omitted are often less than useful and potentially
shortened in ways that incite confusion. Unfortunately, as a replace-only
resource, using a name can lead to an issue if needing to update an existing
compute environment, due to name conflict between the existing environment and
its replacement.

Sometimes that restriction is advantageous, as it acts as something of a barrier
to prevent potentially service-impacting updates. However, for some projects,
omitting the name may be preferable, as doing so allows updates without
requiring explicit name changes or resource duplication.

Review the Batch resource management strategies for more information.


Compute resources
*****************

The majority of the compute environment configuration is provided by the
``ComputeResources`` settings. Refer to the `compute resources CloudFormation
documentation`_ for a complete list of all supported options.

Compute environment scaling is defined by several parameters, most notably
``AllocationStrategy`` and ``MaxvCpus``. As jobs are submitted with a desired
CPU count, the compute environment responds by spinning up instances to match
the total number of CPUs required by all executing jobs. Instances are allocated
to the compute environment using the specified ``AllocationStrategy``. In some
cases, the desired instance type may not be available, and more-strict
strategies may prevent substitute instance types from being allocated, causing
jobs to wait for instance to become available. A similar situation can happen
with large resource demands, where even less-strict allocation strategies cannot
find a suitable instance and jobs have to wait.

Specifying a ``MinvCpus`` value as a multiple of the number of jobs the compute
environment should minimally accommodate without waiting can be a viable
mechanism for dealing with instance inavailability. That is, if needing to
ensure ten jobs each requiring four CPUs can run without a wait then a
``MinvCpus`` value of 40 will ensure enough instances are continuously running
to support those jobs. However, using this parameter can add significant idle
costs and is not recommended unless strictly required. It also does not help
mitigate latency in the case of job bursts beyond the minimum constant capacity.

Back to scaling: the compute environment will continue to allocate instances
until the total number of CPUs in the environment matchs the total CPU demand
from jobs. However, this allocation will only continue as long as ``MaxvCpus``
is greater than the number of CPUs in the environment. In this way ``MaxvCpus``
acts as the cap on instance count and therefore the maximum number of Batch jobs
that can be running at any given time. Therefore, ensuring ``MaxvCpus`` is
appropriately set is important; an optimal value can be calculated by
multiplying the maximum number of simultaneous jobs required by the number of
CPUs each job requires.

.. _compute resources CloudFormation documentation:
   https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-batch-computeenvironment-computeresources.html


Using the AWS spot market
*************************

.. TODO


Launch templates
^^^^^^^^^^^^^^^^

Launch templates provide a way to run scripts, apply configuration, and make
other initialization changes to EC2 instances started in a compute environment.
Perhaps most commonly, launch templates are used to increase the root disk size
to ensure enough space is available for running containers and any scratch space
they may require. The ``ReprojectLaunchTemplate500GB`` resource in the example
``definition.yml`` is doing exactly that, increasing the root disk to 500GB from
the default 30GB.

Other common uses of launch templates for Batch tasks include mounting an EFS
volume or tweaking the ECS container agent settings.

When using launch templates with compute environments please note that *updating
a luanch template will not affect any existing compute environments* referencing
that launch template. The launch template referenced at compute environment
creation is cached independently of the base version, and cannot be updated. If
needing launch template changes to apply to an existing compute environment the
compute environment must to be recreated so the new environment can pull the new
launch template version.

Consult the `CloudFormation documentation for launch templates`_ to learn more.

.. _CloudFormation documentation for launch templates:
   https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-ec2-launchtemplate.html


IAM permissions
^^^^^^^^^^^^^^^

Looking closely at the compute environment in the above example, one will notice
two IAM role keys: ``ServiceRole`` and ``ComputeResources.InstanceRole``.

``ServiceRole`` is the IAM role used by AWS Batch and normally requires a fairly
standard set of permissions. Therefore, the same role is commonly shared across
all compute environments as the permissions typically do not differ between
environments (that role is not part of the example for that reason).

The ``ComputeResources.InstanceRole`` is the role used for each container
instance, and is therefore rather specific to the Batch task at hand. Unlike
``ServiceRole`` the instance role parameter does not expect an IAM role ARN;
instead it expects an `IAM instance profile`_. Consequently, the above example
features both the ``ReprojectInstanceRole`` IAM role resource and the
``ReprojectInstanceProfile`` IAM instance profile referencing the former. We
then resolve the profile's ARN and pass that to the compute environment, and it
can use that profile to associate the desired role and its polices to all Batch
job containers.

Commands run as Batch jobs therefore get the permissions allowed by the
specified IAM role, in a similar manner to the unique role created and used for
Lambda-based components. Ensure this role has all required permissions and no
more, so the Batch task does not encounter any permissions errors but also
cannot access unexpected resources. Roles/profiles can be shared between compute
environments, but doing so is discouraged.

Container overrides can be used when calling ``SubmitJob`` to change the profile
used for a specific job. This feature can be useful for advanced users
attempting to run multiple jobs are executed in the same compute environment
(again, having unique compute environments per task is typically recommended).


.. _IAM instance profile:
   https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_switch-role-ec2_instance-profiles.html


Job queues
^^^^^^^^^^

Compute environments are not actually referenced when submitting a job.
Instead, a job queue is specified, which itself provides a link to a specific
compute environment. Job queues are used as a means of holding submitted jobs
while waiting for available CPUs in a saturated compute environment, and can
also provide prioritization in the case where different types of jobs share a
single compute environment.

Multiple compute environment can also be specified for a single queue. This can
be useful in the case of wanting some on-demand capacity, but pushing overflow
into the spot market, or vise versa.

Job queues can be combined with a `Batch scheduling policy`_ for advanced
use-cases.

See the `job queue CloudFormation documentation`_ for more information about
supported job queue configurations.

.. _Batch scheduling policy:
   https://docs.aws.amazon.com/batch/latest/userguide/scheduling-policies.html
.. _job queue CloudFormation documentation:
   https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-batch-jobqueue.html


Other considerations
--------------------

Shared resources
^^^^^^^^^^^^^^^^

While it is generally encouraged to keep Batch resources isolated to each task,
it can sometimes be advantageous to share resources between multiple Batch
tasks. In this case, these resources can also be declared within the project's
``cloudformation/`` directory, unattached to any specific task instance.

When in doubt, however, defer to declaring unique resources per Batch task
rather than sharing, even at the expense of duplication. Duplicating resources
in this way is often easier to manage and allows more-specific configurations.
Consider shared resources an "expert-pattern", as shared resources bring a lot
of baggage along with them that can increase the potential for issues and other
unintended side effects.

Other CloudFormation template sections
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In addition to support for CloudFormation ``Resources`` under
``batch.resources``, Cirrus also supports defining other CloudFormation
template section types such as ``Outputs`` or ``Conditions``. Use those as
required to keep such items together with the associated Batch task.


Batch CloudFormation resources in the cli
-----------------------------------------

The ``cirrus`` cli allows search/discovery of all CloudFormation resources in a
project. All resources within a project can be listed with the ``show``
command::

    ❯ cirrus show cloudformation
    [Outputs]
    CirrusQueueSnsArn (built-in)

    [Resources]
    AddPreviewAsBatchJob [AWS::Batch::JobDefinition] (from built-in task add-preview)
    AddPreviewComputeEnvironment [AWS::Batch::ComputeEnvironment] (from built-in task add-preview)
    AddPreviewJobQueue [AWS::Batch::JobQueue] (from built-in task add-preview)
    BasicOnDemandComputeEnvironment [AWS::Batch::ComputeEnvironment] (built-in)
    BasicOnDemandJobQueue [AWS::Batch::JobQueue] (built-in)
    ...

The CloudFormation items are broken down by types, and show the source. For
Batch resources, they will look something like ``AddPreviewAsBatchJob``, where
it shows that the resource is specifically from the built-in batch-enabled task
``add-preview``. In this way it is easy to identify a given resource, output, or
other CloudFormation object and determine if its origin is a Batch task, and if
so, which one.


Batch Quotas
------------

AWS limits the number of job queues and compute environments in an account to 50
each. Considering this limit is important when determining how to
structure/organize a project's compute environments. In a large, batch-heavy
deployment, consolidating compute environments and job queus such that they can
be shared between tasks may be advantegeous or even necessary to ensure the
deployment can remain below these quotas. If diverging from the general
recommendation of a unique job queue and compute environment per task, be sure
to fully consider instance requirement compatibilities between tasks (including
instance AMI selection), job queue scheduling policies and prioritization
mechanisms, and compute environment capacities.

Also consider the deployment downtime requirements and how changes to compute
environments must be managed per the following guidelines, making sure that the
chosen strategy will have enough headroom within the quotas.


Managing changes to Batch resources
-----------------------------------

Observed issues
^^^^^^^^^^^^^^^

Several different service-impacting issues can result from changes to Batch
resources. The following is an attempt to capture those issues and the affected
resource types, though it is not an exhaustive list of potential problems.

Workflows started during a deployment can have broken Batch configurations
**************************************************************************

A step function referencing a Batch job definition does so via the definition
ARN, including revision, when using the standard reference syntax like
``#{JobDefinitionName}``. When deploying a new revision of a job definition,
CloudFormation automatically deactivates the old revision before the step
function is updated. Any workflow executions trying to start a batch job between
the deactivation of the old revision and the step function update will fail.

Batch job definitions “roll forward” on CloudFormation rollback
***************************************************************

If CloudFormation encounters an error during stack deployment and has to
rollback after updating a Batch job definition, the old job revision is not
reactivated. Rather, the job definition is "rolled forward," such that the old
definition is used to create a second new revision. It looks something like
this::

    Job definition       A       B      A
    Revision number      1   ->  2  ->  3

At the time the updated definition with B is created as revision 2, revision 1
is deactivated. Then, on rollback, CloudFormation re-deploys the definition with
A as revision 3, deactivating revision 2. But, like the above temporary issue
with job definition revisions, the step function definition will not be updated
and still points to revision 1. Unlike the above issue, this case results in a
premanent issue, unless fixed by another deployment or manual configuration
changes.

Killed jobs on job queue removal
********************************

Perhaps obviously, if deleting a job queue all associated jobs will be killed.
While not typical, it is important to note when making large changes/refactoring
existing compute environments/job queues, or simply just renaming a template
resource.


What to do about these issues
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In essences, each of these issues results from trying to make updates to Batch
infrastructure while jobs are running or can be started. How best to mitigate
these issues, therefore, depends on project uptime requirements and/or how
constantly jobs are run as part of the pipeline.

Downtime an issue, jobs continuously running
********************************************

In the case where jobs are continuously running and any pipeline downtime is
undeserable, the best management strategy is to avoid any Batch resource
updates, instead deferring to strategy of duplicating all changed resources.
Commonly, this results in something like a blue-green deployment where every
Batch resource has two copies, a revision A and revision B. Changes then
alternate between the two revisions, ensuring the active revision is not updated
at any time.

In the provided Batch example above, we would end up with a list of resources
like::

    ReprojectBatchJobRevA
    ReprojectLaunchTemplate500GBrevA
    ReprojectComputeEnvironment500GBrevA
    ReprojectJobQueue500GBrevA
    ReprojectInstanceRoleRevA
    ReprojectInstanceProfileRevA

    ReprojectBatchJobRevB
    ReprojectLaunchTemplate500GBrevB
    ReprojectComputeEnvironment500GBrevB
    ReprojectJobQueue500GBrevB
    ReprojectInstanceRoleRevB
    ReprojectInstanceProfileRevB

In this circumstance, it is advantageous to name things like the compute
environments and job queues to prevent updates and try to force the duplication
workflow.

If currently using the revision A resources and needing to update, say, the
launch template, the procedure would be as follows:

* Copy ``ReprojectLaunchTemplate500GBrevA`` as
  ``ReprojectLaunchTemplate500GBrevB`` and update as required

* Copy ``ReprojectComputeEnvironment500GBrevA`` to
  ``ReprojectComputeEnvironment500GBrevB`` and change the latter to point to the
  new launch template ``ReprojectLaunchTemplate500GBrevB``

* Copy ``ReprojectJobQueue500GBrevA`` to ``ReprojectJobQueue500GBrevB`` and
  update the copy to reference ``ReprojectComputeEnvironment500GBrevB``

* Update all workflow references to ``ReprojectJobQueue500GBrevA`` to point to
  ``ReprojectJobQueue500GBrevB``

On deploy, CloudFormation should perform the following operations, in order:

1. Create the new launch template ``ReprojectLaunchTemplate500GBrevB``

2. Create the new compute environment ``ReprojectComputeEnvironment500GBrevB``

3. Create the new job queue ``ReprojectJobQueue500GBrevB``

4. Update any workflow step functions per the new job queue reference

If at any point in this deployment an error is encountered, the step functions
and the old batch resources are left unmodified. The case of a new workflow
execution prior to the step function updates is similar, in that the step
functions still point to old batch resources which can continue to process jobs.

After a successful deployment of the revision B resources and confirmation that
all running jobs have completed, the old revision A resources can be removed
entirely. Next time changes are required the revision B resources can be copied
to revision A resources.

The above steps are the minimal set of changes for the example launch template
update. In practice it is often easiest to copy all resources at once, to ensure
all resources are consistently using revision A or B.

If needing to use this management strategy for batch resources, be sure to
remember the Batch resource quota. Ensure enough headroom is present at all
times in the batch resource totals to allow any possible changes to take place.

Downtime okay, jobs intermittent
********************************

In the case where downtime is acceptable and jobs are intermittent and/or can
fail without issues, avoiding the complexities of the above management strategy
may be preferable. In this case, use the simpler strategy of simply updating
resources and handling any potential issues as they occur during deployment. In
this case it might be best to omit names from resources like compute
environments and job queues; else plan to change the names on any update.
