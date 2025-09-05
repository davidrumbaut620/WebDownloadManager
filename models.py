from app import db
from datetime import datetime
from sqlalchemy import Text

class AnalysisSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(2048), nullable=False)
    session_id = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='pending')  # pending, completed, error
    error_message = db.Column(Text)
    
    # Relationship to detected files
    files = db.relationship('DetectedFile', backref='session', lazy=True, cascade='all, delete-orphan')

class DetectedFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('analysis_session.id'), nullable=False)
    filename = db.Column(db.String(512), nullable=False)
    url = db.Column(db.String(2048), nullable=False)
    file_type = db.Column(db.String(50), nullable=False)  # image, video, audio, document, other
    mime_type = db.Column(db.String(100))
    file_size = db.Column(db.BigInteger)  # Size in bytes
    preview_path = db.Column(db.String(512))  # Path to preview file
    download_status = db.Column(db.String(50), default='pending')  # pending, downloading, completed, error
    download_path = db.Column(db.String(512))  # Path to downloaded file
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def get_file_size_formatted(self):
        """Return formatted file size"""
        if not self.file_size:
            return "Unknown"
        
        size = self.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
