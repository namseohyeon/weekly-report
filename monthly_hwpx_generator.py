import copy
import io
import re
import zipfile
from pathlib import Path
from lxml import etree as ET

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = BASE_DIR / "월간보고양식.hwpx"
HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HH = "http://www.hancom.co.kr/hwpml/2011/head"
HC = "http://www.hancom.co.kr/hwpml/2011/core"


def _q(name):
    return f"{{{HP}}}{name}"


def _plain_paragraph(prototype, segments):
    paragraph = copy.deepcopy(prototype)
    # 새 텍스트의 길이에 맞게 한글이 줄 배치를 다시 계산하도록 기존 좌표를 제거한다.
    for lines in list(paragraph.findall(_q("linesegarray"))):
        paragraph.remove(lines)

    runs = paragraph.findall(_q("run"))
    for run in runs:
        for child in list(run):
            run.remove(child)
    if isinstance(segments, str):
        segments = [segments]
    for index, text in enumerate(segments):
        target = runs[min(index, len(runs) - 1)]
        node = ET.SubElement(target, _q("t"))
        if text.startswith(" ") or text.endswith(" "):
            node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        node.text = text
    return paragraph


def _set_char_style(paragraph, char_pr_id):
    for run in paragraph.findall(_q("run")):
        run.set("charPrIDRef", str(char_pr_id))
    return paragraph


def _add_sized_char_style(members, base_id, height):
    header_name = "Contents/header.xml"
    parser = ET.XMLParser(remove_blank_text=False, resolve_entities=False)
    root = ET.fromstring(members[header_name], parser=parser)
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
    members[header_name] = ET.tostring(root, encoding="utf-8", xml_declaration=True, standalone=True)
    return new_id


def _apply_hanging_indent(header_root, paragraph_widths):
    for para_pr in header_root.iter(f"{{{HH}}}paraPr"):
        base_width = paragraph_widths.get(para_pr.get("id"))
        if not base_width:
            continue
        for margin_index, margin in enumerate(para_pr.iter(f"{{{HH}}}margin")):
            intent = margin.find(f"{{{HC}}}intent")
            left = margin.find(f"{{{HC}}}left")
            if intent is not None and left is not None:
                width = base_width * (1 if margin_index == 0 else 2)
                original_left = int(left.get("value", "0"))
                # 첫 줄의 절대 시작점(original_left)은 유지하고, 둘째 줄만 본문 위치로 이동한다.
                left.set("value", str(original_left + width))
                intent.set("value", str(-width))


def generate_monthly_hwpx_bytes(month, report_data, department="AI혁신처"):
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Monthly HWPX template not found: {TEMPLATE_PATH}")

    with zipfile.ZipFile(TEMPLATE_PATH, "r") as source:
        source_infos = source.infolist()
        members = {info.filename: source.read(info.filename) for info in source_infos}

    section_name = "Contents/section0.xml"
    parser = ET.XMLParser(remove_blank_text=False, resolve_entities=False)
    root = ET.fromstring(members[section_name], parser=parser)
    table = next(root.iter(_q("tbl")))
    rows = table.findall(_q("tr"))

    for text in root.iter(_q("t")):
        if not text.text:
            continue
        # 이미 생성된 문서를 다시 양식으로 사용해도 현재 부서명과 월로 갱신한다.
        if "경 영 관 리 본 부" in text.text or "경영관리본부" in text.text:
            text.text = re.sub(r"(\]\s*).*$", rf"\1{department}", text.text)
        text.text = text.text.replace("00000처", department).replace("000처", department)
        if re.search(r"\d{1,2}월 추진실적", text.text):
            text.text = re.sub(r"\d{1,2}월 추진실적", f"{int(month)}월 추진실적", text.text)
        if re.search(r"\d{1,2}월 추진계획", text.text):
            plan_month = 1 if int(month) == 12 else int(month) + 1
            text.text = re.sub(r"\d{1,2}월 추진계획", f"{plan_month}월 추진계획", text.text)

    content_cells = rows[2].findall(_q("tc"))
    for cell, category in zip(content_cells, ("performance", "plan")):
        sublist = cell.find(_q("subList"))
        paragraphs = list(sublist.findall(_q("p")))
        blank_proto = paragraphs[0]
        title_proto = paragraphs[1]
        item_proto = paragraphs[2]
        base_char_id = item_proto.findall(_q("run"))[-1].get("charPrIDRef", "0")
        comment_style_id = _add_sized_char_style(members, base_char_id, 1000)
        spacer_style_id = _add_sized_char_style(members, base_char_id, 500)
        spacer_proto = paragraphs[3] if len(paragraphs) > 3 else blank_proto
        for paragraph in list(paragraphs):
            sublist.remove(paragraph)
        sublist.append(_plain_paragraph(blank_proto, [""]))

        entries = report_data.get(category, [])
        for entry_index, entry in enumerate(entries, start=1):
            if entry_index > 1:
                sublist.append(_set_char_style(_plain_paragraph(spacer_proto, [""]), spacer_style_id))
            title = str(entry.get("title", "")).strip()
            sublist.append(_plain_paragraph(title_proto, [f" {entry_index}. ", title]))
            for content in entry.get("contents", []):
                content = str(content).strip().lstrip("○- ")
                if content:
                    sublist.append(_plain_paragraph(item_proto, ["  ○ ", content]))
            comment = str(entry.get("comment", "")).strip()
            if comment:
                sublist.append(_set_char_style(_plain_paragraph(item_proto, ["     ", comment]), comment_style_id))

        if not entries:
            sublist.append(_plain_paragraph(title_proto, [" -", ""]))

    members[section_name] = ET.tostring(root, encoding="utf-8", xml_declaration=True, standalone=True)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as target:
        for info in source_infos:
            target.writestr(info, members[info.filename])
    return output.getvalue()
