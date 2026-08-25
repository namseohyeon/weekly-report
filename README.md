# 주간·월간보고 자동 취합 서비스

주간 실적·계획과 월간 추진실적·추진계획을 작성하고, 원본 한글 양식을 유지한 **동적 HWPX 문서**로 내려받는 Streamlit 서비스입니다.

## 주요 기능

### 공통

- 헤더에서 주간보고·월간보고 전환
- 작성·수정, 미리보기·저장, 다음 기간 이월 흐름 제공
- 실적과 계획을 2열 카드 UI로 확인하고 바로 수정·삭제
- 원본 OWPML 양식을 기반으로 항목 수에 맞게 문단과 표 높이 자동 생성

### 주간보고

- 팀별 이번 주 실적 및 다음 주 계획 관리
- 작성자와 실적 완료일 관리
- 한국 시간 기준 이번 주·다음 주 기간 자동 계산
- 최대 2개 팀을 A4 가로 2열 HWPX 문서로 생성
- 다음 주 계획을 새 주의 이번 주 실적으로 이월하고 이전 데이터 보관

### 월간보고

- 팀 구분 없이 추진실적·추진계획 작성
- 오늘 날짜를 기준으로 이번 달 실적과 다음 달 계획을 자동 표시
- 실적·계획을 하나의 입력 폼과 라디오 버튼으로 구분
- `전략경영회의양식.hwpx`의 1행 2열 구조로 동적 문서 생성
- 현재 계획을 다음 달 추진실적으로 이월

## HWPX 생성 방식

HTML을 한글 문서로 변환하지 않고 HWPX 패키지의 OWPML을 직접 수정합니다. 양식의 글꼴, 문단 속성, 표 테두리와 셀 구조를 유지하면서 제목과 내용 문단을 데이터 개수만큼 복제합니다.

- 주간 양식: `경영관리본부 주간 실적 및 계획.hwpx`
- 월간 양식: `월간보고양식.hwpx`
- 주간 생성기: `dynamic_hwpx_generator.py`
- 월간 생성기: `monthly_hwpx_generator.py`

## 실행 방법

Python 3.10 이상을 권장합니다.

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

pip install -r requirements.txt
streamlit run app.py
```

브라우저에서 `http://localhost:8501`로 접속합니다.

## 주요 파일

- `app.py`: 주간·월간 작성, 수정, 이월, 미리보기 및 다운로드 UI
- `dynamic_hwpx_generator.py`: 주간보고 HWPX 동적 생성
- `monthly_hwpx_generator.py`: 월간보고 HWPX 동적 생성
- `hwp_generator.py`: 주간보고 웹 미리보기 생성
- `storage_backend.py`: Supabase 또는 로컬 JSON 저장소 연결
- `supabase_schema.sql`: 운영 DB 테이블 생성 SQL
- `requirements.txt`: 실행 의존성

## Supabase 운영 저장소

로컬 개발에서는 JSON 파일을 사용하고, 배포 환경에 Supabase Secrets가 설정되면 보고 기간별로 Supabase에 저장됩니다. 앱은 이번 달과 전달 데이터만 유지하며, 그보다 오래된 보고 기간은 접속 시 자동 삭제합니다.

1. Supabase SQL Editor에서 `supabase_schema.sql`을 실행합니다.
2. Streamlit Community Cloud의 **App settings → Secrets**에 아래 값을 등록합니다.

```toml
SUPABASE_URL = "https://프로젝트-ID.supabase.co"
SUPABASE_KEY = "service_role 키"
```

`SUPABASE_KEY`는 코드나 Git에 커밋하지 마세요. 서비스 역할 키를 사용하므로 `report_states` 테이블에 anon 공개 정책을 만들 필요가 없습니다. 기존 `data_store.json`, `monthly_data_store.json`, `.streamlit/secrets.toml`은 Git에서 제외됩니다.
