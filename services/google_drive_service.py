import io
import os
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from routers.upload import get_file_type

import pickle
import tempfile
import shutil

logger = logging.getLogger(__name__)

# If modifying these scopes, delete the file token.pickle
SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/drive.metadata.readonly'
]

class GoogleDriveService:
    def __init__(self, credentials_path: str = "google_credentials.json"):
        """
        Initialize Google Drive service
        
        Args:
            credentials_path: Path to Google OAuth credentials JSON file
        """
        self.credentials_path = credentials_path
        self.service = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Google Drive API"""
        creds = None
        
        # Token file stores the user's access and refresh tokens
        token_path = "google_token.pickle"
        
        if os.path.exists(token_path):
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)
        
        # If there are no (valid) credentials available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_path):
                    raise FileNotFoundError(
                        f"Google credentials file not found: {self.credentials_path}. "
                        "Please download credentials from Google Cloud Console"
                    )
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES
                )
                creds = flow.run_local_server(port=0)
            
            # Save the credentials for the next run
            with open(token_path, 'wb') as token:
                pickle.dump(creds, token)
        
        self.service = build('drive', 'v3', credentials=creds)
        logger.info("✅ Google Drive authenticated")
    
    def list_files(
        self, 
        folder_id: str = None, 
        mime_type: str = None,
        page_size: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List files from Google Drive
        
        Args:
            folder_id: Specific folder ID to list files from
            mime_type: Filter by MIME type (e.g., 'application/pdf')
            page_size: Number of files to return
            
        Returns:
            List of file metadata dictionaries
        """
        try:
            query_parts = []
            
            # If folder_id is provided, list files in that folder
            if folder_id:
                query_parts.append(f"'{folder_id}' in parents")
            
            # If mime_type is provided, filter by it
            if mime_type:
                query_parts.append(f"mimeType = '{mime_type}'")
            
            # Only list files (not folders)
            query_parts.append("mimeType != 'application/vnd.google-apps.folder'")
            
            # Trashed files excluded
            query_parts.append("trashed = false")
            
            query = ' and '.join(query_parts)
            
            results = self.service.files().list(
                q=query,
                pageSize=page_size,
                fields="nextPageToken, files(id, name, mimeType, size, modifiedTime, webViewLink, fileExtension)"
            ).execute()
            
            files = results.get('files', [])
            
            # Format files with additional info
            formatted_files = []
            for file in files:
                formatted_files.append({
                    'id': file['id'],
                    'name': file['name'],
                    'mime_type': file.get('mimeType', ''),
                    'size': int(file.get('size', 0)) if file.get('size') else 0,
                    'modified_time': file.get('modifiedTime', ''),
                    'web_view_link': file.get('webViewLink', ''),
                    'extension': file.get('fileExtension', ''),
                    'source': 'google_drive'
                })
            
            logger.info(f"📁 Found {len(formatted_files)} files from Google Drive")
            return formatted_files
            
        except Exception as e:
            logger.error(f"❌ Error listing Google Drive files: {e}")
            raise
    
    def list_folders(self, parent_id: str = 'root') -> List[Dict[str, Any]]:
        """
        List folders from Google Drive
        
        Args:
            parent_id: Parent folder ID (default: 'root')
            
        Returns:
            List of folder metadata dictionaries
        """
        try:
            query = (
                f"mimeType = 'application/vnd.google-apps.folder' "
                f"and '{parent_id}' in parents "
                f"and trashed = false"
            )
            
            results = self.service.files().list(
                q=query,
                pageSize=100,
                fields="nextPageToken, files(id, name, mimeType, modifiedTime)"
            ).execute()
            
            folders = results.get('files', [])
            
            formatted_folders = []
            for folder in folders:
                formatted_folders.append({
                    'id': folder['id'],
                    'name': folder['name'],
                    'mime_type': folder.get('mimeType', ''),
                    'modified_time': folder.get('modifiedTime', ''),
                    'source': 'google_drive'
                })
            
            logger.info(f"📂 Found {len(formatted_folders)} folders from Google Drive")
            return formatted_folders
            
        except Exception as e:
            logger.error(f"❌ Error listing Google Drive folders: {e}")
            raise
    
    def get_file(self, file_id: str) -> Dict[str, Any]:
        """
        Get metadata for a specific file
        
        Args:
            file_id: Google Drive file ID
            
        Returns:
            File metadata dictionary
        """
        try:
            file = self.service.files().get(
                fileId=file_id,
                fields="id, name, mimeType, size, modifiedTime, webViewLink, fileExtension"
            ).execute()
            
            return {
                'id': file['id'],
                'name': file['name'],
                'mime_type': file.get('mimeType', ''),
                'size': int(file.get('size', 0)) if file.get('size') else 0,
                'modified_time': file.get('modifiedTime', ''),
                'web_view_link': file.get('webViewLink', ''),
                'extension': file.get('fileExtension', ''),
                'source': 'google_drive'
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting file {file_id}: {e}")
            raise
    
    def download_file(self, file_id: str, destination_path: str = None) -> str:
        """
        Download a file from Google Drive
        
        Args:
            file_id: Google Drive file ID
            destination_path: Optional path to save the file
            
        Returns:
            Path to downloaded file
        """
        try:
            # Get file metadata first
            file_metadata = self.get_file(file_id)
            file_name = file_metadata['name']
            
            # Create temp file if no destination specified
            if not destination_path:
                temp_dir = tempfile.mkdtemp()
                destination_path = os.path.join(temp_dir, file_name)
            
            logger.info(f"⬇️ Downloading: {file_name} ({file_metadata.get('size', 0)} bytes)")
            
            # Request file content
            request = self.service.files().get_media(fileId=file_id)
            
            # Download file
            with open(destination_path, 'wb') as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        logger.debug(f"Download {int(status.progress() * 100)}%")
            
            logger.info(f"✅ Downloaded: {destination_path}")
            return destination_path
            
        except Exception as e:
            logger.error(f"❌ Error downloading file {file_id}: {e}")
            raise
    
    def search_files(
        self, 
        query: str, 
        mime_type: str = None,
        page_size: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Search files in Google Drive
        
        Args:
            query: Search query string
            mime_type: Filter by MIME type
            page_size: Number of results
            
        Returns:
            List of file metadata dictionaries
        """
        try:
            query_parts = [f"fullText contains '{query}'"]
            
            if mime_type:
                query_parts.append(f"mimeType = '{mime_type}'")
            
            query_parts.append("mimeType != 'application/vnd.google-apps.folder'")
            query_parts.append("trashed = false")
            
            search_query = ' and '.join(query_parts)
            
            results = self.service.files().list(
                q=search_query,
                pageSize=page_size,
                fields="nextPageToken, files(id, name, mimeType, size, modifiedTime, webViewLink, fileExtension)"
            ).execute()
            
            files = results.get('files', [])
            
            formatted_files = []
            for file in files:
                formatted_files.append({
                    'id': file['id'],
                    'name': file['name'],
                    'mime_type': file.get('mimeType', ''),
                    'size': int(file.get('size', 0)) if file.get('size') else 0,
                    'modified_time': file.get('modifiedTime', ''),
                    'web_view_link': file.get('webViewLink', ''),
                    'extension': file.get('fileExtension', ''),
                    'source': 'google_drive'
                })
            
            logger.info(f"🔍 Found {len(formatted_files)} files matching '{query}'")
            return formatted_files
            
        except Exception as e:
            logger.error(f"❌ Error searching Google Drive: {e}")
            raise
    
    def get_recent_files(self, days: int = 7, page_size: int = 50) -> List[Dict[str, Any]]:
        """
        Get recently modified files
        
        Args:
            days: Number of days to look back
            page_size: Number of files to return
            
        Returns:
            List of recent file metadata
        """
        try:
            from datetime import datetime, timedelta
            
            cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat() + 'Z'
            
            query = (
                f"modifiedTime > '{cutoff_date}' "
                f"and mimeType != 'application/vnd.google-apps.folder' "
                f"and trashed = false"
            )
            
            results = self.service.files().list(
                q=query,
                pageSize=page_size,
                orderBy="modifiedTime desc",
                fields="nextPageToken, files(id, name, mimeType, size, modifiedTime, webViewLink, fileExtension)"
            ).execute()
            
            files = results.get('files', [])
            
            formatted_files = []
            for file in files:
                formatted_files.append({
                    'id': file['id'],
                    'name': file['name'],
                    'mime_type': file.get('mimeType', ''),
                    'size': int(file.get('size', 0)) if file.get('size') else 0,
                    'modified_time': file.get('modifiedTime', ''),
                    'web_view_link': file.get('webViewLink', ''),
                    'extension': file.get('fileExtension', ''),
                    'source': 'google_drive',
                    'recent': True
                })
            
            logger.info(f"🕒 Found {len(formatted_files)} recent files (last {days} days)")
            return formatted_files
            
        except Exception as e:
            logger.error(f"❌ Error getting recent files: {e}")
            raise
    
    def get_starred_files(self, page_size: int = 50) -> List[Dict[str, Any]]:
        """
        Get starred files
        
        Args:
            page_size: Number of files to return
            
        Returns:
            List of starred file metadata
        """
        try:
            query = (
                "starred = true "
                "and mimeType != 'application/vnd.google-apps.folder' "
                "and trashed = false"
            )
            
            results = self.service.files().list(
                q=query,
                pageSize=page_size,
                fields="nextPageToken, files(id, name, mimeType, size, modifiedTime, webViewLink, fileExtension)"
            ).execute()
            
            files = results.get('files', [])
            
            formatted_files = []
            for file in files:
                formatted_files.append({
                    'id': file['id'],
                    'name': file['name'],
                    'mime_type': file.get('mimeType', ''),
                    'size': int(file.get('size', 0)) if file.get('size') else 0,
                    'modified_time': file.get('modifiedTime', ''),
                    'web_view_link': file.get('webViewLink', ''),
                    'extension': file.get('fileExtension', ''),
                    'source': 'google_drive',
                    'starred': True
                })
            
            logger.info(f"⭐ Found {len(formatted_files)} starred files")
            return formatted_files
            
        except Exception as e:
            logger.error(f"❌ Error getting starred files: {e}")
            raise


def get_file_type_from_mime(mime_type: str, filename: str) -> str:
    """
    Map Google Drive MIME types to your application's file types
    
    Args:
        mime_type: Google Drive MIME type
        filename: Original filename
        
    Returns:
        File type string compatible with your upload system
    """
    # Extract extension from filename as fallback
    suffix = Path(filename).suffix.lower()
    
    # MIME type mappings
    mime_to_type = {
        # PDF
        'application/pdf': 'pdf',
        
        # Word documents
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
        'application/msword': 'docx',
        
        # Text files
        'text/plain': 'txt',
        'text/markdown': 'md',
        
        # PowerPoint
        'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx',
        'application/vnd.ms-powerpoint': 'pptx',
        
        # Excel/Spreadsheets
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'excel',
        'application/vnd.ms-excel': 'excel',
        'text/csv': 'excel',
        
        # Images
        'image/png': 'image',
        'image/jpeg': 'image',
        'image/jpg': 'image',
        'image/gif': 'image',
        'image/bmp': 'image',
        'image/webp': 'image',
        'image/tiff': 'image',
        'image/heic': 'image',
        'image/heif': 'image',
        'image/avif': 'image',
        
        # Audio
        'audio/mpeg': 'audio',
        'audio/mp3': 'audio',
        'audio/wav': 'audio',
        'audio/x-wav': 'audio',
        'audio/m4a': 'audio',
        'audio/aac': 'audio',
        'audio/ogg': 'audio',
        'audio/flac': 'audio',
        
        # Video (might contain audio)
        'video/mp4': 'audio',
        'video/mov': 'audio',
        'video/avi': 'audio',
        'video/webm': 'audio',
    }
    
    # Try MIME type first
    if mime_type in mime_to_type:
        return mime_to_type[mime_type]
    
    # Fallback to extension-based detection (using your existing function)
    return get_file_type(filename)