CLIrrus commands
================

CLIrrus currently support a number of commands.

- *list-deployments:* Return a list of all named cirrus deployments available for interacting with.  Names returned here will be the name strings needed to run commands on a specific deployment.  Will default to searching region in config file

    .. code-block:: bash

        cirrus --region us-west-2 list-deployments

- *manage (mgmt):* A wrapper for commands to interact with a specific named deployment

- *payload:* a wrapper for commands for working with payloads.


Manage commands
---------------
- *call:*
    Run an executable, in a new process, with the deployment environment vars loaded

    .. code-block:: bash

        cirrus mgmt name-dev call
- *exec:*
    Run an executable with the deployment environment with vars loaded

    .. code-block:: bash

        cirrus mgmt name-dev exec

- *get-execution:*
    Get a workflow execution using its ARN or its payload-id

    .. code-block:: bash

        cirrus mgmt name-dev get-execution --payload-id sar/workflow-test/example-01_2024-10-31-06-05-10

        cirrus mgmt name-dev get-execution --arn arn:aws:states:us-west-2:000000000011:execution:fd-name-dev-cirrus-project:c123456789-b19292-999

- *get-execution-input:*
    Get a workflow execution's input payload using ARN or payload-id

    .. code-block:: bash

        cirrus mgmt kodiak get-execution-input --arn arn:aws:states:us-west-2:000000000011:execution:fd-name-dev-cirrus-project:c123456789-b19292-999

        cirrus mgmt name-dev get-execution-input --payload-id sar/workflow-test/example-01_2024-10-31-06-05-10

- *get-execution-output:*
    Get a workflow execution's output payload using payload-id or ARN

    .. code-block:: bash

        cirrus mgmt name-dev get-execution-output --payload-id sar/workflow-test/example-01_2024-10-31-06-05-10

        cirrus mgmt name-dev get-execution-output --arn arn:aws:states:us-west-2:000000000011:execution:fd-name-dev-cirrus-project:c123456789-b19292-999

- *get-payload:*
    Get a payload from S3 using its ID

    .. code-block:: bash

        cirrus mgmt name-dev get-payload  sar/workflow-test/example-01_2024-10-31-06-05-10

- *get-state:*
    Get the statedb record for a payload ID

    .. code-block:: bash

        cirrus mgmt name-dev get-state sar/workflow-test/example-01_2024-10-31-06-05-10

- *invoke-lambda:*
    Invoke lambda with event (from stdin)

    .. code-block:: bash

        cirrus mgmt name-dev invoke-lambda process
        {
            "type": "FeatureCollection",
            "process": [{"workflow": "example"}],
            "features": []
        }

- *list-lambdas*:
    List lambda functions

    .. code-block:: bash

        cirrus mgmt name-dev list-lambdas

- *process:*
    Enqueue a payload (from stdin) for processing

    .. code-block:: bash

        cirrus mgmt name-dev process
        {
            "type": "FeatureCollection",
            "process": [{"workflow": "example"}],
            "features": []
        }

- *run-workflow:*
    Pass a payload (from stdin) off to a deployment,...

    .. code-block:: bash

        cirrus mgmt name-dev run-workflow
        {
            "type": "FeatureCollection",
            "process": [{"workflow": "example"}],
            "features": []
        }

- *show:*
    Show a deployment configuration's environment variables

    .. code-block:: bash

        cirrus mgmt name-dev show

- *template-payload:*
    Template a payload using a deployment's vars and '$' based substitution

    .. code-block:: bash

        cirrus mgmt name-dev template-payload


Payload commands
----------------

- *get-id:*
    Get/generate an ID for a given payload

    .. code-block:: bash

        cirrus payload get-id
        {
            "type": "FeatureCollection",
            "process": [{"workflow": "example"}],
            "features": []
        }

- *template:*
    Template a payload (from stdin) with user supplied variables with '$' based substitution

    .. code-block:: bash

        cirrus payload template --var EXAMPLE_VAR VALUE
        {
            "type": "FeatureCollection",
            "process": [{"workflow": $EXAMPLE_VAR}],
            "features": []
        }
- *validate:*

    Validate an input payload (from stdin) is a valid cirrus payload

    .. code-block:: bash

        cirrus payload validate
        {
            "type": "FeatureCollection",
            "process": [{"workflow": "example"}],
            "features": []
        }
