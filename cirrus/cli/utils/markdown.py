import copy
import re

from commonmark import node as cm_node
from commonmark.node import Node

from rich.markdown import TextElement, Markdown as _Markdown


## NOTE ##
# This file is not currently used. The rich markdown parser is based on the
# commonmark spec python parser, which for whatever reason does not support
# tables. rich does support tables, but as the markdown parser doesn't
# understand them, rich cannot properly display tables (they end up as one
# long line).
#
# Therefore, the following is a terrible attempt to hack markdown table
# support into rich. The approach has not and currently does not work, but
# I figured I'd keep it around in case I want to come back it the problem.


cm_node.reContainer = re.compile(
    r'(document|block_quote|list|item|paragraph|'
    r'heading|emph|strong|link|image|'
    r'custom_inline|custom_block|table|tablerow|tablecell)')


class NotTableError(Exception):
    pass


def _new__next__(self):
    cur = self.current
    entering = self.entering

    if cur is None:
        raise StopIteration

    container = cm_node.is_container(cur)

    if entering and container:
        if cur.first_child:
            self.current = cur.first_child
            self.entering = True
        else:
            # stay on node but exit
            self.entering = False
    elif cur == self.root:
        self.current = cur.nxt if entering else None
    elif cur.nxt is None:
        self.current = cur.parent
        self.entering = False
    else:
        self.current = cur.nxt
        self.entering = True

    return cur, entering


cm_node.NodeWalker.__next__ = _new__next__


class Table(TextElement):
    """A table."""

    style_name = "markdown.table"

    #def __init__(self) -> None:
    #    print('init table')
    #    self.elements: Renderables = Renderables()

    #def on_child_close(
    #    self, context: "MarkdownContext", child: "MarkdownElement"
    #) -> bool:
    #    self.elements.append(child)
    #    return False

    #def on_text(self, context: "MarkdownContext", text: TextType) -> None:
    #    self.text.append('element')
    #    self.text.append(text, context.current_style if isinstance(text, str) else None)

    #def __rich_console__(
    #    self, console: Console, options: ConsoleOptions
    #) -> RenderResult:
    #    render_options = options.update(width=options.max_width - 4)
    #    lines = console.render_lines(self.elements, render_options, style=self.style)
    #    style = self.style
    #    new_line = Segment("\n")
    #    padding = Segment("▌ ", style)
    #    for line in lines:
    #        yield padding
    #        yield from line
    #        yield new_line


class TableRow(TextElement):
    """A table row."""

    style_name = "markdown.tablerow"


class TableCell(TextElement):
    """A table cell."""

    style_name = "markdown.tablecell"


def next_paragraph(nodewalker):
    for node,entering in nodewalker:
        if node.t == 'paragraph':
            return node


def print_node_walker(node):
    print(f'---- node walker {node} ----')
    for node, entering in node.walker():
        print(node, entering)
    print('---- end node walker ----')


def yield_rows(node):
    while node:
        first_node = node
        last_node = node
        while node:
            if node.t == 'softbreak':
                node = node.nxt
                break
            last_node = node
            node = node.nxt
        yield new_row(first_node, last_node)


def new_row(first_node: Node, last_node: Node) -> Node:
    if first_node.t != 'text':
        raise NotTableError(1)
    if last_node.t != 'text':
        raise NotTableError(2)
    if not first_node.literal.startswith('|'):
        raise NotTableError(3)
    if not last_node.literal.rstrip().endswith('|'):
        raise NotTableError(4)

    first_node.literal = first_node.literal[1:].lstrip()
    last_node.literal = last_node.literal.rstrip()[:-1].rstrip()

    if first_node.literal == '':
        if first_node.nxt is None:
            raise NotTableError(5)
        first_node = first_node.nxt

    if last_node.literal == '':
        if last_node.prv is None:
            raise NotTableError(6)
        last_node = last_node.prv

    row = Node('tablerow', None)
    for cell in yield_cells(first_node, last_node):
        row.append_child(cell)
    return row


def new_cell(first_node: Node, last_node: Node) -> Node:
    node = first_node
    cell = Node('tablecell', None)
    while node:
        if node.t != 'text' or not '|' in node.literal:
            cell.append_child(copy.copy(node))
            if node == last_node:
                node = None
            else:
                node = node.nxt
        else:
            _node = node
            node = copy.copy(node)
            new_node = Node('text', None)
            text, remainder = node.literal.split('|', 1)
            node.literal = remainder.lstrip()
            new_node.literal = text.rstrip()
            if not node.literal:
                if _node == last_node:
                    node = None
                else:
                    node = node.nxt
            if new_node.literal:
                cell.append_child(new_node)
            break
    return cell, node


def yield_cells(first_node, last_node):
    while True:
        cell, first_node = new_cell(first_node, last_node)
        yield cell
        if first_node is None:
            break


def convert_paragraph_to_table(original_node, entering):
    if not entering or original_node.t != 'paragraph':
        return

    copy_node = copy.deepcopy(original_node)
    new_node = Node('table', None)
    new_node.parent = original_node

    for row in yield_rows(copy_node.first_child):
        new_node.append_child(row)

    print_node_walker(new_node)
    if new_node.first_child is None:
        return
    original_node.first_child = new_node
    original_node.last_child = new_node


class Markdown(_Markdown):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.elements['table'] = Table
        self.elements['tablerow'] = TableRow
        self.elements['tablecell'] = TableCell

        walker = self.parsed.walker()

        for node, entering in walker:
            try:
                convert_paragraph_to_table(node, entering)
            except NotTableError as e:
                print(e)
                pass
