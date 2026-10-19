#!/usr/bin/env python3
"""Extract editable XML or ask an installed draw.io Desktop to export an editable PNG.

Uses the Python standard library. No renderer is downloaded or bundled.
"""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True

from diagram_io import equivalent_document, load_diagrams, serialize_document
from check import inspect_document


class ExportError(ValueError):
    pass


SAFE_STYLES = {
    "fontSize", "fontFamily", "fontColor", "fontStyle", "html", "whiteSpace",
    "fillColor", "strokeColor", "strokeWidth", "rounded", "arcSize", "dashed",
    "align", "verticalAlign", "spacing", "spacingTop", "spacingBottom",
    "spacingLeft", "spacingRight", "container", "connectable", "collapsible",
    "recursiveResize", "edgeStyle", "orthogonalLoop", "jettySize", "endArrow",
    "startArrow", "endFill", "startFill", "jumpStyle", "jumpSize", "exitX",
    "exitY", "exitDx", "exitDy", "entryX", "entryY", "entryDx", "entryDy",
    "exitPerimeter", "entryPerimeter", "labelBackgroundColor", "shape", "opacity",
    "fillOpacity", "strokeOpacity", "textOpacity", "rotation", "horizontal",
    "startSize", "swimlaneFillColor", "swimlaneLine", "text", "ellipse",
    "rhombus", "swimlane", "rectangle", "rect", "perimeter", "shadow",
    "curved", "labelPosition", "verticalLabelPosition", "resizable",
}


def validate_local_render_input(document) -> None:
    """Accept a restricted plain-label/style subset before launching Desktop.

    A regular expression over XML alone cannot catch encoded HTML resource URLs.
    This intentionally declines rich HTML, images, custom stencils and unknown
    style extensions rather than passing them to a renderer with network access.
    It is input validation, not an operating-system network sandbox.
    """
    resource_names = {"src", "href", "link", "image", "backgroundimage", "fontsource"}
    for page in document.pages:
        for element in page.root.iter():
            for key, value in element.attrib.items():
                local_key = key.rsplit("}", 1)[-1].lower()
                if local_key in resource_names and value:
                    raise ExportError("Desktop export refuses resource and link attributes.")
                if key in {"label", "value", "tooltip"} and ("<" in value or ">" in value):
                    raise ExportError("Desktop export accepts plain labels only; rich HTML needs manual review.")
                if key != "style":
                    continue
                for part in value.split(";"):
                    if not part:
                        continue
                    name, _, setting = part.partition("=")
                    if name not in SAFE_STYLES:
                        raise ExportError("Desktop export does not support style: " + name)
                    if name == "html" and setting not in {"", "0"}:
                        raise ExportError("Desktop export accepts plain labels only (html=0).")
                    if name == "fontFamily" and not re.fullmatch(r"[\w ,.-]{1,120}", setting):
                        raise ExportError("Desktop export refuses resource-bearing font settings.")
                    if name == "shape" and not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", setting):
                        raise ExportError("Desktop export refuses custom or encoded shapes.")
                    if re.search(r"(?i)(?:url\s*\(|https?:|file:|data:|javascript:|//|[<>\\\\()])", setting):
                        raise ExportError("Desktop export refuses resource-bearing style values.")


def drawio_executable(explicit: str | None) -> Path:
    candidates = [explicit] if explicit else [
        shutil.which("drawio"),
        shutil.which("draw.io"),
        "/Applications/draw.io.app/Contents/MacOS/draw.io",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return path.resolve()
    raise ExportError(
        "draw.io Desktop was not found. Supply --drawio with a trusted installed "
        "executable, or use preview.py for an approximate offline preview."
    )


def validate_output(source: Path, output: Path, force: bool) -> None:
    if output.is_symlink():
        raise ExportError("Refusing to replace a symbolic link.")
    if source.resolve() == output.resolve() or (source.exists() and output.exists() and source.samefile(output)):
        raise ExportError("The output must differ from the input, including with --force.")
    if output.exists() and (not force or not output.is_file()):
        raise ExportError("The output already exists; use --force only after saving a backup.")
    if not output.parent.is_dir():
        raise ExportError("Create the output directory explicitly before exporting.")


def publish_file(temporary: Path, output: Path, force: bool) -> None:
    if force:
        if output.is_symlink() or (output.exists() and not output.is_file()):
            raise ExportError("Refusing to replace a non-regular output file.")
        os.replace(temporary, output)
    else:
        # Exclusive creation preserves an existing file even if it appeared during export.
        with temporary.open("rb") as reader, output.open("xb") as writer:
            shutil.copyfileobj(reader, writer)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", "-o", required=True, type=Path)
    parser.add_argument("--extract-only", action="store_true", help="save all editable pages as XML")
    parser.add_argument("--drawio", help="trusted installed draw.io Desktop executable")
    parser.add_argument("--page", type=int, default=1, help="1-based page for the PNG image")
    parser.add_argument("--layers", help="comma-separated zero-based layer indexes to show")
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    try:
        source = args.input.expanduser()
        output = args.output.expanduser().absolute()
        validate_output(source, output, args.force)
        if not math.isfinite(args.scale) or not 0 < args.scale <= 8:
            raise ExportError("--scale must be finite, greater than zero and at most 8.")
        if not 1 <= args.timeout <= 300:
            raise ExportError("--timeout must be between 1 and 300 seconds.")
        document = load_diagrams(source)
        if any(item["severity"] == "error" for item in inspect_document(document)):
            raise ExportError("Input has structural issues; inspect it with check.py first.")
        xml = serialize_document(document)

        if args.extract_only:
            if output.suffix.lower() not in (".drawio", ".xml"):
                raise ExportError("XML extraction output must end in .drawio or .xml.")
            if args.layers is not None or args.drawio is not None or args.page != 1:
                raise ExportError("--extract-only preserves every page and layer; omit renderer options.")
            with tempfile.TemporaryDirectory(prefix="drawio-extract-", dir=output.parent) as folder:
                temporary = Path(folder) / "diagram.drawio"
                temporary.write_bytes(xml)
                if not equivalent_document(document, load_diagrams(temporary)):
                    raise ExportError("Extraction changed editable diagram data.")
                publish_file(temporary, output, args.force)
            print("Saved editable XML for all pages and layers. No image was rendered.")
            return 0

        if output.suffix.lower() != ".png":
            raise ExportError("PNG output must end in .png, normally .drawio.png.")
        if not 1 <= args.page <= len(document.pages):
            raise ExportError("--page is outside the available pages.")
        if args.layers is not None:
            if not re.fullmatch(r"\d+(?:,\d+)*", args.layers):
                raise ExportError("--layers must be comma-separated nonnegative integers.")
            indexes = [int(value) for value in args.layers.split(",")]
            page = document.pages[args.page - 1]
            layers = [cell for cell in page.cells if cell.get("parent") == "0"]
            if len(indexes) != len(set(indexes)) or any(index >= len(layers) for index in indexes):
                raise ExportError("--layers contains a duplicate or unavailable layer index.")

        # Desktop can fetch referenced media. Restrict supported input before launching it;
        # this validation does not isolate the Desktop process from the network.
        validate_local_render_input(document)
        executable = drawio_executable(args.drawio)
        with tempfile.TemporaryDirectory(prefix="drawio-export-", dir=output.parent) as folder:
            temporary_input = Path(folder) / "diagram.drawio"
            temporary_output = Path(folder) / "diagram.drawio.png"
            temporary_input.write_bytes(xml)
            command = [
                str(executable), "--disable-update", "--export", "--format", "png",
                "--embed-diagram", "--page-index", str(args.page), "--scale", str(args.scale),
                "--output", str(temporary_output),
            ]
            if args.layers is not None:
                command.extend(["--layers", args.layers])
            command.append(str(temporary_input))
            environment = os.environ.copy()
            environment["DRAWIO_DISABLE_UPDATE"] = "true"
            completed = subprocess.run(
                command, shell=False, env=environment, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=args.timeout, check=False,
            )
            if completed.returncode != 0:
                raise ExportError("draw.io Desktop returned an export error; the existing output was preserved.")
            if not temporary_output.is_file() or temporary_output.stat().st_size == 0:
                raise ExportError("draw.io Desktop did not produce a PNG.")
            embedded = load_diagrams(temporary_output)
            if not equivalent_document(document, embedded):
                raise ExportError(
                    "The PNG's embedded editable data differs from the input. "
                    "No output was published; inspect the Desktop version's export behavior."
                )
            publish_file(temporary_output, output, args.force)
        print(
            "Saved PNG and verified embedded editable data. Open the image and re-edit it in "
            "draw.io to confirm appearance; this structural check does not inspect pixels."
        )
        if args.layers is not None:
            print("Layer selection affects the image; embedded data retains all input layers.")
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"Export failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
