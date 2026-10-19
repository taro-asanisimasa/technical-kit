#!/usr/bin/env python3
"""Read-only structural and approximate layout checks for draw.io files.

Errors are malformed structures. Warnings require inspection and may include
intentional overlaps. A zero exit status does not certify visual correctness.
"""
from __future__ import annotations

import argparse
from collections import Counter
from html.parser import HTMLParser
import json
import math
import sys
import unicodedata

from diagram_io import (DiagramError, absolute_rect, edge_points, geometry,
                        load_diagrams, number, parse_style)


class PlainLabel(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"br", "div", "p"} and self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"div", "p"} and self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def plain_label(cell):
    value = cell.get("value", "")
    if parse_style(cell).get("html") == "1":
        parser = PlainLabel()
        parser.feed(value)
        return "".join(parser.parts).strip("\n")
    return value


def invisible_container(style):
    return (style.get("container") == "1" and style.get("fillColor") == "none"
            and style.get("strokeColor") == "none")


def invisible_point(cell):
    style = parse_style(cell)
    geom = geometry(cell)
    return (not cell.get("value") and style.get("fillColor") == "none"
            and style.get("strokeColor") == "none" and geom is not None
            and number(geom.get("width")) == 0 and number(geom.get("height")) == 0)


def visible(page, cell):
    seen = set()
    while cell is not None:
        identity = cell.get("id")
        if identity in seen:
            return False
        seen.add(identity)
        if cell.get("visible") == "0":
            return False
        cell = page.by_id.get(cell.get("parent", ""))
    return True


def ancestors(page, cell):
    result = set()
    while cell is not None and cell.get("parent"):
        identity = cell.get("parent")
        if identity in result:
            break
        result.add(identity)
        cell = page.by_id.get(identity)
    return result


def intersects_rect(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def segment_box(a, b, rect, inset=0.2):
    """Liang-Barsky interior intersection, excluding mere boundary touches."""
    x, y, w, h = rect
    x, y, w, h = x + inset, y + inset, w - 2 * inset, h - 2 * inset
    if w <= 0 or h <= 0:
        return False
    dx, dy = b[0] - a[0], b[1] - a[1]
    low, high = 0.0, 1.0
    for p, q in ((-dx, a[0] - x), (dx, x + w - a[0]), (-dy, a[1] - y), (dy, y + h - a[1])):
        if abs(p) < 1e-10:
            if q < 0:
                return False
        else:
            fraction = q / p
            if p < 0:
                low = max(low, fraction)
            else:
                high = min(high, fraction)
            if low > high:
                return False
    return high > low + 1e-8


def crossing(a, b, c, d):
    # Interior crossings; shared endpoints are legitimate joins.
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    one, two, three, four = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    return one * two < -1e-8 and three * four < -1e-8


def inspect_document(document, *, font_size=18.0, font_family="sans-serif", max_lines=3):
    issues = []

    def add(severity, code, message, page=None, cell=None):
        item = {"severity": severity, "code": code, "message": message}
        if page is not None:
            item["page"] = page.name
        if cell is not None:
            item["cell"] = cell.get("id", "")
        issues.append(item)

    for message in document.warnings:
        add("warning", "embedded-pixels-unverified", message)
    for page in document.pages:
        page_issue_start = len(issues)
        counts = Counter(c.get("id", "") for c in page.cells)
        for identity, count in counts.items():
            if not identity:
                add("error", "missing-id", "A cell has no ID", page)
            if count > 1:
                add("error", "duplicate-id", "Duplicate cell ID: " + identity, page)
        rects, routes = {}, {}
        for cell in page.cells:
            identity = cell.get("id", "")
            for attr in ("parent", "source", "target"):
                ref = cell.get(attr)
                if ref is not None and ref not in page.by_id:
                    add("error", "missing-reference", attr + " references unknown ID: " + ref, page, cell)
            try:
                # Check every numeric field used by geometry, even unused bends.
                for elem in cell.iter():
                    if elem.tag in {"mxGeometry", "mxPoint", "mxRectangle"}:
                        for key in ("x", "y", "width", "height"):
                            if key in elem.attrib:
                                number(elem.get(key))
                rect = absolute_rect(page, cell)
                if cell.get("vertex") == "1":
                    if rect is None:
                        add("error", "missing-geometry", "Vertex has no usable geometry", page, cell)
                    elif (rect[2] <= 0 or rect[3] <= 0) and not invisible_point(cell):
                        add("error", "invalid-size", "Vertex width and height must be positive", page, cell)
                    else:
                        rects[identity] = rect
            except DiagramError as exc:
                add("error", "invalid-geometry", str(exc), page, cell)
        if any(item["severity"] == "error" for item in issues[page_issue_start:]):
            add("information", "layout-skipped", "Layout checks skipped because structural errors must be fixed first", page)
            continue
        # Rendering order follows layer/root order, then child order.
        children = {}
        for cell in page.cells:
            children.setdefault(cell.get("parent"), []).append(cell)
        order = {}
        seen = set()

        def visit(cell):
            stack = [cell]
            while stack:
                current = stack.pop()
                identity = current.get("id", "")
                if identity in seen:
                    continue
                seen.add(identity)
                order[identity] = len(order)
                stack.extend(reversed(children.get(identity, [])))

        for cell in children.get(None, []):
            visit(cell)
        for cell in page.cells:
            visit(cell)
        active_boxes = []
        for cell in page.cells:
            if not visible(page, cell):
                add("information", "hidden-cell", "Cell or its layer is hidden; its layout is not visually checked", page, cell)
                continue
            style = parse_style(cell)
            identity = cell.get("id", "")
            label = plain_label(cell)
            if cell.get("vertex") == "1" and not invisible_container(style) and not invisible_point(cell):
                rect = rects.get(identity)
                if rect:
                    active_boxes.append((cell, rect))
            if label and (cell.get("vertex") == "1" or cell.get("edge") == "1") and not invisible_container(style):
                try:
                    size = number(style.get("fontSize"), font_size)
                    if size <= 0:
                        raise DiagramError("fontSize must be positive")
                    if "fontSize" not in style:
                        add("warning", "inherited-font-size", "fontSize is inherited; the editor default has not been verified", page, cell)
                    elif abs(size - font_size) > 0.01:
                        add("warning", "font-size-policy", "fontSize differs from configured reference " + str(font_size), page, cell)
                    family = style.get("fontFamily")
                    if not family:
                        add("warning", "inherited-font-family", "fontFamily is inherited; availability and fallback need visual inspection", page, cell)
                    elif family.casefold() != font_family.casefold():
                        add("warning", "font-family-policy", "fontFamily differs from configured reference: " + font_family, page, cell)
                    lines = label.splitlines() or [""]
                    if len(lines) > max_lines:
                        add("warning", "label-lines", "Label has more than " + str(max_lines) + " explicit lines", page, cell)
                    rect = rects.get(identity)
                    if rect and cell.get("vertex") == "1":
                        widths = [sum(1.0 if unicodedata.east_asian_width(ch) in {"W", "F"} else 0.55 for ch in line) * size for line in lines]
                        padding = number(style.get("spacing"), 4)
                        available = rect[2] - 2 * padding
                        if max(widths, default=0) > available:
                            add("warning", "label-width-estimate", "Estimated label width exceeds its box; font metrics and wrapping need visual inspection", page, cell)
                        if len(lines) * size * 1.2 > rect[3] - 2 * padding:
                            add("warning", "label-height-estimate", "Estimated label height exceeds its box", page, cell)
                except DiagramError as exc:
                    add("error", "invalid-font", str(exc), page, cell)
            if style.get("rotation") not in {None, "0"} or style.get("shape") in {"swimlane"} or "swimlane" in style:
                add("warning", "special-geometry", "Rotation or swimlane layout needs native rendering; box checks use explicit unrotated geometry", page, cell)
            if cell.get("edge") != "1":
                continue
            for prefix in ("exit", "entry"):
                values = [style.get(prefix + key) for key in ("X", "Y")]
                if any(v is not None for v in values) and not all(v is not None for v in values):
                    add("warning", "incomplete-port", prefix + " port has only one normalized coordinate", page, cell)
                try:
                    if any(v is not None and not 0 <= number(v) <= 1 for v in values):
                        add("warning", "port-range", prefix + " port is outside its box", page, cell)
                    for suffix in ("Dx", "Dy"):
                        if prefix + suffix in style:
                            number(style[prefix + suffix])
                except DiagramError as exc:
                    add("error", "invalid-port", str(exc), page, cell)
            try:
                points = edge_points(page, cell)
                if points is None:
                    add("warning", "implicit-route", "Route cannot be resolved from explicit points; inspect in draw.io", page, cell)
                    continue
                routes[identity] = points
                if len(points) > 32:
                    add("warning", "many-bends", "Route has more than 30 waypoints", page, cell)
                ortho = "orthogonal" in style.get("edgeStyle", "").lower() or "elbow" in style.get("edgeStyle", "").lower()
                for a, b in zip(points, points[1:]):
                    if math.dist(a, b) < 0.01:
                        add("warning", "zero-segment", "Route has coincident adjacent points", page, cell)
                    elif ortho and abs(a[0] - b[0]) > 0.01 and abs(a[1] - b[1]) > 0.01:
                        add("warning", "diagonal-orthogonal", "Explicit orthogonal route contains a diagonal segment; native routing may add bends", page, cell)
                for role in ("source", "target"):
                    rect = rects.get(cell.get(role, ""))
                    terminal = page.by_id.get(cell.get(role, ""))
                    terminal_style = parse_style(terminal) if terminal is not None else {}
                    junction_marker = (rect is not None and rect[2] <= 12 and rect[3] <= 12
                                       and terminal_style.get("shape") == "ellipse"
                                       and terminal_style.get("connectable") == "0"
                                       and not terminal.get("value"))
                    if rect and not junction_marker and any(
                            segment_box(a, b, rect) for a, b in zip(points, points[1:])):
                        add("warning", "connection-direction", "Route crosses the interior of its " + role + " box; check ports and intermediate bends", page, cell)
            except DiagramError as exc:
                add("error", "invalid-route", str(exc), page, cell)
        # Bound quadratic layout checks, disclosing omitted checks instead of PASS.
        if len(active_boxes) > 500 or len(routes) > 500 or sum(len(p) for p in routes.values()) > 4000:
            add("warning", "layout-limit", "Large page: pairwise overlap/crossing checks were skipped (500 boxes/routes, 4000 route points maximum)", page)
            continue
        for index, (cell, rect) in enumerate(active_boxes):
            style = parse_style(cell)
            is_background = style.get("container") == "1" or style.get("swimlane") is not None or style.get("shape") == "swimlane"
            for other, other_rect in active_boxes[index + 1:]:
                if not intersects_rect(rect, other_rect):
                    continue
                related = cell.get("id") in ancestors(page, other) or other.get("id") in ancestors(page, cell)
                other_style = parse_style(other)
                other_background = other_style.get("container") == "1"
                if not related and not is_background and not other_background:
                    add("warning", "box-overlap", "Overlaps box " + other.get("id", ""), page, cell)
            for edge_id, points in routes.items():
                edge = page.by_id[edge_id]
                if cell.get("id") in {edge.get("source"), edge.get("target")}:
                    continue
                if any(segment_box(a, b, rect) for a, b in zip(points, points[1:])):
                    if is_background:
                        fill = style.get("fillColor", "default")
                        if fill != "none" and style.get("opacity") != "0" and order.get(cell.get("id"), -1) > order.get(edge_id, -1):
                            add("warning", "background-covers-route", "Filled background is drawn after crossing edge " + edge_id, page, cell)
                    elif cell.get("id") not in ancestors(page, edge):
                        add("warning", "route-box-intersection", "Route " + edge_id + " passes through this unrelated box", page, cell)
        items = list(routes.items())
        for index, (first_id, first) in enumerate(items):
            for second_id, second in items[index + 1:]:
                if any(crossing(a, b, c, d) for a, b in zip(first, first[1:]) for c, d in zip(second, second[1:])):
                    add("warning", "route-crossing", "Crosses route " + second_id + "; inspect whether an explicit junction is needed", page, page.by_id[first_id])
        add("information", "visual-check-required", "Checks use approximate text widths and rectangular bounds; fonts, curved paths, icons, inherited styles, labels on edges, and final rendering still require visual review", page)
    return issues


def positive(value):
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("must be finite and positive")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("--json", action="store_true", help="Machine-readable result; input is never modified")
    parser.add_argument("--font-size", type=positive, default=18.0, help="Reference size; default 18")
    parser.add_argument("--font-family", default="sans-serif", help="Reference family; availability is not verified")
    parser.add_argument("--max-lines", type=int, choices=range(1, 101), default=3, metavar="1..100")
    args = parser.parse_args(argv)
    try:
        document = load_diagrams(args.input)
        issues = inspect_document(document, font_size=args.font_size, font_family=args.font_family, max_lines=args.max_lines)
    except (DiagramError, OSError, UnicodeError) as exc:
        issues = [{"severity": "error", "code": "input-error", "message": str(exc)}]
    counts = Counter(item["severity"] for item in issues)
    result = {"input": args.input, "summary": {"errors": counts["error"], "warnings": counts["warning"], "information": counts["information"]}, "issues": issues}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for item in issues:
            location = " / ".join(str(item[key]) for key in ("page", "cell") if key in item)
            print(item["severity"].upper() + " " + item["code"] + (" [" + location + "]" if location else "") + ": " + item["message"])
        print("Errors: {errors}; warnings: {warnings}; information: {information}".format(**result["summary"]))
    return 1 if counts["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
