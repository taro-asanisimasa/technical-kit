#!/usr/bin/env python3
"""Create an offline, approximate SVG/HTML preview (not a native renderer).

The HTML shows the selected page fitted to the available width and at 100%.
No external resources, diagram links, images, or embedded markup are executed.
"""
from __future__ import annotations

import argparse
import html
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata

from check import inspect_document, invisible_container, invisible_point, plain_label, visible
from diagram_io import DiagramError, absolute_rect, edge_points, load_diagrams, number, parse_style


def escape(value):
    return html.escape(str(value), quote=True)


def color(value, fallback):
    if value == "none" or re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?", value or ""):
        return value
    return fallback


def family(value):
    # SVG text attributes, not CSS declarations. Reject punctuation with CSS meaning.
    return value if re.fullmatch(r"[\w ,.-]{1,120}", value or "", re.UNICODE) else "sans-serif"


def polyline_midpoint(points):
    """Interpolate halfway along the visible polyline, including unequal legs."""
    if not points:
        raise DiagramError("Cannot position a label on an empty route")
    lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
    remaining = sum(lengths) / 2
    if not remaining:
        return points[0]
    for first, second, length in zip(points, points[1:], lengths):
        if length and remaining <= length:
            fraction = remaining / length
            return (first[0] + (second[0] - first[0]) * fraction,
                    first[1] + (second[1] - first[1]) * fraction)
        remaining -= length
    return points[-1]


def svg_page(page):
    limitations = ["This is an approximate offline preview. Verify and re-save the final file in draw.io.",
                   "Text metrics, wrapping, rectangular connection points, shadows, and inherited styles are approximate."]
    children = {}
    for cell in page.cells:
        children.setdefault(cell.get("parent"), []).append(cell)
    ordered = []
    seen = set()

    def visit(cell):
        stack = [cell]
        while stack:
            current = stack.pop()
            identity = current.get("id", "")
            if identity in seen:
                continue
            seen.add(identity)
            ordered.append(current)
            stack.extend(reversed(children.get(identity, [])))

    for cell in children.get(None, []):
        visit(cell)
    for cell in page.cells:
        visit(cell)
    bounds = []
    pieces = []
    for cell in ordered:
        identity = cell.get("id", "")
        if not visible(page, cell):
            limitations.append("Hidden cell or layer omitted: " + identity)
            continue
        style = parse_style(cell)
        if invisible_container(style) or invisible_point(cell):
            continue
        if style.get("html") == "1" and cell.get("value"):
            limitations.append("HTML label reduced to plain text: " + identity)
        if cell.get("link") or "image" in style:
            limitations.append("External link/image omitted: " + identity)
        if style.get("rotation") not in {None, "0"}:
            limitations.append("Rotation omitted: " + identity)
        if style.get("opacity") is not None:
            opacity = max(0, min(1, number(style.get("opacity")) / 100))
        else:
            opacity = 1
        fill = color(style.get("fillColor"), "#ffffff")
        stroke = color(style.get("strokeColor"), "#333333")
        width = max(0.1, min(20, number(style.get("strokeWidth"), 1)))
        dashed = ' stroke-dasharray="6 4"' if style.get("dashed") == "1" else ""
        label = plain_label(cell)
        label_at = None
        label_background = None
        if cell.get("vertex") == "1":
            rect = absolute_rect(page, cell)
            if rect is None:
                raise DiagramError("No usable rectangle: " + identity)
            x, y, w, h = rect
            bounds.append((x, y, x + w, y + h))
            shape = style.get("shape", "")
            if "ellipse" in style:
                shape = "ellipse"
            if "rhombus" in style:
                shape = "rhombus"
            if "swimlane" in style:
                shape = "swimlane"
            common = ' fill="{}" stroke="{}" stroke-width="{}" opacity="{}"{}'.format(fill, stroke, width, opacity, dashed)
            if shape == "ellipse":
                pieces.append('<ellipse cx="{}" cy="{}" rx="{}" ry="{}"{}/>'.format(x + w / 2, y + h / 2, w / 2, h / 2, common))
            elif shape == "rhombus":
                points = [(x + w / 2, y), (x + w, y + h / 2), (x + w / 2, y + h), (x, y + h / 2)]
                pieces.append('<polygon points="{}"{}/>'.format(" ".join("{},{}".format(*p) for p in points), common))
            elif shape in {"", "rectangle", "rect", "text"}:
                radius = min(w, h) * 0.08 if style.get("rounded") == "1" else 0
                if "text" in style or shape == "text":
                    common = ' fill="none" stroke="none"'
                pieces.append('<rect x="{}" y="{}" width="{}" height="{}" rx="{}"{}/>'.format(x, y, w, h, radius, common))
            else:
                limitations.append("Unsupported shape shown only as a red bounding box: " + identity + " (" + shape + ")")
                pieces.append('<rect x="{}" y="{}" width="{}" height="{}" fill="none" stroke="#cc0000" stroke-dasharray="4 4"/>'.format(x, y, w, h))
            align = style.get("align", "center")
            if align not in {"left", "center", "right"}:
                align = "center"
            tx = x + 6 if align == "left" else x + w - 6 if align == "right" else x + w / 2
            label_at = (tx, y + h / 2, align)
            if style.get("verticalAlign") in {"top", "bottom"}:
                label_at = (tx, y + 10 if style["verticalAlign"] == "top" else y + h - 10, align)
        elif cell.get("edge") == "1":
            points = edge_points(page, cell)
            if points is None:
                limitations.append("Implicit or curved route omitted; inspect in draw.io: " + identity)
                continue
            if len(points) > 2000:
                raise DiagramError("Too many points to preview for edge " + identity)
            bounds.extend((px, py, px, py) for px, py in points)
            marker = ''
            for attr, suffix in (("endArrow", "end"), ("startArrow", "start")):
                arrow = style.get(attr, "classic" if suffix == "end" else "none")
                if arrow not in {"", "none", "0"}:
                    marker += ' marker-{}="url(#arrow)"'.format(suffix)
                    if arrow not in {"classic", "block"}:
                        limitations.append("Arrow style approximated as triangle: " + identity + " (" + arrow + ")")
            pieces.append('<polyline points="{}" fill="none" stroke="{}" stroke-width="{}" opacity="{}"{}{}/>'.format(
                " ".join("{},{}".format(*p) for p in points), stroke, width, opacity, dashed, marker))
            if label:
                middle = polyline_midpoint(points)
                label_at = (*middle, "center")
                label_background = color(style.get("labelBackgroundColor"), None)
                limitations.append("Edge label position approximated: " + identity)
        if label and label_at:
            size = max(1, min(200, number(style.get("fontSize"), 18)))
            tx, ty, align = label_at
            lines = label.splitlines() or [""]
            if len(lines) > 200:
                raise DiagramError("Label has too many lines to preview: " + identity)
            if label_background and label_background != "none":
                label_width = max(sum(1.0 if unicodedata.east_asian_width(char) in {"W", "F"}
                                      else 0.58 for char in line) for line in lines) * size
                label_height = len(lines) * size * 1.2
                bx, by = tx - label_width / 2 - 4, ty - label_height / 2 - 2
                bw, bh = label_width + 8, label_height + 4
                pieces.append('<rect x="{}" y="{}" width="{}" height="{}" fill="{}" stroke="none" rx="2"/>'.format(
                    bx, by, bw, bh, label_background))
                bounds.append((bx, by, bx + bw, by + bh))
            ty -= (len(lines) - 1) * size * 1.2 / 2
            anchor = {"left": "start", "center": "middle", "right": "end"}[align]
            pieces.append('<text x="{}" y="{}" text-anchor="{}" dominant-baseline="middle" font-family="{}" font-size="{}" fill="{}">'.format(
                tx, ty, anchor, escape(family(style.get("fontFamily"))), size, color(style.get("fontColor"), "#222222")))
            for index, line in enumerate(lines):
                pieces.append('<tspan x="{}" dy="{}">{}</tspan>'.format(tx, 0 if index == 0 else size * 1.2, escape(line)))
            pieces.append('</text>')
    if not bounds:
        raise DiagramError("Selected page has no visible geometry")
    left = min(b[0] for b in bounds) - 24
    top = min(b[1] for b in bounds) - 24
    right = max(b[2] for b in bounds) + 24
    bottom = max(b[3] for b in bounds) + 24
    width, height = max(1, right - left), max(1, bottom - top)
    if width > 100000 or height > 100000:
        raise DiagramError("Preview bounds exceed 100,000 units")
    content = '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#333333"/></marker></defs>' + "".join(pieces)
    return content, (left, top, width, height), list(dict.fromkeys(limitations))


def make_html(document, page_index):
    page = document.pages[page_index]
    errors = [item for item in inspect_document(document) if item["severity"] == "error"]
    if errors:
        raise DiagramError("Structural checks failed: " + "; ".join(item["message"] for item in errors[:5]))
    content, bounds, limitations = svg_page(page)
    limitations.extend(document.warnings)
    if len(document.pages) > 1:
        limitations.append("Only page {} of {} is shown. Use --page to inspect every other page.".format(page_index + 1, len(document.pages)))
    left, top, width, height = bounds
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="{} {} {} {}" width="{}" height="{}" role="img" aria-label="{}">{}</svg>'.format(
        left, top, width, height, width, height, escape(page.name), content)
    # Local marker IDs are repeated across the two SVGs but have identical content.
    notes = "".join("<li>" + escape(item) + "</li>" for item in limitations)
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; script-src \'none\'; connect-src \'none\'; img-src \'none\'; object-src \'none\'; base-uri \'none\'; form-action \'none\'">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Offline diagram preview</title>'
            '<style>body{font-family:sans-serif;margin:24px;color:#222}h1{font-size:24px}h2{font-size:20px}.notice{padding:12px;border:2px solid #b55d00;background:#fff7e8}.frame{border:1px solid #bbb;background:white;overflow:auto;margin-bottom:24px}.fit svg{display:block;width:100%;height:auto}.actual svg{display:block;max-width:none}li{margin:.4em 0}</style>'
            '</head><body><h1>' + escape(page.name) + '</h1>'
            '<p class="notice">Approximate preview. This page does not confirm native draw.io rendering or consistency with visible PNG pixels.</p>'
            '<details open><summary>Scope and limitations</summary><ul>' + notes + '</ul></details>'
            '<h2>Fit to width</h2><div class="frame fit">' + svg + '</div>'
            '<h2>100% (one diagram unit per CSS pixel)</h2><div class="frame actual">' + svg + '</div>'
            '</body></html>')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("--output", required=True, help="Output HTML path; no automatic browser opening")
    parser.add_argument("--page", type=int, default=1, help="1-based page number; default 1")
    parser.add_argument("--force", action="store_true", help="Replace an existing regular file")
    args = parser.parse_args(argv)
    try:
        source = Path(args.input)
        output = Path(args.output)
        if output.is_symlink() or source.resolve() == output.resolve():
            raise DiagramError("Output must not be a symbolic link or the input file")
        if output.exists() and source.samefile(output):
            raise DiagramError("Output must not be a hard link to the input file")
        if output.exists() and (not args.force or not output.is_file()):
            raise DiagramError("Output exists; use --force to replace a regular file")
        document = load_diagrams(source)
        if not 1 <= args.page <= len(document.pages):
            raise DiagramError("--page is outside the document page range")
        rendered = make_html(document, args.page - 1)
        if args.force:
            temporary_name = None
            try:
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output.parent,
                                                 prefix=".diagram-preview-", suffix=".tmp",
                                                 delete=False) as stream:
                    temporary_name = stream.name
                    stream.write(rendered)
                if output.is_symlink() or (output.exists() and source.samefile(output)):
                    raise DiagramError("Output changed to a symbolic link or an input hard link")
                os.replace(temporary_name, output)
                temporary_name = None
            finally:
                if temporary_name is not None:
                    Path(temporary_name).unlink(missing_ok=True)
        else:
            with output.open("x", encoding="utf-8") as stream:
                stream.write(rendered)
        print("Wrote approximate offline preview: " + str(output))
        print("Native rendering and saved final artifact still require separate review.")
        return 0
    except (DiagramError, OSError, UnicodeError) as exc:
        print("Preview error: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
