# additional utility functions that rely on core & API functionality
from __future__ import annotations

import pathlib

from ..api import Variables
from ..core import get_variables


def add_env_file_source(src: str | pathlib.Path, v: Variables = None):
    """
    Leverage python-dotenv to load environment data from a file and add it as a source to our variables instance.
    This allows for more flexible configuration, especially in development or Kubernetes environments. The
    imported environment data is added as an additional source that has higher priority than default values but lower
    priority than environment variables or locally configured values. Therefore, this is useful for importing configuration
    but still allowing for overrides by environment or programmatic configuration.

    :param src: source file (e.g. ".env") to load that should be a text file in standard environment text format (e.g. KEY=VALUE)
    :param v: variables instance to augment. Will use the default instance if none provided.
    """
    try:
        import dotenv

        get_variables(v).add_source(dotenv.dotenv_values(src))
    except ImportError:
        raise ImportError('Cannot add environment file source without dotenv. Install with `pip install python-dotenv` first!')
