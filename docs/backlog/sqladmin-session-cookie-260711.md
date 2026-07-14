# sqladmin 세션 쿠키 하드닝

- **심각도**: 중간 (보안)
- **출처**: 2026-07-11 security-auditor 점검

## 문제

sqladmin이 장착하는 `SessionMiddleware`가 기본값 — `https_only=False`(Secure 플래그 없음), `max_age` 14일. 어드민이 `http://` 주소로 한 번이라도 요청하면 세션 쿠키가 평문 전송될 수 있고, admin JWT(8h)와 달리 세션은 2주간 유효.

- 위치: `vivacapi/main.py:63-68`, `vivacapi/admin/auth.py`

## 수정 방향

`AdminAuth` 초기화에서 middleware override:

```python
self.middlewares = [
    Middleware(
        SessionMiddleware,
        secret_key=...,
        https_only=True,
        same_site="strict",
        max_age=8 * 3600,
    )
]
```

## 프론트 영향

없음. 어드민 사용자 재로그인 주기만 14일 → 8시간.
