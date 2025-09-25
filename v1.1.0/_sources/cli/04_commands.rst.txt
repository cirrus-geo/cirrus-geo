Command Examples
================

CLIrrus currently support a number of commands.

- *list-deployments:*
    Return a list of all named cirrus deployments available for interacting
    with by pulling deployments available in AWS parameter store.  Defaults to looking in the region used in AWS SSO login.  Names returned here will be the name strings needed to run commands on a specific deployment.

    .. code-block:: bash

        cirrus list-deployments

- *manage (mgmt):*
    A wrapper for commands to interact with a specific named deployment

    .. code-block:: bash

        cirrus mgmt DEPLOYMENT_NAME COMMAND


- *payload:*
    a wrapper for commands for working with payloads.

    .. code-block:: bash

        cirrus payload COMMAND


Manage commands
---------------
- *call:*
    Call a new command with the deployment environment variables loaded

    .. code-block:: bash

        cirrus mgmt name-dev call ls

- *exec:*
    Run an executable with the deployment specific environment variables loaded into the local environment

    .. code-block:: bash

        cirrus mgmt name-dev exec "bash" "hello_env_var_world.sh"

- *get-execution:*
    Get a workflow execution using its ARN or its payload-id

    .. code-block:: bash

        cirrus mgmt name-dev get-execution --payload-id sar/workflow-test/example-01_2024-10-31-06-05-10

        cirrus mgmt name-dev get-execution --arn arn:aws:states:us-west-2:000000000011:execution:fd-name-dev-cirrus-project:c123456789-b19292-999

- *get-execution-input:*
    Get a workflow execution's input payload using ARN or payload-id

    .. code-block:: bash

        cirrus mgmt name-dev get-execution-input --arn arn:aws:states:us-west-2:000000000011:execution:fd-name-dev-cirrus-project:c123456789-b19292-999

        cirrus mgmt name-dev get-execution-input --payload-id sar/workflow-test/example-01_2024-10-31-06-05-10

- *get-execution-output:*
    Get a workflow execution's output payload using payload-id or ARN

    .. code-block:: bash

        cirrus mgmt name-dev get-execution-output --payload-id sar/workflow-test/example-01_2024-10-31-06-05-10

        cirrus mgmt name-dev get-execution-output --arn arn:aws:states:us-west-2:000000000011:execution:fd-name-dev-cirrus-project:c123456789-b19292-999

- *get-payload:*
    Get a payload from S3 using its payload ID

    .. code-block:: bash

        cirrus mgmt name-dev get-payload sar/workflow-test/example-01_2024-10-31-06-05-10

- *get-state:*
    Get the stateDB record for a payload ID

    .. code-block:: bash

        cirrus mgmt name-dev get-state sar/workflow-test/example-01_2024-10-31-06-05-10

- *invoke-lambda:*
    Invoke lambda with event (from stdin) and specifying by name which lambda to invoke

    .. code-block:: bash

        <payload.json cirrus mgmt name-dev invoke-lambda process

- *list-lambdas*:
    List all lambda functions available in a given deployment

    .. code-block:: bash

        cirrus mgmt name-dev list-lambdas

- *process:*
    Enqueue a payload (from stdin) for processing

    .. code-block:: bash

        <payload.json cirrus mgmt name-dev process

- *run-workflow:*
    Pass a payload (from stdin) off to a deployment, wait for the workflow to finish, and retrieve and return its output payload

    .. code-block:: bash

        <payload.json cirrus mgmt name-dev run-workflow

- *show:*
    Show a deployment configuration's environment variables available in the parameter store

    .. code-block:: bash

        cirrus mgmt name-dev show

- *template-payload:*
    Template a payload using a deployment's environment variables and '$' based substitution

    .. code-block:: bash

        <payload.json cirrus mgmt name-dev template-payload --var EXAMPLE_VAR VALUE

- *get-payloads*
    Bulk retrieve payloads as NDJSON.  Can be filtered on fields available in
    StateDB - 'collections-workflow', 'state', 'since', 'limit',
    'error-prefix'.  Output may be piped into additional commands to rerun payloads using 'rerun' flag which alters payload to allow rerunning

    piping with xargs to resubmit failed workflows
    .. code-block:: bash

        cirrus manage name-dev get-payloads --collections-workflow "sar-test_flow" --state "FAILED" --since "10 d" --rerun | xargs -0 -L 1 echo |  cirrus manage name-dev process

Payload commands
----------------

- *get-id:*
    Get/generate an ID for a given payload

    .. code-block:: bash

        <payload.json cirrus payload get-id

- *template:*
    Template a payload (from stdin) with user supplied variables with '$' based substitution

    .. code-block:: bash

        <payload.json cirrus payload template --var EXAMPLE_VAR VALUE

- *validate:*
    Validate an input payload (from stdin) is a valid cirrus payload

    .. code-block:: bash

        <payload.json cirrus payload validate
