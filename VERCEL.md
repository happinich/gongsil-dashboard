# Vercel 배포

이 프로젝트는 Vercel Python Function으로 배포할 수 있습니다.

Vercel은 장시간 실행 서버가 아니라 요청마다 실행되는 서버리스 환경입니다. 그래서 로컬의 `scripts/run_dashboard.py`를 그대로 실행하지 않고, `api/index.py`를 통해 기존 대시보드 핸들러를 Vercel Function으로 연결합니다.

## 배포 구조

- Vercel 진입점: `api/index.py`
- 라우팅 설정: `vercel.json`
- 런타임 SQLite 경로: `/tmp/gongsil.sqlite3`
- 로컬 DB/민감 파일 업로드 방지: `.vercelignore`

## Vercel 환경변수

Vercel 프로젝트의 Settings > Environment Variables에 아래 값을 넣습니다.

```text
GONGSIL_DB=/tmp/gongsil.sqlite3
GONGSIL_ID=your_gongsil_id
GONGSIL_PASSWORD=your_gongsil_password
DASHBOARD_USER=admin
DASHBOARD_PASSWORD=strong_private_password
GONGSIL_COLLECTION_DISTRICTS=강남구
```

`DASHBOARD_PASSWORD`는 반드시 설정하세요. 설정하지 않으면 Vercel URL을 아는 사람이 화면을 볼 수 있습니다.

## 배포 방법

GitHub에 push한 뒤 Vercel에서 이 저장소를 Import 합니다.

- Framework Preset: Other
- Build Command: 비워둠
- Output Directory: 비워둠
- Install Command: 기본값 사용 또는 비워둠

Vercel Python 런타임은 `/api/index.py`의 `handler` 클래스를 서버리스 함수로 인식합니다.

## 중요한 제한

Vercel의 `/tmp`는 임시 저장소입니다. 재배포, 콜드 스타트, 함수 인스턴스 교체 이후 DB가 비어 보일 수 있습니다.

따라서 Vercel 방식은 우선 화면 배포와 간단한 확인용으로 쓰고, 매물 데이터를 안정적으로 보존하려면 다음 단계에서 Supabase/PostgreSQL 같은 외부 DB로 옮기는 것이 좋습니다.

## 의존성 메모

Vercel 배포용 `requirements.txt`는 비워둡니다. 대시보드는 표준 라이브러리만 사용하므로 별도 패키지가 필요 없습니다. Playwright가 필요한 실험/드라이런 스크립트는 `requirements-dev.txt`로 따로 관리합니다.
