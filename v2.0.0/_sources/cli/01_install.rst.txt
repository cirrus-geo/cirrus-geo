Installing
==========

Built using python `click`_ library and included in the broader `cirrus-geo`_
library, you can install the CLI tool on its own or alongside other project
requirements.  A standalone CLI installation might look like

.. code-block:: bash

   pipx install 'cirrus-geo[cli]'

Another way is to use a more modern tool like ``uv`` to run specific CLI
commands in an ephemeral environment.

.. code-block:: bash

    uvx --from 'cirrus-geo[cli]' cirrus [COMMAND]

.. _click: https://click.palletsprojects.com/en/stable/
.. _cirrus-geo: https://github.com/cirrus-geo/cirrus-geo
