"""Bounded, values-only Excel 97–2003 (BIFF8) catalog conversion."""

import base64
import binascii
import csv
import math
import struct
from io import StringIO
import xlrd
from xlrd.compdoc import CompDoc
from fastapi import HTTPException
from ..rules import fail

MAX_FILE_BYTES = 1_000_000
OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def inspect_stream(raw):
    log = StringIO()
    if raw.startswith(OLE):
        doc = CompDoc(raw, logfile=log)
        allowed = {
            "Workbook",
            "Book",
            "\x05SummaryInformation",
            "\x05DocumentSummaryInformation",
        }
        if any(
            d.etype not in (0, 5) and (d.etype != 2 or d.name not in allowed)
            for d in doc.dirlist
        ):
            fail(
                "XLS macros, embedded objects and additional document streams are not supported."
            )
        stream = doc.get_named_stream("Workbook") or doc.get_named_stream("Book")
        if stream is None:
            fail("Invalid or unsupported XLS workbook.")
    else:
        stream = raw
    if len(stream) > MAX_FILE_BYTES:
        fail("XLS file is too large. Maximum 1 MB.")
    offset = 0
    sheet_count = 0
    in_sheet = False
    first = True
    while offset < len(stream):
        if stream[offset : offset + 4] == b"\0" * 4:
            if any(stream[offset:]):
                fail("Invalid or unsupported XLS workbook.")
            break
        if offset + 4 > len(stream):
            fail("Invalid or unsupported XLS workbook.")
        code, length = struct.unpack_from("<HH", stream, offset)
        offset += 4
        if offset + length > len(stream):
            fail("Invalid or unsupported XLS workbook.")
        data = stream[offset : offset + length]
        offset += length
        if first:
            if (
                code != 0x0809
                or length < 4
                or struct.unpack_from("<H", data)[0] != 0x0600
            ):
                fail("Use Excel 97–2003 XLS (BIFF8), or save the file as XLSX.")
            first = False
        if code == 0x0809:
            if length < 4 or struct.unpack_from("<H", data)[0] != 0x0600:
                fail("Invalid or unsupported XLS workbook.")
            kind = struct.unpack_from("<H", data, 2)[0]
            if kind not in (0x0005, 0x0010):
                fail("Use one visible worksheet without charts or macro sheets.")
            in_sheet = kind == 0x0010
            if in_sheet:
                sheet_count += 1
        elif code == 0x000A:
            in_sheet = False
        elif code == 0x0085:
            if length < 6 or data[4] != 0 or data[5] != 0:
                fail("Use one visible worksheet without charts or macro sheets.")
        elif code in (0x0006, 0x0206, 0x0406, 0x04BC, 0x0221, 0x0021, 0x0236):
            fail("XLS formulas are not supported; paste values instead.")
        elif code in (0x002F, 0x0018, 0x0017, 0x0023, 0x01AE, 0x00D3):
            fail(
                "XLS encryption, named formulas, macros and external links are not supported."
            )
        elif in_sheet and code in (
            0x00FD,
            0x0203,
            0x027E,
            0x0205,
            0x0204,
            0x0201,
            0x00D6,
            0x00BD,
            0x00BE,
        ):
            if length < 4:
                fail("Invalid or unsupported XLS workbook.")
            row, col = struct.unpack_from("<HH", data)
            last = (
                struct.unpack_from("<H", data, length - 2)[0]
                if code in (0x00BD, 0x00BE)
                else col
            )
            if row > 200 or col > 8 or last > 8 or last < col:
                fail("Use only template columns A–I and at most 200 product rows.")
        elif in_sheet and code == 0x0208:
            if length < 2 or struct.unpack_from("<H", data)[0] > 200:
                fail("Import at most 200 products at a time.")
    if first or sheet_count != 1:
        fail("Use one visible worksheet without charts or macro sheets.")


def convert(encoded):
    from ..api.imports import COLUMNS, parse

    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        fail("Invalid XLS file encoding.")
    if len(raw) > MAX_FILE_BYTES:
        fail("XLS file is too large. Maximum 1 MB.")
    book = None
    try:
        inspect_stream(raw)
        book = xlrd.open_workbook(
            file_contents=raw, on_demand=True, ragged_rows=True, logfile=StringIO()
        )
        if book.biff_version != 80 or book.nsheets != 1:
            fail("Use one visible Excel 97–2003 worksheet.")
        sheet = book.sheet_by_index(0)
        if sheet.nrows > 201 or sheet.ncols > 9:
            fail("Use only template columns A–I and at most 200 product rows.")
        if sheet.visibility:
            fail("Use one visible Excel 97–2003 worksheet.")
        output = StringIO()
        writer = csv.writer(output, lineterminator="\r\n")
        count = 0
        for row in range(sheet.nrows):
            values = []
            for col in range(9):
                cell = sheet.cell(row, col) if col < sheet.row_len(row) else None
                if cell is None or cell.ctype in (
                    xlrd.XL_CELL_EMPTY,
                    xlrd.XL_CELL_BLANK,
                ):
                    value = ""
                elif cell.ctype == xlrd.XL_CELL_TEXT:
                    value = cell.value
                elif cell.ctype == xlrd.XL_CELL_NUMBER:
                    if row == 0 or col in (0, 2, 3, 4):
                        fail(
                            f"XLS row {row+1}: SKU, category, unit and barcode cells must be text to preserve identifiers."
                        )
                    if not math.isfinite(cell.value):
                        fail("XLS contains an invalid numeric value.")
                    value = (
                        str(int(cell.value))
                        if cell.value.is_integer()
                        else str(cell.value)
                    )
                else:
                    fail(
                        f"XLS row {row+1}: dates, booleans and error cells are not supported."
                    )
                values.append(value)
            if row == 0:
                if values != COLUMNS:
                    fail("XLS headers must match the downloadable template exactly.")
                writer.writerow(values)
            elif any(values):
                writer.writerow(values)
                count += 1
            if (
                output.tell() > 200_000
                or len(output.getvalue().encode("utf-8")) > 200_000
            ):
                fail("Converted catalog is too large. Maximum 200 KB of CSV text.")
        text = output.getvalue()
        parse(text)
        return {"csv_text": text, "count": count}
    except HTTPException:
        raise
    except Exception:
        fail("Invalid or unsupported XLS workbook.")
    finally:
        if book is not None:
            book.release_resources()
