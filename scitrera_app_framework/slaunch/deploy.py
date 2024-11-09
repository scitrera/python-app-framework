from shutil import copytree

import yaml
from vpd.next.util import read_yaml, open_ensure_paths

from .constants import *


def update_manifest(name, latest_ver=None, libs=False, update_current_ver=False):
    from .main import REPOSITORY_PATH
    manifest_home = REPOSITORY_PATH / LIBS if libs else REPOSITORY_PATH
    manifest_path = manifest_home / MANIFEST_YAML

    manifest = read_yaml(manifest_path) if manifest_path.exists() else {}
    existing_def = manifest[name] if name in manifest else {}
    new_def = existing_def.copy() if latest_ver is None else {VERSION_LATEST: latest_ver, }

    # if we have a current version and shouldn't update it, then we keep it
    if VERSION_CURRENT in existing_def and not update_current_ver:
        new_def[VERSION_CURRENT] = existing_def[VERSION_CURRENT]

    # if we have a current version and should update it, then we swap it for the latest
    elif VERSION_CURRENT in existing_def and update_current_ver:
        new_def[VERSION_CURRENT] = new_def[VERSION_LATEST]

    # if we don't have a current version and shouldn't update it, then we
    # adopt the previous latest version as the current version
    elif VERSION_CURRENT not in existing_def and not update_current_ver:
        new_def[VERSION_CURRENT] = existing_def[VERSION_LATEST]

    manifest[name] = new_def

    with open_ensure_paths(REPOSITORY_PATH / MANIFEST_YAML, 'w') as f:
        yaml.safe_dump(manifest, f)

    return


def deploy_app(src_path, name, version, update_current=False):
    from .main import REPOSITORY_PATH
    tgt_path = REPOSITORY_PATH / name / version
    copytree(src_path, tgt_path)
    update_manifest(name, version, update_current_ver=update_current)
    return


def deploy_lib(src_path, name, version, update_current=False):
    from .main import REPOSITORY_PATH
    tgt_path = REPOSITORY_PATH / LIBS / name / version
    copytree(src_path, tgt_path)
    update_manifest(name, version, libs=True, update_current_ver=update_current)
    return
