import pathlib
import subprocess

from shutil import copytree, copy2
from typing import Optional, Iterable, Callable

import yaml
from vpd.next.util import read_yaml, open_ensure_paths
from botwinick_utils.platforms import operating_system
from botwinick_utils.paths import native_copy
from botwinick_utils.platforms.python import read_pkg_version

from .constants import *


def read_app_version(app_path: pathlib.Path, app_name: str):
    """
    Read application version from __version__ variable in _{app_name}_version.py file in the application path

    :param app_path: root path of **application**
    :param app_name: name of application (typically same as {app_path.name})
    :return: version or raises ValueError if unable to load/get version
    """
    app_name = app_name.lower()
    app_version_module = f'_{app_name}_version'
    version = read_pkg_version(app_name, app_path, file=f'{app_version_module}.py')
    return version


def read_lib_version(lib_path: pathlib.Path, lib_name: str):
    """
    Read library version from __version__ variable in library package (either compiled .pyd or .so or __init__.py in package root)

    :param lib_path: root path of **library**
    :param lib_name: name of library (typically same as {lib_path.name})
    :return: version or raises ValueError if unable to load/get version
    """
    lib_name = lib_name.lower()

    os = operating_system()
    if os == 'windows' and (pyd_files := list(lib_path.glob('*.pyd'))):  # TODO: potential matching w/ py version too?
        v_file = pyd_files[0].name
    elif (os == 'linux' or os == 'darwin') and (so_files := list(lib_path.glob('*.so'))):
        v_file = so_files[0].name
    elif (lib_path / '__init__.py').exists():
        v_file = '__init__.py'
    else:
        raise ValueError(f'unable to find version file for {lib_name} in {lib_path}')

    version = read_pkg_version(lib_name, lib_path, file=v_file)
    return version


def update_manifest(name: str, latest_ver: Optional[str] = None, libs: bool = False, update_current_ver: bool = False,
                    force_current_ver: Optional[str] = None):
    """
    Update either applications or libraries manifest for a given app/library name

    :param name: name of application or library
    :param latest_ver: the latest version of the app/library (None means using existing data)
    :param libs: True means editing libraries manifest, False means editing applications manifest
    :param update_current_ver: True means the current version should be set to the latest version
    :param force_current_ver: if given, the given version will be set as the "current" version
    :return: revised parameters for manifest entry
    """
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
    elif VERSION_CURRENT not in existing_def and not update_current_ver and VERSION_LATEST in existing_def:
        new_def[VERSION_CURRENT] = existing_def[VERSION_LATEST]

    # override to enable setting a specific current version if it's an "arbitrary" rollback rather than switching to latest/not
    if force_current_ver is not None:
        new_def[VERSION_CURRENT] = force_current_ver

    manifest[name] = new_def

    with open_ensure_paths(manifest_path, 'w') as f:
        yaml.safe_dump(manifest, f)

    return new_def


def _deploy_app(src_path: pathlib.Path, name: str, version: str, update_current: bool = False, **kwargs):
    from .main import REPOSITORY_PATH, NATIVE_COPY
    tgt_path = REPOSITORY_PATH / name / version
    copytree(src_path, tgt_path, copy_function=native_copy if NATIVE_COPY else copy2, **kwargs)
    m = update_manifest(name, version, update_current_ver=update_current)
    return m


def _deploy_lib(src_path: pathlib.Path, name: str, version: str, update_current: bool = False, **kwargs):
    from .main import REPOSITORY_PATH, NATIVE_COPY
    tgt_path = REPOSITORY_PATH / LIBS / name / version
    copytree(src_path, tgt_path, copy_function=native_copy if NATIVE_COPY else copy2, **kwargs)
    m = update_manifest(name, version, libs=True, update_current_ver=update_current)
    return m


def deploy_library(pkg: str, build_path: pathlib.Path, update_current: bool = False, version: Optional[str] = None,
                   ignore_fn: Optional[Callable] = None):
    """
    Deploy an already built/compiled library to central repository

    :param pkg: the name of the library package
    :param build_path: the root path of the built library
    :param update_current: if True, the current version will be set to the latest version when updating the manifest
    :param version: version string if it exists already, will be ready from library if not provided
    :param ignore_fn: a callable function for shutil.copytree to ignore files during copy. See shutil.copytree for details
            on function requirements. Default function if none provided will screen out: *-build-report-*.xml | *.build | __pycache__
    :return: updated manifest parameters on success, raises ValueError or other OSError (from shutil.copytree) on problems
    """
    if version is None:
        version = read_lib_version(build_path, pkg)

    if not (build_path / MANIFEST_YAML).exists():
        raise ValueError(f'skipping {pkg} because no manifest file')

    if ignore_fn is None:
        def ignore_fn(src, names):
            screened = [n for n in names if (
                    ('-build-report-' in n and n.endswith('.xml'))
                    or n.endswith('.build')
                    or n == '__pycache__'
            )]
            return screened

    print(f'Deployment lib XFR for {pkg} {version}')
    return _deploy_lib(build_path, pkg, version, update_current=update_current, ignore=ignore_fn, dirs_exist_ok=True)


def deploy_libraries(build_root: pathlib.Path, update_current: bool = False, subset: Optional[Iterable[str]] = None, ignore_fn=None):
    """
    Deploy all libraries in a build path (or a given subset)

    :param build_root: root build path for CI/CD
    :param update_current: if True, the current version will be set to the latest version when updating the manifest
    :param subset: optional list of strings for libraries that were successfully built (and should be deployed)
    :param ignore_fn: a callable function for shutil.copytree to ignore files during copy. See shutil.copytree for details
            on function requirements. Default function if none provided will screen out: *-build-report-*.xml | *.build | __pycache__
    :return: list of libraries that were successfully deployed
    """
    build_libs = build_root / LIBS
    deployed = []
    for pkg in (build_libs.glob('*/') if subset is None else [build_libs / s for s in subset]):
        pkg = pkg.stem
        if pkg in ('__pycache__',):
            continue
        try:
            print(f'Deploying library: {pkg}')
            deploy_library(pkg, build_path=build_libs / pkg, update_current=update_current, ignore_fn=ignore_fn)
            deployed.append(pkg)
        except (ValueError, ImportError, AttributeError, subprocess.CalledProcessError) as e:
            print(f'\t{e}')

    return deployed


def deploy_application(name: str, app_path: pathlib.Path, update_current: bool = False, ignore_fn: Optional[Callable] = None):
    """
    Deploy an already built/compiled application to central repository

    :param name: the name of the application
    :param app_path: the root path of the built application
    :param update_current: if True, the current version will be set to the latest version when updating the manifest
    :param ignore_fn: a callable function for shutil.copytree to ignore files during copy. See shutil.copytree for details
            on function requirements. Default function if none provided will screen out: *-build-report-*.xml | *.build | __pycache__
    :return: updated manifest parameters on success, raises ValueError or other OSError (from shutil.copytree) on problems
    """
    l_name = name.lower()
    version_file = f'_{l_name}_version'
    version = read_app_version(app_path, l_name)

    if ignore_fn is None:
        def ignore_fn(src, names):
            screened = [n for n in names if (
                    ('-build-report-' in n and n.endswith('.xml'))
                    or n.endswith('.build')
                    or n == '__pycache__'
                # or version_file in n  # originally we were excluding the version file but honestly... why?
            )]
            return screened

    print(f'Deployment app XFR for {name} {version}')
    return _deploy_app(app_path, l_name, version, update_current=update_current, ignore=ignore_fn, dirs_exist_ok=True)


def deploy_applications(build_root: pathlib.Path, update_current: bool = False, subset: Optional[Iterable[str]] = None,
                        ignore_fn: Optional[Callable] = None):
    """
    Deploy all applications in a build path (or a given subset)

    :param build_root: root build path for CI/CD
    :param update_current: if True, the current version will be set to the latest version when updating the manifest
    :param subset: optional list of strings for applications that were successfully built (and should be deployed)
    :param ignore_fn: a callable function for shutil.copytree to ignore files during copy. See shutil.copytree for details
            on function requirements. Default function if none provided will screen out: *-build-report-*.xml | *.build | __pycache__
    :return: list of applications that were successfully deployed
    """
    for pkg in (build_root.glob('*/') if subset is None else [build_root / s for s in subset]):
        pkg = pkg.stem
        if pkg in ('__pycache__', LIBS):
            continue
        try:
            print(f'Deploying application: {pkg}')
            deploy_application(pkg, app_path=build_root / pkg, update_current=update_current, ignore_fn=ignore_fn)
        except (ValueError, ImportError, AttributeError, subprocess.CalledProcessError) as e:
            print(f'\t{e}')

    return


def deploy_environments(environments_root: pathlib.Path):
    """
    Copy environment definitions from given path (one named directory per environment). Each environment
    should be made up of two files: environment.yml & requirements.txt to provide basis for building a
    conda environment and installing pip requirements from pypi.

    :param environments_root: base path for environments, children of this path should be directories with names corresponding
                              to environment names, children of those directories should be environment and requirements files.
    """
    from .main import REPOSITORY_PATH, NATIVE_COPY
    # just copy the whole tree...
    print('Copying Environments')
    copytree(environments_root, REPOSITORY_PATH / ENV_DEFS, dirs_exist_ok=True, copy_function=native_copy if NATIVE_COPY else copy2)
