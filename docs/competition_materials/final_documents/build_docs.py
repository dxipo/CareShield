#!/usr/bin/env python3
"""Normalize the supplied Word reference style and trim unused template media."""

from __future__ import annotations

import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
ET.register_namespace("w", W)


def qn(name: str) -> str:
    return f"{{{W}}}{name}"


def replace_child(parent: ET.Element, name: str, attributes: dict[str, str]) -> None:
    child = parent.find(f"w:{name}", NS)
    if child is None:
        child = ET.SubElement(parent, qn(name))
    child.attrib.clear()
    child.attrib.update({qn(key): value for key, value in attributes.items()})


def remove_child(parent: ET.Element, name: str) -> None:
    child = parent.find(f"w:{name}", NS)
    if child is not None:
        parent.remove(child)


def patch_styles(xml: bytes) -> bytes:
    root = ET.fromstring(xml)
    body_style = None
    for style in root.findall("w:style", NS):
        if style.get(qn("styleId")) == "8":
            body_style = style
            break
    if body_style is None:
        raise RuntimeError("Body Text style 8 was not found in the reference document")

    paragraph = body_style.find("w:pPr", NS)
    if paragraph is None:
        paragraph = ET.SubElement(body_style, qn("pPr"))
    replace_child(paragraph, "jc", {"val": "both"})
    replace_child(paragraph, "spacing", {"line": "360", "lineRule": "auto", "after": "80"})
    replace_child(paragraph, "ind", {"firstLineChars": "200"})

    run = body_style.find("w:rPr", NS)
    if run is None:
        run = ET.SubElement(body_style, qn("rPr"))
    remove_child(run, "b")
    remove_child(run, "bCs")
    replace_child(
        run,
        "rFonts",
        {"ascii": "Times New Roman", "hAnsi": "Times New Roman", "eastAsia": "宋体", "cs": "Times New Roman"},
    )
    replace_child(run, "sz", {"val": "24"})
    replace_child(run, "szCs", {"val": "24"})

    if not any(style.get(qn("styleId")) == "Compact" for style in root.findall("w:style", NS)):
        compact = ET.SubElement(
            root,
            qn("style"),
            {qn("type"): "paragraph", qn("customStyle"): "1", qn("styleId"): "Compact"},
        )
        ET.SubElement(compact, qn("name"), {qn("val"): "Compact"})
        ET.SubElement(compact, qn("basedOn"), {qn("val"): "1"})
        ET.SubElement(compact, qn("qFormat"))
        compact_paragraph = ET.SubElement(compact, qn("pPr"))
        ET.SubElement(
            compact_paragraph,
            qn("spacing"),
            {qn("before"): "0", qn("after"): "0", qn("line"): "240", qn("lineRule"): "auto"},
        )
        compact_run = ET.SubElement(compact, qn("rPr"))
        ET.SubElement(
            compact_run,
            qn("rFonts"),
            {
                qn("ascii"): "Times New Roman",
                qn("hAnsi"): "Times New Roman",
                qn("eastAsia"): "宋体",
                qn("cs"): "Times New Roman",
            },
        )
        ET.SubElement(compact_run, qn("sz"), {qn("val"): "21"})
        ET.SubElement(compact_run, qn("szCs"), {qn("val"): "21"})

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def patch_document(xml: bytes) -> bytes:
    root = ET.fromstring(xml)
    for table in root.findall(".//w:tbl", NS):
        table_properties = table.find("w:tblPr", NS)
        if table_properties is None:
            table_properties = ET.Element(qn("tblPr"))
            table.insert(0, table_properties)
        replace_child(table_properties, "tblStyle", {"val": "24"})
        replace_child(table_properties, "tblW", {"val": "0", "type": "auto"})
        replace_child(table_properties, "tblLayout", {"type": "autofit"})
        rows = table.findall("w:tr", NS)
        for index, row in enumerate(rows):
            row_properties = row.find("w:trPr", NS)
            if row_properties is None:
                row_properties = ET.Element(qn("trPr"))
                row.insert(0, row_properties)
            if index == 0:
                replace_child(row_properties, "tblHeader", {})
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def rewrite_docx(
    source: Path,
    target: Path,
    *,
    patch_body_style: bool,
    patch_tables: bool = False,
) -> None:
    with tempfile.TemporaryDirectory(prefix="careshield-docx-") as temp_dir:
        root = Path(temp_dir)
        with zipfile.ZipFile(source) as archive:
            archive.extractall(root)

        if patch_body_style:
            styles = root / "word" / "styles.xml"
            styles.write_bytes(patch_styles(styles.read_bytes()))

        if patch_tables:
            document = root / "word" / "document.xml"
            document.write_bytes(patch_document(document.read_bytes()))

        media = root / "word" / "media"
        if media.exists():
            for path in media.glob("image*.png"):
                path.unlink()

        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(root))


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: build_docs.py reference.docx input.docx output.docx", file=sys.stderr)
        return 2
    reference, input_docx, output_docx = map(Path, sys.argv[1:])
    if input_docx == reference:
        rewrite_docx(reference, output_docx, patch_body_style=True)
    else:
        rewrite_docx(input_docx, output_docx, patch_body_style=False, patch_tables=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
