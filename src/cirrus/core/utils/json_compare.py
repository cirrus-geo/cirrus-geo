import sys

from cirrus.lib2 import utils


def parse_args(args=None):
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("json1_file")
    parser.add_argument("json2_file")

    return parser.parse_args(args)


def load_json(json_file):
    import json

    with open(json_file) as jf:
        return json.load(jf)


if __name__ == "__main__":
    args = parse_args()
    d1 = load_json(args.json1_file)
    d2 = load_json(args.json2_file)

    sys.exit(not utils.recursive_compare(d1, d2))
