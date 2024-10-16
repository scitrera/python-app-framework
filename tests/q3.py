from scitrera_app_framework import (init_framework, get_extension, EXT_BACKGROUND_EXEC)

if __name__ == '__main__':
    init_framework('test-app-q3')

    get_extension(EXT_BACKGROUND_EXEC).submit_job(print, 'bg exec job')

    from scitrera_app_framework.base_plugins import get_background_exec

    get_background_exec().submit_job(print, 'bg exec job 2')
