"""The supplier specification, as a Word document, written with the standard library.

A .docx is a zip of XML, and this particular document is prose and tables:
headings, paragraphs, one row per attribute. No formulas, no cell validation,
no style index pointing into a font table pointing into a fill table. So it is
written here rather than by a library, and the reason is not thrift.

``python-docx`` requires ``lxml``, a compiled C extension, and
``requirements.txt`` spends three paragraphs refusing exactly that class of
dependency - the LiteLLM proxy is kept out of the runtime install because one
of *its* transitive dependencies has no wheel on 3.14 and fails to build. The
rule that falls out, and the one this file follows: a pure-Python dependency
that does something we could not meaningfully test is worth taking; a compiled
one is not. ``openpyxl`` passes that test because Excel silently repairing a
malformed workbook is a failure no assertion here could catch. Word opening a
document made of five parts and forty tags is not that, and the test for this
file unzips it and parses the XML.

The document is generated from the same registry the readiness checks read, so
it cannot drift from what the system actually enforces - which is more than can
be said for a specification maintained by hand.
"""

from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape

from sc.datapack.schema import LIST_SEPARATOR, Pack, Sheet

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>"""

DOCUMENT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

#: Five styles, which is every style this document uses. A sixth would be a
#: style nothing applies.
STYLES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{W}">
<w:docDefaults><w:rPrDefault><w:rPr>
<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="20"/>
</w:rPr></w:rPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:pPr>
<w:spacing w:after="240"/></w:pPr><w:rPr><w:b/><w:sz w:val="48"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:pPr>
<w:spacing w:before="360" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr>
<w:rPr><w:b/><w:sz w:val="30"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:pPr>
<w:spacing w:before="260" w:after="100"/><w:outlineLvl w:val="1"/></w:pPr>
<w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Body"><w:name w:val="Body"/><w:pPr>
<w:spacing w:after="120"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="Mono"><w:name w:val="Mono"/>
<w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:sz w:val="18"/></w:rPr></w:style>
</w:styles>"""


def _core(pack: Pack) -> str:
    title = escape(f"{pack.fascia} supplier product specification")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<cp:coreProperties '
        'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f"<dc:title>{title}</dc:title>"
        f"<dc:creator>{escape(pack.fascia)}</dc:creator>"
        "</cp:coreProperties>")


def _run(text: str, *, bold: bool = False, mono: bool = False) -> str:
    props = ""
    if bold or mono:
        props = "<w:rPr>"
        if mono:
            props += '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:sz w:val="18"/>'
        if bold:
            props += "<w:b/>"
        props += "</w:rPr>"
    # xml:space matters: a trailing space in a run is meaningful here and Word
    # strips it otherwise.
    return f'<w:r>{props}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def _para(text: str = "", style: str = "Body", **kwargs) -> str:
    return (f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>'
            f"{_run(text, **kwargs) if text else ''}</w:p>")


def _cell(text: str, width: int, *, bold: bool = False,
          mono: bool = False) -> str:
    return (f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/></w:tcPr>'
            f"{_para(text, style='Mono' if mono else 'Body', bold=bold, mono=mono)}"
            "</w:tc>")


def _table(headers: list[str], rows: list[list[str]],
           widths: list[int], mono_columns: set[int] = frozenset()) -> str:
    xml = [
        '<w:tbl><w:tblPr>'
        '<w:tblW w:w="9360" w:type="dxa"/>'
        '<w:tblBorders>'
        '<w:top w:val="single" w:sz="4" w:color="BFBFBF"/>'
        '<w:left w:val="single" w:sz="4" w:color="BFBFBF"/>'
        '<w:bottom w:val="single" w:sz="4" w:color="BFBFBF"/>'
        '<w:right w:val="single" w:sz="4" w:color="BFBFBF"/>'
        '<w:insideH w:val="single" w:sz="4" w:color="D9D9D9"/>'
        '<w:insideV w:val="single" w:sz="4" w:color="D9D9D9"/>'
        "</w:tblBorders></w:tblPr>",
        "<w:tr>",
    ]
    for index, head in enumerate(headers):
        xml.append(_cell(head, widths[index], bold=True))
    xml.append("</w:tr>")
    for row in rows:
        xml.append("<w:tr>")
        for index, value in enumerate(row):
            xml.append(_cell(value, widths[index], mono=index in mono_columns))
        xml.append("</w:tr>")
    xml.append("</w:tbl>")
    xml.append(_para())
    return "".join(xml)


def _sheet_section(sheet: Sheet, pack: Pack) -> str:
    body = [
        f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
        f"{_run(sheet.label)}</w:p>",
        _para(
            f"{len(sheet.leaves)} categories; "
            f"{sum(1 for c in sheet.columns if c.kind == 'attribute')} "
            f"attributes; "
            f"{sum(1 for c in sheet.columns if c.kind == 'image' and c.required)}"
            f" required photographs."
            + (" This part of the assortment is regulated."
               if sheet.regulated else "")),
    ]

    rows = []
    for column in sheet.columns:
        if column.kind != "attribute":
            continue
        marks = []
        if column.required_for:
            marks.append("required by " + ", ".join(column.required_for))
        if column.safety:
            marks.append("safety class")
        if column.ordered:
            marks.append("ordered")
        if column.only_leaves:
            marks.append(f"{len(column.only_leaves)} of {len(sheet.leaves)} "
                         f"categories")
        rows.append([column.name, column.label,
                     column.dtype + (f" ({column.unit})" if column.unit else ""),
                     "; ".join(marks) or "optional"])
    body.append(_table(["Field", "Label", "Type", "Notes"], rows,
                       [2900, 2200, 1500, 2760], mono_columns={0}))

    images = [c for c in sheet.columns if c.kind == "image"]
    if images:
        body.append(f'<w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr>'
                    f"{_run('Photographs')}</w:p>")
        body.append(_table(
            ["Field", "Role", "Required"],
            [[c.name, c.label.replace("Image - ", ""),
              "yes" if c.required else "no"] for c in images],
            [3400, 3400, 2560], mono_columns={0}))

    scoped = [c for c in sheet.columns if c.only_leaves]
    if scoped:
        body.append(f'<w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr>'
                    f"{_run('Fields that apply to some categories only')}</w:p>")
        body.append(_para(
            "These are named category by category rather than by department. A "
            "kettle takes a mains voltage and a saucepan does not, and both sit "
            "in Home & Kitchen. Leave the cell empty where the field does not "
            "apply; we will not ask for it."))
        body.append(_table(
            ["Field", "Categories"],
            [[c.name, ", ".join(c.only_leaves)] for c in scoped],
            [2900, 6460], mono_columns={0}))
    return "".join(body)


def _preamble(pack: Pack) -> str:
    safety = sorted({c.name for s in pack.sheets for c in s.columns if c.safety})
    ordered = sorted({c.name for s in pack.sheets for c in s.columns if c.ordered})
    return "".join([
        _para(f"{pack.fascia} supplier product specification", style="Title"),
        _para("What we need from you in order to list a product, generated "
              "from the rules our systems actually apply. Every field below is "
              "read by a check; nothing here is aspirational."),

        f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
        f"{_run('How to send it')}</w:p>",
        _para("Fill in the template for the part of the assortment your line "
              "belongs to - a spreadsheet, a workbook, or a delimited file, "
              "whichever suits your systems. Put it in a .zip together with an "
              "images/ folder holding your photographs, and send the .zip "
              "through the vendor portal."),
        _para("One row per SKU. Rows that share a product reference are "
              "variants of one line, which is how a range is expressed. Your "
              "own identity is taken from the portal session and is "
              "deliberately not a column in the file."),

        f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
        f"{_run('How values are written')}</w:p>",
        _para("Units belong in the header and never in the cell. Write 65, not "
              "65 W. A percentage is a plain number: 90, not 90%."),
        _para(f"A list goes in one cell, separated by "
              f"'{LIST_SEPARATOR.strip()}'. A comma is inside too many "
              f"ingredient names to be a safe separator."),
        _para("A GTIN is text, not a number. Leading zeros are part of it, and "
              "a spreadsheet will remove them if the column is numeric. The "
              "workbook we supply already formats that column as text."),

        f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
        f"{_run('Safety-class fields')}</w:p>",
        _para(f"{len(safety)} fields are safety class. A person reviews every "
              f"change to one; a value we have had to infer rather than read "
              f"blocks publication instead of degrading it; and where one has "
              f"to be withheld, a marketplace listing comes down rather than "
              f"showing a placeholder."),
        _para(", ".join(safety), style="Mono", mono=True),

        f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
        f"{_run('Fields whose order is part of the value')}</w:p>",
        _para("In these the sequence is a legal declaration, not a "
              "presentation choice. Please send them in the order they appear "
              "on the pack, and do not sort them."),
        _para(", ".join(ordered), style="Mono", mono=True),
    ])


def write(pack: Pack) -> bytes:
    """The specification as a .docx, in memory."""
    body = [_preamble(pack)]
    for sheet in pack.sheets:
        body.append(_sheet_section(sheet, pack))
    body.append(
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/>'
        "</w:sectPr>")

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<w:document xmlns:w="{W}"><w:body>{"".join(body)}</w:body></w:document>')

    buffer = io.BytesIO()
    # Deflated and with fixed timestamps, so two builds of the same catalog
    # produce the same bytes and a diff of two packs is a real difference.
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in (
            ("[Content_Types].xml", CONTENT_TYPES),
            ("_rels/.rels", ROOT_RELS),
            ("docProps/core.xml", _core(pack)),
            ("word/_rels/document.xml.rels", DOCUMENT_RELS),
            ("word/styles.xml", STYLES),
            ("word/document.xml", document),
        ):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, text.encode("utf-8"))
    return buffer.getvalue()
