"""MinIO client utilities for file storage."""

import io
import logging
import os
from typing import Optional, BinaryIO
from urllib.parse import urlparse
from datetime import timedelta

from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)

class MinIOClient:
    """MinIO client wrapper for file operations."""

    def __init__(self):
        """Initialize MinIO client from environment variables."""
        # Parse main endpoint to extract host:port and determine if secure
        endpoint_raw = os.environ.get('MINIO_ENDPOINT', "minio:9000")
        self.endpoint, self.secure = self._parse_endpoint(endpoint_raw)
        
        # Parse public endpoint to extract host:port and determine if secure
        public_endpoint_raw = os.environ.get('MINIO_PUBLIC_ENDPOINT', endpoint_raw)
        self.public_endpoint, self.public_secure = self._parse_endpoint(public_endpoint_raw)
        
        # Store credentials for later use
        self.access_key = os.environ.get('MINIO_ACCESS_KEY', "minioadmin")
        self.secret_key = os.environ.get('MINIO_SECRET_KEY', "minioadmin")
        self.region = os.environ.get('MINIO_REGION', "us-east-1")
        
        self.client = Minio(
            endpoint=self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure,
            region=self.region
        )
        self.bucket = os.environ.get('MINIO_BUCKET', "trs-files")
        self._ensure_bucket()

    def _parse_endpoint(self, endpoint_url: str) -> tuple[str, bool]:
        """Parse endpoint URL to extract host:port and determine if secure."""
        if endpoint_url.startswith(('http://', 'https://')):
            parsed = urlparse(endpoint_url)
            secure = parsed.scheme == 'https'
            # Extract host:port and path
            path = parsed.path.rstrip('/')
            endpoint = parsed.netloc + path
            return endpoint, secure
        else:
            # Assume it's already in host:port format
            return endpoint_url, False

    def _ensure_bucket(self):
        """Create bucket if it doesn't exist."""
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
                logger.info(f"Created MinIO bucket: {self.bucket}")
        except S3Error as e:
            logger.error(f"Failed to create bucket {self.bucket}: {e}")
            raise

    def upload_file(self, object_name: str, file_content: str | bytes,
                   content_type: str = "text/plain") -> str:
        """Upload file content to MinIO."""
        try:
            if isinstance(file_content, str):
                file_content = file_content.encode('utf-8')

            data = io.BytesIO(file_content)
            self.client.put_object(
                bucket_name=self.bucket,
                object_name=object_name,
                data=data,
                length=len(file_content),
                content_type=content_type
            )
            logger.info(f"Uploaded file to MinIO: {object_name}")
            return object_name
        except S3Error as e:
            logger.error(f"Failed to upload file {object_name}: {e}")
            raise

    def get_presigned_url(self, object_name: str) -> str:
        """Generate a presigned URL to download a file."""
        try:
            print(f"Public endpoint: {self.public_endpoint}")
            print(f"Endpoint: {self.endpoint}")
            # Create a separate client with the public endpoint for presigned URLs
            # This ensures the signature is calculated with the correct host
            public_client = Minio(
                endpoint=self.public_endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.public_secure,
                region=self.region
            )
            
            presigned_url = public_client.presigned_get_object(
                bucket_name=self.bucket,
                object_name=object_name,
                expires=timedelta(hours=1)
            )
            return presigned_url
        except S3Error as e:
            logger.error(f"Failed to generate presigned URL for {object_name}: {e}")
            raise
    
    def download_file(self, object_name: str) -> bytes:
        """Download file content from MinIO."""
        try:
            response = self.client.get_object(self.bucket, object_name)
            content = response.read()
            response.close()
            response.release_conn()
            return content
        except S3Error as e:
            logger.error(f"Failed to download file {object_name}: {e}")
            raise

    def delete_file(self, object_name: str) -> bool:
        """Delete file from MinIO."""
        try:
            self.client.remove_object(self.bucket, object_name)
            logger.info(f"Deleted file from MinIO: {object_name}")
            return True
        except S3Error as e:
            logger.error(f"Failed to delete file {object_name}: {e}")
            return False

    def file_exists(self, object_name: str) -> bool:
        """Check if file exists in MinIO."""
        try:
            self.client.stat_object(self.bucket, object_name)
            return True
        except S3Error:
            return False
