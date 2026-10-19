#!/usr/bin/env python3
"""Generate an editable, uncompressed draw.io diagram from a small grid JSON.

No network, shell, downloaded icons or third-party libraries are used. Layout is
deliberately explicit: the caller selects the row, column and parent of each box.
Routing compares a bounded set of orthogonal candidates; it is not a general
graph-layout engine and must be followed by structural and visual review.
"""

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

from geometry import (Rect, absolute_rect, estimate_text_width,
                      polyline_length, polyline_segments, proper_intersections,
                      segment_hits_rect, simplify_points, wrap_text)


DEFAULTS = {"margin": 60, "cell_width": 200, "cell_height": 80,
            "gap_x": 104, "gap_y": 60, "padding": 32, "title_height": 42,
            "route_spacing": 26, "font_size": 18, "font_family": "sans-serif"}
ROLES = {
    "external": ("#f5f5f5", "#666666", "External / input"),
    "process": ("#fff2cc", "#d6b656", "Processing"),
    "storage": ("#dae8fc", "#6c8ebf", "Storage"),
    "control": ("#d5e8d4", "#82b366", "Control"),
}
OWNER_COLORS = ["#3b647e", "#7a5195", "#7c5b30", "#35745c", "#555555"]
LAYERS = [("_routes", "Routes"),
          ("_nodes", "Elements"),
          ("_notes", "Notes and legend")]
IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")


def require_object(value, where):
    if not isinstance(value, dict):
        raise ValueError(f"{where}: expected an object")
    return value


def known(value, keys, where):
    require_object(value, where)
    extra = set(value) - set(keys)
    if extra:
        raise ValueError(f"{where}: unknown keys: {', '.join(sorted(extra))}")


def number(value, where, minimum=0, maximum=100000):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{where}: expected a finite number")
    if not minimum <= value <= maximum:
        raise ValueError(f"{where}: expected {minimum}..{maximum}")
    return float(value)


def text(value, where, limit=2000):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f"{where}: expected text, at most {limit} characters")
    if any(not (ord(char) in (9, 10) or 0x20 <= ord(char) <= 0xD7FF or
                0xE000 <= ord(char) <= 0xFFFD or 0x10000 <= ord(char) <= 0x10FFFF) for char in value):
        raise ValueError(f"{where}: unsupported XML character")
    return value


def sequence(value, where):
    if not isinstance(value, list) or len(value) > 1000:
        raise ValueError(f"{where}: expected a list, at most 1000 items")
    return value


def identifier(value, where):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError(f"{where}: use a letter followed by up to 63 letters, digits, _ or -")
    return value


def boolean(value, where):
    if not isinstance(value, bool):
        raise ValueError(f"{where}: expected true or false")
    return value


def point(value, where):
    known(value, {"x", "y"}, where)
    if set(value) != {"x", "y"}:
        raise ValueError(f"{where}: x and y are required")
    return (number(value["x"], where + ".x", -100000),
            number(value["y"], where + ".y", -100000))


def port(value, default, where):
    if value is None:
        return (default, 0.5)
    if isinstance(value, str):
        value = {"side": value}
    known(value, {"side", "position"}, where)
    side = value.get("side", default)
    if side not in ("left", "right", "top", "bottom"):
        raise ValueError(f"{where}: side must be left, right, top or bottom")
    # One normalized fraction is shared by geometry and serialized port style.
    # Otherwise a tall box magnifies the difference from XML's 4-digit value.
    return (side, round(number(value.get("position", 0.5), where + ".position", 0, 1), 4))


def validate(data):
    known(data, {"title", "layout", "groups", "nodes", "edges", "notes", "legend"}, "diagram")
    text(data.get("title", "Diagram"), "title", 200)
    layout = data.get("layout", {})
    known(layout, DEFAULTS, "layout")
    config = dict(DEFAULTS, **layout)
    for key, value in config.items():
        if key == "font_family":
            text(value, "layout.font_family", 80)
            if not re.fullmatch(r"[\w ,.-]+", value):
                raise ValueError("font_family: use a plain font family name")
        else:
            number(value, "layout." + key, 1 if key != "margin" else 0, 5000)
    if config["font_size"] < 12:
        raise ValueError("font_size must be at least 12; 18 is the default")
    if config["cell_width"] < config["font_size"] * 3:
        raise ValueError("cell_width is too narrow for the font_size")
    for key in ("gap_x", "gap_y"):
        if config[key] < config["route_spacing"] * 2:
            raise ValueError(f"{key} must be at least twice route_spacing")
    if "legend" in data:
        boolean(data["legend"], "legend")
    # The helper targets a diagram a person can review, rather than an
    # unbounded architecture graph. Route search is also bounded per edge.
    if len(sequence(data.get("groups", []), "groups")) + len(sequence(data.get("nodes", []), "nodes")) > 250:
        raise ValueError("at most 250 boxes; split a larger diagram")
    if len(sequence(data.get("edges", []), "edges")) > 300:
        raise ValueError("at most 300 logical edges; split a larger diagram")
    objects, groups, nodes, parents = {}, [], [], {}
    occupied = set()
    for kind in ("groups", "nodes"):
        for item in sequence(data.get(kind, []), kind):
            allowed = {"id", "label", "parent", "row", "col", "width", "height", "evidence"}
            if kind == "nodes":
                allowed |= {"role", "status"}
            known(item, allowed, kind)
            for required in ("id", "label", "row", "col"):
                if required not in item:
                    raise ValueError(f"{kind}: {required} is required")
            ident = identifier(item["id"], kind + ".id")
            if ident in objects:
                raise ValueError("duplicate id: " + ident)
            text(item["label"], ident + ".label")
            text(item.get("evidence", ""), ident + ".evidence")
            for key in ("row", "col"):
                if isinstance(item[key], bool) or not isinstance(item[key], int) or not 0 <= item[key] <= 100:
                    raise ValueError(f"{ident}.{key}: expected an integer, 0..100")
            for key in ("width", "height"):
                if key in item:
                    number(item[key], ident + "." + key, config["font_size"] * 2)
            owner = item.get("parent")
            if owner is not None:
                identifier(owner, ident + ".parent")
            slot = (owner, item["row"], item["col"])
            if slot in occupied:
                raise ValueError(f"{ident}: two boxes occupy the same parent/row/col")
            occupied.add(slot)
            parents[ident] = owner
            if kind == "nodes":
                if item.get("role", "process") not in ROLES:
                    raise ValueError(f"{ident}.role: expected {', '.join(ROLES)}")
                text(item.get("status", ""), ident + ".status", 120)
                nodes.append(item)
            else:
                groups.append(item)
            objects[ident] = item
    group_ids = {g["id"] for g in groups}
    for ident, owner in parents.items():
        if owner is not None and owner not in group_ids:
            raise ValueError(f"{ident}: parent must name a group")
        seen = {ident}
        depth = 0
        while owner is not None:
            if owner in seen:
                raise ValueError("parent cycle")
            seen.add(owner)
            owner = parents[owner]
            depth += 1
            if depth > 10:
                raise ValueError("group nesting exceeds 10")
    node_ids = {n["id"] for n in nodes}
    edge_ids = set()
    for edge in sequence(data.get("edges", []), "edges"):
        known(edge, {"id", "source", "target", "label", "owner", "status", "kind", "condition", "source_port", "target_port", "waypoints", "bundle", "evidence"}, "edge")
        for key in ("id", "source", "target"):
            if key not in edge:
                raise ValueError("edge: " + key + " is required")
            identifier(edge[key], "edge." + key)
        ident = edge["id"]
        if ident in objects or ident in edge_ids:
            raise ValueError("duplicate id: " + ident)
        edge_ids.add(ident)
        if edge["source"] not in node_ids or edge["target"] not in node_ids:
            raise ValueError(ident + ": source and target must name nodes")
        if edge["source"] == edge["target"]:
            raise ValueError(ident + ": self loops are outside this generator's scope")
        for key in ("label", "owner", "status", "kind", "condition"):
            text(edge.get(key, ""), ident + "." + key, 300)
        text(edge.get("evidence", ""), ident + ".evidence")
        for key in ("source_port", "target_port"):
            if key in edge:
                port(edge[key], "right", ident + "." + key)
        if "bundle" in edge:
            boolean(edge["bundle"], ident + ".bundle")
        for wp in sequence(edge.get("waypoints", []), ident + ".waypoints"):
            point(wp, ident + ".waypoints")
    for note in sequence(data.get("notes", []), "notes"):
        known(note, {"label", "x", "y", "width"}, "note")
        text(note.get("label", ""), "note.label")
        for key in ("x", "y"):
            number(note.get(key, 0), "note." + key, -100000)
        number(note.get("width", 300), "note.width", 40)
    return config, objects, groups, nodes, parents


def arrange(config, objects, groups, parents):
    """Resolve child extents bottom-up, then use one absolute-position function."""
    children = defaultdict(list)
    for ident, owner in parents.items():
        children[owner].append(ident)
    rects, labels = {}, {}
    group_ids = {g["id"] for g in groups}

    def build(owner):
        members = sorted(children[owner], key=lambda i: (objects[i]["row"], objects[i]["col"], i))
        sizes = {}
        for ident in members:
            item = objects[ident]
            if ident in group_ids:
                inner_w, inner_h = build(ident)
                header_w = estimate_text_width(item["label"], config["font_size"]) + 32
                width = max(inner_w, header_w, item.get("width", 0), config["cell_width"])
                height = max(inner_h, item.get("height", 0), config["cell_height"])
                labels[ident] = item["label"]
            else:
                width = item.get("width", config["cell_width"])
                raw_label = item["label"]
                if item.get("status"):
                    raw_label += "\n[State: " + item["status"] + "]"
                label = wrap_text(raw_label, width - 24, config["font_size"])
                # If an automatic box would require 3+ lines, widen it before
                # establishing the shared column widths.
                if "width" not in item and len(label.split("\n")) > 2:
                    width = max(width, estimate_text_width(raw_label, config["font_size"]) / 2 + 30)
                    label = wrap_text(raw_label, width - 24, config["font_size"])
                height = max(item.get("height", config["cell_height"]), len(label.split("\n")) * config["font_size"] * 1.3 + 24)
                labels[ident] = label
            sizes[ident] = (width, height)
        max_col = max((objects[i]["col"] for i in members), default=-1)
        max_row = max((objects[i]["row"] for i in members), default=-1)
        col_widths = [config["cell_width"]] * (max_col + 1)
        row_heights = [config["cell_height"]] * (max_row + 1)
        for ident in members:
            item = objects[ident]
            col_widths[item["col"]] = max(col_widths[item["col"]], sizes[ident][0])
            row_heights[item["row"]] = max(row_heights[item["row"]], sizes[ident][1])
        inset = config["margin"] if owner is None else config["padding"]
        header = 0 if owner is None else group_title_height(objects[owner], config)
        for ident in members:
            item = objects[ident]
            col, row = item["col"], item["row"]
            x = inset + sum(col_widths[:col]) + col * config["gap_x"]
            y = inset + header + sum(row_heights[:row]) + row * config["gap_y"]
            width, height = sizes[ident]
            # Same-column boxes share their left edge; rows share their center.
            y += (row_heights[row] - height) / 2
            rects[ident] = Rect(x, y, width, height)
        width = sum(col_widths) + max(0, max_col) * config["gap_x"] + 2 * inset
        height = sum(row_heights) + max(0, max_row) * config["gap_y"] + 2 * inset + header
        return width, height

    size = build(None)
    absolute = {ident: absolute_rect(ident, rects, parents) for ident in objects}
    return rects, absolute, labels, size


def group_title_height(group, config):
    return max(config["title_height"], len(group["label"].split("\n")) * config["font_size"] * 1.3 + 12)


def port_xy(rect, endpoint):
    side, fraction = endpoint
    return {"left": (rect.x, rect.y + rect.height * fraction),
            "right": (rect.right, rect.y + rect.height * fraction),
            "top": (rect.x + rect.width * fraction, rect.y),
            "bottom": (rect.x + rect.width * fraction, rect.bottom)}[side]


def normal(endpoint):
    return {"left": (-1, 0), "right": (1, 0), "top": (0, -1), "bottom": (0, 1)}[endpoint[0]]


def endpoint_defaults(source, target):
    dx = target.center[0] - source.center[0]
    dy = target.center[1] - source.center[1]
    if abs(dx) >= abs(dy):
        return ("right", "left") if dx >= 0 else ("left", "right")
    return ("bottom", "top") if dy >= 0 else ("top", "bottom")


def route_score(points, obstacles, prior, spacing):
    hits = sum(segment_hits_rect(a, b, box) for a, b in polyline_segments(points) for box in obstacles)
    crossings = sum(proper_intersections(points, old) for old in prior)
    nearby = 0
    for a, b in polyline_segments(points):
        for old in prior:
            for c, d in polyline_segments(old):
                if a[0] == b[0] and c[0] == d[0] and 0 < abs(a[0] - c[0]) < spacing:
                    nearby += max(0, min(max(a[1], b[1]), max(c[1], d[1])) - max(min(a[1], b[1]), min(c[1], d[1])))
                if a[1] == b[1] and c[1] == d[1] and 0 < abs(a[1] - c[1]) < spacing:
                    nearby += max(0, min(max(a[0], b[0]), max(c[0], d[0])) - max(min(a[0], b[0]), min(c[0], d[0])))
    return (hits, crossings, nearby, polyline_length(points), len(points))


def auto_route(start, finish, source_port, target_port, obstacles, prior, spacing, index):
    sn, tn = normal(source_port), normal(target_port)
    lead = (start[0] + sn[0] * spacing, start[1] + sn[1] * spacing)
    tail = (finish[0] + tn[0] * spacing, finish[1] + tn[1] * spacing)
    left = min([start[0], finish[0]] + [r.x for r in obstacles]) - spacing * (index + 1)
    right = max([start[0], finish[0]] + [r.right for r in obstacles]) + spacing * (index + 1)
    top = min([start[1], finish[1]] + [r.y for r in obstacles]) - spacing * (index + 1)
    bottom = max([start[1], finish[1]] + [r.bottom for r in obstacles]) + spacing * (index + 1)
    candidates = []
    xs = [lead[0], tail[0], (lead[0] + tail[0]) / 2, left, right]
    ys = [lead[1], tail[1], (lead[1] + tail[1]) / 2, top, bottom]
    for shift in range(1, 4):
        xs.extend([(lead[0] + tail[0]) / 2 + spacing * shift,
                   (lead[0] + tail[0]) / 2 - spacing * shift])
    for x in xs:
        candidates.append(simplify_points([start, lead, (x, lead[1]), (x, tail[1]), tail, finish]))
    for y in ys:
        candidates.append(simplify_points([start, lead, (lead[0], y), (tail[0], y), tail, finish]))
    # Avoid an immediate reversal toward the inside of a box.
    valid = []
    for path in candidates:
        if len(path) < 2:
            continue
        first = (path[1][0] - start[0], path[1][1] - start[1])
        last = (path[-2][0] - finish[0], path[-2][1] - finish[1])
        if first[0] * sn[0] + first[1] * sn[1] > 0 and last[0] * tn[0] + last[1] * tn[1] > 0:
            valid.append(path)
    return min(valid, key=lambda p: route_score(p, obstacles, prior, spacing))


def fmt(value):
    return f"{float(value):.4f}".rstrip("0").rstrip(".") or "0"


def style_string(values):
    return ";".join(f"{key}={value}" for key, value in values.items()) + ";"


class Diagram:
    def __init__(self, data, boxes_only=False):
        self.data = data
        self.config, self.objects, self.groups, self.nodes, self.parents = validate(data)
        self.rects, self.absolute, self.labels, self.size = arrange(self.config, self.objects, self.groups, self.parents)
        self.boxes_only = boxes_only
        self.root = ET.Element("root")
        ET.SubElement(self.root, "mxCell", id="0")
        self.cells = {"0": self.root[0]}
        self.buckets = {ident: [] for ident, _ in LAYERS}
        self.prior = []
        self.warnings = []
        owners = sorted({e.get("owner", "Flow") or "Flow" for e in data.get("edges", [])})
        self.owner_colors = {owner: OWNER_COLORS[i % len(OWNER_COLORS)] for i, owner in enumerate(owners)}
        if len(owners) > len(OWNER_COLORS):
            self.warnings.append("More line owners than palette colors; add direct labels or split the diagram")
        self.endpoint_cache = {}
        exits = defaultdict(set)
        for edge in data.get("edges", []):
            source, target = self.absolute[edge["source"]], self.absolute[edge["target"]]
            defaults = endpoint_defaults(source, target)
            sp = port(edge.get("source_port"), defaults[0], edge["id"] + ".source_port")
            tp = port(edge.get("target_port"), defaults[1], edge["id"] + ".target_port")
            key = json.dumps([edge.get("owner", "Flow") or "Flow", edge.get("status", ""), edge.get("kind", ""), edge.get("condition", "")]) if edge.get("bundle", False) else edge["id"]
            self.endpoint_cache[edge["id"]] = (sp, tp, key)
            if "source_port" not in edge:
                exits[(edge["source"], sp[0])].add(key)
        for edge in data.get("edges", []):
            sp, tp, key = self.endpoint_cache[edge["id"]]
            if "source_port" not in edge:
                keys = sorted(exits[(edge["source"], sp[0])])
                sp = (sp[0], round((keys.index(key) + 1) / (len(keys) + 1), 4))
            self.endpoint_cache[edge["id"]] = (sp, tp)

    def base_style(self):
        return {"fontSize": fmt(self.config["font_size"]), "fontFamily": self.config["font_family"],
                "fontColor": "#333333", "html": "0", "whiteSpace": "wrap"}

    def vertex(self, ident, label, rect, parent, styles=None, layer="_nodes"):
        values = self.base_style()
        values.update(styles or {})
        cell = ET.Element("mxCell", id=ident, value=label, style=style_string(values), vertex="1", parent=parent)
        if "connectable" in values:
            cell.set("connectable", str(values["connectable"]))
        ET.SubElement(cell, "mxGeometry", x=fmt(rect.x), y=fmt(rect.y), width=fmt(rect.width), height=fmt(rect.height), **{"as": "geometry"})
        self.buckets[layer].append(cell)
        self.cells[ident] = cell
        return cell

    def edge(self, ident, source, target, points, source_port, target_port, color, label="", arrow=True):
        sx, sy = {"left": (0, source_port[1]), "right": (1, source_port[1]),
                  "top": (source_port[1], 0), "bottom": (source_port[1], 1)}[source_port[0]]
        tx, ty = {"left": (0, target_port[1]), "right": (1, target_port[1]),
                  "top": (target_port[1], 0), "bottom": (target_port[1], 1)}[target_port[0]]
        if source.startswith("_junction"):
            sx = sy = 0.5
        if target.startswith("_junction"):
            tx = ty = 0.5
        style = self.base_style()
        style.update({"edgeStyle": "orthogonalEdgeStyle", "rounded": "0", "orthogonalLoop": "1",
                      "jettySize": "0", "strokeColor": color, "strokeWidth": "2", "endArrow": "block" if arrow else "none",
                      "endFill": "1", "jumpStyle": "arc", "jumpSize": "8", "exitX": fmt(sx), "exitY": fmt(sy),
                      "exitDx": "0", "exitDy": "0", "entryX": fmt(tx), "entryY": fmt(ty), "entryDx": "0", "entryDy": "0",
                      "exitPerimeter": "0", "entryPerimeter": "0", "labelBackgroundColor": "#ffffff"})
        cell = ET.Element("mxCell", id=ident, value=label, edge="1", parent="_routes", source=source, target=target, style=style_string(style))
        geom = ET.SubElement(cell, "mxGeometry", relative="1", **{"as": "geometry"})
        arr = ET.SubElement(geom, "Array", **{"as": "points"})
        for x, y in points[1:-1]:
            ET.SubElement(arr, "mxPoint", x=fmt(x), y=fmt(y))
        self.buckets["_routes"].append(cell)
        self.cells[ident] = cell
        self.prior.append(points)

    def make_boxes(self):
        # A real transparent parent keeps frame, header and children together
        # when moved in a GUI. Routes are in a lower layer and remain visible
        # through the parent's unfilled body.
        by_depth = sorted(self.groups, key=lambda g: (self.depth(g["id"]), g["id"]))
        for group in by_depth:
            ident = group["id"]
            self.vertex(ident, "", self.rects[ident], self.parents[ident] or "_nodes",
                        {"fillColor": "none", "strokeColor": "#94a3b8", "container": "1", "connectable": "0", "collapsible": "0", "recursiveResize": "0"})
            self.vertex("_title_" + ident, self.labels[ident], Rect(0, 0, self.rects[ident].width, group_title_height(group, self.config)), ident,
                        {"fillColor": "#e8edf2", "strokeColor": "none", "whiteSpace": "nowrap", "align": "left", "spacingLeft": "16", "connectable": "0"})
        for node in self.nodes:
            ident = node["id"]
            fill, stroke, _ = ROLES[node.get("role", "process")]
            self.vertex(ident, self.labels[ident], self.rects[ident], self.parents[ident] or "_nodes",
                        {"fillColor": fill, "strokeColor": stroke, "rounded": "1", "spacing": "10"})

    def depth(self, ident):
        result = 0
        while self.parents[ident] is not None:
            ident = self.parents[ident]
            result += 1
        return result

    def endpoints(self, edge):
        return self.endpoint_cache[edge["id"]]

    def make_routes(self):
        if self.boxes_only:
            return
        edges = sorted(self.data.get("edges", []), key=lambda e: e["id"])
        bundles = defaultdict(list)
        for edge in edges:
            sp, tp = self.endpoints(edge)
            if edge.get("bundle", False) and not edge.get("waypoints") and sp[0] in ("left", "right") and tp[0] != sp[0]:
                bundles[(edge["source"], edge.get("owner", "Flow") or "Flow", sp,
                         edge.get("status", ""), edge.get("kind", ""), edge.get("condition", ""))].append(edge)
        bundled = set()
        for index, (_, members) in enumerate(sorted(bundles.items())):
            if len(members) < 2:
                continue
            if self.make_bundle(members, index):
                bundled.update(e["id"] for e in members)
        # Remaining independent routes compare crossings with already selected
        # candidates; they do not claim to minimize crossings globally.
        for index, edge in enumerate(edges):
            if edge["id"] in bundled:
                continue
            source, target = edge["source"], edge["target"]
            sp, tp = self.endpoints(edge)
            start, finish = port_xy(self.absolute[source], sp), port_xy(self.absolute[target], tp)
            # End boxes are obstacles too: an outward-facing port must route
            # around their bodies rather than leave and then cut back through.
            obstacles = [self.absolute[n["id"]] for n in self.nodes]
            if "waypoints" in edge:
                points = simplify_points([start] + [point(p, edge["id"]) for p in edge["waypoints"]] + [finish])
                for a, b in polyline_segments(points):
                    if a[0] != b[0] and a[1] != b[1]:
                        raise ValueError(edge["id"] + ": waypoints must form an orthogonal path including endpoints")
                sn, tn = normal(sp), normal(tp)
                if len(points) < 2 or ((points[1][0] - start[0]) * sn[0] + (points[1][1] - start[1]) * sn[1] <= 0 or
                                      (points[-2][0] - finish[0]) * tn[0] + (points[-2][1] - finish[1]) * tn[1] <= 0):
                    raise ValueError(edge["id"] + ": path must leave and enter perpendicular to the selected ports")
            else:
                points = auto_route(start, finish, sp, tp, obstacles, self.prior, self.config["route_spacing"], index)
            if route_score(points, obstacles, [], self.config["route_spacing"])[0]:
                self.warnings.append(edge["id"] + ": route crosses a box; adjust the grid or explicit waypoints")
            color = self.owner_colors[edge.get("owner", "Flow") or "Flow"]
            self.edge(edge["id"], source, target, points, sp, tp, color, self.edge_label(edge))
            self.logical_metadata(edge)

    def edge_label(self, edge):
        pieces = [edge.get("label", "")]
        if edge.get("kind") and edge["kind"] not in pieces:
            pieces.append(edge["kind"])
        if edge.get("condition"):
            pieces.append("Condition: " + edge["condition"])
        if edge.get("status"):
            pieces.append("[State: " + edge["status"] + "]")
        return "\n".join(piece for piece in pieces if piece)

    def logical_metadata(self, edge):
        cell = self.cells[edge["id"]]
        cell.set("logicalSource", edge["source"])
        cell.set("logicalTarget", edge["target"])
        cell.set("logicalRelation", edge["id"])

    def make_bundle(self, members, index):
        source = members[0]["source"]
        sp, _ = self.endpoints(members[0])
        start = port_xy(self.absolute[source], sp)
        direction = 1 if sp[0] == "right" else -1
        targets = []
        for edge in members:
            _, tp = self.endpoints(edge)
            if tp[0] != ("left" if direction == 1 else "right"):
                return False
            finish = port_xy(self.absolute[edge["target"]], tp)
            if (finish[0] - start[0]) * direction < self.config["route_spacing"] * 2:
                return False
            targets.append((edge, finish, tp))
        spacing = self.config["route_spacing"]
        limit = min((p[0] - start[0]) * direction for _, p, _ in targets)
        max_lane = max(1, int(math.ceil(limit / spacing)) - 1)
        # Bounded lane search even when the caller leaves an unusually large
        # gap. Try near-source, middle and near-target lanes.
        lane_numbers = set(range(1, min(max_lane, 8) + 1))
        lane_numbers.update(range(max(1, max_lane - 7), max_lane + 1))
        lane_numbers.update(n for n in range(max_lane // 2 - 4, max_lane // 2 + 5) if 1 <= n <= max_lane)
        candidates = [start[0] + direction * spacing * n for n in sorted(lane_numbers) if spacing * n < limit]
        def paths_at(x):
            low = min([start[1]] + [p[1] for _, p, _ in targets])
            high = max([start[1]] + [p[1] for _, p, _ in targets])
            routes = [[start, (x, start[1])], [(x, low), (x, high)]]
            routes += [[(x, finish[1]), finish] for _, finish, _ in targets]
            return routes

        def score_at(x):
            routes = paths_at(x)
            box_hits = 0
            for path in routes:
                boxes = [self.absolute[n["id"]] for n in self.nodes]
                box_hits += route_score(path, boxes, [], spacing)[0]
            return (box_hits, sum(sum(proper_intersections(p, old) for old in self.prior) for p in routes),
                    sum(route_score(p, [], self.prior, spacing)[2] for p in routes), abs(x - start[0]))

        lane = min(candidates, key=score_at)
        if score_at(lane)[0]:
            return False
        color = self.owner_colors[members[0].get("owner", "Flow") or "Flow"]
        ys = sorted({start[1]} | {finish[1] for _, finish, _ in targets})
        junction_ids = {}
        for j, y in enumerate(ys):
            degree = (1 if j > 0 else 0) + (1 if j < len(ys) - 1 else 0)
            degree += sum(finish[1] == y for _, finish, _ in targets) + (1 if start[1] == y else 0)
            visible = degree >= 3
            size = 8 if visible else 0
            ident = f"_junction_{index}_{j}"
            junction_ids[y] = ident
            self.vertex(ident, "", Rect(lane - size / 2, y - size / 2, size, size), "_routes",
                        {"shape": "ellipse", "fillColor": color if visible else "none", "strokeColor": "none", "connectable": "0"}, "_routes")
        self.edge(f"_trunk_{index}_entry", source, junction_ids[start[1]], [start, (lane, start[1])], sp, ("left", 0.5), color, arrow=False)
        for j, (y1, y2) in enumerate(zip(ys, ys[1:])):
            self.edge(f"_trunk_{index}_{j}", junction_ids[y1], junction_ids[y2], [(lane, y1), (lane, y2)], ("bottom", 0.5), ("top", 0.5), color, arrow=False)
        for edge, finish, tp in targets:
            points = [(lane, finish[1]), finish]
            self.edge(edge["id"], junction_ids[finish[1]], edge["target"], points, (sp[0], 0.5), tp, color, self.edge_label(edge))
            self.logical_metadata(edge)
        return True

    def make_legend_and_notes(self):
        for index, note in enumerate(self.data.get("notes", [])):
            width = note.get("width", 300)
            label = wrap_text(note.get("label", ""), width - 20, self.config["font_size"])
            height = len(label.split("\n")) * self.config["font_size"] * 1.3 + 20
            self.vertex(f"_note_{index}", label, Rect(note.get("x", 0), note.get("y", 0), width, height), "_notes",
                        {"fillColor": "#ffffff", "strokeColor": "#94a3b8", "dashed": "1", "spacing": "10"}, "_notes")
        if not self.data.get("legend", True):
            return
        x = self.config["margin"]
        y = max([box.bottom for box in self.absolute.values()] + [self.size[1]]) + 50
        width = max(self.size[0] - x * 2, 600)
        entries = []
        roles = sorted({n.get("role", "process") for n in self.nodes})
        for role in roles:
            fill, stroke, label = ROLES[role]
            entries.append(("Role: " + label, fill, stroke))
        if not self.boxes_only:
            for owner, color in self.owner_colors.items():
                entries.append(("Line owner: " + owner, "#ffffff", color))
        states = sorted({n.get("status") for n in self.nodes if n.get("status")} |
                        ({e.get("status") for e in self.data.get("edges", []) if e.get("status")} if not self.boxes_only else set()))
        for status in states:
            entries.append(("[State: " + status + "]", "none", "#666666"))
        col_count = max(1, int(width // 240))
        cell_width = width / col_count
        rows = math.ceil(max(len(entries), 1) / col_count)
        self.vertex("_legend", "Legend", Rect(x, y, width, rows * 100 + 52), "_notes",
                    {"fillColor": "#ffffff", "strokeColor": "#94a3b8", "verticalAlign": "top", "align": "left", "spacingTop": "10", "spacingLeft": "16", "container": "1", "connectable": "0"}, "_notes")
        for index, (label, fill, stroke) in enumerate(entries):
            rect = Rect(index % col_count * cell_width + 12, 48 + index // col_count * 100, cell_width - 24, 84)
            self.vertex(f"_legend_{index}", wrap_text(label, rect.width - 20, self.config["font_size"]), rect, "_legend",
                        {"fillColor": fill, "strokeColor": stroke, "rounded": "1", "spacing": "10"}, "_notes")

    def xml(self):
        self.make_boxes()
        self.make_routes()
        self.make_legend_and_notes()
        for ident, label in LAYERS:
            ET.SubElement(self.root, "mxCell", id=ident, value=label, parent="0")
            self.root.extend(self.buckets[ident])
        document = ET.Element("mxfile")
        page = ET.SubElement(document, "diagram", id="generated", name=self.data.get("title", "Diagram"))
        model = ET.SubElement(page, "mxGraphModel", dx="0", dy="0", grid="1", gridSize="10", guides="1",
                              tooltips="1", connect="1", arrows="1", fold="1", page="0", math="0", shadow="0")
        model.append(self.root)
        ET.indent(document, space="  ")
        return ET.tostring(document, encoding="utf-8", xml_declaration=True) + b"\n"


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="UTF-8 grid JSON")
    parser.add_argument("output", type=Path, help="editable .drawio output")
    parser.add_argument("--boxes-only", action="store_true", help="generate boxes and legend without routes")
    parser.add_argument("--force", action="store_true", help="replace an existing output (never the input)")
    args = parser.parse_args(argv)
    try:
        if args.input.resolve() == args.output.resolve():
            raise ValueError("input and output must be different files")
        if args.output.exists() and args.input.samefile(args.output):
            raise ValueError("input and output must not refer to the same file")
        if args.output.suffix.lower() != ".drawio":
            raise ValueError("output must have the .drawio extension")
        if args.output.is_symlink():
            raise ValueError("refusing a symbolic-link output")
        if args.output.exists() and not args.force:
            raise ValueError("output exists; use --force to replace it")
        if args.input.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("input exceeds 4 MiB")
        data = json.loads(args.input.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys)
        diagram = Diagram(data, args.boxes_only)
        content = diagram.xml()
        mode = "wb" if args.force else "xb"
        with args.output.open(mode) as handle:
            handle.write(content)
        print(f"Generated {args.output.name}: {len(diagram.nodes)} nodes, {len(diagram.groups)} groups")
        for warning in diagram.warnings:
            print("Warning: " + warning, file=sys.stderr)
        return 0
    except (ValueError, OSError, json.JSONDecodeError, RecursionError) as error:
        print("Error: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
