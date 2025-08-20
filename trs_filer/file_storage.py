"""File storage strategy manager."""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from flask import current_app
import uuid
import os

from trs_filer.minio_client import MinIOClient

logger = logging.getLogger(__name__)

class FileStorageStrategy(ABC):
    """Abstract base class for file storage strategies."""

    @abstractmethod
    def store_file(self, file_content: str | bytes, file_path: str,
                  file_type: str) -> Dict[str, Any]:
        """Store file and return file wrapper data."""
        pass

    @abstractmethod
    def retrieve_file_content(self, file_wrapper: Dict[str, Any]) -> bytes:
        """Retrieve file content from storage."""
        pass

    @abstractmethod
    def get_file_url(self, file_wrapper: Dict[str, Any]) -> Optional[str]:
        """Get a downloadable URL for the file."""
        pass

    @abstractmethod
    def delete_file(self, file_wrapper: Dict[str, Any]) -> bool:
        """Delete file from storage."""
        pass

class MongoDBStorage(FileStorageStrategy):
    """Store files directly in MongoDB."""

    def store_file(self, file_content: str | bytes, file_path: str,
                  file_type: str) -> Dict[str, Any]:
        """Store file content directly in the file wrapper."""
        if isinstance(file_content, bytes):
            file_content = file_content.decode('utf-8')
        return {"content": file_content}

    def retrieve_file_content(self, file_wrapper: Dict[str, Any]) -> bytes:
        """Retrieve file content from the file wrapper."""
        content = file_wrapper.get("content", "")
        return content.encode('utf-8')

    def get_file_url(self, file_wrapper: Dict[str, Any]) -> Optional[str]:
        """Return None as MongoDB storage does not provide external URLs."""
        return None

    def delete_file(self, file_wrapper: Dict[str, Any]) -> bool:
        """No action needed; content is deleted with the parent document."""
        return True

class MinIOStorage(FileStorageStrategy):
    """Store files in MinIO object storage."""

    def __init__(self):
        """Initialize MinIO client."""
        self.minio_client = MinIOClient()

    def store_file(self, file_content: str | bytes, file_path: str,
                  file_type: str) -> Dict[str, Any]:
        """Store file in MinIO and return metadata."""
        object_name = f"{uuid.uuid4()}/{file_path}"
        self.minio_client.upload_file(
            object_name=object_name,
            file_content=file_content,
            content_type=self._get_content_type(file_type)
        )
        return {"minio_path": object_name}

    def retrieve_file_content(self, file_wrapper: Dict[str, Any]) -> bytes:
        """Retrieve file content from MinIO."""
        object_name = file_wrapper.get("minio_path")
        if not object_name:
            raise ValueError("No MinIO path specified in file wrapper")
        return self.minio_client.download_file(object_name)

    def get_file_url(self, file_wrapper: Dict[str, Any]) -> Optional[str]:
        """Get a presigned URL for the file from MinIO."""
        object_name = file_wrapper.get("minio_path")
        if not object_name:
            return None
        return self.minio_client.get_presigned_url(object_name)

    def delete_file(self, file_wrapper: Dict[str, Any]) -> bool:
        """Delete file from MinIO."""
        object_name = file_wrapper.get("minio_path")
        if not object_name:
            return False
        return self.minio_client.delete_file(object_name)

    def _get_content_type(self, file_type: str) -> str:
        """Get content type based on file type."""
        content_types = {
            "PRIMARY_DESCRIPTOR": "text/plain",
            "SECONDARY_DESCRIPTOR": "text/plain",
            "TEST_FILE": "application/json",
            "CONTAINERFILE": "text/plain",
            "OTHER": "application/octet-stream"
        }
        return content_types.get(file_type, "application/octet-stream")

class FileStorageManager:
    """Manager for file storage strategies."""

    def __init__(self):
        """Initialize storage manager."""
        strategy = os.environ.get('FILE_STORAGE_STRATEGY', 'minio')
        if strategy == "minio":
            self.strategy = MinIOStorage()
        elif strategy == "mongodb":
            self.strategy = MongoDBStorage()
        else:
            raise ValueError(f"Unsupported file storage strategy: {strategy}")

    def store_file(self, file_content: str | bytes, file_path: str,
                  file_type: str) -> Dict[str, Any]:
        """Store file using configured strategy."""
        return self.strategy.store_file(file_content, file_path, file_type)

    def retrieve_file_content(self, file_wrapper: Dict[str, Any]) -> bytes:
        """Retrieve file content using configured strategy."""
        return self.strategy.retrieve_file_content(file_wrapper)

    def get_file_url(self, file_wrapper: Dict[str, Any]) -> Optional[str]:
        """Get a file URL using the configured strategy."""
        return self.strategy.get_file_url(file_wrapper)

    def delete_file(self, file_wrapper: Dict[str, Any]) -> bool:
        """Delete file using configured strategy."""
        return self.strategy.delete_file(file_wrapper)
