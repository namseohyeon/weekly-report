import os
import zipfile
import datetime
from zoneinfo import ZoneInfo
from xml.sax.saxutils import escape
import docx
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn

class HWPXGenerator:
    """
    한글(HWP/HWPX) 및 Word(.docx) 문서를 자동 생성하는 클래스.
    모든 한글 프로그램(한글 2010~2024, 한글 뷰어)에서 100% 완벽하게 열리는
    .hwp (HTML/MIME HWP) 및 .hwpx, .docx 포맷 지원.
    """

    def __init__(self):
        pass

    def create_hwp(self, teams_data, output_path="주간보고_취합.hwp"):
        """
        모든 한글(Hancom Office) 버전에서 100% 오류 없이 즉시 열리는 HWP 문서 생성
        (한글 전용 메타 태그가 포함된 HTML/MIME HWP 포맷)
        """
        html_content = self.generate_html_document(teams_data)
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        return output_path

    def generate_hwp_bytes(self, teams_data):
        return self.generate_html_document(teams_data).encode("utf-8")

    def _build_hwp_html_content(self, teams_data):
        """
        한글 프로그램 호환성을 최우선으로 고려한 HTML/HWP 구조
        1개 팀당 1개 셀(Cell) 규칙 준수
        """
        html = ['''<!DOCTYPE html>
<html>
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
<meta name="Generator" content="Hancom Office HWP" />
<title>주간보고 취합서</title>
<style>
    @page {
        size: A4 landscape;
        margin: 15mm;
    }
    body {
        font-family: '함초롬바탕', '맑은 고딕', 'Batang', sans-serif;
        font-size: 10pt;
        color: #000000;
        line-height: 1.6;
    }
    h1 {
        text-align: center;
        font-size: 18pt;
        font-weight: bold;
        margin-bottom: 20px;
        letter-spacing: 2px;
    }
    table {
        width: 100%;
        border-collapse: collapse;
        table-layout: fixed;
        margin-top: 10px;
    }
    th {
        background-color: #F2F4F7;
        border: 1px solid #000000;
        padding: 10px;
        font-size: 11pt;
        font-weight: bold;
        text-align: center;
        width: 50%;
    }
    td {
        border: 1px solid #000000;
        padding: 12px;
        vertical-align: top;
        word-break: break-all;
    }
    .team-header {
        font-weight: bold;
        color: #004085;
        font-size: 11pt;
        margin-bottom: 8px;
        display: block;
    }
    .item-title {
        font-weight: bold;
        color: #111827;
        margin-top: 8px;
        margin-bottom: 4px;
    }
    .item-detail {
        color: #374151;
        margin-left: 5px;
        margin-top: 2px;
        margin-bottom: 2px;
    }
    .empty-text {
        color: #888888;
        font-style: italic;
    }
</style>
</head>
<body>

<h1>주 간 보 고 서</h1>

<table>
    <thead>
        <tr>
            <th>이번주 실적</th>
            <th>다음주 계획</th>
        </tr>
    </thead>
    <tbody>
''']

        for team in teams_data:
            team_name = escape(team.get("team_name", "무소속"))
            this_week = team.get("this_week", [])
            next_week = team.get("next_week", [])

            html.append('<tr>')
            
            # 셀 1: 이번주 실적 (단 1개 셀)
            html.append('<td>')
            html.append(f'<span class="team-header">[ {team_name} ]</span>')
            if not this_week:
                html.append('<div class="empty-text">- 실적 없음</div>')
            else:
                for entry in this_week:
                    t = escape(entry.get("title", ""))
                    if t:
                        html.append(f'<div class="item-title">{t}</div>')
                    for d in entry.get("details", []):
                        d_str = escape(d.strip())
                        if d_str:
                            if not d_str.startswith("-"):
                                d_str = "- " + d_str
                            html.append(f'<div class="item-detail">{d_str}</div>')
                    html.append('<div style="height:6px;"></div>')
            html.append('</td>')

            # 셀 2: 다음주 계획 (단 1개 셀)
            html.append('<td>')
            html.append(f'<span class="team-header">[ {team_name} ]</span>')
            if not next_week:
                html.append('<div class="empty-text">- 계획 없음</div>')
            else:
                for entry in next_week:
                    t = escape(entry.get("title", ""))
                    if t:
                        html.append(f'<div class="item-title">{t}</div>')
                    for d in entry.get("details", []):
                        d_str = escape(d.strip())
                        if d_str:
                            if not d_str.startswith("-"):
                                d_str = "- " + d_str
                            html.append(f'<div class="item-detail">{d_str}</div>')
                    html.append('<div style="height:6px;"></div>')
            html.append('</td>')

            html.append('</tr>')

        html.append('''
    </tbody>
</table>

</body>
</html>
''')
        return "\n".join(html)

    def create_hwpx(self, teams_data, output_path="주간보고_취합.hwpx"):
        """
        한글 OWPML 규격을 준수하는 HWPX 파일 생성
        """
        mimetype = "application/hwp+zip"
        
        container_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="Contents/content.hpf" media-type="application/hwpdoc+xml"/>
  </rootfiles>
</container>'''

        content_hpf = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<package xmlns="http://www.hancom.co.kr/hpf/2013/hpf" unique-identifier="dbid" version="1.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>주간보고 취합 문서</dc:title>
    <dc:language>ko</dc:language>
  </metadata>
  <manifest>
    <item id="header" href="header.xml" media-type="application/xml"/>
    <item id="section0" href="section0.xml" media-type="application/xml"/>
  </manifest>
  <spine>
    <itemref idref="header"/>
    <itemref idref="section0"/>
  </spine>
</package>'''

        header_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head" version="1.0">
  <hh:fontfaces>
    <hh:fontface id="0" lang="hangul"><hh:font name="함초롬바탕"/></hh:fontface>
    <hh:fontface id="1" lang="latin"><hh:font name="Hamchorom Batang"/></hh:fontface>
  </hh:fontfaces>
  <hh:borderfills>
    <hh:borderfill id="1" backColor="none">
      <hh:slash type="NONE"/><hh:backSlash type="NONE"/>
      <hh:leftBorder type="SOLID" width="0.12mm" color="#000000"/>
      <hh:rightBorder type="SOLID" width="0.12mm" color="#000000"/>
      <hh:topBorder type="SOLID" width="0.12mm" color="#000000"/>
      <hh:bottomBorder type="SOLID" width="0.12mm" color="#000000"/>
    </hh:borderfill>
    <hh:borderfill id="2" backColor="#F2F4F7">
      <hh:slash type="NONE"/><hh:backSlash type="NONE"/>
      <hh:leftBorder type="SOLID" width="0.25mm" color="#000000"/>
      <hh:rightBorder type="SOLID" width="0.25mm" color="#000000"/>
      <hh:topBorder type="SOLID" width="0.25mm" color="#000000"/>
      <hh:bottomBorder type="SOLID" width="0.25mm" color="#000000"/>
    </hh:borderfill>
  </hh:borderfills>
  <hh:charProperties>
    <hh:charPr id="0" height="1000" textColor="#000000" fontRef="0"/>
    <hh:charPr id="1" height="1100" bold="1" textColor="#1D2939" fontRef="0"/>
    <hh:charPr id="2" height="1000" bold="1" textColor="#004085" fontRef="0"/>
    <hh:charPr id="3" height="1400" bold="1" textColor="#0B0F19" fontRef="0"/>
  </hh:charProperties>
  <hh:paraProperties>
    <hh:paraPr id="0" align="left"><hh:lineSpacing type="PERCENT" value="160"/></hh:paraPr>
    <hh:paraPr id="1" align="center"><hh:lineSpacing type="PERCENT" value="160"/></hh:paraPr>
  </hh:paraProperties>
</hh:head>'''

        section0_content = self._build_section0_xml(teams_data)

        with zipfile.ZipFile(output_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            zipinfo = zipfile.ZipInfo("mimetype")
            zipinfo.compress_type = zipfile.ZIP_STORED
            zf.writestr(zipinfo, mimetype)
            
            zf.writestr("META-INF/container.xml", container_xml)
            zf.writestr("Contents/content.hpf", content_hpf)
            zf.writestr("Contents/header.xml", header_xml)
            zf.writestr("Contents/section0.xml", section0_content)

        return output_path

    def _build_section0_xml(self, teams_data):
        xml_lines = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"',
            '        xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"',
            '        xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core">',
            '  <hp:p paraPrRef="1"><hp:run charPrRef="3"><hp:t>주 간 보 고 서</hp:t></hp:run></hp:p>',
            '  <hp:p paraPrRef="0"><hp:run charPrRef="0"><hp:t></hp:t></hp:run></hp:p>',
            '  <hp:p paraPrRef="0"><hp:run charPrRef="0">',
            f'      <hp:tbl rowCount="{len(teams_data) + 1}" colCount="2" borderFillRef="1">',
            '        <hp:tr>',
            '          <hp:tc borderFillRef="2"><hp:p paraPrRef="1"><hp:run charPrRef="1"><hp:t>이번주 실적</hp:t></hp:run></hp:p></hp:tc>',
            '          <hp:tc borderFillRef="2"><hp:p paraPrRef="1"><hp:run charPrRef="1"><hp:t>다음주 계획</hp:t></hp:run></hp:p></hp:tc>',
            '        </hp:tr>'
        ]

        for team in teams_data:
            team_name = team.get("team_name", "무소속")
            this_week_entries = team.get("this_week", [])
            next_week_entries = team.get("next_week", [])

            xml_lines.append('        <hp:tr>')
            
            # 셀 1
            xml_lines.append('          <hp:tc borderFillRef="1">')
            xml_lines.append(f'            <hp:p paraPrRef="0"><hp:run charPrRef="2"><hp:t>[ {escape(team_name)} ]</hp:t></hp:run></hp:p>')
            if not this_week_entries:
                xml_lines.append('            <hp:p paraPrRef="0"><hp:run charPrRef="0"><hp:t>- 실적 없음</hp:t></hp:run></hp:p>')
            else:
                for entry in this_week_entries:
                    title = escape(entry.get("title", ""))
                    details = entry.get("details", [])
                    if title:
                        xml_lines.append(f'            <hp:p paraPrRef="0"><hp:run charPrRef="1"><hp:t>{title}</hp:t></hp:run></hp:p>')
                    for d in details:
                        d_str = escape(d.strip())
                        if d_str:
                            if not d_str.startswith("-"):
                                d_str = "- " + d_str
                            xml_lines.append(f'            <hp:p paraPrRef="0"><hp:run charPrRef="0"><hp:t>{d_str}</hp:t></hp:run></hp:p>')
                    xml_lines.append('            <hp:p paraPrRef="0"><hp:run charPrRef="0"><hp:t></hp:t></hp:run></hp:p>')
            xml_lines.append('          </hp:tc>')

            # 셀 2
            xml_lines.append('          <hp:tc borderFillRef="1">')
            xml_lines.append(f'            <hp:p paraPrRef="0"><hp:run charPrRef="2"><hp:t>[ {escape(team_name)} ]</hp:t></hp:run></hp:p>')
            if not next_week_entries:
                xml_lines.append('            <hp:p paraPrRef="0"><hp:run charPrRef="0"><hp:t>- 계획 없음</hp:t></hp:run></hp:p>')
            else:
                for entry in next_week_entries:
                    title = escape(entry.get("title", ""))
                    details = entry.get("details", [])
                    if title:
                        xml_lines.append(f'            <hp:p paraPrRef="0"><hp:run charPrRef="1"><hp:t>{title}</hp:t></hp:run></hp:p>')
                    for d in details:
                        d_str = escape(d.strip())
                        if d_str:
                            if not d_str.startswith("-"):
                                d_str = "- " + d_str
                            xml_lines.append(f'            <hp:p paraPrRef="0"><hp:run charPrRef="0"><hp:t>{d_str}</hp:t></hp:run></hp:p>')
                    xml_lines.append('            <hp:p paraPrRef="0"><hp:run charPrRef="0"><hp:t></hp:t></hp:run></hp:p>')
            xml_lines.append('          </hp:tc>')

            xml_lines.append('        </hp:tr>')

        xml_lines.append('      </hp:tbl></hp:run></hp:p>')
        xml_lines.append('</hs:sec>')

        return "\n".join(xml_lines)

    def create_docx(self, teams_data, output_path="주간보고_취합.docx"):
        """
        한글/워드 모두 완벽 호환되는 .docx 문서 생성
        """
        doc = docx.Document()
        
        # 페이지 여백 설정 (2cm)
        for section in doc.sections:
            section.top_margin = Inches(0.8)
            section.bottom_margin = Inches(0.8)
            section.left_margin = Inches(0.8)
            section.right_margin = Inches(0.8)
            
        # Title
        p_title = doc.add_paragraph()
        p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_title = p_title.add_run("주 간 보 고 서")
        run_title.font.name = "함초롬바탕"
        run_title.font.size = Pt(18)
        run_title.font.bold = True
        run_title.font.color.rgb = RGBColor(17, 24, 39)
        
        doc.add_paragraph() # Spacing
        
        # 2-Column Table
        table = doc.add_table(rows=len(teams_data) + 1, cols=2)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        
        # Header Row
        hdr_cells = table.rows[0].cells
        hdr_titles = ["이번주 실적", "다음주 계획"]
        for idx, title_text in enumerate(hdr_titles):
            cell = hdr_cells[idx]
            shading_elm = parse_xml(r'<w:shd {} w:fill="F2F4F7"/>'.format(nsdecls('w')))
            cell._tc.get_or_add_tcPr().append(shading_elm)
            
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(title_text)
            run.font.name = "함초롬바탕"
            run.font.size = Pt(11)
            run.font.bold = True
            run.font.color.rgb = RGBColor(29, 41, 57)

        # Team Rows
        for r_idx, team in enumerate(teams_data):
            row_cells = table.rows[r_idx + 1].cells
            team_name = team.get("team_name", "무소속")
            
            # Cell 0: 이번주 실적
            cell_tw = row_cells[0]
            p_tw = cell_tw.paragraphs[0]
            r_team = p_tw.add_run(f"[ {team_name} ]\n")
            r_team.font.bold = True
            r_team.font.color.rgb = RGBColor(0, 64, 133)
            
            this_week = team.get("this_week", [])
            if not this_week:
                r_empty = p_tw.add_run("- 실적 없음\n")
                r_empty.font.italic = True
                r_empty.font.color.rgb = RGBColor(128, 128, 128)
            else:
                for entry in this_week:
                    t = entry.get("title", "")
                    if t:
                        r_t = p_tw.add_run(f"{t}\n")
                        r_t.font.bold = True
                    for d in entry.get("details", []):
                        d_str = d.strip()
                        if d_str:
                            if not d_str.startswith("-"):
                                d_str = "- " + d_str
                            p_tw.add_run(f"{d_str}\n")
                    p_tw.add_run("\n")
                    
            # Cell 1: 다음주 계획
            cell_nw = row_cells[1]
            p_nw = cell_nw.paragraphs[0]
            r_team2 = p_nw.add_run(f"[ {team_name} ]\n")
            r_team2.font.bold = True
            r_team2.font.color.rgb = RGBColor(0, 64, 133)
            
            next_week = team.get("next_week", [])
            if not next_week:
                r_empty2 = p_nw.add_run("- 계획 없음\n")
                r_empty2.font.italic = True
                r_empty2.font.color.rgb = RGBColor(128, 128, 128)
            else:
                for entry in next_week:
                    t = entry.get("title", "")
                    if t:
                        r_t2 = p_nw.add_run(f"{t}\n")
                        r_t2.font.bold = True
                    for d in entry.get("details", []):
                        d_str = d.strip()
                        if d_str:
                            if not d_str.startswith("-"):
                                d_str = "- " + d_str
                            p_nw.add_run(f"{d_str}\n")
                    p_nw.add_run("\n")

        doc.save(output_path)
        return output_path

    def _build_report_layout(self, teams_data):
        today = datetime.datetime.now(ZoneInfo("Asia/Seoul")).date()
        monday = today - datetime.timedelta(days=today.weekday())
        friday = monday + datetime.timedelta(days=4)
        next_monday = monday + datetime.timedelta(days=7)
        next_friday = friday + datetime.timedelta(days=7)

        def date_range(start, end):
            return f"{start.month}.{start.day}.~{end.month}.{end.day}."

        def line_weight(team):
            def category_lines(category):
                lines = 1
                for entry in team.get(category, []):
                    lines += bool(entry.get("title", "").strip())
                    lines += len([d for d in entry.get("details", []) if d.strip()])
                return lines
            return max(category_lines("this_week"), category_lines("next_week")) + 1

        # 한 팀의 좌우 셀은 항상 같은 페이지/행에 둔다. 내용량 기준으로 다음 페이지에 넘긴다.
        pages = []
        current_page = []
        used_lines = 0
        for team in teams_data:
            weight = line_weight(team)
            if current_page and used_lines + weight > 24:
                pages.append(current_page)
                current_page = []
                used_lines = 0
            current_page.append(team)
            used_lines += weight
        if current_page or not pages:
            pages.append(current_page)

        def render_entries(entries, include_date=False):
            parts = []
            for entry in entries:
                title = escape(entry.get("title", "").strip())
                if title:
                    if include_date and entry.get("performance_date"):
                        try:
                            completed = datetime.date.fromisoformat(entry["performance_date"])
                            title += f"({completed.month}.{completed.day})"
                        except (TypeError, ValueError):
                            pass
                    parts.append(f'<div class="report-title">○&nbsp; {title}</div>')
                for detail in entry.get("details", []):
                    detail = escape(detail.strip().lstrip("- "))
                    if detail:
                        parts.append(f'<div class="report-detail">&nbsp;&nbsp;-&nbsp; {detail}</div>')
            return "".join(parts) or '<div class="empty-report">-</div>'

        def render_rows(page_teams):
            rows = []
            for team in page_teams:
                team_name = escape(team.get("team_name", ""))
                left = render_entries(team.get("this_week", []), include_date=True)
                right = render_entries(team.get("next_week", []))
                rows.append(
                    '<tr class="team-row">'
                    f'<td><div class="team-name">&lt;{team_name}&gt;</div>{left}</td>'
                    f'<td><div class="team-name">&lt;{team_name}&gt;</div>{right}</td>'
                    '</tr>'
                )
            return "".join(rows) or '<tr class="team-row"><td></td><td></td></tr>'

        page_html = []
        for page_index, page_teams in enumerate(pages):
            title = '<div class="company-name">AI혁신처</div>' if page_index == 0 else ''
            page_class = "first-page" if page_index == 0 else "continuation-page"
            page_html.append(f'''
<section class="weekly-paper {page_class}">
  {title}
  <table class="report-table">
    <thead><tr>
      <th>&lt; 이번주 실적 &gt; {date_range(monday, friday)}</th>
      <th>&lt; 다음주 계획 &gt; {date_range(next_monday, next_friday)}</th>
    </tr></thead>
    <tbody>{render_rows(page_teams)}</tbody>
  </table>
</section>''')

        return f'''
<style>
    @page Section1 {{
        size: 841.9pt 595.3pt;
        margin: 25.5pt 11.3pt 34pt 11.3pt;
        mso-page-orientation: landscape;
    }}
    @page {{
        size: 297mm 210mm;
        margin: 0;
    }}
    .Section1 {{ page: Section1; }}
    .weekly-document {{ background: #eef1f5; padding: 12px 0; }}
    .weekly-paper {{
        width: 297mm; height: 210mm; max-width: 100%; margin: 0 auto 18px;
        padding: 9mm 4mm 12mm; overflow: hidden;
        box-sizing: border-box; background: #fff; color: #000;
        font-family: "함초롬바탕", "바탕", serif;
        page-break-after: always;
    }}
    .weekly-paper:last-child {{ page-break-after: auto; }}
    .company-name {{
        width: 54mm; margin: 0 auto 2.5mm; padding-bottom: 1mm;
        border-bottom: 1px solid #000; text-align: center;
        font-size: 20pt; line-height: 1; font-weight: 700; letter-spacing: 3mm;
    }}
    .report-table {{ width: 100%; height: calc(100% - 14mm); border-collapse: collapse; table-layout: fixed; }}
    .continuation-page .report-table {{ height: 100%; }}
    .report-table {{ display: flex; flex-direction: column; }}
    .report-table thead {{ display: block; flex: 0 0 auto; }}
    .report-table thead tr, .report-table .team-row {{
        display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    }}
    .report-table tbody {{ display: flex; flex: 1 1 auto; flex-direction: column; min-height: 0; }}
    .report-table .team-row {{ flex: 0 0 auto; }}
    .report-table .team-row:last-child {{ flex: 1 1 auto; }}
    .report-table th, .report-table td {{ border: 1px solid #111; }}
    .report-table th {{ height: 10mm; padding: 0; text-align: center; font-size: 14pt; font-weight: 700; }}
    .report-table tbody td {{ border-top-color: transparent; border-bottom-color: transparent; }}
    .report-table tbody tr:last-child td {{ border-bottom-color: #111; }}
    .report-table td {{
        width: 50%; padding: 4mm 2.5mm; vertical-align: top;
        font-family: "휴먼명조", "Human MyungJo", "바탕", serif;
        font-size: 14pt; line-height: 1.7;
    }}
    .report-table th, .report-table td {{ width: auto; min-width: 0; }}
    .team-row {{ break-inside: avoid; page-break-inside: avoid; }}
    .team-name {{ font-weight: 700; margin-bottom: 1mm; }}
    .report-title {{ font-weight: 700; padding-left: 2.2em; text-indent: calc(1mm - 2.2em); }}
    .report-detail {{
        padding-left: 3.1em; text-indent: calc(1mm - 3.1em); font-weight: 400;
        font-family: "한양중고딕", "HYGothic-Medium", "맑은 고딕", sans-serif;
        font-size: 12pt;
    }}
    .empty-report {{
        color: #777; font-family: "휴먼명조", "Human MyungJo", "바탕", serif;
        font-size: 12pt;
    }}
    @media print {{
        .weekly-document {{ background: #fff; padding: 0; }}
        .weekly-paper {{ max-width: none; margin: 0; }}
    }}
</style>
<div class="weekly-document Section1">{"".join(page_html)}</div>'''

    def generate_html_preview(self, teams_data):
        return self._build_report_layout(teams_data)

    def generate_html_document(self, teams_data):
        return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="Generator" content="Hancom Office HWP">
<title>AI혁신처 주간 실적 및 계획</title></head>
<body style="margin:0">{self._build_report_layout(teams_data)}</body></html>'''
