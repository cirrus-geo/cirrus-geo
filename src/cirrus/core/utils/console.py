from rich.console import Console
from rich.markup import escape

console = Console()


def print_escaped(self, *args, **kwargs):
    self.print(escape(*args, **kwargs))


console.print_escaped = print_escaped.__get__(console)
