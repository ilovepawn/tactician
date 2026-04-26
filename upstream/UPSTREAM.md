# Upstream Source

This directory contains code vendored from Lichess's puzzle generator.

- **Source**: https://github.com/ornicar/lichess-puzzler
- **License**: AGPL-3.0 (see `LICENSE.upstream`)
- **Author**: Thibault Duplessis (ornicar)
- **Vendored commit**: `c188837cd2411d5c17d4f33c59ac38a8722d694f`
- **Vendored at**: 2026-04-26

## Components

- `generator/` — Python pipeline that reads PGN with `%eval` annotations, runs Stockfish, produces puzzle candidates.
- `tagger/` — Python theme classifier (~60 themes including `fork`, `pin`, `mateInN`, `zugzwang`, etc.).

## Modification Policy

This vendored code should be modified **as little as possible**. Adapters live outside this directory (`src/`) and replace I/O boundaries (DB, storage) without touching core chess logic.

## Updating

To pull a newer upstream snapshot:

```bash
git clone --depth 1 https://github.com/ornicar/lichess-puzzler /tmp/lichess-puzzler-src
rm -rf upstream/generator upstream/tagger
cp -r /tmp/lichess-puzzler-src/{generator,tagger} upstream/
# Update the commit hash and date in this file
```
