-- 001_init.sql
-- Initial schema for tactician-generator puzzle service.

CREATE TABLE puzzle (
  id                 BIGINT AUTO_INCREMENT PRIMARY KEY,
  game_id            VARCHAR(64) NOT NULL,
  fen                VARCHAR(100) COLLATE utf8mb4_bin NOT NULL,
  ply                INT NOT NULL,
  moves              VARCHAR(255) NOT NULL,
  cp                 INT NOT NULL,
  generator_version  INT NOT NULL,
  is_hidden          BOOLEAN NOT NULL DEFAULT FALSE,
  created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_game (game_id)
);

CREATE TABLE puzzle_theme (
  puzzle_id  BIGINT      NOT NULL,
  theme      VARCHAR(32) NOT NULL,
  PRIMARY KEY (puzzle_id, theme),
  FOREIGN KEY (puzzle_id) REFERENCES puzzle(id) ON DELETE CASCADE,
  INDEX idx_theme (theme)
);
