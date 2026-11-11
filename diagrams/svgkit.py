#!/usr/bin/env python3
"""Drawing kit for this submission's figures.

The grammar is deliberately small, because the subject is small: an order is a
sequence of events that is never erased, and the compute that produces them is
not there to draw. So a box means "a thing that runs", a line means "a message",
a number means "a position in the stream", and nothing else is given chrome.

Two colours carry meaning and no others: one for the path that commits, one for
the path that undoes. Everything drawn at a design width of 880 units.
"""
from pathlib import Path

OUT = Path(__file__).parent / "src"

FONT = "Optima, Palatino, serif"
INK = "#17323b"          # slate-teal; the only text colour
RULE = "#9fb0b5"         # structure
QUIET = "#6b7d83"        # secondary text
COMMIT = "#0e6e58"       # the path that completes. Used for nothing else.
UNDO = "#8c2f22"         # the path that compensates. Used for nothing else.
WASH = "#eef3f2"         # one fill, for things MaltaShop does not run
WHITE = "#ffffff"

COLOURS = {"ink": INK, "rule": RULE, "quiet": QUIET, "commit": COMMIT, "undo": UNDO}


def svg(width, height, body):
    markers = "".join(
        f'<marker id="a-{name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" '
        f'markerHeight="6.5" orient="auto-start-reverse">'
        f'<path d="M0,1.5 L9,5 L0,8.5 z" fill="{colour}"/></marker>'
        for name, colour in COLOURS.items())
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" font-family="{FONT}">\n<defs>{markers}</defs>\n'
            f'<rect width="{width}" height="{height}" fill="white"/>\n{body}\n</svg>\n')


def esc(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, content, size=13, anchor="middle", colour=INK, weight=None, italic=False):
    style = f' font-weight="{weight}"' if weight else ""
    style += ' font-style="italic"' if italic else ""
    return (f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" fill="{colour}"'
            f'{style}>{esc(content)}</text>')


def lines(x, y, rows, size=12, gap=16, **kw):
    return "\n".join(text(x, y + i * gap, row, size=size, **kw) for i, row in enumerate(rows))


def rule(x1, y, x2, colour=RULE, width=0.9, dashed=False):
    dash = ' stroke-dasharray="5 4"' if dashed else ""
    return (f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{colour}" '
            f'stroke-width="{width}"{dash}/>')


def vrule(x, y1, y2, colour=RULE, width=0.9, dashed=False):
    dash = ' stroke-dasharray="5 4"' if dashed else ""
    return (f'<line x1="{x}" y1="{y1}" x2="{x}" y2="{y2}" stroke="{colour}" '
            f'stroke-width="{width}"{dash}/>')


def box(x, y, w, h, fill=WHITE, stroke=INK, width=1.1, dashed=False):
    """A box means a thing that runs. Nothing decorative is ever boxed."""
    dash = ' stroke-dasharray="5 4"' if dashed else ""
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{width}"{dash}/>')


def node(x, y, w, h, name, rows=(), stroke=INK, fill=WHITE, size=13, weight="600", gap=15):
    """A deployable: its name, and what it owns or does."""
    parts = [box(x, y, w, h, fill, stroke, 1.1 if stroke == INK else 1.5),
             text(x + w / 2, y + 20, name, size=size, weight=weight, colour=stroke)]
    if rows:
        parts.append(lines(x + w / 2, y + 38, rows, size=11, gap=gap, colour=QUIET))
    return "\n".join(parts)


def arrow(x1, y1, x2, y2, colour="ink", dashed=False, width=1.1, both=False):
    dash = ' stroke-dasharray="5 4"' if dashed else ""
    start = f' marker-start="url(#a-{colour})"' if both else ""
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{COLOURS[colour]}" '
            f'stroke-width="{width}"{dash}{start} marker-end="url(#a-{colour})"/>')


def path(points, colour="ink", dashed=False, width=1.1, arrowhead=True):
    dash = ' stroke-dasharray="5 4"' if dashed else ""
    head = f' marker-end="url(#a-{colour})"' if arrowhead else ""
    pts = " ".join(f"{x},{y}" for x, y in points)
    return (f'<polyline points="{pts}" fill="none" stroke="{COLOURS[colour]}" '
            f'stroke-width="{width}"{dash}{head}/>')


def spine(y, x1, x2, name, detail=None):
    """The event bus: one continuous line that producers drop onto and consumers
    rise from. It is the shape of the system, so it is drawn as one object."""
    parts = [f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{INK}" stroke-width="3"/>',
             f'<circle cx="{x1}" cy="{y}" r="3.5" fill="{INK}"/>',
             f'<circle cx="{x2}" cy="{y}" r="3.5" fill="{INK}"/>',
             text(x1, y - 16, name, size=13, anchor="start", weight="600")]
    if detail:
        parts.append(text(x2, y - 16, detail, size=11, anchor="end", colour=QUIET))
    return "\n".join(parts)


def tap(x, y_spine, y_node, colour="ink", up=False, dashed=False):
    """A drop onto the spine, or a rise from it."""
    return "\n".join([
        arrow(x, y_node, x, y_spine - (0 if up else 0), colour, dashed=dashed) if not up
        else arrow(x, y_spine, x, y_node, colour, dashed=dashed),
        f'<circle cx="{x}" cy="{y_spine}" r="2.6" fill="{COLOURS[colour]}"/>'])


def seq(x, y, number, label, detail=None, colour=INK):
    """One entry on the sequence rail. The numbers are the prototype's real
    sequence numbers, not decoration: the stream is genuinely ordered."""
    parts = [f'<circle cx="{x}" cy="{y}" r="9" fill="{WHITE}" stroke="{colour}" stroke-width="1.2"/>',
             text(x, y + 4, number, size=11, weight="600", colour=colour),
             text(x + 18, y + 4, label, size=12.5, anchor="start", colour=INK)]
    if detail:
        parts.append(text(x + 18, y + 19, detail, size=10.5, anchor="start", colour=QUIET))
    return "\n".join(parts)


def bar(x, y, w, h, filled, fill_colour=UNDO, track=WASH):
    """A quantity drawn to scale, because a quantity drawn to scale says more than
    the same number set large."""
    return "\n".join([
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{track}" stroke="{RULE}" stroke-width="0.8"/>',
        f'<rect x="{x}" y="{y}" width="{max(w * filled, 1.5)}" height="{h}" fill="{fill_colour}"/>'])


def store(x, y, label, colour=INK):
    """A persistent store, drawn small because it is not the point of any figure."""
    return "\n".join([
        f'<path d="M{x},{y + 3.5} v7 a5,3.5 0 0 0 10,0 v-7" fill="none" stroke="{colour}" stroke-width="1"/>',
        f'<ellipse cx="{x + 5}" cy="{y + 3.5}" rx="5" ry="3.5" fill="none" stroke="{colour}" stroke-width="1"/>',
        text(x + 14, y + 11, label, size=10.5, anchor="start", colour=QUIET)])
