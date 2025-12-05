import os
import sys
import logging
from typing import Dict, Any
from prefect import flow, task, get_run_logger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Database configuration - use environment variables or defaults
# psycopg2 requires postgresql:// (not postgresql+psycopg2://)
_raw_db_url = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@postgres:5432/cai_data"
)
# Convert SQLAlchemy URL format to psycopg2 format if needed
if _raw_db_url.startswith("postgresql+psycopg2://"):
    DATABASE_URL = _raw_db_url.replace("postgresql+psycopg2://", "postgresql://", 1)
else:
    DATABASE_URL = _raw_db_url

# Conditional dlt import - only needed for data extraction, not for S3-to-S3 file moves
try:
    import dlt
    from dlt.sources.filesystem import filesystem, read_csv
    DLT_AVAILABLE = True
except Exception as e:
    DLT_AVAILABLE = False
    filesystem = None
    read_csv = None

import psycopg2
from psycopg2.extras import RealDictCursor
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
import s3fs
import csv
import tempfile
import io
from datetime import datetime
import os

# Configure logging for Prefect flows
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def get_s3_credentials(config: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Get S3 credentials based on storage environment.
    
    Args:
        config: Optional configuration dict with aws_access_key_id, aws_secret_access_key, etc.
    
    Returns:
        Dictionary with credentials for boto3 client
    """
    storage_env = os.getenv("STORAGE_ENVIRONMENT", "production").lower()
    
    if storage_env == "production":
        # Production: AWS S3
        return {
            "aws_access_key_id": (config.get("aws_access_key_id") if config 
                                 else os.getenv("AWS_ACCESS_KEY_ID")),
            "aws_secret_access_key": (config.get("aws_secret_access_key") if config 
                                     else os.getenv("AWS_SECRET_ACCESS_KEY")),
            "region_name": (config.get("region") if config 
                           else os.getenv("AWS_REGION", "us-east-1")),
            # No endpoint_url for AWS S3 (uses default AWS endpoints)
        }
    else:
        # Development: MinIO
        return {
            "aws_access_key_id": (config.get("aws_access_key_id") if config 
                                 else os.getenv("MINIO_ACCESS_KEY", "minioadmin")),
            "aws_secret_access_key": (config.get("aws_secret_access_key") if config 
                                     else os.getenv("MINIO_SECRET_KEY", "minioadmin")),
            "endpoint_url": (config.get("endpoint_url") if config 
                           else os.getenv("MINIO_ENDPOINT", "http://minio:9000")),
        }


def get_db_connection():
    """Create a database connection for the flow."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to connect to database with URL: {DATABASE_URL[:50]}... Error: {e}")
        raise


@task(name="read_connector_config")
def read_connector_config(connector_id: int) -> Dict[str, Any]:
    """Read connector configuration from database."""
    logger = get_run_logger()
    logger.info(f"Reading configuration for connector {connector_id}")
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Query connector with joins to get source and destination info
            cur.execute("""
                SELECT 
                    c.id, c.name, c.source_config_override, c.destination_config_override,
                    ds.config as source_base_config, dd.config as dest_base_config,
                    alc_s.lookup_code as source_type,
                    alc_d.lookup_code as dest_type
                FROM cai_connectors c
                LEFT JOIN cai_defined_sources ds ON c.defined_source_id = ds.id
                LEFT JOIN cai_defined_destinations dd ON c.defined_destination_id = dd.id
                LEFT JOIN ad_lookup_codes alc_s ON ds.source_type_lookup_code_id = alc_s.id
                LEFT JOIN ad_lookup_codes alc_d ON dd.destination_type_lookup_code_id = alc_d.id
                WHERE c.id = %s
            """, (connector_id,))
            
            row = cur.fetchone()
            if not row:
                logger.error(f"Connector {connector_id} not found")
                raise ValueError(f"Connector {connector_id} not found")
            
            # Merge base configs with overrides
            source_base = row['source_base_config'] or {}
            dest_base = row['dest_base_config'] or {}
            source_override = row['source_config_override'] or {}
            dest_override = row['destination_config_override'] or {}
            
            source_config = {**source_base, **source_override}
            destination_config = {**dest_base, **dest_override}
            
            return {
                "connector_id": connector_id,
                "connector_name": row['name'],
                "source_type": row['source_type'] or 'filesystem',
                "source_config": source_config,
                "destination_type": row['dest_type'] or 's3',
                "destination_config": destination_config,
            }
    finally:
        conn.close()


@task(name="create_run_record")
def create_run_record(connector_id: int, prefect_flow_run_id: str) -> int:
    """Create a run record in the database."""
    try:
        logger = get_run_logger()
    except:
        # Fallback if not in Prefect context
        logger = logging.getLogger(__name__)
    logger.info(f"Creating run record for connector {connector_id}, flow run {prefect_flow_run_id}")
    logger.info(f"Database URL: {DATABASE_URL[:50]}...")
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            logger.info(f"Executing INSERT for connector {connector_id}")
            cur.execute("""
                INSERT INTO cai_connector_runs (connector_id, status, prefect_flow_run_id, started_at)
                VALUES (%s, 'started', %s, NOW())
                RETURNING id
            """, (connector_id, prefect_flow_run_id))
            run_id = cur.fetchone()[0]
            conn.commit()
            logger.info(f"Successfully created run record {run_id} for connector {connector_id}")
            return run_id
    except Exception as e:
        logger.error(f"Error creating run record: {e}", exc_info=True)
        conn.rollback()
        raise
    finally:
        conn.close()


def transfer_files_function(source_config: Dict[str, Any], destination_config: Dict[str, Any], credentials: Dict[str, str], logger, destination_type: str) -> int:
    """Transfer files from S3 source to various destination types (S3, SFTP, NFS, REST API, etc.).
    
    This is a regular function (not a task) to allow calling from within tasks.
    """
    if destination_type == "s3":
        return move_processed_files_function(source_config, destination_config, credentials, logger)
    elif destination_type == "sftp":
        return transfer_to_sftp_function(source_config, destination_config, credentials, logger)
    elif destination_type in ["nfs", "filesystem"]:
        return transfer_to_filesystem_function(source_config, destination_config, credentials, logger)
    elif destination_type == "rest_api":
        return transfer_to_rest_api_function(source_config, destination_config, credentials, logger)
    else:
        logger.error(f"Unsupported destination type for file transfer: {destination_type}")
        return 0


def move_processed_files_function(source_config: Dict[str, Any], destination_config: Dict[str, Any], credentials: Dict[str, str], logger) -> int:
    """Move processed files from source folder to processed folder in S3."""
    try:
        import boto3
        from botocore.config import Config
        
        # Get credentials (prefer source_config, then passed credentials, then environment)
        creds = get_s3_credentials(source_config) if source_config else credentials
        
        # Build boto3 client arguments
        client_kwargs = {
            'service_name': 's3',
            'config': Config(signature_version='s3v4')
        }
        
        # Add credentials
        if creds.get('aws_access_key_id'):
            client_kwargs['aws_access_key_id'] = creds['aws_access_key_id']
        if creds.get('aws_secret_access_key'):
            client_kwargs['aws_secret_access_key'] = creds['aws_secret_access_key']
        if creds.get('region_name'):
            client_kwargs['region_name'] = creds['region_name']
        if creds.get('endpoint_url'):
            client_kwargs['endpoint_url'] = creds['endpoint_url']
        
        # Create S3 client
        s3_client = boto3.client(**client_kwargs)
        
        source_bucket = source_config.get("bucket")
        source_path = source_config.get("path", "").rstrip('/')
        file_pattern = source_config.get("file_pattern", "*")
        
        dest_bucket = destination_config.get("bucket")
        dest_prefix = destination_config.get("prefix", "").rstrip('/')
        
        # List files in source path
        prefix = f"{source_path}/" if source_path else ""
        response = s3_client.list_objects_v2(Bucket=source_bucket, Prefix=prefix)
        
        moved_count = 0
        if 'Contents' in response:
            import fnmatch
            for obj in response['Contents']:
                file_key = obj['Key']
                file_name = file_key.split('/')[-1]
                
                # Skip if it's a directory marker
                if file_key.endswith('/'):
                    continue
                
                # Check if file matches pattern
                # Support glob patterns like *.pdf, *.csv, etc.
                matches_pattern = False
                if file_pattern == "*":
                    matches_pattern = True
                elif fnmatch.fnmatch(file_name, file_pattern):
                    matches_pattern = True
                elif fnmatch.fnmatch(file_key, f"{prefix}{file_pattern}"):
                    matches_pattern = True
                elif fnmatch.fnmatch(file_key, file_pattern):
                    matches_pattern = True
                
                if matches_pattern:
                    # Construct destination key
                    dest_key = f"{dest_prefix}/{file_name}" if dest_prefix else file_name
                    
                    # Copy file to destination
                    copy_source = {'Bucket': source_bucket, 'Key': file_key}
                    logger.info(f"Copying {file_key} to {dest_key} (pattern: {file_pattern}, file_name: {file_name})")
                    s3_client.copy_object(CopySource=copy_source, Bucket=dest_bucket, Key=dest_key)
                    
                    # Delete from source
                    s3_client.delete_object(Bucket=source_bucket, Key=file_key)
                    
                    logger.info(f"Moved {file_key} to {dest_key}")
                    moved_count += 1
                else:
                    logger.debug(f"Skipping {file_key} (pattern: {file_pattern}, file_name: {file_name})")
        
        return moved_count
    except Exception as e:
        logger.error(f"Error moving files: {str(e)}", exc_info=True)
        return 0


def transfer_to_sftp_function(source_config: Dict[str, Any], destination_config: Dict[str, Any], credentials: Dict[str, str], logger) -> int:
    """Transfer files from S3 to TrueNAS Scale via SFTP."""
    try:
        import boto3
        import paramiko
        from botocore.config import Config
        import tempfile
        import os
        
        # Get S3 client
        s3_creds = source_config.get("aws_access_key_id") or credentials.get('aws_access_key_id', 'minioadmin')
        s3_secret = source_config.get("aws_secret_access_key") or credentials.get('aws_secret_access_key', 'minioadmin')
        endpoint = source_config.get("endpoint_url") or credentials.get('endpoint_url', 'http://minio:9000')
        
        s3_client = boto3.client(
            's3',
            endpoint_url=endpoint,
            aws_access_key_id=s3_creds,
            aws_secret_access_key=s3_secret,
            config=Config(signature_version='s3v4')
        )
        
        # Get SFTP connection details
        sftp_host = destination_config.get("host", "truenas-ip")
        sftp_port = destination_config.get("port", 22)
        sftp_username = destination_config.get("username")
        sftp_password = destination_config.get("password")
        sftp_key_path = destination_config.get("pkey_path")
        sftp_dest_path = destination_config.get("path", "/")
        
        # Connect to SFTP
        transport = paramiko.Transport((sftp_host, sftp_port))
        if sftp_key_path:
            private_key = paramiko.RSAKey.from_private_key_file(sftp_key_path)
            transport.connect(username=sftp_username, pkey=private_key)
        else:
            transport.connect(username=sftp_username, password=sftp_password)
        
        sftp = paramiko.SFTPClient.from_transport(transport)
        
        # List and transfer files
        source_bucket = source_config.get("bucket")
        source_path = source_config.get("path", "").rstrip('/')
        file_pattern = source_config.get("file_pattern", "*")
        
        prefix = f"{source_path}/" if source_path else ""
        response = s3_client.list_objects_v2(Bucket=source_bucket, Prefix=prefix)
        
        transferred_count = 0
        if 'Contents' in response:
            import fnmatch
            with tempfile.TemporaryDirectory() as tmpdir:
                for obj in response['Contents']:
                    file_key = obj['Key']
                    file_name = file_key.split('/')[-1]
                    
                    if file_key.endswith('/'):
                        continue
                    
                    if fnmatch.fnmatch(file_name, file_pattern) or fnmatch.fnmatch(file_key, f"{prefix}{file_pattern}") or file_pattern == "*":
                        # Download from S3 to temp file
                        local_file = os.path.join(tmpdir, file_name)
                        s3_client.download_file(source_bucket, file_key, local_file)
                        
                        # Upload to SFTP
                        remote_path = f"{sftp_dest_path.rstrip('/')}/{file_name}"
                        sftp.put(local_file, remote_path)
                        
                        # Delete from source S3
                        s3_client.delete_object(Bucket=source_bucket, Key=file_key)
                        
                        logger.info(f"Transferred {file_key} to SFTP {remote_path}")
                        transferred_count += 1
        
        sftp.close()
        transport.close()
        return transferred_count
    except Exception as e:
        logger.error(f"Error transferring files to SFTP: {str(e)}", exc_info=True)
        return 0


def transfer_to_filesystem_function(source_config: Dict[str, Any], destination_config: Dict[str, Any], credentials: Dict[str, str], logger) -> int:
    """Transfer files from S3 to NFS/local filesystem."""
    try:
        import boto3
        from botocore.config import Config
        import shutil
        import os
        
        # Get S3 client
        s3_creds = source_config.get("aws_access_key_id") or credentials.get('aws_access_key_id', 'minioadmin')
        s3_secret = source_config.get("aws_secret_access_key") or credentials.get('aws_secret_access_key', 'minioadmin')
        endpoint = source_config.get("endpoint_url") or credentials.get('endpoint_url', 'http://minio:9000')
        
        s3_client = boto3.client(
            's3',
            endpoint_url=endpoint,
            aws_access_key_id=s3_creds,
            aws_secret_access_key=s3_secret,
            config=Config(signature_version='s3v4')
        )
        
        # Get destination path (NFS mounted or local)
        dest_path = destination_config.get("path", "/mnt/destination")
        os.makedirs(dest_path, exist_ok=True)
        
        # List and transfer files
        source_bucket = source_config.get("bucket")
        source_path = source_config.get("path", "").rstrip('/')
        file_pattern = source_config.get("file_pattern", "*")
        
        prefix = f"{source_path}/" if source_path else ""
        response = s3_client.list_objects_v2(Bucket=source_bucket, Prefix=prefix)
        
        transferred_count = 0
        if 'Contents' in response:
            import fnmatch
            for obj in response['Contents']:
                file_key = obj['Key']
                file_name = file_key.split('/')[-1]
                
                if file_key.endswith('/'):
                    continue
                
                if fnmatch.fnmatch(file_name, file_pattern) or fnmatch.fnmatch(file_key, f"{prefix}{file_pattern}") or file_pattern == "*":
                    # Download from S3 to destination
                    local_file = os.path.join(dest_path, file_name)
                    s3_client.download_file(source_bucket, file_key, local_file)
                    
                    # Delete from source
                    s3_client.delete_object(Bucket=source_bucket, Key=file_key)
                    
                    logger.info(f"Transferred {file_key} to {local_file}")
                    transferred_count += 1
        
        return transferred_count
    except Exception as e:
        logger.error(f"Error transferring files to filesystem: {str(e)}", exc_info=True)
        return 0


def transfer_to_rest_api_function(source_config: Dict[str, Any], destination_config: Dict[str, Any], credentials: Dict[str, str], logger) -> int:
    """Transfer files from S3 to customer via REST API (POST/PUT file upload).
    
    Supports:
    - POST/PUT methods
    - Multipart/form-data file uploads
    - Bearer token, API key, OAuth2, Basic auth
    - Custom headers
    - File metadata in request body
    """
    try:
        import boto3
        from botocore.config import Config
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        import fnmatch
        import tempfile
        
        # Get S3 client
        s3_creds = source_config.get("aws_access_key_id") or credentials.get('aws_access_key_id', 'minioadmin')
        s3_secret = source_config.get("aws_secret_access_key") or credentials.get('aws_secret_access_key', 'minioadmin')
        endpoint = source_config.get("endpoint_url") or credentials.get('endpoint_url', 'http://minio:9000')
        
        # Ensure endpoint has http:// prefix
        if not endpoint.startswith("http://") and not endpoint.startswith("https://"):
            endpoint = f"http://{endpoint}"
        
        s3_client = boto3.client(
            's3',
            endpoint_url=endpoint,
            aws_access_key_id=s3_creds,
            aws_secret_access_key=s3_secret,
            config=Config(signature_version='s3v4')
        )
        
        # Get REST API configuration
        api_url = destination_config.get("url") or destination_config.get("endpoint_url")
        if not api_url:
            raise ValueError("REST API destination requires 'url' or 'endpoint_url' in destination_config")
        
        http_method = destination_config.get("method", "POST").upper()  # POST, PUT, PATCH
        auth_type = destination_config.get("auth_type", "bearer_token")
        api_key = destination_config.get("api_key") or destination_config.get("token")
        api_key_header = destination_config.get("api_key_header", "Authorization")
        username = destination_config.get("username")
        password = destination_config.get("password")
        
        # File upload configuration
        file_field_name = destination_config.get("file_field_name", "file")  # Form field name for file
        additional_fields = destination_config.get("additional_fields", {})  # Additional form fields
        content_type = destination_config.get("content_type", "application/octet-stream")
        use_multipart = destination_config.get("use_multipart", True)  # Use multipart/form-data
        
        # Build headers
        headers = destination_config.get("headers", {})
        if not headers:
            headers = {}
        
        # Configure authentication
        if auth_type == "bearer_token" and api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        elif auth_type == "api_key" and api_key:
            headers[api_key_header] = api_key
        elif auth_type == "basic" and username and password:
            import base64
            auth_string = f"{username}:{password}"
            auth_bytes = auth_string.encode('ascii')
            auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
            headers["Authorization"] = f"Basic {auth_b64}"
        
        # Add custom headers
        custom_headers = destination_config.get("custom_headers", {})
        headers.update(custom_headers)
        
        # Configure requests session with retries
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST", "PUT", "PATCH"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # List and transfer files
        source_bucket = source_config.get("bucket")
        source_path = source_config.get("path", "").rstrip('/')
        file_pattern = source_config.get("file_pattern", "*")
        
        prefix = f"{source_path}/" if source_path else ""
        response = s3_client.list_objects_v2(Bucket=source_bucket, Prefix=prefix)
        
        transferred_count = 0
        if 'Contents' in response:
            with tempfile.TemporaryDirectory() as tmpdir:
                for obj in response['Contents']:
                    file_key = obj['Key']
                    file_name = file_key.split('/')[-1]
                    
                    if file_key.endswith('/'):
                        continue
                    
                    # Check if file matches pattern
                    if not (fnmatch.fnmatch(file_name, file_pattern) or 
                            fnmatch.fnmatch(file_key, f"{prefix}{file_pattern}") or 
                            file_pattern == "*"):
                        continue
                    
                    # Download from S3 to temp file
                    local_file = os.path.join(tmpdir, file_name)
                    s3_client.download_file(source_bucket, file_key, local_file)
                    
                    # Upload to REST API
                    try:
                        if use_multipart:
                            # Multipart/form-data upload
                            with open(local_file, 'rb') as f:
                                files = {file_field_name: (file_name, f, content_type)}
                                data = additional_fields
                                
                                api_response = session.request(
                                    method=http_method,
                                    url=api_url,
                                    headers=headers,
                                    files=files,
                                    data=data,
                                    timeout=300  # 5 minute timeout for large files
                                )
                        else:
                            # Raw binary upload (PUT/PATCH)
                            with open(local_file, 'rb') as f:
                                file_data = f.read()
                                if additional_fields:
                                    # For non-multipart, additional fields might need to be in URL or headers
                                    headers.update(additional_fields)
                                
                                api_response = session.request(
                                    method=http_method,
                                    url=api_url,
                                    headers={**headers, "Content-Type": content_type},
                                    data=file_data,
                                    timeout=300
                                )
                        
                        api_response.raise_for_status()
                        
                        # Delete from source S3 if upload successful
                        s3_client.delete_object(Bucket=source_bucket, Key=file_key)
                        
                        logger.info(f"Transferred {file_key} to REST API {api_url} (status: {api_response.status_code})")
                        transferred_count += 1
                        
                    except requests.exceptions.RequestException as e:
                        logger.error(f"Failed to upload {file_key} to REST API: {e}")
                        if hasattr(e, 'response') and e.response is not None:
                            logger.error(f"API response: {e.response.status_code} - {e.response.text}")
                        # Don't delete from source if upload failed
                        continue
        
        session.close()
        return transferred_count
        
    except Exception as e:
        logger.error(f"Error transferring files to REST API: {str(e)}", exc_info=True)
        return 0


def transfer_csv_to_sftp(csv_file_path: str, csv_filename: str, destination_config: Dict[str, Any], logger, row_count: int) -> Dict[str, Any]:
    """Transfer a CSV file directly to TrueNAS Scale via SFTP."""
    try:
        import paramiko
        
        # Get SFTP connection details
        sftp_host = destination_config.get("host")
        sftp_port = destination_config.get("port", 22)
        sftp_username = destination_config.get("username")
        sftp_password = destination_config.get("password")
        sftp_key_path = destination_config.get("pkey_path")
        sftp_dest_path = destination_config.get("path", "/")
        
        if not sftp_host or not sftp_username:
            raise ValueError("SFTP destination requires 'host' and 'username' in destination_config")
        
        logger.info(f"Connecting to SFTP server: {sftp_host}:{sftp_port}")
        
        # Connect to SFTP
        transport = paramiko.Transport((sftp_host, sftp_port))
        try:
            if sftp_key_path:
                private_key = paramiko.RSAKey.from_private_key_file(sftp_key_path)
                transport.connect(username=sftp_username, pkey=private_key)
            else:
                if not sftp_password:
                    raise ValueError("SFTP destination requires 'password' or 'pkey_path' in destination_config")
                transport.connect(username=sftp_username, password=sftp_password)
            
            sftp = paramiko.SFTPClient.from_transport(transport)
            
            # Ensure destination directory exists
            try:
                sftp.stat(sftp_dest_path)
            except IOError:
                # Directory doesn't exist, try to create it
                logger.info(f"Creating SFTP directory: {sftp_dest_path}")
                try:
                    sftp.mkdir(sftp_dest_path)
                except:
                    pass  # May fail if parent doesn't exist, but we'll try upload anyway
            
            # Upload CSV file
            remote_path = f"{sftp_dest_path.rstrip('/')}/{csv_filename}"
            logger.info(f"Uploading CSV to SFTP: {remote_path}")
            sftp.put(csv_file_path, remote_path)
            
            file_size = os.path.getsize(csv_file_path)
            file_size_mb = file_size / (1024 * 1024)
            
            sftp.close()
            transport.close()
            
            # Clean up temp file
            os.unlink(csv_file_path)
            
            logger.info(f"Successfully uploaded CSV to SFTP {remote_path} ({file_size_mb:.2f} MB)")
            
            return {
                "status": "success",
                "rows_ingested": row_count,
                "log_summary": f"Exported {row_count:,} rows ({file_size_mb:.2f} MB) to CSV and uploaded to SFTP {remote_path}",
            }
        finally:
            try:
                transport.close()
            except:
                pass
                
    except Exception as e:
        logger.error(f"Error transferring CSV to SFTP: {str(e)}", exc_info=True)
        # Clean up temp file on error
        try:
            if os.path.exists(csv_file_path):
                os.unlink(csv_file_path)
        except:
            pass
        return {
            "status": "failed",
            "rows_ingested": 0,
            "log_summary": f"Error: {str(e)}",
        }


def transfer_csv_to_filesystem(csv_file_path: str, csv_filename: str, destination_config: Dict[str, Any], logger, row_count: int) -> Dict[str, Any]:
    """Transfer a CSV file directly to NFS/local filesystem."""
    try:
        # Get destination path (NFS mounted or local)
        dest_path = destination_config.get("path", "/mnt/destination")
        
        if not dest_path:
            raise ValueError("Filesystem destination requires 'path' in destination_config")
        
        logger.info(f"Writing CSV to filesystem: {dest_path}")
        
        # Ensure destination directory exists
        os.makedirs(dest_path, exist_ok=True)
        
        # Copy CSV file to destination
        dest_file_path = os.path.join(dest_path, csv_filename)
        import shutil
        shutil.copy2(csv_file_path, dest_file_path)
        
        file_size = os.path.getsize(dest_file_path)
        file_size_mb = file_size / (1024 * 1024)
        
        # Clean up temp file
        os.unlink(csv_file_path)
        
        logger.info(f"Successfully wrote CSV to {dest_file_path} ({file_size_mb:.2f} MB)")
        
        return {
            "status": "success",
            "rows_ingested": row_count,
            "log_summary": f"Exported {row_count:,} rows ({file_size_mb:.2f} MB) to CSV and wrote to {dest_file_path}",
        }
                
    except Exception as e:
        logger.error(f"Error transferring CSV to filesystem: {str(e)}", exc_info=True)
        # Clean up temp file on error
        try:
            if os.path.exists(csv_file_path):
                os.unlink(csv_file_path)
        except:
            pass
        return {
            "status": "failed",
            "rows_ingested": 0,
            "log_summary": f"Error: {str(e)}",
        }


def handle_database_source(config: Dict[str, Any], source_config: Dict[str, Any], destination_config: Dict[str, Any], logger) -> Dict[str, Any]:
    """Extract data from PostgreSQL database, export to CSV, and upload to destination.
    
    Supported destinations:
    - S3/MinIO (s3): Direct upload to S3-compatible storage
    - TrueNAS Scale via SFTP (sftp): Transfer CSV file via SFTP
    - NFS/Local filesystem (nfs, filesystem): Write CSV to mounted path
    
    This function handles large datasets efficiently by:
    - Using server-side cursors for streaming results
    - Writing CSV in chunks to avoid memory issues
    - Using multipart upload for large files to S3
    - Direct file transfer for SFTP/NFS destinations
    - Processing with configurable batch sizes
    """
    try:
        # Get source database connection details - all required, no hardcoded defaults
        source_db_host = source_config.get("host")
        source_db_port = source_config.get("port")
        source_db_name = source_config.get("database")
        source_db_user = source_config.get("username")
        source_db_password = source_config.get("password")
        source_query = source_config.get("query")
        csv_filename = source_config.get("csv_filename")
        
        # Validate required fields
        required_fields = {
            "host": source_db_host,
            "port": source_db_port,
            "database": source_db_name,
            "username": source_db_user,
            "password": source_db_password,
            "query": source_query
        }
        
        missing_fields = [field for field, value in required_fields.items() if value is None]
        if missing_fields:
            error_msg = f"Missing required source configuration fields: {', '.join(missing_fields)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Default port to 5432 if not provided (standard PostgreSQL port)
        if source_db_port is None:
            source_db_port = 5432
            logger.info("Using default PostgreSQL port 5432")
        
        # Generate default CSV filename if not provided
        if not csv_filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            csv_filename = f"export_{timestamp}.csv"
            logger.info(f"Using auto-generated CSV filename: {csv_filename}")
        
        # Configuration for large dataset handling
        batch_size = source_config.get("batch_size", 10000)  # Rows to process in memory at once
        use_server_side_cursor = source_config.get("use_server_side_cursor", True)  # Stream results
        chunk_size_mb = source_config.get("chunk_size_mb", 5)  # S3 multipart chunk size in MB
        
        # Connect to source database
        source_db_url = f"postgresql://{source_db_user}:{source_db_password}@{source_db_host}:{source_db_port}/{source_db_name}"
        logger.info(f"Connecting to source database: {source_db_host}:{source_db_port}/{source_db_name}")
        logger.info(f"Using batch_size={batch_size}, server_side_cursor={use_server_side_cursor}")
        
        source_conn = psycopg2.connect(source_db_url)
        try:
            # Use server-side cursor for large datasets to avoid loading all rows into memory
            if use_server_side_cursor:
                # Named cursor for server-side fetching
                # Server-side cursors must be used within a transaction
                source_conn.set_session(autocommit=False)
                # Create named cursor for server-side fetching
                cur = source_conn.cursor('large_query_cursor', cursor_factory=RealDictCursor)
                logger.info("Using server-side cursor for streaming results")
            else:
                cur = source_conn.cursor(cursor_factory=RealDictCursor)
            
            try:
                logger.info(f"Executing query: {source_query}")
                
                # Execute the query
                cur.execute(source_query)
                
                # For server-side cursors, description might not be available immediately
                # Try to fetch one row to ensure description is populated
                if use_server_side_cursor:
                    # Peek at first row to populate description, then reset
                    test_row = cur.fetchone()
                    if test_row is not None:
                        # Put the row back by creating a new cursor or store it
                        # Actually, we'll just process it in the loop
                        # But first, get description
                        if cur.description is None:
                            logger.error("Server-side cursor has no description after fetchone")
                            raise ValueError("Query must be a SELECT statement that returns rows.")
                        column_names = [desc[0] for desc in cur.description]
                        # We'll need to process test_row in the loop, so note we already have one row
                        first_row_processed = False
                    else:
                        # No rows returned
                        if cur.description is None:
                            logger.warning("Query returned no rows and no description")
                            return {
                                "status": "success",
                                "rows_ingested": 0,
                                "log_summary": "Query returned no rows. No CSV file created.",
                            }
                        column_names = [desc[0] for desc in cur.description]
                        first_row_processed = True
                else:
                    # Regular cursor - description should be available immediately
                    if cur.description is None:
                        logger.error("Query returned no description - likely a non-SELECT query")
                        raise ValueError("Query must be a SELECT statement that returns rows. Cursor description is None.")
                    column_names = [desc[0] for desc in cur.description]
                    test_row = None
                    first_row_processed = True
                
                logger.info(f"Query columns: {column_names}")
                
                if not column_names:
                    logger.error("Query returned no columns")
                    raise ValueError("Query returned no columns")
                
                # Use temporary file for large datasets to avoid memory issues
                use_temp_file = batch_size > 1000 or source_config.get("use_temp_file", False)
                
                if use_temp_file:
                    # Write to temporary file, then upload
                    temp_file = tempfile.NamedTemporaryFile(mode='w+', delete=False, newline='', encoding='utf-8')
                    temp_file_path = temp_file.name
                    logger.info(f"Writing CSV to temporary file: {temp_file_path}")
                    csv_writer = csv.DictWriter(temp_file, fieldnames=column_names)
                    csv_writer.writeheader()
                else:
                    # For smaller datasets, use in-memory buffer
                    csv_buffer = io.StringIO()
                    csv_writer = csv.DictWriter(csv_buffer, fieldnames=column_names)
                    csv_writer.writeheader()
                
                row_count = 0
                batch_count = 0
                
                # For server-side cursor, process the test row we already fetched
                if use_server_side_cursor and test_row is not None:
                    try:
                        csv_writer.writerow(dict(test_row))
                        row_count += 1
                        logger.debug(f"Processed first row from server-side cursor")
                    except Exception as write_error:
                        logger.error(f"Error writing first row to CSV: {write_error}", exc_info=True)
                        raise
                
                # Fetch rows in batches to control memory usage
                while True:
                    try:
                        if use_server_side_cursor:
                            rows = cur.fetchmany(batch_size)
                        else:
                            # For regular cursor, fetch all at once if first batch, then break
                            if row_count == 0:
                                rows = cur.fetchall()
                            else:
                                break
                    except Exception as fetch_error:
                        logger.error(f"Error fetching rows: {fetch_error}", exc_info=True)
                        raise
                    
                    if not rows:
                        break
                    
                    # Write batch to CSV
                    try:
                        for row in rows:
                            if row is None:
                                logger.warning("Encountered None row, skipping")
                                continue
                            csv_writer.writerow(dict(row))
                            row_count += 1
                    except Exception as write_error:
                        logger.error(f"Error writing row to CSV: {write_error}", exc_info=True)
                        logger.error(f"Row type: {type(row)}, Row value: {row}")
                        raise
                    
                    batch_count += 1
                    if batch_count % 10 == 0 or row_count % 50000 == 0:
                        logger.info(f"Processed {row_count:,} rows in {batch_count} batches")
                    
                    # If not using server-side cursor, break after first fetch
                    if not use_server_side_cursor:
                        break
                
                if row_count == 0:
                    logger.warning("Query returned no rows")
                    if use_temp_file:
                        temp_file.close()
                        os.unlink(temp_file_path)
                    return {
                        "status": "success",
                        "rows_ingested": 0,
                        "log_summary": "Query returned no rows. No CSV file created.",
                    }
                
                logger.info(f"Generated CSV with {row_count:,} rows")
                
                # Get destination type from config
                destination_type = config.get("destination_type", "s3")
                logger.info(f"Destination type: {destination_type}")
                
                # Handle different destination types
                if destination_type in ["sftp", "nfs", "filesystem"]:
                    # For SFTP/NFS, we need to write to a file and transfer it
                    if use_temp_file:
                        # Already written to temp file, just need to transfer it
                        final_file_path = temp_file_path
                        file_size = os.path.getsize(temp_file_path)
                        logger.info(f"CSV file size: {file_size:,} bytes ({file_size / (1024*1024):.2f} MB)")
                        # Don't delete temp file yet - transfer functions will handle it
                    else:
                        # Write in-memory buffer to temp file for transfer
                        temp_file = tempfile.NamedTemporaryFile(mode='w+', delete=False, newline='', encoding='utf-8')
                        final_file_path = temp_file.name
                        csv_content = csv_buffer.getvalue()
                        temp_file.write(csv_content)
                        temp_file.close()
                        file_size = len(csv_content.encode('utf-8'))
                        logger.info(f"CSV file size: {file_size:,} bytes ({file_size / (1024*1024):.2f} MB)")
                    
                    # Transfer to SFTP or NFS
                    if destination_type == "sftp":
                        return transfer_csv_to_sftp(final_file_path, csv_filename, destination_config, logger, row_count)
                    elif destination_type in ["nfs", "filesystem"]:
                        return transfer_csv_to_filesystem(final_file_path, csv_filename, destination_config, logger, row_count)
                
                # Default: Upload to S3/MinIO
                # Prepare file for upload
                if use_temp_file:
                    temp_file.close()
                    file_size = os.path.getsize(temp_file_path)
                    logger.info(f"CSV file size: {file_size:,} bytes ({file_size / (1024*1024):.2f} MB)")
                    # Read file for upload
                    with open(temp_file_path, 'rb') as f:
                        csv_bytes = f.read()
                    # Clean up temp file
                    os.unlink(temp_file_path)
                else:
                    csv_content = csv_buffer.getvalue()
                    csv_bytes = csv_content.encode('utf-8')
                    file_size = len(csv_bytes)
                    logger.info(f"CSV size: {file_size:,} bytes ({file_size / (1024*1024):.2f} MB)")
                
                # Upload to S3/MinIO
                dest_bucket = destination_config.get("bucket", "customer-data")
                dest_prefix = destination_config.get("prefix", "processed/").rstrip('/')
                dest_key = f"{dest_prefix}/{csv_filename}" if dest_prefix else csv_filename
                
                # Get credentials based on storage environment
                creds = get_s3_credentials(destination_config)
                
                # Build boto3 client arguments
                client_kwargs = {
                    'service_name': 's3',
                    'config': Config(signature_version='s3v4')
                }
                
                # Add credentials
                if creds.get('aws_access_key_id'):
                    client_kwargs['aws_access_key_id'] = creds['aws_access_key_id']
                if creds.get('aws_secret_access_key'):
                    client_kwargs['aws_secret_access_key'] = creds['aws_secret_access_key']
                if creds.get('region_name'):
                    client_kwargs['region_name'] = creds['region_name']
                if creds.get('endpoint_url'):
                    # Ensure endpoint has http:// prefix
                    endpoint = str(creds['endpoint_url']).strip().strip('"').strip("'")
                    if not endpoint.startswith("http://") and not endpoint.startswith("https://"):
                        endpoint = f"http://{endpoint}"
                    client_kwargs['endpoint_url'] = endpoint
                    logger.info(f"Connecting to S3-compatible endpoint: {endpoint}, bucket: {dest_bucket}, key: {dest_key}")
                else:
                    logger.info(f"Connecting to AWS S3, bucket: {dest_bucket}, key: {dest_key}")
                
                # Create S3 client
                s3_client = boto3.client(**client_kwargs)
                
                # Upload CSV to S3 - use multipart upload for large files
                file_size_mb = file_size / (1024 * 1024)
                if file_size_mb > 25:  # Use multipart upload for files > 25 MB
                    logger.info(f"Uploading large file ({file_size_mb:.2f} MB) using multipart upload")
                    # Use TransferConfig for multipart upload settings
                    from boto3.s3.transfer import TransferConfig
                    transfer_config = TransferConfig(
                        multipart_threshold=1024 * 1024 * 25,  # 25 MB in bytes
                        max_multipart_count=10,
                        multipart_chunksize=1024 * 1024 * chunk_size_mb,  # Chunk size in bytes
                        use_threads=True
                    )
                    # Use upload_fileobj with TransferConfig for automatic multipart handling
                    csv_file_obj = io.BytesIO(csv_bytes)
                    s3_client.upload_fileobj(
                        csv_file_obj,
                        dest_bucket,
                        dest_key,
                        ExtraArgs={'ContentType': 'text/csv'},
                        Config=transfer_config
                    )
                else:
                    # Use put_object for smaller files
                    logger.info(f"Uploading file ({file_size_mb:.2f} MB) using standard upload")
                    s3_client.put_object(
                        Bucket=dest_bucket,
                        Key=dest_key,
                        Body=csv_bytes,
                        ContentType='text/csv'
                    )
                
                logger.info(f"Successfully uploaded CSV to s3://{dest_bucket}/{dest_key} ({file_size_mb:.2f} MB)")
                
                return {
                    "status": "success",
                    "rows_ingested": row_count,
                    "log_summary": f"Exported {row_count:,} rows ({file_size_mb:.2f} MB) to CSV and uploaded to s3://{dest_bucket}/{dest_key}",
                }
            finally:
                cur.close()
        finally:
            source_conn.close()
            
    except Exception as e:
        logger.error(f"Error extracting from database: {str(e)}", exc_info=True)
        return {
            "status": "failed",
            "rows_ingested": 0,
            "log_summary": f"Error: {str(e)}",
        }


@task(name="update_run_record")
def update_run_record(
    run_id: int,
    status: str,
    rows_ingested: int = None,
    log_summary: str = None,
):
    """Update run record with completion status."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE cai_connector_runs
                SET status = %s,
                    finished_at = NOW(),
                    rows_ingested = COALESCE(%s, rows_ingested),
                    log_summary = COALESCE(%s, log_summary)
                WHERE id = %s
            """, (status, rows_ingested, log_summary, run_id))
            conn.commit()
    finally:
        conn.close()


@task(name="run_dlt_pipeline")
def run_dlt_pipeline(config: Dict[str, Any], project_id = "default_project", env = "") -> Dict[str, Any]:
    """Run the dlt pipeline based on connector configuration."""
    logger = get_run_logger()
    logger.info(f"Starting dlt pipeline for connector {config['connector_id']}: {config['connector_name']}")
    
    source_type = config["source_type"]
    destination_type = config["destination_type"]
    source_config = config["source_config"]
    destination_config = config["destination_config"]
    if "path" in destination_config:
        dest_path = destination_config.get("path", "/mnt/env/{env}/{project_id}/")
        variables = {"project_id": project_id, "env": env}
        if "{project_id}" in dest_path or "{env}" in dest_path:
            dest_path = dest_path.format(**variables)
        destination_config["path"] = dest_path
    
    rows_ingested = 0
    log_summary = ""
    
    try:
        logger.info(f"Source: {source_type}, Destination: {destination_type}")
        
        # Handle database source (PostgreSQL query -> CSV -> S3)
        if source_type == "sql_database" or source_type == "postgres" or source_type == "database":
            return handle_database_source(config, source_config, destination_config, logger)
        
        # Build S3/filesystem source
        if source_type == "filesystem":
            # Extract S3 bucket and path from config
            bucket = source_config.get("bucket", "customer-data")
            path = source_config.get("path", "incoming")
            file_pattern = source_config.get("file_pattern", "*.csv")
            
            # Construct S3 URL
            s3_url = f"s3://{bucket}/{path}"
            
            # Configure credentials - use helper function to get credentials based on storage environment
            credentials = get_s3_credentials(source_config)
            
            # For S3-to-S3 file transfers, skip dlt processing and just move files
            # Also handle S3-to-other-storage transfers (SFTP, NFS, REST API, etc.)
            if source_type == "filesystem" and destination_type in ["s3", "sftp", "nfs", "filesystem", "rest_api"]:
                # For file transfers (not data extraction), use direct file transfer
                logger.info(f"S3-to-{destination_type} file transfer detected. Transferring files directly.")
                transferred_files = transfer_files_function(source_config, destination_config, credentials, logger, destination_type)
                return {
                    "status": "success",
                    "rows_ingested": 0,
                    "log_summary": f"Transferred {transferred_files} file(s) to destination.",
                }
            
            # Create filesystem source - handle both CSV and other files
            if not DLT_AVAILABLE:
                raise ValueError("dlt library not available. Cannot process data files.")
            if file_pattern.endswith('.csv') or file_pattern == "*":
                source = filesystem(bucket_url=s3_url, file_glob=file_pattern, credentials=credentials) | read_csv()
            else:
                # For non-CSV files (like PDFs), use filesystem source without read_csv
                source = filesystem(bucket_url=s3_url, file_glob=file_pattern, credentials=credentials)
            
            # Build destination
            if destination_type == "postgres":
                # Use destination_config to get connection details
                db_url = destination_config.get("connection_string")
                if not db_url:
                    # Build from components
                    host = destination_config.get("host", "postgres")
                    port = destination_config.get("port", 5432)
                    database = destination_config.get("database", "cai_data")
                    username = destination_config.get("username", "postgres")
                    password = destination_config.get("password", "postgres")
                    schema = destination_config.get("schema", "public")
                    db_url = f"postgresql://{username}:{password}@{host}:{port}/{database}"
                
                destination = dlt.destinations.postgres(credentials=db_url, dataset_name=destination_config.get("schema", "public"))
            
            elif destination_type == "s3":
                bucket = destination_config.get("bucket", "output")
                prefix = destination_config.get("prefix", "")
                destination = dlt.destinations.filesystem(
                    bucket_url=f"s3://{bucket}/{prefix}",
                    credentials=credentials
                )
            elif destination_type == "sftp":
                # TrueNAS Scale via SFTP
                host = destination_config.get("host", "truenas-ip")
                port = destination_config.get("port", 22)
                path = destination_config.get("path", "/")
                username = destination_config.get("username")
                password = destination_config.get("password")
                pkey_path = destination_config.get("pkey_path")
                
                sftp_creds = {}
                if password:
                    sftp_creds["sftp_password"] = password
                if pkey_path:
                    sftp_creds["sftp_key_filename"] = pkey_path
                if username:
                    sftp_creds["sftp_username"] = username
                if port != 22:
                    sftp_creds["sftp_port"] = port
                
                destination = dlt.destinations.filesystem(
                    bucket_url=f"sftp://{host}{path}",
                    credentials=sftp_creds
                )
            elif destination_type == "nfs" or destination_type == "filesystem":
                # NFS mounted path or local filesystem
                path = destination_config.get("path", "/mnt/destination")
                destination = dlt.destinations.filesystem(
                    bucket_url=f"file://{path}"
                )
            else:
                raise ValueError(f"Unsupported destination type: {destination_type}")
            
            # Create and run pipeline
            # Default to 'dlt' schema instead of 'public' for better organization
            dataset_schema = destination_config.get("schema", "dlt")
            pipeline = dlt.pipeline(
                pipeline_name=f"connector_{config['connector_id']}",
                destination=destination,
                dataset_name=dataset_schema
            )
            
            logger.info(f"Executing dlt pipeline.run() for connector {config['connector_id']}")
            info = pipeline.run(source)
            rows_ingested = info.loads[0].dataset_rows if info.loads else 0
            log_summary = f"Pipeline completed successfully. Loaded {len(info.loads)} packages."
            logger.info(f"dlt pipeline completed: {rows_ingested} rows ingested, {len(info.loads)} packages loaded")
            
            # After processing, move files from source to processed folder if destination is PostgreSQL
            # (For S3-to-S3, files are moved earlier, before dlt processing)
            if destination_type == "postgres" and source_type == "filesystem":
                moved_files = move_processed_files_function(source_config, destination_config, credentials, logger)
                log_summary += f" Moved {moved_files} file(s) to processed folder."
            
        else:
            error_msg = f"Unsupported source type: {source_type}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        return {
            "status": "success",
            "rows_ingested": rows_ingested,
            "log_summary": log_summary,
        }
    
    except Exception as e:
        logger.error(f"dlt pipeline failed for connector {config.get('connector_id', 'unknown')}: {str(e)}", exc_info=True)
        return {
            "status": "failed",
            "rows_ingested": 0,
            "log_summary": f"Error: {str(e)}",
        }


@flow(name="run_connector_pipeline")
def run_connector_pipeline(connector_id: int, project_id: str = "default_project", env: str = None, prefect_flow_run_id: str = None):
    """
    Main Prefect flow to run a dlt pipeline for a connector.
    
    Args:
        connector_id: ID of the connector to run
        project_id: Project id
        env: Environment
        prefect_flow_run_id: Prefect flow run ID (optional, will be retrieved from context if not provided)
    """
    # Get flow run ID from context if not provided
    if not prefect_flow_run_id:
        try:
            from prefect.context import get_run_context
            context = get_run_context()
            prefect_flow_run_id = str(context.flow_run.id)
        except (ImportError, Exception) as e:
            # If not in Prefect context (e.g., called directly), generate a unique ID
            import time
            prefect_flow_run_id = f"manual-{connector_id}-{int(time.time())}"
            logger = logging.getLogger(__name__)
            logger.warning(f"Not in Prefect context, using generated flow run ID: {prefect_flow_run_id}")
    
    logger = get_run_logger()
    logger.info(f"Starting flow run for connector {connector_id}, flow_run_id: {prefect_flow_run_id}")
    
    # Create run record - wrap in try/except to ensure we can continue even if DB write fails
    run_id = None
    try:
        run_id = create_run_record(connector_id, prefect_flow_run_id)
        logger.info(f"Created run record {run_id} for connector {connector_id}")
    except Exception as e:
        logger.error(f"Failed to create run record: {e}", exc_info=True)
        # Continue execution even if record creation fails
        run_id = None
    
    try:
        # Read connector configuration
        config = read_connector_config(connector_id)
        
        # Run dlt pipeline
        result = run_dlt_pipeline(config, project_id, env)
        
        # Update run record if it was created
        if run_id is not None:
            try:
                update_run_record(
                    run_id=run_id,
                    status=result["status"],
                    rows_ingested=result["rows_ingested"],
                    log_summary=result["log_summary"],
                )
                logger.info(f"Updated run record {run_id} with status: {result['status']}")
            except Exception as e:
                logger.error(f"Failed to update run record: {e}", exc_info=True)
        else:
            logger.warning("Run record was not created, skipping update")
        
        logger.info(f"Flow completed successfully for connector {connector_id}: {result['status']}")
        return result
    
    except Exception as e:
        logger.error(f"Flow failed for connector {connector_id}: {str(e)}", exc_info=True)
        # Update run record with failure if it was created
        if run_id is not None:
            try:
                update_run_record(
                    run_id=run_id,
                    status="failed",
                    log_summary=f"Flow error: {str(e)}",
                )
            except Exception as update_error:
                logger.error(f"Failed to update run record with failure: {update_error}", exc_info=True)
        raise

