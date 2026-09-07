import copy
import datetime
import io
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = BASE_DIR / "경영관리본부 주간 실적 및 계획.hwpx"
HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HS = "http://www.hancom.co.kr/hwpml/2011/section"


def _q(ns, name):
    return f"{{{ns}}}{name}"


def _clean_title(value):
    title = str(value or "").strip()
    for marker in ("○", "◯", "ㅇ"):
        if title == marker:
            return ""
        if title.startswith(marker + " "):
            return title[len(marker):].strip()
    return title


def _clean_detail(value, legacy_auto_dash=False):
    raw = str(value or "").strip()
    return raw.startswith("-") or legacy_auto_dash, raw[1:].lstrip() if raw.startswith("-") else raw


def _field_names(element):
    return {
        field.get("name", "")
        for field in element.iter(_q(HP, "fieldBegin"))
    }


def _plain_paragraph(prototype, segments):
    paragraph = copy.deepcopy(prototype)
    for lines in list(paragraph.findall(_q(HP, "linesegarray"))):
        paragraph.remove(lines)
    runs = paragraph.findall(_q(HP, "run"))
    for run in runs:
        for child in list(run):
            run.remove(child)
    for index, text in enumerate(segments):
        run = runs[min(index, len(runs) - 1)]
        node = ET.SubElement(run, _q(HP, "t"))
        if text.startswith(" ") or text.endswith(" "):
            node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        node.text = text
    return paragraph


def _set_char_style(paragraph, char_pr_id):
    for run in paragraph.findall(_q(HP, "run")):
        run.set("charPrIDRef", str(char_pr_id))
    return paragraph


def _add_sized_char_style(members, base_id, height):
    header_name = "Contents/header.xml"
    root = ET.fromstring(members[header_name])
    char_properties = next(e for e in root.iter() if e.tag.endswith("charProperties"))
    styles = [e for e in list(char_properties) if e.tag.endswith("charPr")]
    base = next((e for e in styles if e.get("id") == str(base_id)), styles[0])
    created = copy.deepcopy(base)
    new_id = max(int(e.get("id", "0")) for e in styles) + 1
    created.set("id", str(new_id))
    created.set("height", str(height))
    char_properties.append(created)
    for count_name in ("itemCnt", "itemCount"):
        if count_name in char_properties.attrib:
            char_properties.set(count_name, str(len(styles) + 1))
    members[header_name] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return new_id


def _dated_title(entry, include_date):
    title = _clean_title(entry.get("title"))
    if include_date and title and entry.get("performance_date"):
        try:
            completed = datetime.date.fromisoformat(entry["performance_date"])
            title += f"({completed.month}.{completed.day})"
        except (TypeError, ValueError):
            pass
    return title


def _replace_cell_content(cell, team_name, entries, include_date, team_field, title_field, detail_field, comment_style_id, spacer_style_id):
    sublist = cell.find(_q(HP, "subList"))
    paragraphs = list(sublist.findall(_q(HP, "p")))
    title_index = next(i for i, p in enumerate(paragraphs) if title_field in _field_names(p))
    title_proto = paragraphs[title_index]
    detail_proto = next(p for p in paragraphs if detail_field in _field_names(p))

    for paragraph in paragraphs[title_index:]:
        sublist.remove(paragraph)

    created = 0
    for entry_index, entry in enumerate(entries):
        if entry_index:
            sublist.append(_set_char_style(_plain_paragraph(detail_proto, ["", "", ""]), spacer_style_id))
        title = _dated_title(entry, include_date)
        legacy_auto_dash = not entry.get("detail_markers_explicit", False)
        details = [_clean_detail(d, legacy_auto_dash) for d in entry.get("details", [])]
        details = [(has_dash, d) for has_dash, d in details if d]
        if title:
            sublist.append(_plain_paragraph(title_proto, ["ㅇ ", title, ""]))
            created += 1
        for has_dash, detail in details:
            marker = "  - " if has_dash else "     "
            sublist.append(_plain_paragraph(detail_proto, [marker, detail, ""]))
            created += 1
        comment = str(entry.get("comment", "")).strip()
        if comment:
            # The template paragraph already contributes two spaces of indentation.
            # Three literal spaces place the comment one space after the detail text start.
            sublist.append(_set_char_style(_plain_paragraph(detail_proto, ["   ", comment, ""]), comment_style_id))
            created += 1
    if not created:
        sublist.append(_plain_paragraph(detail_proto, ["-", "", ""]))

    for text in cell.iter(_q(HP, "t")):
        if text.text:
            text.text = text.text.replace("{", "").replace("}", "")
            if text.text == team_field:
                text.text = team_name
    return max(created, 1)


def generate_dynamic_hwpx_bytes(teams_data):
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"HWPX template not found: {TEMPLATE_PATH}")

    with zipfile.ZipFile(TEMPLATE_PATH, "r") as source:
        members = {name: source.read(name) for name in source.namelist()}

    section_name = "Contents/section0.xml"
    namespaces = {}
    for _, pair in ET.iterparse(io.BytesIO(members[section_name]), events=("start-ns",)):
        prefix, uri = pair
        namespaces.setdefault(prefix, uri)
    for prefix, uri in namespaces.items():
        ET.register_namespace(prefix, uri)

    root = ET.fromstring(members[section_name])
    first_detail = next(p for p in root.iter(_q(HP, "p")) if any("detail" in name for name in _field_names(p)))
    base_char_id = first_detail.find(_q(HP, "run")).get("charPrIDRef", "0")
    comment_style_id = _add_sized_char_style(members, base_char_id, 1000)
    spacer_style_id = _add_sized_char_style(members, base_char_id, 500)
    active = [team for team in teams_data if team.get("this_week") or team.get("next_week")][:2]

    today = datetime.datetime.now(ZoneInfo("Asia/Seoul")).date()
    monday = today - datetime.timedelta(days=today.weekday())
    friday = monday + datetime.timedelta(days=4)
    next_monday = monday + datetime.timedelta(days=7)
    next_friday = friday + datetime.timedelta(days=7)
    period = lambda start, end: f"{start.month}.{start.day}.~{end.month}.{end.day}."
    replacements = {
        "department_name": "AI혁신처",
        "this_week_period": period(monday, friday),
        "next_week_period": period(next_monday, next_friday),
    }

    table = next(root.iter(_q(HP, "tbl")))
    rows = table.findall(_q(HP, "tr"))
    data_rows = rows[1:]
    for row_index, row in enumerate(list(data_rows)):
        if row_index >= len(active):
            table.remove(row)
            continue
        team = active[row_index]
        team_no = row_index + 1
        team_field = f"this_team_{team_no:02d}"
        cells = row.findall(_q(HP, "tc"))
        if row_index > 0:
            # Add the template's 6pt blank paragraph before every team after
            # the first, keeping the same spacing in the left and right cells.
            first_data_cells = data_rows[0].findall(_q(HP, "tc"))
            for cell_index, cell in enumerate(cells):
                spacing_source = first_data_cells[cell_index].find(_q(HP, "subList")).find(_q(HP, "p"))
                cell.find(_q(HP, "subList")).insert(0, copy.deepcopy(spacing_source))
        left_lines = _replace_cell_content(
            cells[0], team.get("team_name", ""), team.get("this_week", []), True,
            team_field, f"this_title_{team_no:02d}_01", f"this_detail_{team_no:02d}_01", comment_style_id, spacer_style_id,
        )
        right_lines = _replace_cell_content(
            cells[1], team.get("team_name", ""), team.get("next_week", []), False,
            team_field, f"this_title_{team_no:02d}_02", f"this_detail_{team_no:02d}_02", comment_style_id, spacer_style_id,
        )
        height = str(max(9000, 4200 + max(left_lines, right_lines) * 1900))
        for cell in cells:
            size = cell.find(_q(HP, "cellSz"))
            if size is not None:
                size.set("height", height)

    table.set("rowCnt", str(1 + len(active)))
    for text in root.iter(_q(HP, "t")):
        if not text.text:
            continue
        text.text = text.text.replace("{", "").replace("}", "")
        if text.text in replacements:
            text.text = replacements[text.text]

    members[section_name] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as target:
        if "mimetype" in members:
            target.writestr("mimetype", members.pop("mimetype"), compress_type=zipfile.ZIP_STORED)
        for name, content in members.items():
            target.writestr(name, content, compress_type=zipfile.ZIP_DEFLATED)
    return output.getvalue()
