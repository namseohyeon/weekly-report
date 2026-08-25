import copy
import io
import re
import zipfile
from pathlib import Path
from lxml import etree as ET

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = BASE_DIR / "전략경영회의양식.hwpx"
HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"


def _q(name):
    return f"{{{HP}}}{name}"


def _plain_paragraph(prototype, text):
    paragraph = copy.deepcopy(prototype)
    # 새 텍스트의 길이에 맞게 한글이 줄 배치를 다시 계산하도록 기존 좌표를 제거한다.
    for lines in list(paragraph.findall(_q("linesegarray"))):
        paragraph.remove(lines)

    runs = paragraph.findall(_q("run"))
    for run in runs:
        for child in list(run):
            run.remove(child)
    target = runs[0]
    node = ET.SubElement(target, _q("t"))
    if text.startswith(" ") or text.endswith(" "):
        node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    node.text = text
    return paragraph


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
        paragraphs = sublist.findall(_q("p"))
        blank_proto = paragraphs[0]
        title_proto = paragraphs[1]
        item_proto = paragraphs[2]
        spacer_proto = paragraphs[3] if len(paragraphs) > 3 else paragraphs[0]
        for paragraph in list(paragraphs):
            sublist.remove(paragraph)
        sublist.append(_plain_paragraph(blank_proto, ""))

        entries = report_data.get(category, [])
        for entry_index, entry in enumerate(entries, start=1):
            if entry_index > 1:
                sublist.append(_plain_paragraph(spacer_proto, ""))
            title = str(entry.get("title", "")).strip()
            sublist.append(_plain_paragraph(title_proto, f"{entry_index}. {title}"))
            for content in entry.get("contents", []):
                content = str(content).strip().lstrip("○ ")
                if content:
                    sublist.append(_plain_paragraph(item_proto, f"  ○  {content}"))

        if not entries:
            sublist.append(_plain_paragraph(title_proto, "-"))

    members[section_name] = ET.tostring(root, encoding="utf-8", xml_declaration=True, standalone=True)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as target:
        for info in source_infos:
            target.writestr(info, members[info.filename])
    return output.getvalue()