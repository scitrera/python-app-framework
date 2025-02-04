import time
import multiprocessing

from scitrera_app_framework import init_framework, get_logger
from scitrera_app_framework.core import log_framework_variables


def launch_sub_main(sub_id: int, parent_name: str = 'test-app-mp1-no-name-given', ):
    s = init_framework(parent_name, sub_id=sub_id)
    log_framework_variables(s)

    l = get_logger(s)
    l.info('APP_NAME = %s', s.get('APP_NAME'))
    l.info('BASE_APP_NAME = %s', s.get('SAF_BASE_APP_NAME'))

    time.sleep(5)


if __name__ == '__main__':
    v = init_framework('test-app-mp1')
    log_framework_variables(v)

    logger = get_logger(v)
    logger.info('APP_NAME = %s', v.get('APP_NAME'))
    logger.info('BASE_APP_NAME = %s', v.get('SAF_BASE_APP_NAME'))

    logger.info('p1 start')
    p1 = multiprocessing.Process(target=launch_sub_main, args=(1,), kwargs={'parent_name': v.get('SAF_BASE_APP_NAME')})
    p1.start()

    logger.info('p2 start')
    p2 = multiprocessing.Process(target=launch_sub_main, args=(2,), kwargs={'parent_name': v.get('SAF_BASE_APP_NAME')})
    p2.start()

    logger.info('end')
