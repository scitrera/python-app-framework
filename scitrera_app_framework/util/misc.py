import time


def no_op(*args, **kwargs):
    return


def now_ms():
    return time.time_ns() // 1_000_000
