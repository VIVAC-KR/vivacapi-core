# vivac-console Frontend — 별도 리포 초기 세팅

> 내부 운영팀 전용 운영 콘솔. `vivacapi-core`와는 완전 독립된 GitHub 리포로 분리.
> 같은 DB를 보지만 **직접 붙지 않고** `vivacapi-core`의 `/v1/admin/*` API를 호출한다.
> 작성일: 2026-06-07
> 짝 문서: [vivac-console-backend.md](./vivac-console-backend.md)

---

## 0. 네이밍 노트
ㅇ
| 이름 | 의미 |
|---|---|
| **vivac-console** | 이 리포. 운영팀 전용 GUI |
| **`/v1/admin/*`** | 백엔드 API 경로. 권한(staff 전용) 의미를 그대로 유지. 콘솔이 호출하는 대상 |

콘솔은 어드민 API의 한 소비자다. 다른 소비자(CLI, 일회성 스크립트)도 있을 수 있다.

---

## 1. 개요

| 항목 | 값 |
|---|---|
| 리포 이름 | `vivac-console` |
| 용도 | 내부 운영팀 전용. `spots`, `spot_business_info` CRUD부터 시작 |
| 사용자 | 내부 직원만 (`@vivac.co.kr` 등 회사 도메인) |
| 배포 | Vercel (권장) 또는 자체 Lightsail |
| 도메인 | TBD (예: `console.vivac.kr` 또는 `vivac.kr/console` 서브패스) |

**중요 — 데이터 접근 정책**:
콘솔은 PostgreSQL에 직접 접속하지 않는다. 모든 읽기·쓰기는 `vivacapi-core`의 `/v1/admin/*` HTTP API를 경유한다. 이유는 짝 문서 참조 (검증·정합성·감사 일원화).

---

## 2. 기술 스택

| 영역 | 선택 | 비고 |
|---|---|---|
| 프레임워크 | **Next.js 15+ (App Router) + TypeScript** | |
| 어드민 패턴 | **Refine** (`@refinedev/core`, `@refinedev/nextjs-router`, `@refinedev/simple-rest`) | CRUD 훅·리소스 라우팅 제공. React Admin보다 가볍고 Next.js 친화 |
| UI | **shadcn/ui** + Tailwind CSS | Refine의 shadcn integration 사용 |
| 테이블 | **TanStack Table v8** | 정렬·필터·페이지네이션 |
| 폼 | **React Hook Form + Zod** | 필드 검증, `SpotAdminCreate` 스키마 미러링 |
| 인증 | **NextAuth (Auth.js v5)** + Google Provider | hd(hosted domain) 제한으로 회사 도메인만 |
| HTTP | `ky` 또는 `fetch` wrapper (Refine dataProvider에 주입) | 토큰 자동 첨부 |
| 패키지 매니저 | **pnpm** | |
| 노드 | 22 LTS | |

### 왜 Refine인가
백지부터 어드민 화면을 짜면 리스트/폼/필터/네비게이션을 매번 반복하게 됨. Refine은 "리소스" 개념으로 CRUD를 추상화하면서도 UI는 직접 고르게 해줘서 lock-in이 거의 없음. Retool 같은 로우코드와 달리 코드 리뷰·버전관리·테스트가 정상적으로 가능.

---

## 3. 리포 초기 구조

```
vivac-console/
├── README.md
├── package.json
├── pnpm-lock.yaml
├── tsconfig.json
├── next.config.ts
├── tailwind.config.ts
├── .env.local                    # 로컬 (gitignore)
├── .env.example                  # 가이드
├── .github/
│   └── workflows/
│       ├── ci.yml                # lint + typecheck + build
│       └── deploy.yml            # (옵션) Vercel/Lightsail 배포
├── src/
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── (auth)/
│   │   │   └── login/page.tsx
│   │   ├── (dashboard)/
│   │   │   ├── layout.tsx        # Refine + 사이드바
│   │   │   ├── spots/
│   │   │   │   ├── page.tsx      # 목록
│   │   │   │   ├── new/page.tsx  # 생성
│   │   │   │   └── [uid]/
│   │   │   │       ├── page.tsx  # 상세
│   │   │   │       └── edit/page.tsx
│   │   │   └── spot-business-info/
│   │   │       └── ... (동일 구조)
│   │   └── api/
│   │       └── auth/[...nextauth]/route.ts
│   ├── lib/
│   │   ├── auth.ts               # NextAuth 설정
│   │   ├── api.ts                # fetch wrapper (Bearer 자동 첨부)
│   │   └── data-provider.ts      # Refine dataProvider
│   ├── components/
│   │   └── ui/                   # shadcn/ui 생성물
│   └── types/
│       └── api.ts                # 백엔드 응답 타입
├── eslint.config.mjs
└── .prettierrc
```

---

## 4. 환경 변수 (`.env.example`)

```bash
# 백엔드 API
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/v1

# NextAuth
AUTH_SECRET=                       # `openssl rand -base64 32`
AUTH_URL=http://localhost:3000

# Google OAuth (회사 GCP 콘솔에서 발급)
AUTH_GOOGLE_ID=
AUTH_GOOGLE_SECRET=

# 회사 도메인 (한 개만 허용)
ALLOWED_EMAIL_DOMAIN=vivac.kr      # 예시 — 실제 도메인으로 변경
```

> 로컬 실행 시 `vivacapi-core` 서버를 8000 포트에 띄워둬야 함.

---

## 5. 인증 흐름

1. 사용자가 `/login` 진입 → "Google 로그인" 클릭
2. NextAuth Google Provider → Google OAuth
3. NextAuth `signIn` 콜백에서 **email 도메인 검증** (`ALLOWED_EMAIL_DOMAIN`)
   - 불일치 → 로그인 거부
4. 검증 통과 시 NextAuth가 받은 **Google ID Token**을 `vivacapi-core`의 `POST /v1/auth/google`로 전달 → 백엔드 JWT(access/refresh) 발급
5. 발급된 백엔드 JWT를 NextAuth session에 저장
6. 이후 모든 `/v1/admin/*` 호출은 fetch wrapper가 `Authorization: Bearer <jwt>` 자동 첨부
7. 백엔드 응답이 401 → refresh 시도 → 실패 시 강제 로그아웃

### NextAuth `signIn` 콜백 예시

```ts
async signIn({ account, profile }) {
  if (account?.provider !== "google") return false;
  const email = profile?.email ?? "";
  const allowed = process.env.ALLOWED_EMAIL_DOMAIN!;
  if (!email.endsWith(`@${allowed}`)) return false;
  // 백엔드 JWT 교환은 jwt 콜백에서 수행
  return true;
},
```

**중요**: 백엔드는 어드민 API에 대해 `require_staff`로 한 번 더 검증한다. 즉 회사 도메인이라도 `User.is_staff=False`이면 401/403. DB에서 직접 `is_staff=True`를 부여한 사람만 실제로 사용 가능.

---

## 6. Refine 리소스 등록 (스케치)

```ts
// src/lib/refine.tsx
const resources = [
  {
    name: "spots",
    list: "/spots",
    create: "/spots/new",
    edit: "/spots/:id/edit",
    show: "/spots/:id",
    meta: { label: "스팟" },
  },
  {
    name: "spot-business-info",
    list: "/spot-business-info",
    create: "/spot-business-info/new",
    edit: "/spot-business-info/:id/edit",
    show: "/spot-business-info/:id",
    meta: { label: "사업자 정보" },
  },
];
```

Refine dataProvider는 `@refinedev/simple-rest`를 백엔드 응답 포맷에 맞게 살짝 감싼다:

- list 응답: `{ items, total, offset, limit }` → Refine은 `{ data, total }` 기대 → 매핑
- id 필드는 `uid` → dataProvider에서 `getOne`/`update`/`delete` 시 `uid`로 라우팅

---

## 7. 필드 매핑 (1차 범위)

### Spot — 목록 컬럼

| 컬럼 | 비고 |
|---|---|
| title | 클릭 시 상세 이동 |
| source | 배지 |
| region_province / region_city | 합쳐서 한 컬럼 |
| rating_avg | 소수 1자리 |
| review_count | |
| updated_at | 상대 시간 (e.g. "3일 전") |
| actions | edit / delete |

### Spot — 폼 필드 (편집·생성 공통)

`SpotAdminCreate` 스키마 그대로. 그룹화:

- **기본 정보**: title, tagline, description, phone, website_url, booking_url
- **주소**: address, address_detail, region_province, region_city, postal_code
- **좌표**: latitude, longitude, altitude
- **운영 정보**: unit_count, is_fee_required, is_pet_allowed, pet_policy
- **시설**: has_equipment_rental(다중), themes(다중), fire_pit_type, amenities(다중), nearby_facilities(다중), camp_sight_type
- **메타**: source, external_id, category(다중), features
- **수치**: total_area_m2, has_liability_insurance
- **읽기 전용**: uid, created_at, updated_at, rating_avg, review_count

### SpotBusinessInfo — 목록 컬럼

| 컬럼 | 비고 |
|---|---|
| spot (title) | spot_uid → 백엔드에서 title 함께 내려주거나 별도 호출 |
| business_reg_no | |
| operating_status | 배지 |
| operating_agency | |
| licensed_at | |
| updated_at | |

폼 필드는 `SpotBusinessInfo` 모델 그대로. `spot_uid`는 셀렉트(spots 검색).

---

## 8. 작업 단계 (단계별 verify 포함)

1. **리포 생성 & 기본 세팅**
   `pnpm create next-app vivac-console --typescript --tailwind --app --eslint --src-dir`
   → verify: `pnpm dev`로 빈 페이지 뜸
2. **의존성 추가**: `refine`, `shadcn/ui`, `next-auth@beta`, `react-hook-form`, `zod`, `@tanstack/react-table`
   → verify: typecheck 통과
3. **NextAuth + Google + 도메인 제한**
   → verify: 회사 도메인 계정 로그인 성공, 외부 도메인 거부
4. **백엔드 JWT 교환 로직**
   → verify: 로그인 후 `/v1/admin/spots` GET이 401 없이 200 반환
5. **Refine + dataProvider + 리소스 등록**
   → verify: `/spots` 페이지에서 목록이 백엔드 데이터로 채워짐
6. **Spot 목록 → 상세 → 편집 흐름**
   → verify: 필드 수정 → 저장 → 백엔드에 반영 확인 → 목록 갱신
7. **Spot 생성 / 삭제**
   → verify: 새 spot 생성 후 목록에 노출, 삭제 후 사라짐
8. **SpotBusinessInfo 동일 흐름**
   → verify: 위와 동일 + `spot_uid` 셀렉트가 정상 작동
9. **에러 처리 UX**: 422 검증 에러를 필드 단위로 표시
   → verify: 일부러 잘못된 값 입력 시 인라인 에러
10. **CI 세팅**: GitHub Actions — lint + typecheck + build
    → verify: PR에서 그린 체크

---

## 9. 배포 (1차)

**옵션 A — Vercel** (권장 초기)
- Next.js 자체. zero-config
- 환경변수는 Vercel 프로젝트 설정
- Preview deploy로 PR 단위 확인 가능
- 내부 전용이라면 Vercel password protection 또는 Cloudflare Access로 한 겹 더 보호 고려

**옵션 B — 기존 Lightsail에 함께 호스팅**
- `vivacapi-core`와 같은 인스턴스에 Docker로 띄움
- Nginx로 `console.vivac.kr` 또는 `vivac.kr/console` 라우팅
- 비용 절감, 인프라 단순화

운영 도메인 결정 전까지는 Vercel preview만으로 충분.

---

## 10. 보안 체크리스트

- [ ] Google OAuth에서 hd(hosted domain) 제한 또는 signIn 콜백에서 email 도메인 검증
- [ ] 백엔드 `is_staff=True`인 유저만 콘솔에서 실제 동작 (UI 통과해도 백엔드가 막음)
- [ ] `AUTH_SECRET`은 환경별 분리, 절대 커밋 금지
- [ ] CORS — `vivacapi-core`의 `CORS_ALLOWED_ORIGINS`에 콘솔 도메인 추가
- [ ] 운영 도메인은 HTTPS only
- [ ] CSP 헤더 (`script-src 'self'` 등) — Next.js middleware
- [ ] (선택) Cloudflare Access 또는 Vercel password protection으로 한 겹 더

---

## 11. 후속(이 프로젝트 범위 밖)

- spot 외 리소스 (user, spot_review, job 모니터링)
- 대시보드 / 통계 페이지
- 파일·이미지 업로드 UI
- 변경 이력 뷰 (백엔드 audit log 도입 후)
- 역할 기반 권한(어드민 등급)

---

## 12. 백엔드 API 사전 요구사항

이 프론트 작업을 시작하려면 짝 문서의 백엔드 작업이 최소한 다음까지는 끝나 있어야 한다:

- [ ] `/v1/admin/spots` GET (목록 + 상세)
- [ ] `/v1/admin/spots` POST / PATCH / DELETE
- [ ] CORS에 `http://localhost:3000` 허용

`spot-business-info` 라우터는 spot 라우터 직후에 작업하면 됨.
