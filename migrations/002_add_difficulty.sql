-- 002_add_difficulty.sql
-- Add difficulty column to puzzle. Default 0 (unset/easiest); rating
-- algorithm to be wired in later — for now the batch writer relies on
-- this default and does not set the value explicitly.

ALTER TABLE puzzle
  ADD COLUMN difficulty INT NOT NULL DEFAULT 0;
