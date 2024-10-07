from cirrus.core.utils import misc


def test_get_cirrus_geo_lib2_requirements():
    assert misc.get_cirrus_geo_lib2_requirements() == [
        "boto3-utils~=0.4.1",
        "boto3>=1.26.0",
        "python-json-logger~=2.0",
        "jsonpath-ng>=1.5.3",
        "python-dateutil~=2.9.0",
    ]
