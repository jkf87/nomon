---
name: nomon
description: "Rubric-first evaluation harness. Define what good looks like before writing. verifier → writer, not the other way."
---

# /nomon

Nomon — 노몬. 해시계 바늘처럼, 무엇을 측정할지 먼저 세운다.
rubric 없이는 시작하지 않는다. verifier가 먼저다.

## Usage

### `/nomon:setup`
설치 및 환경 초기화. 멱등.

### `/nomon:rubric`
새 작업의 rubric.yaml을 정의한다. 각 항목에 측정방법 라벨 필수: [정량 / 페르소나-LLM / 사람]
LLM 100%면 진입 차단.
**Example:** `/nomon:rubric "카드뉴스 10장 생성"`

### `/nomon:verify-check`
verifier dry-run. dummy input으로 PASS/FAIL 신호가 실제로 떨어지는지 먼저 검증.
**Example:** `/nomon:verify-check rubric.yaml`

### `/nomon:run`
rubric.yaml이 있고 verify-check 통과 후에만 진입 가능.
writer가 verifier를 통과할 때까지 루프.
**Example:** `/nomon:run rubric.yaml`

### `/nomon:calibrate`
결과물 N건 직접 채점 vs LLM 채점 상관계수 계산.
0.7 미만이면 rubric 개선 요청.
**Example:** `/nomon:calibrate rubric.yaml --samples 5`

### `/nomon:status`
실행 상태 확인.

### `/nomon:cancel`
실행 중지.

---

## Rubric.yaml 포맷

```yaml
task: "카드뉴스 10장 생성"
persona: "25-35세 직장인"
criteria:
  - name: "폰트 크기"
    measurement: "정량"
    spec: "모든 텍스트 >= 24pt"
  - name: "이해도"
    measurement: "페르소나-LLM"
    spec: "페르소나가 5초 안에 핵심 요약 가능"
  - name: "이미지 연관성"
    measurement: "사람"
    spec: "내용 톤과 이미지 톤 일치"
taste_residue_gate: 0.7  # 상관계수 임계값
```

LLM-only 항목이 전체의 70% 초과 시 경고.
