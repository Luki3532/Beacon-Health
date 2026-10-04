"""
Minimal .xlsx reader using only the standard library.

An .xlsx file is a zip archive of XML. This module pulls the first worksheet
out and returns it as a list of rows (lists of strings). It handles the shared
string table and inline strings, which is all MDHHS uses.

This exists so the tool has no third-party dependencies.
"""

import re
import zipfile
from xml.etree import ElementTree

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
CELL_REF = re.compile(r"([A-Z]+)(\d+)")


def _column_index(ref):
    """Convert a cell reference like 'AB12' to a zero-based column index."""
    match = CELL_REF.match(ref or "")
    if not match:
        return None
    letters = match.group(1)
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def _shared_strings(archive):
    try:
        raw = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []

    root = ElementTree.fromstring(raw)
    strings = []
    for item in root.findall(NS + "si"):
        # Text may be split across multiple runs; join them all.
        parts = [node.text or "" for node in item.iter(NS + "t")]
        strings.append("".join(parts))
    return strings


def _first_sheet_path(archive):
    names = [n for n in archive.namelist() if n.startswith("xl/worksheets/sheet")]
    if not names:
        raise ValueError("No worksheet found in workbook.")
    return sorted(names)[0]


def read_rows(path):
    """Yield each row of the first worksheet as a list of strings."""
    with zipfile.ZipFile(path) as archive:
        strings = _shared_strings(archive)
        raw = archive.read(_first_sheet_path(archive))

    root = ElementTree.fromstring(raw)
    sheet_data = root.find(NS + "sheetData")
    if sheet_data is None:
        return

    for row in sheet_data.findall(NS + "row"):
        values = []
        for cell in row.findall(NS + "c"):
            index = _column_index(cell.get("r"))
            if index is None:
                index = len(values)

            cell_type = cell.get("t")
            if cell_type == "inlineStr":
                node = cell.find(NS + "is")
                text = "".join(n.text or "" for n in node.iter(NS + "t")) if node is not None else ""
            else:
                node = cell.find(NS + "v")
                text = node.text or "" if node is not None else ""
                if cell_type == "s" and text:
                    position = int(text)
                    text = strings[position] if position < len(strings) else ""

            while len(values) < index:
                values.append("")
            values.append(text.strip())

        yield values


if __name__ == "__main__":
    import sys

    target = sys.argv[1]
    for number, row in enumerate(read_rows(target), start=1):
        print(number, row)
        if number >= 12:
            break
