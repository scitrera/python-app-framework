import pathlib
import platform
import subprocess
import sys

from shutil import copy, copytree, rmtree, copy2
from os import remove, path as osp, getcwd, environ, makedirs

from botwinick_utils.platforms import operating_system as _current_os
from botwinick_utils.paths import native_copy
from scitrera_app_framework import init_framework_desktop, get_logger, get_working_path
from vpd.next.util import open_ensure_paths, read_yaml
from yaml import safe_dump as yaml_write

from .constants import *

CURRENT_OS = _current_os()
if CURRENT_OS == 'windows':
    shell_dl = ['curl', '{in_url}', '-o', '{out_file}']
    mc3_download_url = 'https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe'
    mc3_installer_save_path = '.\\miniconda.exe'
    mc3_install_args = [mc3_installer_save_path] + ['/S', '/NoScripts', '/NoShortcuts', '/D={path}']
    mc3_conda_exec = osp.join('condabin', 'conda.bat')
    python_exe = 'python.exe'
    pythonw_exe = 'pythonw.exe'
elif CURRENT_OS == 'linux':
    shell_dl = ['/bin/wget', '{in_url}', '-O', '{out_file}']
    mc3_download_url = 'https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh'
    mc3_installer_save_path = './miniconda.sh'
    mc3_install_args = ['/bin/bash', mc3_installer_save_path] + ['-b', '-u', '-p', '{path}']
    mc3_conda_exec = osp.join('condabin', 'conda')
    python_exe = 'bin/python'
    pythonw_exe = 'bin/pythonw'
elif CURRENT_OS == 'darwin':
    shell_dl = ['/usr/bin/curl', '{in_url}', '-o', '{out_file}']
    arch = platform.machine()  # expected to be x86_64 or arm64
    mc3_download_url = f'https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-{arch}.sh'
    mc3_installer_save_path = './miniconda.sh'
    mc3_install_args = ['/bin/bash', mc3_installer_save_path] + ['-b', '-u', '-p', '{path}']
    mc3_conda_exec = osp.join('condabin', 'conda')
    python_exe = 'bin/python'
    pythonw_exe = 'bin/pythonw'
else:
    raise ImportError(f'cannot run on OS: {CURRENT_OS}')

APP_NAME = 'slaunch'
REPOSITORY_PATH = pathlib.Path(environ.get('SLAUNCH_REPOSITORY_PATH', '/slaunch_repo'))
NATIVE_COPY = False
SET_DYNAMIC_LIB_ENV_VARS = True


def _env_def_args(name: str, src=None):
    if not name:
        raise ValueError('env name must be defined')

    global REPOSITORY_PATH
    real_src = REPOSITORY_PATH if src is None else src

    try:
        path = real_src / ENV_DEFS / name
        if path.exists() and path.is_dir():
            return name, path / ENVIRONMENT_YML, path / REQUIREMENTS_TXT
    except (IOError, OSError):
        # and if we can't reach it, we fall back to local data
        if src is None:
            working_path = pathlib.Path(get_working_path())
            get_logger().info('Unable to reach central repository, working with local data')
            return _env_def_args(name, src=working_path / DATA)

    return name, None, None


def ensure_mc3():
    logger = get_logger()
    working_path = pathlib.Path(get_working_path())

    if (working_path / MC3 / 'condabin').exists():
        return
    logger.info('MC3 not installed!')

    # download mc3 installer
    logger.info('Downloading MC3')
    subprocess.run([s.format(in_url=mc3_download_url, out_file=mc3_installer_save_path) for s in shell_dl], cwd=working_path, check=True)

    # install mc3
    logger.info('Installing MC3')
    specific_mc3_args = [s.format(path=working_path / MC3) for s in mc3_install_args]
    logger.debug(f'args: %s', specific_mc3_args)
    # TODO: review shell usage and try to eliminate using shell for all operating systems
    subprocess.run(specific_mc3_args, cwd=working_path, check=True, shell=CURRENT_OS != 'darwin')

    # remove mc3 installer
    remove(working_path / mc3_installer_save_path)

    return


def run_conda(env_name, arg0, *args, append_prefix=True, env_root=None, **kwargs):
    working_path = pathlib.Path(get_working_path())
    return subprocess.run(
        [working_path / MC3 / mc3_conda_exec] +
        (list(arg0) if isinstance(arg0, (list, tuple)) else [arg0]) +
        (['--prefix=.'] if append_prefix else []) +
        list(args),
        cwd=env_root if env_root is not None else working_path / ENV / env_name,
        **kwargs
    )


def run_python(env_name, *args, cwd=None, env=None, _pythonw=False, _shell=False, _separate=False):
    working_path = pathlib.Path(get_working_path())
    py_exe = pythonw_exe if _pythonw else python_exe
    full_exe_path = working_path / ENV / env_name / py_exe
    # TODO: review if we want a check here for environment sanity or just let things explode if there is a problem
    # if not full_exe_path.exists():
    #     build_env(*_env_def_args(env_name))
    #     raise ValueError(f'environment {env_name} not available')

    if cwd is None:
        cwd = working_path / ENV / env_name

    sp = {
        'cwd': cwd,
        'shell': _shell,
        'env': env,
    }
    if _separate and CURRENT_OS == 'linux':
        sp['start_new_session'] = True
        fn = subprocess.Popen
    elif _separate and CURRENT_OS == 'windows':
        sp['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        fn = subprocess.Popen
    else:  # TODO: review darwin/OSX _separate (see if we need to add it at all...)
        fn = subprocess.run
    return fn([full_exe_path] + list(args), **sp)


def apply_conda_requirements(env_name, *conda_requirements):
    if not conda_requirements:
        return
    return run_conda(env_name, 'install', '--yes', *conda_requirements)


def apply_pip_requirements(env_name, *pip_requirements, cwd=None):
    if not pip_requirements:
        return
    return run_python(
        env_name, '-m', 'pip', 'install',
        '--upgrade', '--no-warn-script-location', '--compile',
        *pip_requirements, cwd=cwd,
    )


def check_env(name):
    working_path = pathlib.Path(get_working_path())
    env_root = working_path / ENV / name

    if (env_root / python_exe).exists():
        return True
    return False


def build_env(name, env_yaml, pip_req):
    logger = get_logger()
    working_path = pathlib.Path(get_working_path())
    env_root = working_path / ENV / name

    if (env_root / python_exe).exists():
        return
    logger.info(f'Environment "{name}" not configured')

    if env_yaml is None or pip_req is None:
        raise ValueError(f'configuration details for {name} cannot be found!')

    # if we don't have environment, then make sure we have mc3, then install/setup environment
    ensure_mc3()

    # build environment from our environment.yml file
    env_file = pathlib.Path(env_yaml)
    req_file = pathlib.Path(pip_req)

    logger.info('Setting up environment')
    makedirs(env_root, exist_ok=True)
    copy(env_file, env_root / ENVIRONMENT_YML)
    copy(req_file, env_root / REQUIREMENTS_TXT)

    # conda env create command
    run_conda(name, ('env', 'create'), f'--file={ENVIRONMENT_YML}', env_root=env_root)

    # install pip requirements separately because conda is a pain sometimes
    apply_pip_requirements(name, '-r', REQUIREMENTS_TXT, cwd=env_root)

    return


def get_manifest(libs=False, name=None, version=None, src=None):
    global REPOSITORY_PATH
    real_src = REPOSITORY_PATH if src is None else src
    working_path = pathlib.Path(get_working_path())

    if libs:
        real_src = real_src / LIBS
        tgt_path = working_path / DATA / LIBS
    else:
        tgt_path = working_path / DATA

    # get specific manifest
    if name and version:
        real_src = real_src / name.lower() / version
        tgt_path = tgt_path / name.lower() / version

    try:
        manifest = read_yaml(real_src / MANIFEST_YAML)
        if src is None:  # if remote source, then cache the latest version locally
            with open_ensure_paths(tgt_path / MANIFEST_YAML, 'w') as f:
                yaml_write(manifest, f)
        return manifest
    except (IOError, OSError) as e:
        if src is None:
            get_logger().debug('Unable to reach central repo, switching to local data, libs=%s, name=%s, version=%s',
                               libs, name, version)
            return get_manifest(libs=libs, name=name, version=version, src=working_path / DATA)

    return None


def check_update_lib(env_name, lib_name, lib_ver, local_data=None, update=False):
    logger = get_logger()
    if local_data is None:
        working_path = pathlib.Path(get_working_path())
        local_data = working_path / DATA

    global REPOSITORY_PATH
    local_lib_path = local_data / LIBS / lib_name / lib_ver
    remote_lib_path = REPOSITORY_PATH / LIBS / lib_name / lib_ver

    if update:
        logger.warning('Clearing local data for lib %s v%s', lib_name, lib_ver)
        rmtree(local_lib_path, ignore_errors=True)

    remote = False
    logger.debug('loading local lib manifest for %s v%s', lib_name, lib_ver)
    lib_manifest = get_manifest(libs=True, name=lib_name, version=lib_ver, src=local_data)
    if lib_manifest is None:
        remote = True
        if lib_manifest is None:
            logger.debug('local failed; loading remote lib manifest for %s v%s', lib_name, lib_ver)
            lib_manifest = get_manifest(libs=True, name=lib_name, version=lib_ver)
            if lib_manifest is None:
                raise ValueError(f'unable to load library manifest for {lib_name} {lib_ver}')
    else:
        # we have local lib, but we should check if there was a bug fix pushed or something...
        # TODO: some sort of quick check of local vs remote, and if remote reflects update, then we update!
        pass

    if remote:  # handle conda/pip requirements since we just loaded this library and version
        logger.debug('applying conda and pip requirements for %s v%s', lib_name, lib_ver)
        apply_conda_requirements(env_name, *lib_manifest.get('conda_requirements', []))
        apply_pip_requirements(env_name, *lib_manifest.get('pip_requirements', []))
        # if remote, we also need to copy the files over!
        logger.info('Copying library data files for %s v%s', lib_name, lib_ver)
        copytree(remote_lib_path, local_lib_path, dirs_exist_ok=True, ignore_dangling_symlinks=True,
                 copy_function=native_copy if NATIVE_COPY else copy2)

    return


def launch_app(name: str, *args, apps_manifest: dict, libs_manifest: dict,
               version: str = None, app_update: bool = False, libs_update: bool = False, reset: bool = False):
    if not name:
        raise ValueError('name is required')
    name = name.lower()

    logger = get_logger()
    working_path = pathlib.Path(get_working_path())
    local_data = working_path / DATA

    # we cannot proceed if name is not in applications manifest
    if name not in apps_manifest:
        raise ValueError(f'{name} is not a recognized application')

    # establish version
    if version is None:  # TODO: add function to determine app/libs version that can include selectable channels
        # get current/latest version from manifest
        version = apps_manifest[name].get('current', apps_manifest[name]['latest'])
        logger.debug('version not provided, using: %s', version)
        # TODO: should we have fallback handling to find by path if not defined in manifest?

    # if reset is True, then we also ensure that app_update and libs_update is True
    if reset:
        logger.warning('Reset Option Selected!')
        app_update = True
        libs_update = True

    # now that name and version are defined, we can build paths and proceed
    local_app_path = local_data / name / version
    local_lib_root = local_data / LIBS

    # clear local data directory for app version if it exists on either update or reset condition
    if app_update:
        logger.warning('Clearing local data for %s v%s', name, version)
        rmtree(local_app_path, ignore_errors=True)

    # ensure directory exists (after also making sure that we removed it if requested)
    makedirs(local_app_path, exist_ok=True)

    # try getting app manifest (locally first, fallback to remote) [opposite of other manifest fetching]
    remote = False
    logger.debug('loading local app manifest for %s v%s', name, version)
    app_manifest = get_manifest(name=name, version=version, src=local_data)
    if app_manifest is None:
        remote = True
        logger.debug('local failed; loading remote app manifest for %s v%s', name, version)
        app_manifest = get_manifest(name=name, version=version)
        if app_manifest is None:
            raise ValueError(f'unable to load manifest for {name} {version}')
    else:
        # TODO: check for bug fixes or something against remote manifest?
        pass

    # populate some useful stuff from the app manifest
    entrypoint = app_manifest.get('entrypoint', 'main.py')
    if not entrypoint:  # special exception for direct access to python, but requires explicit config
        entrypoint = None

    # check environment
    env_name = app_manifest['environment']
    if reset:  # erase environment before doing checks to redo the whole thing if requested
        logger.warning('Resetting environment "%s"', env_name)
        rmtree(working_path / ENV / env_name, ignore_errors=True)
    if not check_env(env_name):
        build_env(*_env_def_args(env_name))

    # get libraries requirements
    libraries = app_manifest.get('lib_versions', None)
    # if lib_versions not specified in manifest, we assume current/latest for all available libs!
    # (but if it's defined as empty mapping, then we effectively skip libs)
    if libraries is None:
        logger.debug('Libraries not specified for "%s", assuming current/latest...', name)
        libraries = {k: v.get(VERSION_CURRENT, v.get(VERSION_LATEST, None)) for k, v in libs_manifest.items()}
        # TODO: if someone get new libs manifest then disconnected, they might have libs trouble? not worth effort?

    logger.debug('Ensuring that libraries for "%s" are available', name)
    library_import_paths = []
    for lib_name, lib_ver in libraries.items():
        # if library entry but empty version string, then we use current/latest
        # this mechanism allows selecting particular libraries but leaving versions open-ended
        if not lib_ver:
            lmd = libs_manifest[lib_name]  # lib_manifest_data
            lib_ver = lmd.get(VERSION_CURRENT, lmd.get(VERSION_LATEST, None))
        check_update_lib(env_name, lib_name, lib_ver, local_data=local_data, update=libs_update)
        library_import_paths.append(str(local_lib_root / lib_name / lib_ver))

    # handle app pip/conda requirements if this was a remote definition (meaning first run)
    if remote:
        apply_conda_requirements(env_name, *app_manifest.get(REQ_CONDA, []))
        apply_pip_requirements(env_name, *app_manifest.get(REQ_PIP, []))

    # if remote or main.py is missing, we also need to copy the files over!
    if remote or (entrypoint and not (local_app_path / entrypoint).exists()):
        global REPOSITORY_PATH
        logger.info('Copying data files for %s v%s', name, version)
        copytree(REPOSITORY_PATH / name / version, local_app_path, dirs_exist_ok=True, ignore_dangling_symlinks=True,
                 copy_function=native_copy if NATIVE_COPY else copy2)

    # TODO: maybe checksum verification?

    env = environ.copy()
    ld_paths = [str(local_app_path), str(local_app_path / 'libs')] + library_import_paths
    env['PYTHONPATH'] = osp.pathsep.join(
        [env.get('PYTHONPATH', '')] +  # prioritize externally provided PYTHONPATH (e.g. from IDE) above built-in libs
        ld_paths  # followed by possible dynamic library paths
    )
    # library paths plus include externally provided LD_LIBRARY_PATH (e.g. from user shell)
    if SET_DYNAMIC_LIB_ENV_VARS and CURRENT_OS == 'linux':
        env['LD_LIBRARY_PATH'] = osp.pathsep.join(ld_paths + [env.get('LD_LIBRARY_PATH', '')])
    elif SET_DYNAMIC_LIB_ENV_VARS and CURRENT_OS == 'darwin':
        env['DYLD_LIBRARY_PATH'] = osp.pathsep.join(ld_paths + [env.get('DYLD_LIBRARY_PATH', '')])

    # spawn separate process for desired code using current directory, passing arguments, and app/lib config
    logger.info('Launching %s v%s', name, version)
    command_args = ([local_app_path / entrypoint] + list(args)) if entrypoint else list(args)
    return run_python(env_name, *command_args, env=env, cwd=getcwd(), _separate=False)


def main(*args):
    if not args:
        args = sys.argv

    global APP_NAME
    init_framework_desktop(APP_NAME, log_level='WARNING')
    logger = get_logger()

    # update apps and libs manifests up front from central registry if possible
    logger.debug('Getting app manifest')
    apps_manifest = get_manifest()
    if apps_manifest is None:
        logger.error('unable to get applications manifest')
        sys.exit(2)

    logger.debug('Getting libs manifest')
    libs_manifest = get_manifest(libs=True)
    if libs_manifest is None:
        logger.error('unable to get libraries manifest')
        sys.exit(3)

    # process arguments in a customized way trying to avoid args that could come from other applications
    version = None
    update = False
    libs_update = False
    reset = False
    processed_args = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == '--app-version':
            version = args[i + 1].strip()
            i += 2
            continue
        elif arg == '--slaunch-app-update':  # update local app
            update = True
        elif arg == '--slaunch-libs-update':  # update local libs
            libs_update = True
        elif arg == '--slaunch-update':  # update local app + libs
            update = True
            libs_update = True
        elif arg == '--slaunch-full-reset':  # update local app + libs + environment
            reset = True
        else:
            processed_args.append(arg)
        i += 1

    # select if name comes from executable/link name or if it should be from an argument
    if (app_name := pathlib.Path(processed_args[0]).stem.lower()) in apps_manifest:
        app_args = processed_args[1:]
    elif len(processed_args) > 1:  # 1st entry is self, so we need to get at least 2nd entry if stem is not app_name
        app_name = processed_args[1]
        app_args = processed_args[2:]
    else:
        logger.error('Insufficient Arguments to determine app name and run...: %s', processed_args)
        sys.exit(1)

    return launch_app(app_name, *app_args,
                      apps_manifest=apps_manifest, libs_manifest=libs_manifest,
                      version=version, app_update=update, libs_update=libs_update, reset=reset)
