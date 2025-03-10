Installing the Cirrus CLI Management Tool (CLIrrus)
===================================================
Installing CLIrrus is quick and easy.  Built using python `click`_ library and included in the broader `cirrus-geo`_ library, to install CLIrrus you just need to install the cirrus project requirements.

For better environment management we recommend you create a specific virtual environment.  This might look like

.. code-block:: bash

    python3.12 -m venv .venv

    source .venv/bin/activate

    pip install -r requirements-dev.txt -r requirements-cli.txt -r requirements.txt

.. _click: https://click.palletsprojects.com/en/stable/
.. _cirrus-geo: https://github.com/cirrus-geo/cirrus-geo
