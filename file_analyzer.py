import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import mimetypes
import logging
from PIL import Image
import os
from app import app
import uuid

class FileAnalyzer:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # File type mappings - enhanced for better video detection
        self.image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.ico', '.tiff', '.heic', '.avif'}
        self.video_extensions = {'.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mkv', '.m4v', '.3gp', '.ogv', '.mpg', '.mpeg', '.ts', '.mts', '.m3u8', '.mpd'}
        self.audio_extensions = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a', '.opus', '.aiff', '.au'}
        self.document_extensions = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.rtf', '.odt', '.ods', '.odp'}
        
        # Video URL patterns for aggressive detection
        self.video_url_patterns = [
            r'/video/',
            r'/media/',
            r'/stream/',
            r'/assets/',
            r'/cdn/',
            r'/uploads/',
            r'/content/',
            r'\.mp4',
            r'\.webm',
            r'\.avi',
            r'\.mov',
            r'\.m3u8',
            r'\.mpd',
        ]
        
    def analyze_url(self, url):
        """Analyze a URL and return list of downloadable files"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            files = []
            
            # Find images
            for img in soup.find_all('img'):
                src = img.get('src')
                if src:
                    file_info = self._analyze_file_url(urljoin(url, src), 'image')
                    if file_info:
                        files.append(file_info)
            
            # Find videos
            for video in soup.find_all('video'):
                src = video.get('src')
                if src:
                    file_info = self._analyze_file_url(urljoin(url, src), 'video')
                    if file_info:
                        # Add video poster as preview if available
                        poster = video.get('poster')
                        if poster:
                            file_info['video_poster'] = urljoin(url, poster)
                        files.append(file_info)
                
                # Check source tags within video
                for source in video.find_all('source'):
                    src = source.get('src')
                    if src:
                        file_info = self._analyze_file_url(urljoin(url, src), 'video')
                        if file_info:
                            # Add video poster as preview if available
                            poster = video.get('poster')
                            if poster:
                                file_info['video_poster'] = urljoin(url, poster)
                            files.append(file_info)
            
            # Find iframe videos (YouTube, Vimeo, etc.)
            for iframe in soup.find_all('iframe'):
                src = iframe.get('src')
                if src and ('youtube.com/embed' in src or 'vimeo.com/video' in src or 'dailymotion.com/embed' in src or 'twitch.tv' in src):
                    video_title = iframe.get('title', f"video_{str(uuid.uuid4())[:8]}")
                    file_info = {
                        'filename': f"{video_title}.mp4",
                        'url': src,
                        'type': 'video',
                        'mime_type': 'video/mp4',
                        'size': None,
                        'preview_path': None,
                        'external_video': True
                    }
                    files.append(file_info)
            
            # Find additional video links
            for link in soup.find_all('a', href=True):
                href = link.get('href')
                if href and ('youtube.com/watch' in href or 'youtu.be/' in href or 'vimeo.com/' in href or 'twitch.tv/' in href):
                    link_text = link.get_text(strip=True) or f"video_{str(uuid.uuid4())[:8]}"
                    file_info = {
                        'filename': f"{link_text}.mp4",
                        'url': href,
                        'type': 'video',
                        'mime_type': 'video/mp4',
                        'size': None,
                        'preview_path': None,
                        'external_video': True
                    }
                    files.append(file_info)
            
            # Find audio
            for audio in soup.find_all('audio'):
                src = audio.get('src')
                if src:
                    file_info = self._analyze_file_url(urljoin(url, src), 'audio')
                    if file_info:
                        files.append(file_info)
                
                # Check source tags within audio
                for source in audio.find_all('source'):
                    src = source.get('src')
                    if src:
                        file_info = self._analyze_file_url(urljoin(url, src), 'audio')
                        if file_info:
                            files.append(file_info)
            
            # Find all links and scan for video URLs
            for link in soup.find_all('a', href=True):
                href = link.get('href')
                if href:
                    full_url = urljoin(url, href)
                    file_info = self._analyze_file_url(full_url)
                    if file_info:
                        files.append(file_info)
            
            # Enhanced video URL detection - scan all script tags for video URLs
            for script in soup.find_all('script'):
                script_content = script.string
                if script_content:
                    # Look for common video URL patterns in JavaScript
                    import re
                    video_patterns = [
                        # Direct video file URLs
                        r'["\'](https?://[^"\']+\.(?:mp4|webm|avi|mov|flv|mkv|m4v|3gp|ogv|mpg|mpeg|ts|mts|m3u8)[^"\']*)["\']',
                        # Video URLs with 'video' in path
                        r'["\'](https?://[^"\']*video[^"\']*\.(?:mp4|webm|avi|mov|flv|mkv|m4v|3gp|ogv|mpg|mpeg|ts|mts|m3u8)[^"\']*)["\']',
                        # Common video URL patterns in JavaScript
                        r'src:\s*["\'](https?://[^"\']+\.(?:mp4|webm|avi|mov|flv|mkv|m4v|3gp|ogv|mpg|mpeg|ts|mts|m3u8)[^"\']*)["\']',
                        r'url:\s*["\'](https?://[^"\']+\.(?:mp4|webm|avi|mov|flv|mkv|m4v|3gp|ogv|mpg|mpeg|ts|mts|m3u8)[^"\']*)["\']',
                        r'file:\s*["\'](https?://[^"\']+\.(?:mp4|webm|avi|mov|flv|mkv|m4v|3gp|ogv|mpg|mpeg|ts|mts|m3u8)[^"\']*)["\']',
                        r'source:\s*["\'](https?://[^"\']+\.(?:mp4|webm|avi|mov|flv|mkv|m4v|3gp|ogv|mpg|mpeg|ts|mts|m3u8)[^"\']*)["\']',
                        r'href:\s*["\'](https?://[^"\']+\.(?:mp4|webm|avi|mov|flv|mkv|m4v|3gp|ogv|mpg|mpeg|ts|mts|m3u8)[^"\']*)["\']',
                        # HLS and streaming patterns
                        r'["\'](https?://[^"\']*\.m3u8[^"\']*)["\']',
                        r'["\'](https?://[^"\']*stream[^"\']*)["\']',
                        r'["\'](https?://[^"\']*manifest[^"\']*)["\']',
                        # CDN and media server patterns
                        r'["\'](https?://[^"\']*cdn[^"\']*\.(?:mp4|webm|avi|mov)[^"\']*)["\']',
                        r'["\'](https?://[^"\']*media[^"\']*\.(?:mp4|webm|avi|mov)[^"\']*)["\']',
                        r'["\'](https?://[^"\']*assets[^"\']*\.(?:mp4|webm|avi|mov)[^"\']*)["\']',
                    ]
                    
                    for pattern in video_patterns:
                        matches = re.findall(pattern, script_content, re.IGNORECASE)
                        for match in matches:
                            try:
                                # Clean up the URL
                                video_url = match.strip()
                                if video_url.startswith('http'):
                                    file_info = self._analyze_file_url(video_url, 'video')
                                    if file_info:
                                        files.append(file_info)
                            except:
                                continue
            
            # Scan for JSON-LD structured data with video content
            for script in soup.find_all('script', type='application/ld+json'):
                try:
                    import json
                    data = json.loads(script.string)
                    
                    def extract_video_urls(obj):
                        video_urls = []
                        if isinstance(obj, dict):
                            for key, value in obj.items():
                                if key.lower() in ['contenturl', 'url', 'embedurl'] and isinstance(value, str) and any(ext in value.lower() for ext in ['.mp4', '.webm', '.avi', '.mov']):
                                    video_urls.append(value)
                                elif isinstance(value, (dict, list)):
                                    video_urls.extend(extract_video_urls(value))
                        elif isinstance(obj, list):
                            for item in obj:
                                video_urls.extend(extract_video_urls(item))
                        return video_urls
                    
                    video_urls = extract_video_urls(data)
                    for video_url in video_urls:
                        file_info = self._analyze_file_url(video_url, 'video')
                        if file_info:
                            files.append(file_info)
                except:
                    continue
            
            # Scan all data attributes for video URLs
            for element in soup.find_all(attrs={'data-src': True}):
                data_src = element.get('data-src')
                if data_src and any(ext in data_src.lower() for ext in ['.mp4', '.webm', '.avi', '.mov', '.flv', '.mkv']):
                    full_url = urljoin(url, data_src)
                    file_info = self._analyze_file_url(full_url, 'video')
                    if file_info:
                        files.append(file_info)
            
            # Check for data-video, data-url, and similar attributes
            for element in soup.find_all():
                for attr_name, attr_value in element.attrs.items():
                    if attr_name.startswith('data-') and isinstance(attr_value, str):
                        if any(ext in attr_value.lower() for ext in ['.mp4', '.webm', '.avi', '.mov', '.flv', '.mkv', '.m4v']):
                            full_url = urljoin(url, attr_value)
                            file_info = self._analyze_file_url(full_url, 'video')
                            if file_info:
                                files.append(file_info)
            
            # Scan entire page source with regex for any video URLs that might be missed
            page_source = response.text
            import re
            
            # More aggressive video URL patterns
            comprehensive_patterns = [
                r'(https?://[^\s"\'<>]+\.(?:mp4|webm|avi|mov|flv|mkv|m4v|3gp|ogv|mpg|mpeg|ts|mts|m3u8)(?:\?[^\s"\'<>]*)?)',
                r'(https?://[^\s"\'<>]*(?:video|stream|media|cdn|assets)[^\s"\'<>]*\.(?:mp4|webm|avi|mov)(?:\?[^\s"\'<>]*)?)',
                r'(https?://[^\s"\'<>]*\.m3u8(?:\?[^\s"\'<>]*)?)',
                r'(https?://[^\s"\'<>]*(?:manifest|playlist)\.m3u8(?:\?[^\s"\'<>]*)?)',
            ]
            
            for pattern in comprehensive_patterns:
                matches = re.findall(pattern, page_source, re.IGNORECASE)
                for match in matches:
                    try:
                        video_url = match.strip()
                        if video_url and video_url.startswith('http'):
                            # Basic validation - check if URL looks legitimate
                            if len(video_url) > 10 and not any(invalid in video_url.lower() for invalid in ['javascript:', 'data:', 'blob:']):
                                file_info = self._analyze_file_url(video_url, 'video')
                                if file_info:
                                    files.append(file_info)
                    except:
                        continue
            
            # Remove duplicates
            seen_urls = set()
            unique_files = []
            for file_info in files:
                if file_info['url'] not in seen_urls:
                    seen_urls.add(file_info['url'])
                    unique_files.append(file_info)
            
            return unique_files
            
        except Exception as e:
            logging.error(f"Error analyzing URL {url}: {str(e)}")
            raise e
    
    def _analyze_file_url(self, file_url, suggested_type=None):
        """Analyze a specific file URL and return file information"""
        try:
            parsed_url = urlparse(file_url)
            filename = os.path.basename(parsed_url.path)
            
            if not filename:
                filename = 'unknown_file'
            
            # Get file extension
            _, ext = os.path.splitext(filename.lower())
            
            # Determine file type
            file_type = suggested_type or self._get_file_type(ext, file_url)
            
            if file_type == 'unknown':
                return None
            
            # Get file metadata
            try:
                head_response = self.session.head(file_url, timeout=10)
                file_size = head_response.headers.get('content-length')
                mime_type = head_response.headers.get('content-type')
                
                if file_size:
                    file_size = int(file_size)
                
            except:
                file_size = None
                mime_type = mimetypes.guess_type(file_url)[0]
            
            file_info = {
                'filename': filename,
                'url': file_url,
                'type': file_type,
                'mime_type': mime_type,
                'size': file_size,
                'preview_path': None
            }
            
            # Generate preview for images
            if file_type == 'image':
                preview_path = self._generate_image_preview(file_url, filename)
                file_info['preview_path'] = preview_path
            
            return file_info
            
        except Exception as e:
            logging.error(f"Error analyzing file URL {file_url}: {str(e)}")
            return None
    
    def _get_file_type(self, extension, url):
        """Determine file type based on extension and URL"""
        if extension in self.image_extensions:
            return 'image'
        elif extension in self.video_extensions:
            return 'video'
        elif extension in self.audio_extensions:
            return 'audio'
        elif extension in self.document_extensions:
            return 'document'
        else:
            # Enhanced video detection based on URL patterns
            url_lower = url.lower()
            for pattern in self.video_url_patterns:
                if pattern in url_lower:
                    return 'video'
            
            # Try to determine from URL or mime type
            mime_type, _ = mimetypes.guess_type(url)
            if mime_type:
                if mime_type.startswith('image/'):
                    return 'image'
                elif mime_type.startswith('video/'):
                    return 'video'
                elif mime_type.startswith('audio/'):
                    return 'audio'
                elif mime_type in ['application/pdf', 'application/msword', 'text/plain']:
                    return 'document'
            
            # Additional video URL heuristics
            if any(keyword in url_lower for keyword in ['video', 'stream', 'media', 'mp4', 'webm', 'avi', 'mov']):
                return 'video'
            
            return 'other'
    
    def _generate_image_preview(self, image_url, filename):
        """Generate a thumbnail preview for an image"""
        try:
            response = self.session.get(image_url, timeout=30)
            response.raise_for_status()
            
            # Create unique preview filename
            preview_filename = f"preview_{str(uuid.uuid4())[:8]}_{filename}"
            preview_path = os.path.join(app.config['PREVIEW_FOLDER'], preview_filename)
            
            # Open and resize image
            with Image.open(requests.get(image_url, stream=True).raw) as img:
                # Convert to RGB if necessary
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                # Create larger, higher quality thumbnail for better preview
                img.thumbnail((400, 400), Image.Resampling.LANCZOS)
                img.save(preview_path, 'JPEG', quality=95)
            
            return preview_path
            
        except Exception as e:
            logging.error(f"Error generating preview for {image_url}: {str(e)}")
            return None
