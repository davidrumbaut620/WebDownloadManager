import requests
import os
import logging
from app import app, db
from models import DetectedFile
import zipfile
from urllib.parse import urlparse
import uuid

class FileDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def download_file(self, detected_file):
        """Download a single file"""
        try:
            # Update download status
            detected_file.download_status = 'downloading'
            db.session.commit()
            
            response = self.session.get(detected_file.url, stream=True, timeout=30)
            response.raise_for_status()
            
            # Generate unique filename
            safe_filename = self._get_safe_filename(detected_file.filename)
            file_path = os.path.join(app.config['DOWNLOAD_FOLDER'], safe_filename)
            
            # Ensure unique filename
            counter = 1
            base_name, ext = os.path.splitext(file_path)
            while os.path.exists(file_path):
                file_path = f"{base_name}_{counter}{ext}"
                counter += 1
            
            # Download file
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # Update database
            detected_file.download_status = 'completed'
            detected_file.download_path = file_path
            db.session.commit()
            
            return file_path
            
        except Exception as e:
            logging.error(f"Error downloading file {detected_file.url}: {str(e)}")
            detected_file.download_status = 'error'
            db.session.commit()
            raise e
    
    def create_zip_download(self, files, source_url):
        """Create a ZIP file containing multiple downloaded files"""
        try:
            # Create unique zip filename
            parsed_url = urlparse(source_url)
            domain = parsed_url.netloc.replace('.', '_')
            zip_filename = f"download_{domain}_{str(uuid.uuid4())[:8]}.zip"
            zip_path = os.path.join(app.config['DOWNLOAD_FOLDER'], zip_filename)
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for detected_file in files:
                    try:
                        # Download file if not already downloaded
                        if detected_file.download_status != 'completed' or not detected_file.download_path:
                            file_path = self.download_file(detected_file)
                        else:
                            file_path = detected_file.download_path
                        
                        # Add to zip if file exists
                        if file_path and os.path.exists(file_path):
                            # Use original filename in zip
                            arcname = f"{detected_file.file_type}/{detected_file.filename}"
                            zipf.write(file_path, arcname)
                            
                    except Exception as e:
                        logging.error(f"Error adding file to zip: {str(e)}")
                        continue
            
            return zip_path
            
        except Exception as e:
            logging.error(f"Error creating zip archive: {str(e)}")
            raise e
    
    def _get_safe_filename(self, filename):
        """Generate a safe filename for the filesystem"""
        # Remove or replace unsafe characters
        unsafe_chars = '<>:"/\\|?*'
        safe_filename = filename
        
        for char in unsafe_chars:
            safe_filename = safe_filename.replace(char, '_')
        
        # Limit length
        if len(safe_filename) > 200:
            name, ext = os.path.splitext(safe_filename)
            safe_filename = name[:200-len(ext)] + ext
        
        return safe_filename
