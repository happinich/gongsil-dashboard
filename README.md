# Gongsil Internal MVP

공실닷컴에서 강남구/서초구 오피스텔(`k_code=21`) 매물을 내부 확인용으로 수집하고, 로컬 웹 대시보드에서 확인하는 MVP입니다.

중요:
- 공실닷컴 `robots.txt`는 전체 수집을 허용하지 않습니다. 공개 서비스나 대량 수집 전에 반드시 공실닷컴의 허가/제휴/API 여부를 확인하세요.
- 매물에는 중개사 연락처 등 민감할 수 있는 영업정보가 포함됩니다. 외부 재게시보다 내부 검색/알림 용도로 제한하는 것을 권장합니다.
- 계정 비밀번호와 알림 토큰은 코드나 문서에 저장하지 말고 환경변수 또는 로컬 `.env`에만 보관하세요.

## 현재 구현 범위

- 로그인 세션 유지
- 관심 단지 오피스텔 목록 수집
- 신규 매물 상세 페이지 수집
- SQLite 저장 및 중복 제거
- 조건 저장 UI와 프로필별 매물 필터링
- 역명 + 반경(m) 기반 위치 검색
- 매물 주소 지오코딩 및 좌표 저장
- 신규 매물 / 가격 변경 이벤트 기록
- 텔레그램 알림 발송 및 중복 방지 로그
- 로컬 웹 대시보드 제공

## 준비

외부 Python 패키지는 현재 MVP에는 필요하지 않습니다. `requirements.txt`는 Render 빌드 호환을 위해 비워두었습니다.

로컬 환경변수를 설정합니다.

```bash
export GONGSIL_ID="your_gongsil_id"
export GONGSIL_PASSWORD="your_gongsil_password"
export GONGSIL_DB="data/gongsil.sqlite3"
export DASHBOARD_USER="admin"
export DASHBOARD_PASSWORD="change_this_password"
export GONGSIL_GEOCODE_DELAY_SECONDS="1.0"
export GONGSIL_COLLECTION_DISTRICTS="강남구"
export GONGSIL_COMPLEX_NAMES="삼성롯데캐슬클라쎄,현대위버포레,선릉LG에클라트,현대썬앤빌삼성역,삼성파크엘나인,대치3차아이파크,대치2차아이파크,대치트레비스타,코업레지던스,역삼역센트럴아이파크시티,리에바움,강남헤븐리치더써밋761,역삼노블루체언주"
export KAKAO_REST_API_KEY=""
export TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
export TELEGRAM_CHAT_ID="your_telegram_chat_id"
export TELEGRAM_TOPIC_ID="your_topic_id"
```

## 오피스텔 매물 수집

기본값은 관심 단지 목록만 수집합니다. 현재 기본 관심 단지는 아래 5개입니다.

- 삼성롯데캐슬클라쎄
- 현대위버포레
- 선릉LG에클라트
- 현대썬앤빌삼성역
- 삼성파크엘나인
- 대치3차아이파크
- 대치2차아이파크
- 대치트레비스타
- 코업레지던스
- 역삼역센트럴아이파크시티
- 리에바움
- 강남헤븐리치더써밋761
- 역삼노블루체언주

관심 단지를 기본 설정대로 수집합니다.

```bash
python3 scripts/collect_officetels.py --max-pages 1
```

상세 페이지 수집 없이 목록만 빠르게 확인하려면:

```bash
python3 scripts/collect_officetels.py --max-pages 1 --no-details
```

특정 단지만 임시로 수집하려면:

```bash
python3 scripts/collect_officetels.py --complex-name 삼성롯데캐슬클라쎄 --max-pages 1
```

특정 구만 수집하려면:

```bash
python3 scripts/collect_officetels.py --district 강남구 --max-pages 2
python3 scripts/collect_officetels.py --district 서초구 --max-pages 2
```

강남구/서초구 전체를 모두 검색하려면:

```bash
python3 scripts/collect_officetels.py --all-districts --max-pages 1
```

수집 직후 텔레그램 알림까지 보내려면:

```bash
python3 scripts/collect_officetels.py --max-pages 2 --notify
```

기존 저장 매물에 좌표를 채우려면:

```bash
python3 scripts/geocode_listings.py --limit 100
```

저장된 미발송 이벤트만 별도로 텔레그램 전송하려면:

```bash
python3 scripts/notify_telegram.py
```

## 대시보드 실행

```bash
python3 scripts/run_dashboard.py
```

브라우저에서 아래 주소를 엽니다. 대시보드 안에서 `지금 다시 검색` 버튼으로 재수집도 바로 실행할 수 있습니다.

```text
http://127.0.0.1:8000
```

## Render 배포

이 프로젝트는 Render Web Service로 배포할 수 있습니다. `render.yaml`은 아래 구성을 기준으로 준비되어 있습니다.

- Python Web Service
- 인스턴스 타입: Free
- 무료 배포용 SQLite DB: `/tmp/gongsil.sqlite3`
- 시작 명령: `python3 scripts/run_dashboard.py`
- 외부 접속 보호: `DASHBOARD_USER`, `DASHBOARD_PASSWORD`

Render에서 배포할 때 필요한 환경변수:

```text
HOST=0.0.0.0
GONGSIL_DB=/tmp/gongsil.sqlite3
GONGSIL_ID=your_gongsil_id
GONGSIL_PASSWORD=your_gongsil_password
DASHBOARD_USER=admin
DASHBOARD_PASSWORD=strong_private_password
GONGSIL_COLLECTION_DISTRICTS=강남구
```

선택 환경변수:

```text
KAKAO_REST_API_KEY=your_kakao_key
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
```

배포 후 처음에는 DB가 비어 있으므로 Render Shell 또는 수동 Job에서 한 번 수집을 실행합니다.

```bash
python3 scripts/collect_officetels.py --max-pages 1
```

주의: Render에 외부 URL이 생기므로 `DASHBOARD_PASSWORD`는 반드시 설정하세요. 설정하지 않으면 URL을 아는 사람이 화면을 볼 수 있습니다.

무료 플랜에서 `/tmp/gongsil.sqlite3`를 쓰면 재배포/재시작 때 DB가 초기화될 수 있습니다. 나중에 데이터 보존이 필요하면 Render Disk가 지원되는 플랜으로 바꾸거나 PostgreSQL/Supabase로 옮기면 됩니다.

## 데이터베이스

기본 DB 경로는 `data/gongsil.sqlite3`입니다.

주요 테이블:

- `listings`: 매물 목록/상세 데이터
- `collection_runs`: 수집 실행 로그
- `search_profiles`: 저장한 검색 조건
- `listing_events`: 신규 매물 / 가격 변경 이벤트
- `notification_logs`: 알림 발송 기록

위치 검색 정확도를 높이려면 `KAKAO_REST_API_KEY`를 넣는 것을 권장합니다. 키가 없으면 기본적으로 Nominatim(OpenStreetMap)으로 지오코딩합니다.

## 기존 스크립트

`recruit_dry_run.py`는 기존 구인게시판 드라이런 스크립트입니다. 이번 오피스텔 MVP와 독립적으로 유지됩니다.

## 다음 구현 순서

1. 수집 스케줄러 추가
2. 조건별 알림 이력 / 읽음 상태 추가
3. 상세 페이지 기반 옵션/주차/입주일 필터 확장
4. 이메일 알림 채널 추가
5. 내부 운영 안정화
