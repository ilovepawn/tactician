import os
from dataclasses import dataclass


@dataclass(frozen=True)
class MySQLConfig:
    host: str
    port: int
    user: str
    password: str
    database: str


@dataclass(frozen=True)
class S3Config:
    endpoint_url: str
    access_key: str
    secret_key: str
    bucket_games: str


@dataclass(frozen=True)
class StockfishConfig:
    path: str
    threads: int


@dataclass(frozen=True)
class Config:
    mysql: MySQLConfig
    s3: S3Config
    stockfish: StockfishConfig
    pushgateway_url: str | None = None


def load_config() -> Config:
    return Config(
        mysql=MySQLConfig(
            host=os.environ["MYSQL_HOST"],
            port=int(os.environ["MYSQL_PORT"]),
            user=os.environ["MYSQL_USER"],
            password=os.environ["MYSQL_PASSWORD"],
            database=os.environ["MYSQL_DATABASE"],
        ),
        s3=S3Config(
            endpoint_url=os.environ["S3_ENDPOINT_URL"],
            access_key=os.environ["S3_ACCESS_KEY"],
            secret_key=os.environ["S3_SECRET_KEY"],
            bucket_games=os.environ["S3_BUCKET_GAMES"],
        ),
        stockfish=StockfishConfig(
            path=os.environ["STOCKFISH_PATH"],
            threads=int(os.environ["STOCKFISH_THREADS"]),
        ),
        pushgateway_url=os.environ.get("PUSHGATEWAY_URL") or None,
    )
