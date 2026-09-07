import streamlit as st
import json
import os
import datetime
import importlib
import copy
import html
import streamlit.components.v1 as components
import hwp_generator
importlib.reload(hwp_generator)
from hwp_generator import HWPXGenerator
import dynamic_hwpx_generator
importlib.reload(dynamic_hwpx_generator)
from dynamic_hwpx_generator import generate_dynamic_hwpx_bytes
import monthly_hwpx_generator
importlib.reload(monthly_hwpx_generator)
from monthly_hwpx_generator import generate_monthly_hwpx_bytes
from storage_backend import cleanup_old_states, load_state, load_state_for_period, save_state, save_state_for_period, supabase_enabled


def enable_google_analytics():
    """Load GA4 in the top-level Streamlit page when a Measurement ID is configured."""
    try:
        measurement_id = str(st.secrets.get("GA_MEASUREMENT_ID", "")).strip()
    except Exception:
        measurement_id = os.getenv("GA_MEASUREMENT_ID", "").strip()
    if not measurement_id.startswith("G-"):
        return
    safe_id = json.dumps(measurement_id)
    components.html(
        f"""
        <script>
        (() => {{
          const id = {safe_id};
          const doc = window.parent.document;
          if (doc.getElementById('weekly-report-ga4')) return;
          const script = doc.createElement('script');
          script.id = 'weekly-report-ga4';
          script.async = true;
          script.src = 'https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(id);
          doc.head.appendChild(script);
          window.parent.dataLayer = window.parent.dataLayer || [];
          window.parent.gtag = window.parent.gtag || function() {{ window.parent.dataLayer.push(arguments); }};
          window.parent.gtag('js', new Date());
          window.parent.gtag('config', id, {{ send_page_view: true }});
        }})();
        </script>
        """,
        height=0,
    )

# 페이지 구성 설정
st.set_page_config(
    page_title="주간·월간보고 자동 취합 서비스",
    page_icon="📝",
    layout="wide"
)
enable_google_analytics()

if supabase_enabled():
    try:
        cleanup_old_states(datetime.date.today().isoformat())
    except Exception as error:
        st.warning(f"데이터 보관 기간 정리를 완료하지 못했습니다: {error}")

DATA_FILE = "data_store.json"
HISTORY_DIR = os.path.join("data", "history")
MONTHLY_DATA_FILE = "monthly_data_store.json"

def load_data():
    return load_state("weekly", DATA_FILE, [])

def save_data(data):
    save_state("weekly", data, DATA_FILE)
    # 입력 내용이 바뀌면 이전에 생성한 문서는 더 이상 최신 문서가 아니다.
    st.session_state.pop("generated_hwp", None)
    st.session_state.pop("generated_hwp_key", None)

def parse_saved_date(value):
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return None

def format_entry_title(entry, include_date=False):
    title = entry.get("title", "")
    if include_date:
        saved_date = parse_saved_date(entry.get("performance_date"))
        if saved_date:
            title = f"{title}({saved_date.month}.{saved_date.day})"
    return title

def queue_feedback(message, level="success"):
    st.session_state["action_feedback"] = {"message": message, "level": level}

def show_queued_feedback():
    feedback = st.session_state.pop("action_feedback", None)
    if not feedback:
        return
    message = feedback["message"]
    level = feedback.get("level", "success")
    getattr(st, level, st.info)(message)
    if level == "success":
        st.toast(message, icon="✅")

# 세션 상태 초기화
if "reports_data" not in st.session_state:
    st.session_state["reports_data"] = load_data()
def load_monthly_data():
    default = {
        "month": datetime.datetime.now().month,
        "department": "AI혁신처",
        "performance": [],
        "plan": [],
    }
    saved = load_state("monthly", MONTHLY_DATA_FILE, default)
    return saved if "performance" in saved and "plan" in saved else default


def save_monthly_data(data):
    save_state("monthly", data, MONTHLY_DATA_FILE)


def render_monthly_report():
    monthly = st.session_state["monthly_data"]
    today = datetime.datetime.now()
    if int(monthly.get("month", 0)) != today.month:
        monthly["month"] = today.month
        save_monthly_data(monthly)
    write_tab, preview_tab, rollover_tab = st.tabs([
        "📝 작성·수정",
        "👁️ 미리보기·저장",
        "🔄 다음 달로 이월",
    ])

    with write_tab:
        report_month = int(monthly["month"])
        plan_month = 1 if report_month == 12 else report_month + 1
        st.subheader("📝 월간보고 작성·수정")
        st.caption(f"오늘 {today.year}.{today.month}.{today.day}. 기준 · {report_month}월 추진실적 / {plan_month}월 추진계획")
        with st.container(border=True):
            st.markdown("### ✍️ 보고 항목 작성")
            st.caption("작성 구분만 선택하고 같은 입력란에서 실적과 계획을 작성합니다.")
            with st.form("monthly_add_entry_form", clear_on_submit=True):
                category = st.radio(
                    "작성 구분",
                    options=["performance", "plan"],
                    format_func=lambda value: (
                        f"{report_month}월 추진실적" if value == "performance"
                        else f"{plan_month}월 추진계획"
                    ),
                    horizontal=True,
                    key="monthly_entry_category",
                )
                title = st.text_input("제목", placeholder="핵심 업무 제목을 입력하세요")
                contents_text = st.text_area(
                    "세부내용",
                    placeholder="한 줄에 한 항목씩 입력하세요",
                    height=140,
                )
                comment = st.text_area(
                    "주석 (선택)",
                    placeholder="*입력필요",
                    height=90,
                )
                if st.form_submit_button("보고 항목 추가", type="primary", use_container_width=True):
                    contents = [line.strip() for line in contents_text.splitlines() if line.strip()]
                    if not title.strip():
                        st.error("제목을 입력해 주세요.")
                    elif not contents:
                        st.error("세부내용을 한 줄 이상 입력해 주세요.")
                    else:
                        monthly[category].append({"title": title.strip(), "contents": contents, "comment": comment.strip()})
                        save_monthly_data(monthly)
                        category_label = "추진실적" if category == "performance" else "추진계획"
                        st.toast(f"{category_label}을 추가했습니다.", icon="✅")
                        st.rerun()

        total_entries = len(monthly.get("performance", [])) + len(monthly.get("plan", []))
        st.markdown(f"### 등록 항목 <span class='monthly-count'>{total_entries}건</span>", unsafe_allow_html=True)
        st.caption("왼쪽은 이번 달 추진실적, 오른쪽은 다음 달 추진계획입니다.")

        def render_monthly_cards(category_key, category_label, badge_class):
            entries = monthly.get(category_key, [])
            st.markdown(
                f'<div class="monthly-column-heading {badge_class}"><strong>{category_label}</strong><span>{len(entries)}건</span></div>',
                unsafe_allow_html=True,
            )
            if not entries:
                st.info("등록된 항목이 없습니다.")
            for entry_index, entry in enumerate(entries):
                with st.container(border=True):
                    st.markdown(
                        f'<span class="monthly-entry-badge {badge_class}">{category_label}</span>'
                        f'<div class="monthly-list-title">{html.escape(str(entry.get("title", "")))}</div>',
                        unsafe_allow_html=True,
                    )
                    for content in entry.get("contents", []):
                        st.markdown(f"&nbsp;&nbsp;○&nbsp;&nbsp;{html.escape(str(content))}", unsafe_allow_html=True)
                    if entry.get("comment", "").strip():
                        st.markdown(f'<div class="entry-comment">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{html.escape(entry["comment"])}</div>', unsafe_allow_html=True)
                    edit_col, up_col, down_col, delete_col = st.columns([1.25, 1, 1, 1.25])
                    with edit_col:
                        with st.popover("✏️ 수정", use_container_width=True):
                            edited_title = st.text_input(
                                "제목", value=entry.get("title", ""),
                                key=f"monthly_edit_title_{category_key}_{entry_index}",
                            )
                            edited_contents = st.text_area(
                                "세부내용", value="\n".join(entry.get("contents", [])), height=180,
                                key=f"monthly_edit_contents_{category_key}_{entry_index}",
                            )
                            edited_comment = st.text_area(
                                "주석 (선택)", value=entry.get("comment", ""), height=110,
                                key=f"monthly_edit_comment_{category_key}_{entry_index}",
                            )
                            if st.button("수정 저장", key=f"monthly_save_{category_key}_{entry_index}", type="primary", use_container_width=True):
                                entry["title"] = edited_title.strip()
                                entry["contents"] = [line.strip() for line in edited_contents.splitlines() if line.strip()]
                                entry["comment"] = edited_comment.strip()
                                save_monthly_data(monthly)
                                st.rerun()
                    with up_col:
                        if st.button(
                            "↑ 위로", key=f"monthly_up_{category_key}_{entry_index}",
                            disabled=entry_index == 0, use_container_width=True,
                        ):
                            entries[entry_index - 1], entries[entry_index] = entries[entry_index], entries[entry_index - 1]
                            save_monthly_data(monthly)
                            st.rerun()
                    with down_col:
                        if st.button(
                            "↓ 아래로", key=f"monthly_down_{category_key}_{entry_index}",
                            disabled=entry_index == len(entries) - 1, use_container_width=True,
                        ):
                            entries[entry_index], entries[entry_index + 1] = entries[entry_index + 1], entries[entry_index]
                            save_monthly_data(monthly)
                            st.rerun()
                    with delete_col:
                        if st.button("🗑️ 삭제", key=f"monthly_delete_{category_key}_{entry_index}", use_container_width=True):
                            monthly[category_key].pop(entry_index)
                            save_monthly_data(monthly)
                            st.rerun()

        performance_list_col, plan_list_col = st.columns(2, gap="large")
        with performance_list_col:
            render_monthly_cards("performance", f"{report_month}월 추진실적", "performance")
        with plan_list_col:
            render_monthly_cards("plan", f"{plan_month}월 추진계획", "plan")
    with preview_tab:
        st.subheader("👁️ 월간보고 미리보기·저장")
        report_month = int(monthly["month"])
        plan_month = 1 if report_month == 12 else report_month + 1
        setting_left_space, setting_center, setting_right_space = st.columns([1, 2.2, 1])
        with setting_center:
            department_col, save_col = st.columns(
                [2.2, 1], gap="medium", vertical_alignment="bottom"
            )
            with department_col:
                department = st.text_input(
                    "처명",
                    value=monthly.get("department", "AI혁신처"),
                    key="monthly_department",
                )
            with save_col:
                if st.button("처명 저장", use_container_width=True):
                    monthly["department"] = department.strip() or "AI혁신처"
                    save_monthly_data(monthly)
                    st.rerun()

        st.divider()
        monthly_bytes = generate_monthly_hwpx_bytes(
            monthly.get("month", datetime.datetime.now().month),
            monthly,
            monthly.get("department", "AI혁신처"),
        )
        monthly_file_name = f"전략경영회의_{monthly.get('month')}월_{datetime.datetime.now().strftime('%Y%m%d')}.hwpx"
        download_left_space, download_center, download_right_space = st.columns([1, 2.2, 1])
        with download_center:
            st.download_button(
                "📥 월간보고(.hwpx) 다운로드",
                data=monthly_bytes,
                file_name=monthly_file_name,
                mime="application/hwp+zip",
                type="primary",
                use_container_width=True,
            )

        def monthly_cell_html(category_key):
            entries = monthly.get(category_key, [])
            if not entries:
                return '<div class="monthly-empty">-</div>'
            blocks = []
            for entry_index, entry in enumerate(entries, start=1):
                title = html.escape(str(entry.get("title", "")))
                contents = "".join(
                    f'<div class="monthly-item">&nbsp;&nbsp;○&nbsp;{html.escape(str(content).strip().lstrip("○- "))}</div>'
                    for content in entry.get("contents", [])
                    if str(content).strip().lstrip("○- ")
                )
                blocks.append(
                    f'<div class="monthly-entry"><div class="monthly-title">'
                    f'&nbsp;{entry_index}.&nbsp;{title}</div>{contents}'
                    f'<div class="monthly-comment">{html.escape(str(entry.get("comment", "")).strip()) if str(entry.get("comment", "")).strip() else ""}</div></div>'
                )
            return "".join(blocks)

        report_month = int(monthly.get("month", datetime.datetime.now().month))
        plan_month = 1 if report_month == 12 else report_month + 1
        report_department = html.escape(monthly.get("department", "AI혁신처"))
        st.markdown(
            f"""
            <div class="monthly-page">
              <table class="monthly-report-table">
                <thead>
                <tr class="monthly-department-row"><th colspan="2">[ 경 영 관 리 본 부 ]&nbsp;&nbsp;{report_department}</th></tr>
                <tr class="monthly-period-row">
                  <th>▣ {report_month}월 추진실적</th>
                  <th>▣ {plan_month}월 추진계획</th>
                </tr></thead>
                <tbody><tr>
                  <td>{monthly_cell_html("performance")}</td>
                  <td>{monthly_cell_html("plan")}</td>
                </tr></tbody>
              </table>
            </div>
            <style>
              .monthly-page {{ width: min(100%, 1120px); aspect-ratio: 297 / 210; min-height: 600px; margin: 20px auto 40px; padding: 10mm; box-sizing: border-box; background: white; color: #111; border: 1px solid #e2e2e2; box-shadow: 0 2px 12px rgba(0,0,0,.06); font-family: "한양중고딕", "HY중고딕", "Malgun Gothic", sans-serif; }}
              .monthly-report-table {{ width: 100%; height: 100%; border-collapse: collapse; table-layout: fixed; }}
              .monthly-report-table th, .monthly-report-table td {{ border: 1px solid #222; }}
              .monthly-department-row {{ height: 3.4%; }}
              .monthly-department-row th {{ border: 0; padding: 2px; text-align: center; font-size: 27px; font-weight: 700; }}
              .monthly-period-row {{ height: 4.4%; }}
              .monthly-period-row th {{ padding: 3px 5px; font-size: 21px; line-height: 1.5; text-align: left; }}
              .monthly-report-table tbody tr {{ height: 92.2%; }}
              .monthly-report-table td {{ padding: 2px 3px; vertical-align: top; font-size: 17px; line-height: 1.55; }}
              .monthly-entry + .monthly-entry {{ margin-top: 5pt; }}
              .monthly-title {{ font-size: 20px; font-weight: 700; margin: 0 0 7px; padding-left: 1.8em; text-indent: calc(1mm - 1.8em); line-height: 1.45; }}
              .monthly-item {{ font-size: 17px; margin: 3px 0 0; padding-left: calc(1mm + 4ch); text-indent: -4ch; line-height: 1.55; }}
              .monthly-comment {{ min-height: 0; margin: 2px 0 0; padding-left: calc(1mm + 5ch); font-family: "한양중고딕", "HY중고딕", sans-serif; font-size: 10pt; line-height: 1.45; white-space: pre-wrap; }}
              .monthly-comment:empty {{ display: none; }}
              .monthly-empty {{ color: #555; }}
              @media (max-width: 700px) {{ .monthly-page {{ aspect-ratio: auto; min-height: 520px; padding: 12px; }} .monthly-department-row th {{ font-size: 18px; }} .monthly-period-row th {{ font-size: 14px; }} .monthly-report-table td {{ font-size: 14px; }} .monthly-title {{ font-size: 16px; }} .monthly-item {{ margin-left: 10px; font-size: 14px; }} }}
            </style>
            """,
            unsafe_allow_html=True,
        )

    with rollover_tab:
        st.subheader("🔄 다음 달로 이월")
        st.caption("현재 추진계획을 다음 달의 추진실적으로 옮기고 현재 추진실적은 비웁니다.")
        confirm = st.checkbox("다음 달로 이월하겠습니다.", key="monthly_rollover_confirm")
        if st.button(
            "추진계획을 다음 달 추진실적으로 이월",
            disabled=not confirm or not monthly.get("plan"),
            type="primary",
            use_container_width=True,
        ):
            monthly["performance"] = copy.deepcopy(monthly.get("plan", []))
            monthly["plan"] = []
            monthly["month"] = 1 if int(monthly.get("month", 1)) == 12 else int(monthly.get("month", 1)) + 1
            save_monthly_data(monthly)
            st.toast("다음 달로 이월했습니다.", icon="✅")
            st.rerun()


if "monthly_data" not in st.session_state or "performance" not in st.session_state.get("monthly_data", {}):
    st.session_state["monthly_data"] = load_monthly_data()

# Custom CSS 스타일링
st.markdown("""
<style>
    .main-header {
        font-size: 26px;
        font-weight: bold;
        color: #1e293b;
        margin-bottom: 5px;
    }
    .sub-header {
        font-size: 14px;
        color: #64748b;
        margin-bottom: 20px;
    }
    .card {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 15px;
    }
    .monthly-hero {
        display: flex; align-items: center; justify-content: space-between; gap: 24px;
        margin: 4px 0 24px; padding: 24px 28px; border-radius: 18px;
        color: white; background: linear-gradient(135deg, #123c69 0%, #1d6b8f 58%, #2a9d8f 100%);
        box-shadow: 0 12px 28px rgba(18, 60, 105, .18);
    }
    .monthly-hero h2 { margin: 5px 0 4px; font-size: 27px; color: white; }
    .monthly-hero p { margin: 0; color: rgba(255,255,255,.82); }
    .monthly-kicker { font-size: 11px; letter-spacing: .18em; font-weight: 800; color: #bde8e1; }
    .monthly-period-badge { flex: 0 0 auto; padding: 12px 17px; border: 1px solid rgba(255,255,255,.35); border-radius: 999px; background: rgba(255,255,255,.12); font-size: 17px; font-weight: 800; }
    [data-testid="stMainBlockContainer"] { max-width: 1500px; padding-left: 3rem; padding-right: 3rem; }
    .st-key-report_type_switcher { margin: 0; padding: 6px; border: 1px solid #dbe5ef; border-radius: 16px; background: #f4f7fa; box-shadow: 0 5px 16px rgba(23,43,77,.08); }
    .st-key-report_type_switcher [data-testid="stButton"] button { min-height: 50px !important; border-radius: 10px !important; font-size: 16px !important; font-weight: 800 !important; }
    .st-key-report_type_switcher [data-testid="stButton"] button[kind="primary"] { box-shadow: 0 6px 16px rgba(239,83,80,.25); }
    [data-testid="stSegmentedControl"] { width: 100%; margin: 16px 0 12px; padding: 7px; border: 1px solid #dbe5ef; border-radius: 16px; background: #f4f7fa; }
    div[data-testid="stElementContainer"]:has([data-testid="stSegmentedControl"]),
    [data-testid="stSegmentedControl"] [data-baseweb="button-group"] { width: 100% !important; }
    [data-testid="stSegmentedControl"] > div,
    [data-testid="stSegmentedControl"] [role="radiogroup"] { display: flex !important; width: 100% !important; gap: 7px !important; }
    [data-testid="stSegmentedControl"] button,
    [data-testid="stSegmentedControl"] label,
    [data-testid="stSegmentedControl"] [role="radio"] { flex: 1 1 50% !important; width: 50% !important; min-height: 58px !important; border-radius: 11px !important; justify-content: center !important; font-weight: 800 !important; }
    [data-testid="stSegmentedControl"] p,
    [data-testid="stSegmentedControl"] span { font-size: 19px !important; font-weight: 800 !important; }
    [data-testid="stSegmentedControl"] button[aria-checked="true"],
    [data-testid="stSegmentedControl"] label:has(input:checked),
    [data-testid="stSegmentedControl"] [role="radio"][aria-checked="true"] { color: white !important; background: linear-gradient(135deg,#ef5350,#ff6b5f) !important; box-shadow: 0 6px 16px rgba(239,83,80,.28); }
    div[data-baseweb="popover"] { min-width: 540px !important; max-width: min(92vw, 640px) !important; }
    div[data-baseweb="popover"] > div { width: 100% !important; }
    [data-testid="stPopoverBody"] { min-width: 540px !important; width: min(92vw, 640px) !important; padding: 22px !important; }
    .monthly-count { display: inline-block; margin-left: 6px; padding: 3px 9px; border-radius: 999px; background: #edf2f7; color: #4a5568; font-size: 13px; vertical-align: middle; }
    .monthly-column-heading { display: flex; align-items: center; justify-content: space-between; margin: 4px 0 10px; padding: 12px 15px; border-radius: 12px; }
    .monthly-column-heading.performance { color: #116149; background: linear-gradient(135deg,#ecfbf5,#dff7ed); }
    .monthly-column-heading.plan { color: #2455a4; background: linear-gradient(135deg,#f1f6ff,#e4edff); }
    .monthly-column-heading span { padding: 2px 8px; border-radius: 999px; background: rgba(255,255,255,.75); font-size: 12px; font-weight: 800; }
    .monthly-entry-badge { display: inline-block; padding: 4px 9px; border-radius: 999px; font-size: 12px; font-weight: 800; }
    .monthly-entry-badge.performance { color: #116149; background: #def7ec; }
    .monthly-entry-badge.plan { color: #2455a4; background: #e6efff; }
    .monthly-list-title { margin: 8px 0 4px; color: #172b4d; font-size: 18px; font-weight: 800; }
    .weekly-entry-author { margin: -1px 0 10px; color: #718096; font-size: 13px; font-style: italic; }
    .entry-comment { margin: 4px 0 8px; color: #596579; font-family: "한양중고딕", "HY중고딕", sans-serif; font-size: 10pt; white-space: pre-wrap; }
    @media (max-width: 700px) { [data-testid="stMainBlockContainer"] { padding-left: 1rem; padding-right: 1rem; } .monthly-hero { align-items: flex-start; flex-direction: column; } }
    .stButton>button {
        border-radius: 6px;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# 메인 타이틀·보고서 전환 영역 — 시안 A
if "active_report_type" not in st.session_state:
    st.session_state["active_report_type"] = "주간보고"

header_title_col, header_switch_col = st.columns([2.2, 1.25], gap="large", vertical_alignment="center")
with header_title_col:
    st.markdown('<div class="main-header">📝 주간보고 자동 취합 서비스</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">주간·월간 실적과 계획을 작성하고 한글(.hwpx) 보고서로 다운로드할 수 있습니다.</div>', unsafe_allow_html=True)
with header_switch_col:
    with st.container(key="report_type_switcher"):
        weekly_switch, monthly_switch = st.columns(2, gap="small")
        with weekly_switch:
            if st.button(
                "📅 주간보고",
                type="primary" if st.session_state["active_report_type"] == "주간보고" else "secondary",
                use_container_width=True,
                key="show_weekly_report",
            ):
                st.session_state["active_report_type"] = "주간보고"
                st.rerun()
        with monthly_switch:
            if st.button(
                "🗓️ 월간보고",
                type="primary" if st.session_state["active_report_type"] == "월간보고" else "secondary",
                use_container_width=True,
                key="show_monthly_report",
            ):
                st.session_state["active_report_type"] = "월간보고"
                st.rerun()

show_queued_feedback()
report_type = st.session_state["active_report_type"]
if report_type == "월간보고":
    render_monthly_report()
    st.stop()

# 상단 현황 영역
total_teams = len(st.session_state["reports_data"])
total_this = sum(len(t.get("this_week", [])) for t in st.session_state["reports_data"])
total_next = sum(len(t.get("next_week", [])) for t in st.session_state["reports_data"])
active_report_teams = [
    team for team in st.session_state["reports_data"]
    if team.get("this_week") or team.get("next_week")
]
missing_performance_dates = sum(
    1
    for team in st.session_state["reports_data"]
    for entry in team.get("this_week", [])
    if not entry.get("performance_date")
)

gen = HWPXGenerator()
today_str = datetime.datetime.now().strftime("%Y%m%d")

st.divider()
st.info(f"📊 **현재 취합 현황**: 총 **{total_teams}개 팀** | 이번주 실적 **{total_this}건** | 다음주 계획 **{total_next}건**")
if missing_performance_dates:
    st.warning(f"⚠️ 실적 날짜가 입력되지 않은 이번 주 실적이 {missing_performance_dates}건 있습니다. 검토용 다운로드는 가능하며, 날짜는 나중에 수정할 수 있습니다.")

# 메인 작업 탭 구분
TAB_MANAGE = "📝 보고서 작성·수정"
TAB_PREVIEW = "👁️ 최종 문서 미리보기·저장"
TAB_REVIEW = "🔄 다음 주로 이월"
target_tab = st.session_state.pop("target_tab", None)
tab2, tab3, tab4 = st.tabs([
    TAB_MANAGE,
    TAB_PREVIEW,
    TAB_REVIEW,
], default=target_tab)

def render_rollover_controls():
    next_week_items = [
        (team_idx, entry_idx, team["team_name"], entry)
        for team_idx, team in enumerate(st.session_state["reports_data"])
        for entry_idx, entry in enumerate(team.get("next_week", []))
    ]
    current_monday = datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday())
    previous_monday = current_monday - datetime.timedelta(days=7)
    previous_reports = load_state_for_period("weekly", previous_monday, [])
    previous_plan_items = [
        (team.get("team_name", ""), entry)
        for team in previous_reports
        for entry in team.get("next_week", [])
    ]

    if previous_plan_items:
        with st.container(border=True):
            st.markdown("#### 지난주 계획 가져오기")
            st.caption(
                f"{previous_monday.isoformat()} 주차의 다음 주 계획 {len(previous_plan_items)}건을 "
                "현재 주의 이번 주 실적으로 가져올 수 있습니다. 이미 가져온 항목은 제외됩니다."
            )
            if st.button(
                "지난주 계획을 이번 주 실적으로 가져오기",
                type="primary",
                use_container_width=True,
                key="import_previous_week_plans",
            ):
                current_by_team = {
                    team.get("team_name", ""): team for team in st.session_state["reports_data"]
                }
                imported = 0
                for previous_team in previous_reports:
                    team_name = previous_team.get("team_name", "").strip()
                    if not team_name:
                        continue
                    target = current_by_team.get(team_name)
                    if target is None:
                        target = {"team_name": team_name, "this_week": [], "next_week": []}
                        st.session_state["reports_data"].append(target)
                        current_by_team[team_name] = target
                    existing = {
                        json.dumps({
                            "title": item.get("title", ""),
                            "details": item.get("details", []),
                            "comment": item.get("comment", ""),
                        }, ensure_ascii=False, sort_keys=True)
                        for item in target.get("this_week", [])
                    }
                    for source in previous_team.get("next_week", []):
                        signature = json.dumps({
                            "title": source.get("title", ""),
                            "details": source.get("details", []),
                            "comment": source.get("comment", ""),
                        }, ensure_ascii=False, sort_keys=True)
                        if signature in existing:
                            continue
                        copied = copy.deepcopy(source)
                        copied["performance_date"] = ""
                        copied["rolled_from"] = previous_monday.isoformat()
                        target.setdefault("this_week", []).append(copied)
                        existing.add(signature)
                        imported += 1
                save_data(st.session_state["reports_data"])
                queue_feedback(f"지난주 계획 {imported}건을 이번 주 실적으로 가져왔습니다.")
                st.session_state["target_tab"] = TAB_MANAGE
                st.rerun()

    st.divider()
    st.markdown("### 🔄 다음 주 보고서 미리 만들기")
    st.caption(f"현재 다음 주 계획 {len(next_week_items)}건으로 다음 주차의 이번 주 실적을 미리 만듭니다. 현재 보고서는 유지됩니다.")
    if not next_week_items:
        st.warning(
            "웹에 저장된 다음 주 계획이 없어 가져오기 버튼을 사용할 수 없습니다. "
            "'보고서 작성·수정'에서 다음 주 계획을 먼저 입력해 주세요."
        )
    confirm_rollover = st.checkbox(
        "현재 보고서를 보관하고 모든 다음 주 계획을 이월하겠습니다.",
        key="review_confirm_rollover",
    )
    if st.button(
        "다음 주 계획으로 다음 주차 보고서 만들기",
        disabled=not next_week_items or not confirm_rollover,
        type="primary",
        key="review_rollover_button",
    ):
        os.makedirs(HISTORY_DIR, exist_ok=True)
        archive_name = f"weekly_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(os.path.join(HISTORY_DIR, archive_name), "w", encoding="utf-8") as archive_file:
            json.dump(st.session_state["reports_data"], archive_file, ensure_ascii=False, indent=2)

        rolled_data = []
        for team in st.session_state["reports_data"]:
            carried_entries = []
            for entry in team.get("next_week", []):
                copied_entry = json.loads(json.dumps(entry, ensure_ascii=False))
                copied_entry["performance_date"] = ""
                carried_entries.append(copied_entry)
            rolled_data.append({
                "team_name": team["team_name"],
                "this_week": carried_entries,
                "next_week": [],
            })

        next_monday = current_monday + datetime.timedelta(days=7)
        save_state_for_period("weekly", next_monday, rolled_data)
        queue_feedback(
            f"{next_monday.isoformat()} 주차 보고서를 미리 만들었습니다. "
            f"현재 보고서는 그대로 유지됩니다. 보관 파일: {archive_name}"
        )
        st.session_state["target_tab"] = TAB_REVIEW
        st.rerun()

# --- TAB 2: 보고서 작성·수정 ---
with tab2:
    st.subheader("📝 보고서 작성·수정")
    st.caption("팀을 선택해 이번 주 실적과 다음 주 계획을 작성하고 기존 내용을 수정할 수 있습니다.")

    with st.expander("➕ 새 팀 추가"):
        new_team_name = st.text_input(
            "팀 이름 (선택사항)",
            placeholder="입력하지 않으면 디지털·AI전략팀",
            key="manage_new_team_name",
        ).strip() or "디지털·AI전략팀"
        if st.button("팀 추가", key="manage_add_team"):
            existing_names = [team["team_name"] for team in st.session_state["reports_data"]]
            if new_team_name in existing_names:
                st.warning("이미 등록된 팀입니다.")
            else:
                st.session_state["reports_data"].append({
                    "team_name": new_team_name,
                    "this_week": [],
                    "next_week": [],
                })
                save_data(st.session_state["reports_data"])
                queue_feedback(f"[{new_team_name}] 팀을 추가했습니다.")
                st.session_state["target_tab"] = TAB_MANAGE
                st.rerun()

    if st.session_state["reports_data"]:
        team_names = [team["team_name"] for team in st.session_state["reports_data"]]
        select_team_col, select_category_col = st.columns(2, gap="large")
        with select_team_col:
            with st.container(border=True):
                st.markdown("#### 🏢 1. 작성할 팀 선택")
                st.caption("내용이 등록될 팀을 선택하세요.")
                selected_manage_team = st.selectbox(
                    "작성할 팀 선택",
                    options=team_names,
                    key="manage_selected_team",
                    label_visibility="collapsed",
                )

        with select_category_col:
            with st.container(border=True):
                st.markdown("#### 🗂️ 2. 작성 구분 선택")
                st.caption("작성할 보고 항목의 종류를 선택하세요.")
                entry_category = st.radio(
                    "작성 구분",
                    options=["이번 주 실적", "다음 주 계획"],
                    horizontal=True,
                    key="manage_entry_category",
                    label_visibility="collapsed",
                )

        selected_team_data = next(
            team for team in st.session_state["reports_data"]
            if team["team_name"] == selected_manage_team
        )

        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        with st.form("manage_add_entry", clear_on_submit=True):
            st.markdown(f"### {entry_category} 작성")
            entry_author = st.text_input("작성자", key="top_entry_author")
            entry_date = None
            if entry_category == "이번 주 실적":
                entry_date = st.date_input(
                    "실적 날짜 (선택사항)",
                    value=None,
                    key="top_entry_date",
                )
            entry_title = st.text_input("제목", key="top_entry_title")
            entry_details = st.text_area(
                "세부내용",
                placeholder="- 입력필요",
                key="top_entry_details",
            )
            entry_comment = st.text_area(
                "주석 (선택)",
                placeholder="*입력필요",
                height=90,
                key="top_entry_comment",
            )
            add_entry = st.form_submit_button(
                f"{entry_category} 추가",
                type="primary",
                use_container_width=True,
            )
            if add_entry:
                if not entry_title.strip() and not entry_details.strip():
                    st.error("제목이나 세부내용 중 하나 이상을 입력해 주세요.")
                else:
                    category_key = "this_week" if entry_category == "이번 주 실적" else "next_week"
                    selected_team_data[category_key].append({
                        "author": entry_author.strip(),
                        "title": entry_title.strip(),
                        "details": [line.strip() for line in entry_details.splitlines() if line.strip()],
                        "comment": entry_comment.strip(),
                        "performance_date": entry_date.isoformat() if entry_date else "",
                        "detail_markers_explicit": True,
                    })
                    save_data(st.session_state["reports_data"])
                    queue_feedback(f"[{selected_manage_team}] {entry_category}을 추가했습니다.")
                    st.session_state["target_tab"] = TAB_MANAGE
                    st.rerun()

        st.divider()

    if not st.session_state["reports_data"]:
        st.info("등록된 팀이 없습니다. 위의 '새 팀 추가'에서 팀을 먼저 추가해 주세요.")
    else:
        def render_weekly_cards(team, team_index, category_key, heading, badge_class, include_date=False):
            entries = team.get(category_key, [])
            st.markdown(
                f'<div class="monthly-column-heading {badge_class}"><strong>{heading}</strong><span>{len(entries)}건</span></div>',
                unsafe_allow_html=True,
            )
            if not entries:
                st.info("등록된 항목이 없습니다.")
            for entry_index, entry in enumerate(entries):
                author = entry.get("author", "").strip() or "미지정"
                shown_title = format_entry_title(entry, include_date=include_date)
                with st.container(border=True):
                    st.markdown(
                        f'<span class="monthly-entry-badge {badge_class}">{heading}</span>'
                        f'<div class="monthly-list-title">{html.escape(shown_title)}</div>'
                        f'<div class="weekly-entry-author">작성자 · {html.escape(author)}</div>',
                        unsafe_allow_html=True,
                    )
                    for detail in entry.get("details", []):
                        raw_detail = str(detail).strip()
                        has_dash = raw_detail.startswith("-") or not entry.get("detail_markers_explicit", False)
                        clean_detail = html.escape(raw_detail[1:].lstrip() if raw_detail.startswith("-") else raw_detail)
                        prefix = "&nbsp;&nbsp;-&nbsp;&nbsp;" if has_dash else "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
                        st.markdown(f"{prefix}{clean_detail}", unsafe_allow_html=True)
                    if entry.get("comment", "").strip():
                        st.markdown(f'<div class="entry-comment">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{html.escape(entry["comment"])}</div>', unsafe_allow_html=True)
                    action_edit, action_up, action_down, action_delete = st.columns([1.25, 1, 1, 1.25])
                    revision = st.session_state.get("edit_popover_revision", 0)
                    with action_edit:
                        with st.popover("✏️ 수정", key=f"weekly_edit_{category_key}_{team_index}_{entry_index}_{revision}", use_container_width=True):
                            edit_author = st.text_input("작성자", value=entry.get("author", ""), key=f"weekly_author_{category_key}_{team_index}_{entry_index}")
                            edit_date = None
                            if include_date:
                                edit_date = st.date_input(
                                    "실적 날짜 (선택사항)", value=parse_saved_date(entry.get("performance_date")),
                                    key=f"weekly_date_{category_key}_{team_index}_{entry_index}",
                                )
                            edit_title = st.text_input("제목", value=entry.get("title", ""), key=f"weekly_title_{category_key}_{team_index}_{entry_index}")
                            edit_details = st.text_area("세부내용", value="\n".join(entry.get("details", [])), height=180, key=f"weekly_details_{category_key}_{team_index}_{entry_index}")
                            edit_comment = st.text_area("주석 (선택)", value=entry.get("comment", ""), height=110, key=f"weekly_comment_{category_key}_{team_index}_{entry_index}")
                            if st.button("수정 저장", key=f"weekly_save_{category_key}_{team_index}_{entry_index}", type="primary", use_container_width=True):
                                entry.update({
                                    "author": edit_author.strip(),
                                    "title": edit_title.strip(),
                                    "details": [line.strip() for line in edit_details.splitlines() if line.strip()],
                                    "comment": edit_comment.strip(),
                                    "performance_date": edit_date.isoformat() if include_date and edit_date else "",
                                    "detail_markers_explicit": True,
                                })
                                save_data(st.session_state["reports_data"])
                                queue_feedback(f"[{team['team_name']}] {heading}을 수정했습니다.")
                                st.session_state["edit_popover_revision"] = revision + 1
                                st.session_state["target_tab"] = TAB_MANAGE
                                st.rerun()
                    with action_up:
                        if st.button(
                            "↑ 위로", key=f"weekly_up_{category_key}_{team_index}_{entry_index}",
                            disabled=entry_index == 0, use_container_width=True,
                        ):
                            entries[entry_index - 1], entries[entry_index] = entries[entry_index], entries[entry_index - 1]
                            save_data(st.session_state["reports_data"])
                            queue_feedback(f"[{team['team_name']}] 항목 순서를 변경했습니다.")
                            st.session_state["target_tab"] = TAB_MANAGE
                            st.rerun()
                    with action_down:
                        if st.button(
                            "↓ 아래로", key=f"weekly_down_{category_key}_{team_index}_{entry_index}",
                            disabled=entry_index == len(entries) - 1, use_container_width=True,
                        ):
                            entries[entry_index], entries[entry_index + 1] = entries[entry_index + 1], entries[entry_index]
                            save_data(st.session_state["reports_data"])
                            queue_feedback(f"[{team['team_name']}] 항목 순서를 변경했습니다.")
                            st.session_state["target_tab"] = TAB_MANAGE
                            st.rerun()
                    with action_delete:
                        if st.button("🗑️ 삭제", key=f"weekly_delete_{category_key}_{team_index}_{entry_index}", use_container_width=True):
                            team[category_key].pop(entry_index)
                            save_data(st.session_state["reports_data"])
                            queue_feedback(f"[{team['team_name']}] {heading}을 삭제했습니다.")
                            st.session_state["target_tab"] = TAB_MANAGE
                            st.rerun()

        for idx, team in enumerate(st.session_state["reports_data"]):
            team_name = team["team_name"]
            with st.expander(
                f"🏢 {team_name} · 실적 {len(team['this_week'])}건 / 계획 {len(team['next_week'])}건",
                expanded=True,
            ):
                team_title_col, team_delete_col = st.columns([5, 1])
                with team_title_col:
                    st.markdown(f"#### {html.escape(team_name)}")
                with team_delete_col:
                    if st.button("🗑️ 팀 삭제", key=f"delete_team_{idx}", use_container_width=True):
                        st.session_state["reports_data"].pop(idx)
                        save_data(st.session_state["reports_data"])
                        queue_feedback(f"[{team_name}] 팀을 삭제했습니다.")
                        st.session_state["target_tab"] = TAB_MANAGE
                        st.rerun()
                performance_col, plan_col = st.columns(2, gap="large")
                with performance_col:
                    render_weekly_cards(team, idx, "this_week", "이번 주 실적", "performance", include_date=True)
                with plan_col:
                    render_weekly_cards(team, idx, "next_week", "다음 주 계획", "plan")
# --- TAB 3: 최종 문서 미리보기 ---
with tab3:
    st.subheader("👁️ 최종 문서 미리보기·저장")
    st.caption("다운로드할 A4 가로형 한글 보고서의 내용을 확인합니다.")

    if active_report_teams:
        dynamic_hwpx = generate_dynamic_hwpx_bytes(active_report_teams)
        st.download_button(
            label="📥 동적 한글(.hwpx) 다운로드",
            data=dynamic_hwpx,
            file_name=f"주간보고_취합_{today_str}.hwpx",
            mime="application/hwp+zip",
            type="primary",
            use_container_width=True,
            key="dynamic_hwpx_download",
        )
        st.caption("항목 수에 따라 제목·내용 문단과 셀 높이가 자동으로 늘어나는 권장 형식입니다.")
    else:
        st.button("📥 동적 한글(.hwpx) 다운로드", disabled=True, use_container_width=True)

    st.divider()
    
    if not st.session_state["reports_data"]:
        st.info("취합할 데이터가 아직 없습니다.")
    else:
        preview_html = gen.generate_html_preview(active_report_teams)
        st.markdown(preview_html, unsafe_allow_html=True)


# --- TAB 4: 다음 주로 이월 ---
with tab4:
    render_rollover_controls()
