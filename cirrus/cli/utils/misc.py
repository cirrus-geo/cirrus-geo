def get_cirrus_lib_requirement() -> str:
    '''
    Get the cirrus-lib dependency specified for this package.
    '''
    from importlib import metadata

    package_name = __package__.split('.')[0]
    return [
        req for req in metadata.requires(package_name)
        if req.startswith('cirrus-lib')
    ][0]
