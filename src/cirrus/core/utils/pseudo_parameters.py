import re

FN_SUB = "Fn::Sub"
PARAMS = re.compile(r"#{(AWS::[a-zA-Z]+)}")


def replace_pseudo_params_with_sub(key, val):
    if not isinstance(val, str):
        return val

    val, subcount = PARAMS.subn(r"${\g<1>}", val)

    if subcount and key != FN_SUB:
        val = {FN_SUB: val}

    return val
