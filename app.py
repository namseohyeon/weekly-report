import streamlit as st
import json
import os
import datetime
import importlib
import hwp_generator
importlib.reload(hwp_generator)
from hwp_generator import HWPXGenerator

# 페이지 구성 설정
st.set_page_config(
    page_title="주간보고 자동 취합 서비스",
    page_icon="📝",
    layout="wide"
)

DATA_FILE = "data_store.json"

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
st.markdown('<div class="sub-header">팀별로 보고 사항을 작성하면, 2열 표의 단 1개 셀(Cell) 안에 깔끔하게 통합되어 한글(.hwp / .hwpx) 파일로 즉시 다운로드됩니다.</div>', unsafe_allow_html=True)

# 상단 현황 영역
total_teams = len(st.session_state["reports_data"])
total_this = sum(len(t.get("this_week", [])) for t in st.session_state["reports_data"])
total_next = sum(len(t.get("next_week", [])) for t in st.session_state["reports_data"])

st.info(f"📊 **현재 취합 현황**: 총 **{total_teams}개 팀** | 이번주 실적 **{total_this}건** | 다음주 계획 **{total_next}건**")

# 파일 다운로드 버튼 구역
st.markdown("### 📥 파일 다운로드 선택")
col_dl1, col_dl2, col_dl3, col_dl4 = st.columns([1.5, 1.5, 1.2, 1])

gen = HWPXGenerator()
today_str = datetime.datetime.now().strftime("%Y%m%d")

with col_dl1:
    if total_teams > 0:
        hwp_path = gen.create_hwp(st.session_state["reports_data"], "temp_output.hwp")
        with open(hwp_path, "rb") as f:
            b_hwp = f.read()
        st.download_button(
            label="📥 한글(.hwp) 다운로드 (추천)",
            data=b_hwp,
            file_name=f"주간보고_취합_{today_str}.hwp",
            mime="application/x-hwp",
            type="primary",
            use_container_width=True,
            help="모든 한글 버전(한글 2010~2024, 한글뷰어)에서 100% 오류 없이 즉시 열립니다."
        )
    else:
        st.button("📥 한글(.hwp) 다운로드 (추천)", disabled=True, use_container_width=True)

with col_dl2:
    if total_teams > 0:
        hwpx_path = gen.create_hwpx(st.session_state["reports_data"], "temp_output.hwpx")
        with open(hwpx_path, "rb") as f:
            b_hwpx = f.read()
        st.download_button(
            label="📥 한글(.hwpx) 다운로드",
            data=b_hwpx,
            file_name=f"주간보고_취합_{today_str}.hwpx",
            mime="application/hwp+zip",
            use_container_width=True,
            help="개방형 한글 포맷(.hwpx) 파일입니다."
        )
    else:
        st.button("📥 한글(.hwpx) 다운로드", disabled=True, use_container_width=True)

with col_dl3:
    if total_teams > 0:
        docx_path = gen.create_docx(st.session_state["reports_data"], "temp_output.docx")
        with open(docx_path, "rb") as f:
            b_docx = f.read()
        st.download_button(
            label="📥 Word(.docx) 다운로드",
            data=b_docx,
            file_name=f"주간보고_취합_{today_str}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True
        )
    else:
        st.button("📥 Word(.docx) 다운로드", disabled=True, use_container_width=True)

with col_dl4:
    if st.button("🗑️ 전체 데이터 초기화", use_container_width=True):
        st.session_state["reports_data"] = []
        save_data([])
        st.rerun()

st.divider()

# 메인 작업 탭 구분
tab1, tab2, tab3 = st.tabs(["✍️ 팀원 보고서 작성", "📊 팀별 현황 및 관리", "👁️ 한글 2열 표 라이브 미리보기"])

# --- TAB 1: 팀원 보고서 작성 ---
with tab1:
    st.subheader("✍️ 주간보고 항목 등록")
    st.caption("소속 팀을 선택한 후 이번주 실적 또는 다음주 계획을 입력하세요. 해당 팀의 단 1개 셀(Cell) 안에 누적 배치됩니다.")
    
    existing_teams = [t["team_name"] for t in st.session_state["reports_data"]]
    
    col_input1, col_input2 = st.columns([1, 1])
    
    with col_input1:
        team_option = st.selectbox(
            "1. 소속 팀 선택",
            options=["+ 새 팀 입력하기"] + existing_teams
        )
        
        if team_option == "+ 새 팀 입력하기":
            selected_team = st.text_input("새 팀 이름을 입력하세요", placeholder="예: 영업1팀").strip()
        else:
            selected_team = team_option

        category = st.radio(
            "2. 작성 구분 선택",
            options=["이번주 실적", "다음주 계획"],
            horizontal=True
        )

        author_name = st.text_input("3. 작성자 이름 (선택사항)", placeholder="예: 홍길동")

    with col_input2:
        item_title = st.text_input("4. 보고 주요 제목", placeholder="예: 주간 시스템 보안점검 실시")
        
        item_details_raw = st.text_area(
            "5. 세부 내역 (줄바꿈으로 구분)",
            placeholder="- CPU 및 메모리 점검 완료\n- 주요 로그 모니터링 적용",
            height=130
        )
        
        if st.button("📌 해당 팀 셀에 보고 추가", type="primary", use_container_width=True):
            if not selected_team:
                st.error("팀 이름을 선택하거나 입력해 주세요!")
            elif not item_title and not item_details_raw:
                st.error("보고 제목이나 세부 내역 중 하나 이상을 입력해 주세요!")
            else:
                details_list = [line.strip() for line in item_details_raw.split("\n") if line.strip()]
                
                team_dict = None
                for t in st.session_state["reports_data"]:
                    if t["team_name"] == selected_team:
                        team_dict = t
                        break
                
                if not team_dict:
                    team_dict = {
                        "team_name": selected_team,
                        "this_week": [],
                        "next_week": []
                    }
                    st.session_state["reports_data"].append(team_dict)
                
                new_entry = {
                    "author": author_name,
                    "title": item_title,
                    "details": details_list
                }
                
                if category == "이번주 실적":
                    team_dict["this_week"].append(new_entry)
                else:
                    team_dict["next_week"].append(new_entry)
                
                save_data(st.session_state["reports_data"])
                st.success(f"✅ [{selected_team}] 팀의 '{category}' 셀에 항목이 등록되었습니다!")
                st.rerun()

# --- TAB 2: 팀별 현황 및 관리 ---
with tab2:
    st.subheader("📊 팀별 등록 항목 관리")
    st.caption("각 팀별로 단 1개의 표 셀에 통합될 항목들을 확인하고 필요시 삭제/수정할 수 있습니다.")
    
    if not st.session_state["reports_data"]:
        st.info("등록된 데이터가 없습니다. '팀원 보고서 작성' 탭에서 보고 항목을 입력해 주세요.")
    else:
        for idx, team in enumerate(st.session_state["reports_data"]):
            t_name = team["team_name"]
            with st.expander(f"🏢 **{t_name}** (실적: {len(team['this_week'])}건 / 계획: {len(team['next_week'])}건)", expanded=True):
                col_t1, col_t2 = st.columns(2)
                
                with col_t1:
                    st.markdown(f"**[이번주 실적 셀 (1 Cell)]**")
                    if not team["this_week"]:
                        st.caption("- 등록된 항목 없음")
                    else:
                        for entry_idx, entry in enumerate(team["this_week"]):
                            st.markdown(f"**• {entry.get('title', '')}** *(작성자: {entry.get('author', '미지정')})*")
                            for d in entry.get("details", []):
                                st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{d}")
                            if st.button(f"삭제 ##tw_{idx}_{entry_idx}", key=f"del_tw_{idx}_{entry_idx}"):
                                team["this_week"].pop(entry_idx)
                                save_data(st.session_state["reports_data"])
                                st.rerun()

                with col_t2:
                    st.markdown(f"**[다음주 계획 셀 (1 Cell)]**")
                    if not team["next_week"]:
                        st.caption("- 등록된 항목 없음")
                    else:
                        for entry_idx, entry in enumerate(team["next_week"]):
                            st.markdown(f"**• {entry.get('title', '')}** *(작성자: {entry.get('author', '미지정')})*")
                            for d in entry.get("details", []):
                                st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{d}")
                            if st.button(f"삭제 ##nw_{idx}_{entry_idx}", key=f"del_nw_{idx}_{entry_idx}"):
                                team["next_week"].pop(entry_idx)
                                save_data(st.session_state["reports_data"])
                                st.rerun()

# --- TAB 3: 한글 2열 표 라이브 미리보기 ---
with tab3:
    st.subheader("👁️ 한글 2열 표 라이브 미리보기")
    st.caption("최종 생성될 2열 표 형태의 한글 문서 모습을 실시간으로 미리 확인합니다.")
    
    if not st.session_state["reports_data"]:
        st.info("취합할 데이터가 아직 없습니다.")
    else:
        preview_html = gen.generate_html_preview(st.session_state["reports_data"])
        st.markdown(preview_html, unsafe_allow_html=True)
