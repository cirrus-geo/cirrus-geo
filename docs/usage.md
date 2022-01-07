# Cirrus Usage

Cirrus jobs (Workflows) are triggered by publishing a **Cirrus ProcessPayload**
(CPP) to the `cirrus-<stage>-process` SNS Topic. This triggers Cirrus as detailed
in the [architecture](./architecture.md). Feeding a CPP into Cirrus can be done
manually (e.g., with the AWS Console or AWS Command Line Interface (CLI)), or
programmatically using a Lambda function, cron process, or other triggered event.

## Cirrus ProcessPayload

The input to Cirrus is STAC metadata (the input Items) and information about the
processing that should be performed. It is inspired by the format of a
[single-file-stac](https://github.com/radiantearth/stac-spec/tree/master/extensions/single-file-stac)
catalog, but features some additional fields and makes others optional.
Take a look at a
[single-file-stac example](https://raw.githubusercontent.com/radiantearth/stac-spec/master/extensions/single-file-stac/examples/example-search.json)
to see that:

- it is a GeoJSON `FeatureCollection` (type field)
- the `features` field is a list of STAC Items
- it has additional fields a STAC Catalog has:
  `id`, `stac_version`, `stac_extensions`, `description`, and `links`
- a`collections` field contains a list of all the STAC Collections of which
  the Items in `features` are a part

A Cirrus ProcessPayload is the same with some changes and additions:

- The `id` field is not specified by the user. Cirrus automatically assigns
  an ID to represent the input data and the worklow to be used.
- The `collections` field is optional and not required by the standard
  Cirrus workflows. There are two reasons for this: 1) At scale, including
  the same Collection metadata for every job is inefficient and, 2) Cirrus
  can store any needed Collection metadata in its STAC catalog for processes
  to use if needed.
- A `process` JSON block is required to specify workflow details and
  optional parameters.
- Workflows included in `cirrus` assume that the STAC Items in the CPP are
  compliant with the STAC spec, but that requirement is not strictly necessary
  for all workflows. Once a workflow gets to the `publish` step, any published
  Items need to be compliant, however users may create workflows that receive
  STAC-like input and geneate STAC-complaint metadata as part of the process.
  This is a common workflow - using a list of assets of a data providers original
  metadata to create STAC Items and possibly transformed data.
- The STAC Items under `features` are required to have a `collection` field
  (STAC does not require Items belong to a Collection) OR an `input_collections`
  field is required in the `process` block containing a list of input collection
  IDs.
- Cirrus does not currently use `stac_version` and `stac_extensions`, however
  in the future Cirrus may use these fields to validate the input.

*Example Cirrus Input Catalog:*

```
{
    "stac_version": "1.0.0-beta.2",
    "stac_extensions": [
        "single-file-stac",
        "eo",
        "view",
        "sat"
    ],
    "type": "FeatureCollection",
    "collections": [],
    "features": [
        ...
    ],
    "process": {
        ...
    },
    "links": []
}
```

In this example `features` is a List of individual STAC Items that will be
processed together and that use the `eo`, `view`, and `sat` STAC extensions.
The `collections` and `links` fields are left as empty lists (though do not
need to be if used in the workflow). The `process` block defines the workflow
and parameters.


### Process definition

The `process` defintion of the CPP is a map that specifies which workflow to run,
options for the output generated, and optional parameters supplied to each of
the steps in the workflow.

*Example process defintion for the `publish-only` workflow:*

```json
{
    "workflow": "publish-only",
    "output_options": {
        "path_template": "${collection}/${year}/${id}",
        "collections": {
            "sentinel-s2-l2a-cogs": ".*"
        }
    },
    "tasks": {
        "publish": {
            "public": true
        }
    }
}
```

The `process` key can also be an array of process definition maps to facilitate
workflow chaining, where each map in the array represents a workflow in a chain.


## Tutorials

Now it's time to put together some Input Catalogs into some workflows.

- [Publishing](./tutorial-publish.md): Add STAC Items to the Cirrus STAC catalog
- [Mirror](./tutorial-mirror.md): Copy data from a source
  (and add STAC Items to catalog)


## Tasks and Workflows

As seen in the above tutorials, workflows can contain mulitple `tasks`.
Tasks included with Cirrus can be viewed by running the command
`cirrus show tasks`, and each task includes a README detailing what
parameters it takes.


## Workflows

A `workflow` is a pre-determined sequence of `tasks` defined as
AWS Step Functions. The `workflows` deployed with Cirrus can be viewed by
running the command `cirrus show workflows`.


## Feeders

A `feeder` is something that publishes CPPs to Cirrus to start workflows.
In the above tutorials the feeder is simply a call to the AWS CLI to publish a
local payload to Cirrus. Much more practical is the ability to dynamically create
input STAC Items and pair them with desired process configurations. A `feeder`
could be a script do this run locally or it could be an AWS Lambda, a Batch job,
or any number of different services that can create a CPP and publish it to the
Cirrus queue SNS topic. Such services could be set up on a schedule, or be
triggered by some event.

The `feeder` programs included with cirrus can be seen with the command
`cirrus show feeders`.
