def recursive_compare(d1, d2, level='root'):
    if isinstance(d1, dict) and isinstance(d2, dict):
        if d1.keys() != d2.keys():
            s1 = set(d1.keys())
            s2 = set(d2.keys())
            print('{:<20} + {} - {}'.format(level, s1-s2, s2-s1))
            common_keys = s1 & s2
        else:
            common_keys = set(d1.keys())

        for k in common_keys:
            recursive_compare(d1[k], d2[k], level='{}.{}'.format(level, k))

    elif isinstance(d1, list) and isinstance(d2, list):
        if len(d1) != len(d2):
            print('{:<20} len1={}; len2={}'.format(level, len(d1), len(d2)))
        common_len = min(len(d1), len(d2))

        for i in range(common_len):
            recursive_compare(d1[i], d2[i], level='{}[{}]'.format(level, i))

    else:
        if d1 != d2:
            print('{:<20} {} != {}'.format(level, d1, d2))


def parse_args(args=None):
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('json1_file')
    parser.add_argument('json2_file')

    return parser.parse_args(args)


def load_json(json_file):
    import json
    with open(json_file) as jf:
        return json.load(jf)


if __name__ == '__main__':
    args = parse_args()
    d1 = load_json(args.json1_file)
    d2 = load_json(args.json2_file)

    recursive_compare(d1, d2)
