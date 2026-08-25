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


def _clean_detail(value):
    return str(value or "").strip().lstrip("- ")


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


def _dated_title(entry, include_date):
    title = _clean_title(entry.get("title"))
    if include_date and title and entry.get("performance_date"):
        try:
            completed = datetime.date.fromisoformat(entry["performance_date"])
            title += f"({completed.month}.{completed.day})"
        except (TypeError, ValueError):
            pass
    return title


def _replace_cell_content(cell, team_name, entries, include_date, team_field, title_field, detail_field):
    sublist = cell.find(_q(HP, "subList"))
    paragraphs = list(sublist.findall(_q(HP, "p")))
    title_index = next(i for i, p in enumerate(paragraphs) if title_field in _field_names(p))
    title_proto = paragraphs[title_index]
    detail_proto = next(p for p in paragraphs if detail_field in _field_names(p))

    for paragraph in paragraphs[title_index:]:
        sublist.remove(paragraph)

    created = 0
    for entry in entries:
        title = _dated_title(entry, include_date)
        details = [_clean_detail(d) for d in entry.get("details", [])]
        details = [d for d in details if d]
        if title:
            sublist.append(_plain_paragraph(title_proto, ["○ ", title, ""]))
            created += 1
        for detail in details:
            sublist.append(_plain_paragraph(detail_proto, ["  - ", detail, ""]))
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
            team_field, f"this_title_{team_no:02d}_01", f"this_detail_{team_no:02d}_01",
        )
        right_lines = _replace_cell_content(
            cells[1], team.get("team_name", ""), team.get("next_week", []), False,
            team_field, f"this_title_{team_no:02d}_02", f"this_detail_{team_no:02d}_02",
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
