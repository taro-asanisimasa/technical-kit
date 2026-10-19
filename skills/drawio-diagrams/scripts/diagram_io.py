#!/usr/bin/env python3
"""Bounded, offline readers and geometry helpers for draw.io documents.

This is not a draw.io renderer. Implicit routing and inherited styles need a
native editor to resolve. No input markup, URL, or executable content is run.
"""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
import math
from pathlib import Path
import re
import struct
import urllib.parse
import xml.etree.ElementTree as ET
import zlib

MAX_INPUT = 16 * 1024 * 1024
MAX_XML = 8 * 1024 * 1024
MAX_TOTAL_XML = 24 * 1024 * 1024
MAX_PAGES = 50
MAX_CELLS = 10000
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class DiagramError(ValueError):
    """Malformed, unsupported, or resource-limited input."""


@dataclass
class Page:
    name: str
    root: ET.Element
    cells: list[ET.Element]
    attributes: dict[str, str] = field(default_factory=dict)
    by_id: dict[str, ET.Element] = field(init=False)

    def __post_init__(self):
        self.by_id = {c.get("id", ""): c for c in self.cells if c.get("id")}


@dataclass
class Document:
    pages: list[Page]
    source_format: str
    warnings: list[str] = field(default_factory=list)
    attributes: dict[str, str] = field(default_factory=dict)


def bounded_decompress(data: bytes, *, raw: bool = False, limit: int = MAX_XML) -> bytes:
    """Decompress one stream, rejecting overflow, truncation, and trailing data."""
    try:
        decoder = zlib.decompressobj(-15 if raw else zlib.MAX_WBITS)
        output = decoder.decompress(data, limit + 1)
        if len(output) > limit or decoder.unconsumed_tail:
            raise DiagramError("Decompressed data exceeds the size limit")
        # A complete stream reaches eof without flush(). The flush length is an
        # initial buffer size, not an output cap, so do not use it on input data.
        if not decoder.eof or decoder.unused_data:
            raise DiagramError("Truncated compressed stream or trailing compressed data")
        return output
    except zlib.error as exc:
        raise DiagramError("Invalid compressed data") from exc


def xml_root(data: bytes) -> ET.Element:
    if len(data) > MAX_XML:
        raise DiagramError("XML exceeds the size limit")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DiagramError("XML must use UTF-8 encoding") from exc
    if "\x00" in text or re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.I):
        raise DiagramError("DTD, entity declarations, and NUL characters are not accepted")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise DiagramError("Invalid XML: " + str(exc)) from exc
    count = 0
    stack = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        count += 1
        if count > 100000 or depth > 100:
            raise DiagramError("XML node count or nesting exceeds the limit")
        stack.extend((child, depth + 1) for child in node)
    return root


def _decode_metadata(payload: bytes) -> bytes:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DiagramError("Embedded diagram text is not UTF-8") from exc
    # draw.io PNG metadata can contain URI-escaped XML.
    if text.lstrip().startswith("%3C") or text.lstrip().startswith("%3c"):
        try:
            payload = urllib.parse.unquote_to_bytes(text)
        except ValueError as exc:
            raise DiagramError("Invalid URI-escaped diagram text") from exc
    if len(payload) > MAX_XML:
        raise DiagramError("Embedded diagram exceeds the size limit")
    return payload


def _png_xml(data: bytes) -> bytes:
    offset = 8
    candidates = []
    saw_header = saw_data = saw_end = False
    metadata_bytes = 0
    chunks = 0
    while offset < len(data):
        chunks += 1
        if chunks > 10000 or offset + 12 > len(data):
            raise DiagramError("Invalid PNG chunk structure")
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + length
        if end > len(data) or length > MAX_INPUT:
            raise DiagramError("Truncated or oversized PNG chunk")
        body = data[offset + 8:offset + 8 + length]
        expected = struct.unpack(">I", data[offset + 8 + length:end])[0]
        if zlib.crc32(kind + body) & 0xffffffff != expected:
            raise DiagramError("PNG chunk checksum mismatch")
        if not saw_header and kind != b"IHDR":
            raise DiagramError("PNG must start with IHDR")
        if kind == b"IHDR":
            if saw_header or length != 13:
                raise DiagramError("Invalid PNG IHDR")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", body)
            depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
            if not width or not height or color not in depths or depth not in depths[color] or compression or filtering or interlace not in {0, 1}:
                raise DiagramError("Invalid PNG image header")
            saw_header = True
        elif kind == b"IDAT":
            saw_data = True
        elif kind in {b"tEXt", b"zTXt", b"iTXt"}:
            # Only diagram metadata is decompressed; raster data is never decoded.
            if b"\x00" not in body:
                raise DiagramError("Invalid PNG text chunk")
            key, rest = body.split(b"\x00", 1)
            if key in {b"mxfile", b"diagram"}:
                if kind == b"zTXt":
                    if not rest or rest[0] != 0:
                        raise DiagramError("Unsupported PNG text compression")
                    payload = bounded_decompress(rest[1:])
                elif kind == b"iTXt":
                    if len(rest) < 2 or rest[0] not in {0, 1} or rest[1] != 0:
                        raise DiagramError("Invalid PNG international text flags")
                    fields = rest[2:].split(b"\x00", 2)
                    if len(fields) != 3:
                        raise DiagramError("Invalid PNG international text chunk")
                    payload = bounded_decompress(fields[2]) if rest[0] else fields[2]
                else:
                    payload = rest
                metadata_bytes += len(payload)
                if metadata_bytes > MAX_TOTAL_XML:
                    raise DiagramError("PNG diagram metadata exceeds the cumulative limit")
                candidates.append(_decode_metadata(payload))
        elif kind == b"IEND":
            if length or end != len(data):
                raise DiagramError("Invalid PNG end chunk or trailing data")
            saw_end = True
        offset = end
    if not saw_header or not saw_data or not saw_end:
        raise DiagramError("PNG is missing required image chunks")
    if len(candidates) != 1:
        raise DiagramError("PNG must contain exactly one mxfile or diagram metadata entry")
    return candidates[0]


def _make_page(model: ET.Element, name: str) -> Page:
    if model.tag != "mxGraphModel":
        raise DiagramError("Each page must contain mxGraphModel")
    graph_root = model.find("root")
    if graph_root is None:
        raise DiagramError("mxGraphModel has no root")
    cells = []
    for child in graph_root:
        if child.tag == "mxCell":
            cells.append(child)
        elif child.tag in {"object", "UserObject"} and child.find("mxCell") is not None:
            # Normalize the common draw.io object wrapper without evaluating it.
            cell = child.find("mxCell")
            cell = ET.fromstring(ET.tostring(cell, encoding="utf-8"))
            if child.get("id"):
                cell.set("id", child.get("id"))
            if child.get("label") is not None:
                cell.set("value", child.get("label"))
            cells.append(cell)
        else:
            raise DiagramError("Unsupported graph-root child: " + child.tag)
    if len(cells) > MAX_CELLS:
        raise DiagramError("Page cell count exceeds the limit")
    return Page(name, model, cells)


def load_diagrams(path: str | Path) -> Document:
    source = Path(path)
    try:
        if not source.is_file() or source.stat().st_size > MAX_INPUT:
            raise DiagramError("Input must be a regular file of at most 16 MiB")
        with source.open("rb") as stream:
            data = stream.read(MAX_INPUT + 1)
    except OSError as exc:
        raise DiagramError("Cannot read input: " + str(exc)) from exc
    if len(data) > MAX_INPUT:
        raise DiagramError("Input exceeds the size limit")
    is_png = data.startswith(PNG_MAGIC)
    if is_png:
        data = _png_xml(data)
    root = xml_root(data)
    warnings = []
    if is_png:
        warnings.append("Only embedded edit data was read; visible PNG pixels have not been compared with it.")
    if root.tag == "mxGraphModel":
        return Document([_make_page(root, "Page 1")], "png" if is_png else "xml", warnings)
    if root.tag != "mxfile":
        raise DiagramError("Expected mxfile or mxGraphModel")
    diagrams = root.findall("diagram")
    if not diagrams or len(diagrams) > MAX_PAGES:
        raise DiagramError("Document must contain between 1 and 50 pages")
    pages = []
    total = len(data)
    for index, diagram in enumerate(diagrams, 1):
        models = list(diagram)
        if models:
            if len(models) != 1 or (diagram.text or "").strip():
                raise DiagramError("Ambiguous mixed page encoding")
            model = models[0]
        else:
            text = (diagram.text or "").strip()
            if text.startswith("<"):
                decoded = text.encode("utf-8")
            else:
                try:
                    compressed = base64.b64decode(text, validate=True)
                except (binascii.Error, ValueError) as exc:
                    raise DiagramError("Invalid compressed page encoding") from exc
                decoded = bounded_decompress(compressed, raw=True)
                decoded = urllib.parse.unquote_to_bytes(decoded.decode("utf-8"))
            total += len(decoded)
            if total > MAX_TOTAL_XML:
                raise DiagramError("Cumulative page XML exceeds the limit")
            model = xml_root(decoded)
        page = _make_page(model, diagram.get("name", "Page " + str(index)))
        page.attributes = dict(diagram.attrib)
        pages.append(page)
    return Document(pages, "png" if is_png else "xml", warnings, dict(root.attrib))


def serialize_document(document: Document) -> bytes:
    """Serialize every loaded page uncompressed, retaining model content."""
    root = ET.Element("mxfile", dict(document.attributes))
    root.set("compressed", "false")
    for page in document.pages:
        diagram = ET.SubElement(root, "diagram", dict(page.attributes))
        if "name" not in diagram.attrib:
            diagram.set("name", page.name)
        diagram.append(ET.fromstring(ET.tostring(page.root, encoding="utf-8")))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _element_signature(node):
    return (node.tag, tuple(sorted(node.attrib.items())), (node.text or "").strip(),
            tuple(_element_signature(child) for child in node))


def equivalent_document(first: Document, second: Document) -> bool:
    """Strict page/model equality, ignoring outer mxfile metadata and page IDs.

    Whitespace-only formatting and attribute order do not count as changes.
    View settings in mxGraphModel still count; no semantic equivalence is claimed.
    """
    return len(first.pages) == len(second.pages) and all(
        a.name == b.name and _element_signature(a.root) == _element_signature(b.root)
        for a, b in zip(first.pages, second.pages))


def parse_style(cell: ET.Element) -> dict[str, str]:
    return dict(part.split("=", 1) if "=" in part else (part, "")
                for part in cell.get("style", "").split(";") if part)


def geometry(cell: ET.Element) -> ET.Element | None:
    return cell.find("mxGeometry")


def number(value: str | None, default: float = 0) -> float:
    try:
        result = float(value) if value is not None else default
    except (ValueError, TypeError) as exc:
        raise DiagramError("Geometry contains a non-numeric value") from exc
    if not math.isfinite(result) or abs(result) > 10000000:
        raise DiagramError("Geometry value must be finite and within 10 million units")
    return result


def absolute_rect(page: Page, cell: ET.Element) -> tuple[float, float, float, float] | None:
    """Resolve explicit vertex positions. Cycles and absent parents are errors."""
    chain = []
    seen = set()
    current = cell
    while current is not None:
        identity = current.get("id", "")
        if identity in seen:
            raise DiagramError("Parent cycle")
        seen.add(identity)
        chain.append(current)
        parent_id = current.get("parent")
        if parent_id is None:
            break
        if parent_id not in page.by_id:
            raise DiagramError("Unknown parent: " + parent_id)
        current = page.by_id[parent_id]
        if len(chain) > 100:
            raise DiagramError("Parent nesting exceeds the limit")
    x = y = w = h = 0.0
    result = None
    for item in reversed(chain):
        geom = geometry(item)
        if geom is None:
            if item.get("vertex") == "1":
                return None
            continue
        gx, gy = number(geom.get("x")), number(geom.get("y"))
        if geom.get("relative") == "1" and item.get("vertex") == "1":
            gx, gy = gx * w, gy * h
            offset = geom.find("mxPoint[@as='offset']")
            if offset is not None:
                gx += number(offset.get("x"))
                gy += number(offset.get("y"))
        x, y = x + gx, y + gy
        w, h = number(geom.get("width")), number(geom.get("height"))
        result = (x, y, w, h)
    return result


def parent_origin(page: Page, cell: ET.Element) -> tuple[float, float]:
    parent = page.by_id.get(cell.get("parent", ""))
    rect = absolute_rect(page, parent) if parent is not None else None
    return rect[:2] if rect else (0.0, 0.0)


def _perimeter(rect, toward):
    x, y, w, h = rect
    cx, cy = x + w / 2, y + h / 2
    dx, dy = toward[0] - cx, toward[1] - cy
    if not dx and not dy:
        return cx, cy
    scale = min(w / (2 * abs(dx)) if dx else float("inf"),
                h / (2 * abs(dy)) if dy else float("inf"))
    return cx + dx * scale, cy + dy * scale


def edge_points(page: Page, cell: ET.Element) -> list[tuple[float, float]] | None:
    """Return explicit polyline coordinates, or None when routing is implicit.

    Rectangular perimeter endpoints are an approximation for non-rectangular
    shapes. Callers must disclose that limitation.
    """
    geom = geometry(cell)
    if geom is None:
        return None
    ox, oy = parent_origin(page, cell)
    style = parse_style(cell)
    waypoints = [(number(p.get("x")) + ox, number(p.get("y")) + oy)
                 for p in geom.findall("Array[@as='points']/mxPoint")]
    endpoints = []
    for role in ("source", "target"):
        vertex = page.by_id.get(cell.get(role, ""))
        rect = absolute_rect(page, vertex) if vertex is not None else None
        explicit = geom.find("mxPoint[@as='" + role + "Point']")
        if rect:
            endpoints.append((rect, None))
        elif explicit is not None:
            endpoints.append((None, (number(explicit.get("x")) + ox, number(explicit.get("y")) + oy)))
        else:
            return None
    centers = [(r[0] + r[2] / 2, r[1] + r[3] / 2) if r else p for r, p in endpoints]
    points = []
    for index, (rect, point) in enumerate(endpoints):
        if rect:
            prefix = "exit" if index == 0 else "entry"
            px, py = style.get(prefix + "X"), style.get(prefix + "Y")
            if px is not None and py is not None:
                point = (rect[0] + number(px) * rect[2], rect[1] + number(py) * rect[3])
                point = (point[0] + number(style.get(prefix + "Dx")), point[1] + number(style.get(prefix + "Dy")))
            else:
                toward = waypoints[0 if index == 0 else -1] if waypoints else centers[1 - index]
                point = _perimeter(rect, toward)
        points.append(point)
    result = [points[0], *waypoints, points[1]]
    # Orthogonal routers add hidden bends. Do not invent a route from centers.
    if not waypoints and style.get("edgeStyle", "") not in {"", "none"}:
        a, b = result
        if abs(a[0] - b[0]) > 0.01 and abs(a[1] - b[1]) > 0.01:
            return None
    if style.get("curved") == "1":
        return None
    return result
