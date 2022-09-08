Cirrus Process Payload
======================

A Cirrus Process Payload is a JSON object containing the input metadata along with a parameters
for processing that metadata and associated data. A Cirrus payload is used to start a
single execution of a workflow.

.. list-table:: Cirrus Process Payload
   :widths: 25 25 50
   :header-rows: 1

   * - Field Name
     - Type
     - Description
   * - type
     - string
     - Type of the GeoJSON Object. If set, it must be set to FeatureCollection.
   * - features
     - [:ref:`payload-item`]
     - An array of STAC-like input items
   * - process
     - [:ref:`payload-processdef`]
     - An array of process definitions


At a high-level, the payload looks like a GeoJSON FeatureCollection with an additional
`process` field.

.. code-block::

    {
        "type": "FeatureCollection",
        "features": [
            {
                <stac-item-1>
            },
            {
                <stac-item-2>
            }
        ],
        "process": {
            <process-definition>
        }
    }

A workflow task may take 1 or more items as input, and could output 1 or more items.
One common use-case is to take in a single input item and generate a single output item.

 .. _payload-item:

Item
^^^^

An input item to Cirrus is commonly 1 or more STAC Items, allowing workflow tasks
to be interoperable across different data sources. For example an NDVI task could
create an NDVI asset, adding it to the item regardless of if it was a Landsat or
Sentinel STAC Item.

However, sometimes workflows are also responsible for creating proper STAC Items,
mapping metadata in different formats into STAC. Thus, as far as Cirrus is concerned,
the only required field in the payload is an `id` field. The `id` is used to track
the individual execution of a workflow.

.. list-table:: Item
   :widths: 25 25 50
   :header-rows: 1

   * - Field Name
     - Type
     - Description
   * - id
     - string
     - **REQUIRED** An ID for this item

Each workflow task will have it's own requirements on the items, and may perform
additional validation. Payloads that fail validation of a workflow task should
throw an `InvalidInput` exception, which will mark the execution in the
state database as `INVALID`.

In the following example the input item is a partial STAC Item, using STAC fields
but missing most required fields (e.g., geometry, datetime). In this case,
this item provides URLs to the original Sentinel-2 metadata which will be converted
to a STAC Item during during one of the workflow tasks.

.. code-block:: json

    {
        "features": [
            {
                "id": "tiles-15-V-WG-2022-3-21-0",
                "assets": {
                    "tileInfo": {
                        "href": "https://roda.sentinel-hub.com/sentinel-s2-l2a/tiles/15/V/WG/2022/3/21/0/tileInfo.json"
                    },
                    "productInfo": {
                        "href": "https://roda.sentinel-hub.com/sentinel-s2-l2a/tiles/15/V/WG/2022/3/21/0/productInfo.json"
                    },
                    "metadata": {
                        "href": "https://roda.sentinel-hub.com/sentinel-s2-l2a/tiles/15/V/WG/2022/3/21/0/metadata.xml"
                    }
                }
            }
        ]
    }

While partial STAC Items make sense as input to workflows that create STAC
metadata, the final output of a Cirrus workflow should always contain an array
of actual STAC Items.


 .. _payload-processdef:

Process Definition
^^^^^^^^^^^^^^^^^^

.. list-table:: Process Definition
   :widths: 25 25 50
   :header-rows: 1

   * - Field Name
     - Type
     - Description
   * - description
     - string
     - An optional description of the process
   * - workflow
     - string
     - **REQUIRED** Name of the workflow to run
   * - input_collections
     - string
     - An identifier representing the set of collections the input items belong to
   * - upload_options
     - :ref:`payload-outputopts`
     - Parameters affecting the upload of item assets
   * - tasks
     - Map<string, Map<str, object>>
     - A dictionary of task names (keys), each containing a dictionary of parameters for that task


input_collections
*****************

The `input_collections` field is a way to explicitly group together input items
across executions of workflows. It is optional, and if not provided `input_collections`
is derived from all the collections the input items belong to. For instance, if
a payload contains a single item, and it belongs in the collection `sat-a-l1`,
then `input_collections` is `sat-a-l1`.

If the payload contains multiple items spanning more than 1 collection, then
`input_collections` is a '/' separated string of the sorted list of collections.
For instance, if the items are in collections `sat-c-l1` and `sat-a-l1` then
`input_collections` would be `sat-a-l1/sat-c-l1`

tasks
*****

The tasks field is a dictionary with an optional key for each task. If present, it
contains a dictionary of parameters for the task. The documentation for each task
will supply the list of available parameters.


.. _payload-outputopts:

Output Options
^^^^^^^^^^^^^^

The output options object is a dictionary of parameters to used to control the
publishing of the metadata and uploading data assets. Any task that uploads
data should use the OutputOptions to control where and how that data is uploaded.
See the cirrus-lib function `transfer.upload_item_assets`


.. list-table:: Output Options
   :widths: 25 25 50
   :header-rows: 1

   * - Field Name
     - Type
     - Description
   * - path_template
     - string
     - **REQUIRED** A string template for specifying the location of uploaded assets
   * - collections
     - Map<str, str>
     - **REQUIRED** A mapping of output collection name to a regex pattern used on Item IDs
   * - public_assets
     - [str]
     - A list of asset keys that should be marked as public when uploaded
   * - headers
     - Map<str, str>
     - A set of key, value headers to send when uploading data to s3
   * - s3_urls
     - bool
     - Controls if the final published URLs should be an s3 (s3://<bucket>/<key>) or https URL.

path_template
*************

The `path_template` string is a way to control the output location of uploaded assets from a
STAC Item using metadata from the Item itself. The template can contain fixed strings
along with variables used for substitution. The following variables can be used in the template.

.. list-table:: Output Options
   :widths: 25 25 50
   :header-rows: 1

   * - Field Name
     - Type
     - Description
   * - id
     - string
     - The id of the Item
   * - collection
     - string
     - The name of the Item's Collection
   * - date
     - string
     - The date portion of the Item's `datetime` property of the form YYYY-MM-DD
   * - year
     - string
     - The year portion of the Item's `datetime` property
   * - month
     - string
     - The month portion of the Item's `datetime` property
   * - day
     - string
     - The day portion of the Item's `datetime` property
   * - <property>
     - varies
     - Any Item property (e.g., `mgrs:utm_zone`)

As an example, a `path_template` of `/data/${collection}/${id}/` will upload all assets
to a path based on the Item's collection and ID to the default Cirrus data bucket.

If a complete s3 URL is provided instead (e.g., s3://my-bucket/data/${collection}/${id}/)
then the data will be uploaded to the provided bucket.

collections
***********

The `collections` dictionary is a way to control what collection output STAC Items
are ultimately assigned to. Each dictionary key is the name of a collection, and it's
value is a regex expression that is used to match against each STAC Item ID that
will be published. The first matching collection will be used.

.. code-block:: json

    "upload_options": {
        "collections": {
            "sat-a-l1": "sa.*"
            "sat-b-l1": "sb.*"
        }
    }

With this example an Item with an ID of "sa-l1-20200107" will be put in the `sat-a-l1`
collection, and Item "sb-l1-19731212" would be put in the `sat-b-l1` collection.

If `collections` is supplied, each Item is assigned a new collection before it is
published. If not provided the collections will remain as they were.
