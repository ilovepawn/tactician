-- 003_unique_game_ply.sql
-- Enforce dedup at the schema level. The batch writer relies on
-- is_seen(game_id) to skip whole games, but that races on re-runs
-- against the same PGN dump (e.g. replay testing) and silently
-- duplicates puzzles. (game_id, ply) is the natural puzzle key.

ALTER TABLE puzzle
  ADD UNIQUE KEY uk_game_ply (game_id, ply);
