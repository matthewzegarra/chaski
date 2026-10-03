"""Data lake writer: ADLS Gen2 with the job's managed identity in Azure, a local folder
otherwise (LAKE_DIR, for local runs and tests). Containers: bronze, silver, quarantine."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol


class Lake(Protocol):
    def put(self, container: str, path: str, data: bytes, content_type: str) -> str: ...


class LocalLake:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def put(self, container: str, path: str, data: bytes, content_type: str) -> str:
        target = self.root / container / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return f"{container}/{path}"


class AdlsLake:
    def __init__(self, account_url: str) -> None:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient

        self.client = BlobServiceClient(account_url, credential=DefaultAzureCredential())

    def put(self, container: str, path: str, data: bytes, content_type: str) -> str:
        from azure.storage.blob import ContentSettings

        self.client.get_blob_client(container, path).upload_blob(
            data, overwrite=True, content_settings=ContentSettings(content_type=content_type)
        )
        return f"{container}/{path}"


def get_lake() -> Lake | None:
    if url := os.environ.get("BLOB_ACCOUNT_URL"):
        return AdlsLake(url)
    if root := os.environ.get("LAKE_DIR"):
        return LocalLake(root)
    return None
