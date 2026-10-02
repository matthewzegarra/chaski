"""KYC image storage: Azure Blob (Managed Identity) when configured, local volume otherwise."""

from __future__ import annotations

from pathlib import Path

from core_api.settings import get_settings


def save_kyc_image(name: str, data: bytes, content_type: str) -> str:
    settings = get_settings()
    if settings.blob_account_url:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient, ContentSettings

        client = BlobServiceClient(settings.blob_account_url, credential=DefaultAzureCredential())
        client.get_blob_client(settings.blob_container, name).upload_blob(
            data, overwrite=True, content_settings=ContentSettings(content_type=content_type)
        )
        return f"blob://{settings.blob_container}/{name}"
    path = Path(settings.uploads_dir) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return f"file://{name}"
