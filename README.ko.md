# Tactician

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![MySQL](https://img.shields.io/badge/MySQL-8.4-4479A1?logo=mysql&logoColor=white)](https://www.mysql.com/)
[![MinIO](https://img.shields.io/badge/MinIO-S3--Compatible-C72E49?logo=minio&logoColor=white)](https://min.io/)
[![Stockfish](https://img.shields.io/badge/Stockfish-18-000000?logo=lichess&logoColor=white)](https://stockfishchess.org/)
[![License](https://img.shields.io/badge/License-AGPL--3.0--or--later-blue)](LICENSE)

[English](README.md)

> *택티션 (Tactician)* — 형세를 결정짓는 한 수를 찾아내는 전술가.

[ilovepawn](https://github.com/ilovepawn) 체스 플랫폼의 **퍼즐 서비스**. 플랫폼 내 게임에서 전술 퍼즐을 자동으로 추출해 사용자에게 제공합니다.

모든 퍼즐은 실제 게임에서 Stockfish가 직접 발굴 — 수작업 큐레이션 없이, 블런더를 잡아내고 결정타를 가하세요.

---

## 동작 방식

1. 사용자가 플랫폼에서 게임을 종료합니다
2. `%eval` 주석이 달린 PGN이 서비스의 S3 버킷에 쌓입니다
3. 새벽 배치가 게임을 훑으며 블런더와 강제 승리 수순을 찾아 후보 퍼즐로 추출합니다
4. 약 60개의 패턴 감지기가 각 후보에 자동으로 테마(`fork`, `pin`, `mateIn3`, `zugzwang` 등)를 부착합니다
5. 태깅 끝난 퍼즐이 MySQL에 저장되어 즉시 서비스 가능 상태가 됩니다

패턴 인식 로직은 [Lichess의 퍼즐 생성기](https://github.com/ornicar/lichess-puzzler)를 AGPL-3.0 라이선스로 그대로 가져와 사용합니다 — Lichess의 수백만 게임에서 검증된 코드입니다.

---

## 기술 스택

| 레이어 | 기술 |
|---|---|
| 체스 엔진 | Stockfish 18 (UCI) |
| 패턴 로직 | python-chess + lichess-puzzler vendored |
| 데이터베이스 | MySQL 8.4 LTS |
| 오브젝트 스토리지 | MinIO (S3 호환) |
| 패키지 매니저 | uv |
| 인프라 | Docker Compose |

---

## 시작하기

### 사전 요구사항

- Python 3.13+
- Docker & Docker Compose
- Stockfish (`brew install stockfish` on macOS)
- [uv](https://docs.astral.sh/uv/) 패키지 매니저

### 실행

```bash
# 의존성 설치
uv sync

# 환경 설정 파일 복사
cp .env.example .env

# MySQL + MinIO 시작
docker compose up -d

# DB 스키마 적용
docker exec -i tactician-db-1 mysql -u tactician -ptactician tactician < migrations/001_init.sql

# 일배치 실행 (운영 모드, S3에서 가져옴)
uv run python -m tactician.batch --date 2026-04-26

# 또는 로컬 PGN 파일로 실행 (테스트)
uv run python -m tactician.batch --file games.pgn.zst --max-games 100
```

---

## 배치 CLI

```bash
uv run python -m tactician.batch [options]
```

| 옵션 | 설명 |
|---|---|
| `--date YYYY-MM-DD` | 해당 날짜의 PGN을 S3에서 가져와 처리. 기본값은 어제. |
| `--file PATH` | 로컬 `.pgn` 또는 `.pgn.zst` 파일로 실행. S3 우회. |
| `--max-games N` | 첫 N개 게임만 처리 (테스트용). |

배치는 **다운로드 → 생성 → 태깅** 3단계를 순차 실행하며, 게임별 시간과 태깅 통계를 로깅합니다.

---

## 데이터 모델

### `puzzle`

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | BIGINT AUTO_INCREMENT | PK |
| `game_id` | VARCHAR(64) | 원본 게임 ID |
| `fen` | VARCHAR(100) `utf8mb4_bin` | 시작 포지션 (대소문자 구분) |
| `ply` | INT | 원본 게임의 반쪽 수 번호 |
| `moves` | VARCHAR(255) | 정답 수순 (UCI, 공백 구분) |
| `cp` | INT | centipawn 평가값. 메이트는 매직값. |
| `generator_version` | INT | 알고리즘 버전 |
| `is_hidden` | BOOLEAN | 숨김 플래그 |
| `created_at` | DATETIME | 생성 시각 |

### `puzzle_theme`

관계 테이블. `(puzzle_id, theme)` 복합 PK. 테마는 upstream tagger가 약 60개 fixed list 중에서 부여합니다.

---

## 프로젝트 구조

```
tactician/
├── upstream/          # Vendored lichess-puzzler (AGPL-3.0, 수정 0)
│   ├── generator/     # 퍼즐 후보 발굴
│   └── tagger/        # 테마 분류 (~60 패턴)
├── src/tactician/
│   ├── batch.py       # 일배치 진입점
│   ├── config.py      # 환경 설정
│   └── adapters/      # MySQL writer, S3 reader, tagger I/O
├── migrations/        # plain SQL 마이그레이션
├── docker-compose.yml
└── pyproject.toml
```

upstream 코드는 런타임에 `Server` 클래스를 monkey-patching해서 우리 인프라에 연결됩니다 — upstream 소스는 한 줄도 수정하지 않습니다.

---

## Attribution

Thibault Duplessis (ornicar)의 [lichess-puzzler](https://github.com/ornicar/lichess-puzzler) 코드를 가져와 사용합니다. Vendored 코드는 `upstream/` 폴더에 있으며 원본 AGPL-3.0 라이선스를 유지합니다. 정확한 커밋 해시와 업데이트 절차는 `upstream/UPSTREAM.md` 참고.

---

## 라이선스

이 프로젝트는 **AGPL-3.0-or-later 라이선스**로 배포됩니다 — 자세한 내용은 [LICENSE](LICENSE) 파일 참고.

`lichess-puzzler` (AGPL)를 vendoring하고 `python-chess` (GPL)에 의존하므로 AGPL-3.0-or-later가 강제됩니다.
