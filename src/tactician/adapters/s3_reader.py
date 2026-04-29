"""S3/MinIO adapter that downloads annotated PGN files for a target date.

Files are expected at: s3://<bucket>/<YYYY>/<MM>/<DD>/<gameId>.pgn
This module lists objects under the date prefix, downloads each, concatenates
them and compresses the result to a single .pgn.zst file ready for the
upstream generator (which natively reads .zst input).
"""
import logging
import tempfile
from datetime import date
from pathlib import Path

import boto3
import zstandard

from tactician.config import S3Config


def download_pgn_for_date(
    logger: logging.Logger, s3_config: S3Config, target_date: date
) -> tuple[Path, int]:
    s3 = boto3.client(
        "s3",
        endpoint_url=s3_config.endpoint_url,
        aws_access_key_id=s3_config.access_key,
        aws_secret_access_key=s3_config.secret_key,
        region_name="us-east-1",
    )

    prefix = target_date.strftime("%Y/%m/%d/")
    paginator = s3.get_paginator("list_objects_v2")

    out_file = Path(tempfile.mktemp(suffix=".pgn.zst"))
    cctx = zstandard.ZstdCompressor()
    count = 0
    with out_file.open("wb") as raw:
        with cctx.stream_writer(raw) as compressor:
            for page in paginator.paginate(Bucket=s3_config.bucket_games, Prefix=prefix):
                for obj in page.get("Contents", []) or []:
                    key = obj["Key"]
                    if not key.endswith(".pgn"):
                        continue
                    response = s3.get_object(Bucket=s3_config.bucket_games, Key=key)
                    compressor.write(response["Body"].read())
                    compressor.write(b"\n\n")
                    count += 1

    logger.info(f"downloaded {count} PGN files for {target_date} into {out_file}")
    return out_file, count
