import streamlit as st
import json
import os
import datetime
import importlib
import hwp_generator
importlib.reload(hwp_generator)
from hwp_generator import HWPXGenerator
import dynamic_hwpx_generator
importlib.reload(dynamic_hwpx_generator)
from dynamic_hwpx_generator import generate_dynamic_hwpx_bytes

# 페이지 구성 설정
st.set_page_config(
    page_title="주간보고 자동 취합 서비스",
    page_icon="📝",
    layout="wide"
)

DATA_FILE = "data_store.json"
HISTORY_DIR = os.path.join("data", "history")

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
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
    .stButton>button {
        border-radius: 6px;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# 메인 타이틀 영역
st.markdown('<div class="main-header">📝 주간보고 자동 취합 서비스</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">팀별 이번 주 실적과 다음 주 계획을 작성하고 한글(.hwp) 보고서로 다운로드할 수 있습니다.</div>', unsafe_allow_html=True)
show_queued_feedback()

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

st.info(f"📊 **현재 취합 현황**: 총 **{total_teams}개 팀** | 이번주 실적 **{total_this}건** | 다음주 계획 **{total_next}건**")
if missing_performance_dates:
    st.warning(f"⚠️ 실적 날짜가 입력되지 않은 이번 주 실적이 {missing_performance_dates}건 있습니다. 검토용 다운로드는 가능하며, 날짜는 나중에 수정할 수 있습니다.")

gen = HWPXGenerator()
today_str = datetime.datetime.now().strftime("%Y%m%d")

st.divider()

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
    st.markdown("### 🔄 다음 주 계획을 이번 주 실적으로 가져오기")
    st.caption(f"웹에 저장된 다음 주 계획 {len(next_week_items)}건을 모두 새 주의 이번 주 실적으로 옮깁니다.")
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
        "모든 다음 주 계획을 이번 주 실적으로 가져오기",
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

        st.session_state["reports_data"] = rolled_data
        save_data(rolled_data)
        queue_feedback(f"새 주 보고서를 만들었습니다. 이전 보고서: {archive_name}")
        st.session_state["target_tab"] = TAB_MANAGE
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
                placeholder="- (작성필요)\n- (작성필요)",
                key="top_entry_details",
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
                        "performance_date": entry_date.isoformat() if entry_date else "",
                    })
                    save_data(st.session_state["reports_data"])
                    queue_feedback(f"[{selected_manage_team}] {entry_category}을 추가했습니다.")
                    st.session_state["target_tab"] = TAB_MANAGE
                    st.rerun()

        st.divider()

    if not st.session_state["reports_data"]:
        st.info("등록된 팀이 없습니다. 위의 '새 팀 추가'에서 팀을 먼저 추가해 주세요.")
    else:
        for idx, team in enumerate(st.session_state["reports_data"]):
            t_name = team["team_name"]
            with st.expander(f"🏢 **{t_name}** (실적: {len(team['this_week'])}건 / 계획: {len(team['next_week'])}건)", expanded=False):
                if st.button("🗑️ 팀 삭제", key=f"delete_team_{idx}"):
                    st.session_state["reports_data"].pop(idx)
                    save_data(st.session_state["reports_data"])
                    queue_feedback(f"[{t_name}] 팀을 삭제했습니다.")
                    st.session_state["target_tab"] = TAB_MANAGE
                    st.rerun()
                col_t1, col_t2 = st.columns(2)
                
                with col_t1:
                    st.markdown("### 이번 주 실적")
                    if not team["this_week"]:
                        st.caption("- 등록된 항목 없음")
                    else:
                        for entry_idx, entry in enumerate(team["this_week"]):
                            author = entry.get("author", "").strip() or "미지정"
                            shown_title = format_entry_title(entry, include_date=True)
                            st.markdown(f"**• {shown_title}** *(작성자: {author})*")
                            for d in entry.get("details", []):
                                st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{d}")
                            popover_revision = st.session_state.get("edit_popover_revision", 0)
                            with st.popover("✏️ 수정", key=f"edit_tw_popover_{idx}_{entry_idx}_{popover_revision}"):
                                edit_author = st.text_input("작성자", value=entry.get("author", ""), key=f"edit_tw_author_{idx}_{entry_idx}")
                                edit_date = st.date_input("실적 날짜 (선택사항)", value=parse_saved_date(entry.get("performance_date")), key=f"edit_tw_date_{idx}_{entry_idx}")
                                edit_title = st.text_input("제목", value=entry.get("title", ""), key=f"edit_tw_title_{idx}_{entry_idx}")
                                if edit_date:
                                    st.caption(f"문서 표시: {edit_title}({edit_date.month}.{edit_date.day})")
                                edit_details = st.text_area("세부내용", value="\n".join(entry.get("details", [])), key=f"edit_tw_details_{idx}_{entry_idx}")
                                if st.button("수정 저장", key=f"save_tw_{idx}_{entry_idx}", type="primary"):
                                    entry.update({
                                        "author": edit_author.strip(),
                                        "performance_date": edit_date.isoformat() if edit_date else "",
                                        "title": edit_title.strip(),
                                        "details": [line.strip() for line in edit_details.splitlines() if line.strip()],
                                    })
                                    save_data(st.session_state["reports_data"])
                                    queue_feedback(f"[{t_name}] 이번 주 실적을 수정했습니다.")
                                    st.session_state["edit_popover_revision"] = popover_revision + 1
                                    st.session_state["target_tab"] = TAB_MANAGE
                                    st.rerun()
                            if st.button("삭제", key=f"del_tw_{idx}_{entry_idx}"):
                                team["this_week"].pop(entry_idx)
                                save_data(st.session_state["reports_data"])
                                queue_feedback(f"[{t_name}] 이번 주 실적을 삭제했습니다.")
                                st.session_state["target_tab"] = TAB_MANAGE
                                st.rerun()

                with col_t2:
                    st.markdown("### 다음 주 계획")
                    if not team["next_week"]:
                        st.caption("- 등록된 항목 없음")
                    else:
                        for entry_idx, entry in enumerate(team["next_week"]):
                            author = entry.get("author", "").strip() or "미지정"
                            st.markdown(f"**• {entry.get('title', '')}** *(작성자: {author})*")
                            for d in entry.get("details", []):
                                st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{d}")
                            popover_revision = st.session_state.get("edit_popover_revision", 0)
                            with st.popover("✏️ 수정", key=f"edit_nw_popover_{idx}_{entry_idx}_{popover_revision}"):
                                edit_author = st.text_input("작성자", value=entry.get("author", ""), key=f"edit_nw_author_{idx}_{entry_idx}")
                                edit_title = st.text_input("제목", value=entry.get("title", ""), key=f"edit_nw_title_{idx}_{entry_idx}")
                                edit_details = st.text_area("세부내용", value="\n".join(entry.get("details", [])), key=f"edit_nw_details_{idx}_{entry_idx}")
                                if st.button("수정 저장", key=f"save_nw_{idx}_{entry_idx}", type="primary"):
                                    entry.update({
                                        "author": edit_author.strip(),
                                        "performance_date": "",
                                        "title": edit_title.strip(),
                                        "details": [line.strip() for line in edit_details.splitlines() if line.strip()],
                                    })
                                    save_data(st.session_state["reports_data"])
                                    queue_feedback(f"[{t_name}] 다음 주 계획을 수정했습니다.")
                                    st.session_state["edit_popover_revision"] = popover_revision + 1
                                    st.session_state["target_tab"] = TAB_MANAGE
                                    st.rerun()
                            if st.button("삭제", key=f"del_nw_{idx}_{entry_idx}"):
                                team["next_week"].pop(entry_idx)
                                save_data(st.session_state["reports_data"])
                                queue_feedback(f"[{t_name}] 다음 주 계획을 삭제했습니다.")
                                st.session_state["target_tab"] = TAB_MANAGE
                                st.rerun()

# --- TAB 3: 최종 문서 미리보기 ---
with tab3:
    st.subheader("👁️ 최종 문서 미리보기·저장")
    st.caption("다운로드할 A4 가로형 한글 보고서의 내용을 확인합니다.")

    download_col, reset_col = st.columns([3, 1])
    with download_col:
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

    with reset_col:
        if st.button("🗑️ 전체 데이터 초기화", use_container_width=True):
            st.session_state["reports_data"] = []
            st.session_state.pop("generated_hwp", None)
            save_data([])
            queue_feedback("전체 보고 데이터를 초기화했습니다.")
            st.session_state["target_tab"] = TAB_PREVIEW
            st.rerun()

    st.divider()
    
    if not st.session_state["reports_data"]:
        st.info("취합할 데이터가 아직 없습니다.")
    else:
        preview_html = gen.generate_html_preview(active_report_teams)
        st.markdown(preview_html, unsafe_allow_html=True)


# --- TAB 4: 다음 주로 이월 ---
with tab4:
    render_rollover_controls()
