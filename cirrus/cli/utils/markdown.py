import copy

from commonmark.node import Node, NodeWalker, is_container
from rich.markdown import TextElement, Markdown as _Markdown


class NotTableError(Exception):
    pass


def _new__next__(self):
    cur = self.current
    entering = self.entering

    if cur is None:
        raise StopIteration

    container = is_container(cur)

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


NodeWalker.__next__ = _new__next__


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


def print_node_walker(node):
    print(f'---- node walker {node} ----')
    for node, entering in node.walker():
        print(node, entering)
    print('---- end node walker ----')


def yield_rows(node):
    #print_node_walker(node)
    walker = node.walker()
    parent = node.parent
    for node, entering in walker:
        first_node = node
        last_node = None
        while node.t != 'softbreak' and node != parent:
            last_node = node
            try:
                node, entering = next(walker)
            except StopIteration:
                break
        # TODO: validate row
        # must start and end with text node
        # start text node must start with |
        # end text node must end with |, stripped
        yield first_node, last_node


def yield_cells(first_node, last_node):
    # TODO: validate row
    #print_node_walker(first_node)
    walker = first_node.walker()
    for node, entering in walker:
        cell_first_node = None
        cell_last_node = None
        # make sure is text else is first node
        # step through each char in node, testing for |
        # save start and end indicies
        # use to get substring and strip
        # if starts with | and ends without | last text is first node
        # if ends with | then is last node
        # if no | then keep going
        while node.t != 'text':
            if cell_first_node is None:
                cell_first_node = node
            cell_last_node = node
            try:
                node, entering = next(walker)
            except StopIteration:
                break
            if node == last_node:
                return cell_first_node, cell_last_node

        cur = 0
        start = 0
        first = True
        while cur < len(node.literal):
            char = node.literal[cur]
            cur += 1
            if char != '|':
                continue

            if start == cur - 1:
                raise NotTableError(1)

            text = node.literal[start:cur-1].strip()
            start = cur

            if first and not text:
                first = False
                yield cell_first_node, cell_last_node
                continue

            if not text and start != len(node.literal):
                raise NotTableError(2)

            text_node = Node('text', None)
            text_node.literal = text

            if cell_last_node:
                text_node.previous = cell_last_node
                cell_last_node.nxt = text_node

            yield cell_first_node if cell_first_node else text_node, text_node
        else:
            text = node.literal[start:].strip()

            if not text:
                continue

            text_node = Node('text', None)
            text_node.literal = text

            if cell_last_node:
                text_node.previous = cell_last_node
                cell_last_node.nxt = text_node

            yield cell_first_node if cell_first_node else text_node, text_node


def convert_paragraph_to_table(original_node, entering):
    if not entering or original_node.t != 'paragraph':
        return

    #new_node = copy.deepcopy(original_node)
    new_node = Node('table', None)
    new_node.parent = original_node

    print_node_walker(original_node)
    #print_node_walker(original_node.first_child)

    last_row = None
    last_cell = None
    for row_first_node, row_last_node in yield_rows(original_node.first_child):
        row = Node('tablerow', None)
        row.parent = new_node

        if last_row == None:
            new_node.first_child = row

        last_row = row

        last_cell = None
        for cell_first_node, cell_last_node in yield_cells(row_first_node, row_last_node):
            cell = Node('tablecell', None)
            cell.parent = last_row

            if last_cell == None:
                last_row.first_child = cell

            cell.first_child = cell_first_node
            cell.last_child = cell_last_node

            for node, entering in cell_first_node.walker():
                node.parent = cell

            last_cell = cell

        last_row.last_child = last_cell

    new_node.last_child = last_row

    #original_node.__dict__ = new_node.__dict__
    print_node_walker(new_node)
    if not last_cell:
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
