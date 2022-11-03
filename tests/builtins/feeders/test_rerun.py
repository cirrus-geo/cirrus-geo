from cirrus.test import run_feeder


def test_empty_event():
    run_feeder("feed-rerun", {})
