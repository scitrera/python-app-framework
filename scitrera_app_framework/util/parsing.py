def ext_parse_bool(val):
    """
    (Extended) Parse a given input (bool string), usually string from environment variable, to a boolean value.

    The logic for this function is basically to see:
    'true', 't', 'yes', 'y', or '1' as True and
    'false', 'f', 'no', 'n', '0' or EMPTY as False

    :param val: value to interpret
    :return: e
    """
    if isinstance(val, bool):
        return val
    elif not val:
        return False  # TODO: maybe differentiate between not set and False
    vl = str(val).lower()
    return '1' in vl or 't' in vl or 'y' in vl


def ext_parse_csv(val):
    """
    (Extended) Parse a csv input (typically from environment variable) into a list of strings

    :param val:
    :return:
    """
    if not val:
        return []
    elif isinstance(val, list):  # handle case when given a list instead of csv
        return [part.strip() for part in val if part]
    return [part.strip() for part in str(val).split(',') if part]
