import click


def cli_only_secho(*args, **kwargs):
    try:
        ctx = click.get_current_context()
    except RuntimeError:
        pass
    else:
        click.secho(*args, **kwargs)
