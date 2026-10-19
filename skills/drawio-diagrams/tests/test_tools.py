"""Offline regression tests. Run with unittest discovery from the repository.

All generated files live in temporary directories. No Desktop application,
network access, third-party library, or credentials are needed.
"""

import base64
import contextlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import urllib.parse
import xml.etree.ElementTree as ET
import zlib


SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

from diagram_io import (DiagramError, MAX_XML, absolute_rect, bounded_decompress,
                        edge_points, equivalent_document, load_diagrams,
                        parse_style, serialize_document)
from check import inspect_document
from preview import make_html, polyline_midpoint, svg_page
import export as export_tool


MODEL = '<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>{}</root></mxGraphModel>'
NODE = ('<mxCell id="a" value="Input" vertex="1" parent="1" '
        'style="fontSize=18;fontFamily=sans-serif">'
        '<mxGeometry x="60" y="70" width="100" height="60" as="geometry"/></mxCell>')


def png_chunk(kind, content):
    checksum = zlib.crc32(kind + content) & 0xffffffff
    return struct.pack(">I", len(content)) + kind + content + struct.pack(">I", checksum)


def png_with_metadata(kind, content):
    """One transparent pixel plus metadata; no raster library is required."""
    return (b"\x89PNG\r\n\x1a\n"
            + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
            + png_chunk(kind, content)
            + png_chunk(b"IDAT", zlib.compress(bytes(5)))
            + png_chunk(b"IEND", b""))


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="drawio-tools-test-")
        self.folder = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, name, content):
        target = self.folder / name
        target.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
        return target

    def run_tool(self, tool, *arguments):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPTS / tool), *map(str, arguments)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            timeout=30, check=False,
        )

    def generate(self, source, name="generated.drawio", boxes=False):
        output = self.folder / name
        arguments = [source, output]
        if boxes:
            arguments.append("--boxes-only")
        result = self.run_tool("generate.py", *arguments)
        self.assertEqual(result.returncode, 0, result.stderr)
        return output

    def assert_no_structural_errors(self, document):
        errors = [item for item in inspect_document(document) if item["severity"] == "error"]
        self.assertFalse(errors, errors)

    def export_main(self, *arguments):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return export_tool.main(list(map(str, arguments)))

    def fake_desktop(self, calls, mode="ok"):
        """Fake only the local CLI contract, never native drawing or pixels."""
        def run(command, **options):
            calls.append((command, options))
            output = Path(command[command.index("--output") + 1])
            source = Path(command[-1])
            if mode == "fail":
                output.write_bytes(b"partial temporary output")
                return subprocess.CompletedProcess(command, 9, stdout=b"", stderr=b"export failed")
            xml = source.read_bytes()
            if mode == "alter":
                root = ET.fromstring(xml)
                next(cell for cell in root.iter("mxCell") if cell.get("vertex") == "1").set("value", "Changed label")
                xml = ET.tostring(root, encoding="utf-8")
            output.write_bytes(png_with_metadata(b"tEXt", b"mxfile\0" + xml))
            return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")
        return run

    def two_page_document(self):
        hidden = '<mxCell id="notes" value="Notes" parent="0" visible="0"/>'
        hidden += NODE.replace('id="a"', 'id="note"').replace('parent="1"', 'parent="notes"')
        xml = ('<mxfile><diagram name="First">' + MODEL.format(NODE + hidden)
               + '</diagram><diagram name="Second">' + MODEL.format(NODE)
               + '</diagram></mxfile>')
        return self.write("two-pages.drawio", xml)

    def test_examples_and_boxes_only_are_deterministic(self):
        for asset, boxes in (("example-diagram.json", False),
                             ("example-nested.json", False),
                             ("example-diagram.json", True)):
            with self.subTest(asset=asset, boxes_only=boxes):
                source = SKILL / "assets" / asset
                first = self.generate(source, "first.drawio", boxes)
                second = self.generate(source, "second.drawio", boxes)
                self.assertEqual(first.read_bytes(), second.read_bytes())
                document = load_diagrams(first)
                self.assert_no_structural_errors(document)
                self.assertFalse([item for item in inspect_document(document)
                                  if item["severity"] == "warning"])
                if boxes:
                    self.assertFalse([cell for cell in document.pages[0].cells
                                      if cell.get("edge") == "1"])
                first.unlink()
                second.unlink()

    def test_nested_example_retains_actual_parent_relationships(self):
        output = self.generate(SKILL / "assets" / "example-nested.json")
        page = load_diagrams(output).pages[0]
        self.assertEqual(page.by_id["process"].get("parent"), "worker")
        self.assertEqual(page.by_id["worker"].get("parent"), "boundary")
        relative_x = float(page.by_id["process"].find("mxGeometry").get("x", "0"))
        self.assertGreater(absolute_rect(page, page.by_id["process"])[0], relative_x)

    def test_fractional_ports_stay_on_the_serialized_orthogonal_route(self):
        data = {
            "nodes": [
                {"id": "a", "label": "Input", "row": 0, "col": 0, "height": 1000},
                {"id": "b", "label": "Output", "row": 0, "col": 1, "height": 1000},
            ],
            "edges": [{"id": "ab", "source": "a", "target": "b",
                       "source_port": {"side": "right", "position": 1 / 3},
                       "target_port": {"side": "left", "position": 0.5}}],
            "legend": False,
        }
        output = self.generate(self.write("ports.json", json.dumps(data)))
        page = load_diagrams(output).pages[0]
        edge = page.by_id["ab"]
        points = edge_points(page, edge)
        self.assertIsNotNone(points)
        for first, second in zip(points, points[1:]):
            self.assertTrue(abs(first[0] - second[0]) < 0.01 or abs(first[1] - second[1]) < 0.01)
        rect = absolute_rect(page, page.by_id["a"])
        self.assertAlmostEqual(points[0][1], rect[1] + float(parse_style(edge)["exitY"]) * rect[3], places=4)

    def test_endpoint_boxes_are_checked_along_the_entire_route(self):
        other = NODE.replace('id="a"', 'id="b"').replace('x="60"', 'x="464"')
        edge = ('<mxCell id="ab" edge="1" parent="1" source="a" target="b" '
                'style="edgeStyle=orthogonalEdgeStyle;exitX=0;exitY=0.5;entryX=1;entryY=0.5">'
                '<mxGeometry relative="1" as="geometry"><Array as="points">'
                '<mxPoint x="34" y="100"/><mxPoint x="590" y="100"/>'
                '</Array></mxGeometry></mxCell>')
        source = self.write("crossed-endpoints.drawio", MODEL.format(NODE + other + edge))
        issues = inspect_document(load_diagrams(source))
        directions = [item for item in issues if item["code"] == "connection-direction"]
        self.assertEqual(len(directions), 2)
        self.assertTrue(any("source box" in item["message"] for item in directions))
        self.assertTrue(any("target box" in item["message"] for item in directions))
        normal = edge.replace("exitX=0;", "exitX=1;").replace("entryX=1;", "entryX=0;")
        normal = normal.replace('<Array as="points"><mxPoint x="34" y="100"/><mxPoint x="590" y="100"/></Array>', "")
        source = self.write("normal-endpoints.drawio", MODEL.format(NODE + other + normal))
        self.assertFalse([item for item in inspect_document(load_diagrams(source))
                          if item["code"] == "connection-direction"])

    def test_generator_routes_away_from_backwards_ports_without_crossing_boxes(self):
        data = {
            "nodes": [{"id": "a", "label": "Input", "row": 0, "col": 0},
                      {"id": "b", "label": "Output", "row": 0, "col": 1}],
            "edges": [{"id": "ab", "source": "a", "target": "b",
                       "source_port": "left", "target_port": "right"}],
            "legend": False,
        }
        output = self.generate(self.write("backwards-ports.json", json.dumps(data)))
        issues = inspect_document(load_diagrams(output))
        self.assertFalse([item for item in issues if item["code"] in
                          {"connection-direction", "route-box-intersection"}], issues)

    def test_check_is_read_only_and_reports_invalid_inputs_as_json(self):
        source = self.write("normal.drawio", MODEL.format(NODE))
        before = source.read_bytes()
        result = self.run_tool("check.py", source, "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["summary"]["errors"], 0)
        self.assertEqual(source.read_bytes(), before)
        for content in ("<broken>", '<!DOCTYPE x [<!ENTITY y "expanded">]><mxGraphModel/>'):
            source = self.write("invalid.drawio", content)
            result = self.run_tool("check.py", source, "--json")
            self.assertEqual(result.returncode, 1)
            self.assertGreater(json.loads(result.stdout)["summary"]["errors"], 0)

    def test_parent_cycles_duplicate_ids_and_nonfinite_geometry_are_errors(self):
        cases = [NODE.replace('parent="1"', 'parent="a"'), NODE + NODE,
                 NODE.replace('x="60"', 'x="NaN"')]
        for index, content in enumerate(cases):
            source = self.write("invalid-{}.drawio".format(index), MODEL.format(content))
            self.assertTrue([item for item in inspect_document(load_diagrams(source))
                             if item["severity"] == "error"])

    def test_deep_parents_produce_diagnostics_without_a_recursion_failure(self):
        cells = []
        for index in range(1100):
            parent = "1" if index == 0 else "deep" + str(index - 1)
            cells.append('<mxCell id="deep{}" parent="{}"/>'.format(index, parent))
        source = self.write("deep.drawio", MODEL.format("".join(cells)))
        self.assertTrue([item for item in inspect_document(load_diagrams(source))
                         if item["severity"] == "error"])

    def test_compressed_pages_and_serialization_keep_both_pages(self):
        escaped = urllib.parse.quote(MODEL.format(NODE), safe="~()*!.'-").encode("utf-8")
        encoder = zlib.compressobj(wbits=-15)
        content = base64.b64encode(encoder.compress(escaped) + encoder.flush()).decode("ascii")
        xml = '<mxfile><diagram name="First">{}</diagram><diagram name="Second">{}</diagram></mxfile>'.format(content, content)
        first = load_diagrams(self.write("compressed.drawio", xml))
        second = load_diagrams(self.write("expanded.drawio", serialize_document(first)))
        self.assertEqual(len(first.pages), 2)
        self.assertTrue(equivalent_document(first, second))
        self.assertIn("Only page 2 of 2", make_html(first, 1))

    def test_decompression_is_bounded_and_rejects_truncated_streams(self):
        payload = zlib.compress(b"x" * 1025)
        with self.assertRaises(DiagramError):
            bounded_decompress(payload, limit=1024)
        with self.assertRaises(DiagramError):
            bounded_decompress(payload[:-1])
        oversized = zlib.compress(b"x" * (MAX_XML + 1))
        source = self.write("oversized.png", png_with_metadata(b"zTXt", b"mxfile\0\0" + oversized))
        with self.assertRaises(DiagramError):
            load_diagrams(source)

    def test_png_text_chunk_variants_are_read_without_decoding_raster_data(self):
        xml = MODEL.format(NODE).encode("utf-8")
        variants = [
            (b"tEXt", b"mxfile\0" + xml),
            (b"zTXt", b"mxfile\0\0" + zlib.compress(xml)),
            (b"iTXt", b"mxfile\0\x01\x00en\0diagram\0" + zlib.compress(xml)),
            (b"iTXt", b"mxfile\0\x00\x00\0\0" + xml),
            (b"tEXt", b"mxfile\0" + urllib.parse.quote(xml.decode("utf-8")).encode("ascii")),
        ]
        for index, (kind, content) in enumerate(variants):
            source = self.write("embedded-{}.png".format(index), png_with_metadata(kind, content))
            document = load_diagrams(source)
            self.assertEqual(len(document.pages), 1)
            self.assertTrue(document.warnings)
        corrupt = bytearray(png_with_metadata(b"tEXt", b"mxfile\0" + xml))
        corrupt[-2] ^= 1
        with self.assertRaises(DiagramError):
            load_diagrams(self.write("corrupt.png", corrupt))

    def test_extract_preserves_hidden_layers_and_every_page(self):
        hidden = '<mxCell id="notes" value="Notes" parent="0" visible="0"/>'
        hidden += NODE.replace('id="a"', 'id="note"').replace('parent="1"', 'parent="notes"')
        xml = ('<mxfile><diagram name="First">' + MODEL.format(NODE + hidden)
               + '</diagram><diagram name="Second">' + MODEL.format(NODE)
               + '</diagram></mxfile>')
        source = self.write("editable.png", png_with_metadata(b"zTXt", b"mxfile\0\0" + zlib.compress(xml.encode("utf-8"))))
        output = self.folder / "extracted.drawio"
        before = source.read_bytes()
        result = self.run_tool("export.py", source, "--extract-only", "--output", output)
        self.assertEqual(result.returncode, 0, result.stderr)
        original, extracted = load_diagrams(source), load_diagrams(output)
        self.assertTrue(equivalent_document(original, extracted))
        self.assertEqual(len(extracted.pages), 2)
        self.assertEqual(extracted.pages[0].by_id["notes"].get("visible"), "0")
        self.assertEqual(source.read_bytes(), before)
        self.assertNotEqual(self.run_tool("export.py", source, "--extract-only", "--output", output).returncode, 0)

    def test_preview_escapes_html_and_never_loads_embedded_resources(self):
        label = '&lt;img src=&quot;https://example.invalid/pixel&quot; onerror=&quot;alert(1)&quot;&gt;&lt;script&gt;alert(2)&lt;/script&gt;'
        node = NODE.replace('value="Input"', 'value="' + label + '"')
        node = node.replace('style="', 'style="html=1;image=https://example.invalid/pixel;')
        source = self.write("markup.drawio", MODEL.format(node))
        output = self.folder / "preview.html"
        result = self.run_tool("preview.py", source, "--output", output)
        self.assertEqual(result.returncode, 0, result.stderr)
        rendered = output.read_text(encoding="utf-8")
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<img ", rendered)
        self.assertNotIn("https://example.invalid", rendered)
        self.assertIn("script-src 'none'", rendered)
        self.assertIn("HTML label reduced to plain text", rendered)
        self.assertIn("100% (one diagram unit per CSS pixel)", rendered)
        self.assertNotEqual(self.run_tool("preview.py", source, "--output", output).returncode, 0)
        self.assertEqual(self.run_tool("preview.py", source, "--output", output, "--force").returncode, 0)

    def test_preview_does_not_replace_input_through_a_hardlink(self):
        source = self.write("source.drawio", MODEL.format(NODE))
        output = self.folder / "hardlink.html"
        try:
            os.link(source, output)
        except OSError as error:
            self.skipTest("Filesystem does not support hard links: " + str(error))
        before = source.read_bytes()
        result = self.run_tool("preview.py", source, "--output", output, "--force")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(source.read_bytes(), before)

    def test_implicit_routing_is_disclosed_in_check_and_preview(self):
        other = NODE.replace('id="a"', 'id="b"').replace('x="60"', 'x="400"').replace('y="70"', 'y="400"')
        edge = ('<mxCell id="ab" edge="1" parent="1" source="a" target="b" '
                'style="edgeStyle=orthogonalEdgeStyle"><mxGeometry relative="1" as="geometry"/></mxCell>')
        document = load_diagrams(self.write("implicit.drawio", MODEL.format(NODE + other + edge)))
        self.assertTrue([item for item in inspect_document(document)
                         if item["code"] == "implicit-route" and item["severity"] == "warning"])
        self.assertIn("Implicit or curved route omitted", make_html(document, 0))

    def test_edge_label_uses_path_midpoint_and_a_safe_background(self):
        self.assertEqual(polyline_midpoint([(0, 0), (10, 0), (10, 30)]), (10, 10))
        self.assertEqual(polyline_midpoint([(2, 3), (2, 3)]), (2, 3))
        other = NODE.replace('id="a"', 'id="b"').replace('x="60"', 'x="464"')
        edge = ('<mxCell id="ab" value="Flow label" edge="1" parent="1" source="a" target="b" '
                'style="exitX=1;exitY=0.5;entryX=0;entryY=0.5;fontSize=18;fontFamily=sans-serif;labelBackgroundColor=#ffffff">'
                '<mxGeometry relative="1" as="geometry"/></mxCell>')
        source = self.write("label.drawio", MODEL.format(NODE + other + edge))
        content, _, _ = svg_page(load_diagrams(source).pages[0])
        root = ET.fromstring("<svg>" + content + "</svg>")
        label = next(item for item in root.iter("text") if "".join(item.itertext()) == "Flow label")
        self.assertEqual((float(label.get("x")), float(label.get("y"))), (312, 100))
        children = list(root)
        background = children[children.index(label) - 1]
        self.assertEqual(background.tag, "rect")
        self.assertEqual(background.get("fill"), "#ffffff")
        self.assertLess(float(background.get("x")), 312)
        self.assertGreater(float(background.get("x")) + float(background.get("width")), 312)
        unsafe = edge.replace("labelBackgroundColor=#ffffff", "labelBackgroundColor=url(https://example.invalid/pixel)")
        source = self.write("unsafe-label.drawio", MODEL.format(NODE + other + unsafe))
        content, _, _ = svg_page(load_diagrams(source).pages[0])
        self.assertNotIn("example.invalid", content)
        self.assertNotIn('fill="url(', content)

    def test_export_refuses_decoded_html_protocol_relative_resources_and_css_escapes(self):
        cases = [
            NODE.replace('value="Input"', 'value="&lt;img src=&quot;//example.invalid/pixel&quot;&gt;"'),
            NODE.replace('value="Input"', 'value="Input" link="//example.invalid/pixel"'),
            NODE.replace('style="', r'style="fillColor=u\72l(\68ttps:\2f\2f example.invalid/pixel);'),
        ]
        for index, node in enumerate(cases):
            with self.subTest(case=index):
                source = self.write("resource-{}.drawio".format(index), MODEL.format(node))
                with self.assertRaises(export_tool.ExportError):
                    export_tool.validate_local_render_input(load_diagrams(source))

    def test_export_refuses_input_hardlink_before_resolving_or_running_desktop(self):
        source = self.write("source.drawio", MODEL.format(NODE))
        output = self.folder / "hardlink.png"
        try:
            os.link(source, output)
        except OSError as error:
            self.skipTest("Filesystem does not support hard links: " + str(error))
        before = source.read_bytes()
        with mock.patch.object(export_tool, "drawio_executable") as executable, \
                mock.patch.object(export_tool.subprocess, "run") as desktop:
            result = self.export_main(source, "--output", output, "--force")
            self.assertEqual(result, 1)
            executable.assert_not_called()
            desktop.assert_not_called()
        self.assertEqual(source.read_bytes(), before)

    def test_fake_desktop_retains_both_pages_and_hidden_layers_in_embedded_data(self):
        source = self.two_page_document()
        output = self.folder / "editable.drawio.png"
        calls = []
        with mock.patch.object(export_tool, "drawio_executable", return_value=self.folder / "fake-desktop"), \
                mock.patch.object(export_tool.subprocess, "run", side_effect=self.fake_desktop(calls)):
            result = self.export_main(source, "--output", output, "--page", 2, "--layers", "0")
        self.assertEqual(result, 0)
        original, embedded = load_diagrams(source), load_diagrams(output)
        self.assertTrue(equivalent_document(original, embedded))
        self.assertEqual(len(embedded.pages), 2)
        self.assertEqual(embedded.pages[0].by_id["notes"].get("visible"), "0")
        self.assertEqual(len(calls), 1)
        command, options = calls[0]
        self.assertIn("--embed-diagram", command)
        self.assertEqual(command[command.index("--page-index") + 1], "2")
        self.assertEqual(command[command.index("--layers") + 1], "0")
        self.assertIs(options["shell"], False)
        self.assertEqual(options["env"]["DRAWIO_DISABLE_UPDATE"], "true")

    def test_fake_desktop_failure_and_embedded_mismatch_preserve_existing_output(self):
        source = self.two_page_document()
        original = source.read_bytes()
        for mode in ("fail", "alter"):
            with self.subTest(mode=mode):
                output = self.write("preserve-{}.png".format(mode), b"existing output")
                calls = []
                with mock.patch.object(export_tool, "drawio_executable", return_value=self.folder / "fake-desktop"), \
                        mock.patch.object(export_tool.subprocess, "run", side_effect=self.fake_desktop(calls, mode)):
                    result = self.export_main(source, "--output", output, "--force")
                self.assertEqual(result, 1)
                self.assertEqual(len(calls), 1)
                self.assertEqual(output.read_bytes(), b"existing output")
                self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
