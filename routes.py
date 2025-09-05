from flask import render_template, request, redirect, url_for, flash, session, jsonify, send_file, abort
from app import app, db
from models import AnalysisSession, DetectedFile
from file_analyzer import FileAnalyzer
from downloader import FileDownloader
import os
import uuid
from urllib.parse import urlparse
import logging

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze_url():
    url = request.form.get('url', '').strip()
    
    if not url:
        flash('Please enter a valid URL', 'error')
        return redirect(url_for('index'))
    
    # Validate URL format
    parsed_url = urlparse(url)
    if not parsed_url.scheme or not parsed_url.netloc:
        flash('Please enter a valid URL with http:// or https://', 'error')
        return redirect(url_for('index'))
    
    # Generate session ID if not exists
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    
    try:
        # Create analysis session
        analysis = AnalysisSession(
            url=url,
            session_id=session['session_id'],
            status='pending'
        )
        db.session.add(analysis)
        db.session.commit()
        
        # Analyze the URL for downloadable files
        analyzer = FileAnalyzer()
        files = analyzer.analyze_url(url)
        
        # Save detected files
        for file_info in files:
            detected_file = DetectedFile(
                session_id=analysis.id,
                filename=file_info['filename'],
                url=file_info['url'],
                file_type=file_info['type'],
                mime_type=file_info.get('mime_type'),
                file_size=file_info.get('size'),
                preview_path=file_info.get('preview_path')
            )
            db.session.add(detected_file)
        
        # Update analysis status
        analysis.status = 'completed'
        db.session.commit()
        
        flash(f'Found {len(files)} downloadable files', 'success')
        return redirect(url_for('results', analysis_id=analysis.id))
        
    except Exception as e:
        logging.error(f"Error analyzing URL: {str(e)}")
        if 'analysis' in locals():
            analysis.status = 'error'
            analysis.error_message = str(e)
            db.session.commit()
        flash(f'Error analyzing URL: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/results/<int:analysis_id>')
def results(analysis_id):
    analysis = AnalysisSession.query.get_or_404(analysis_id)
    
    # Check if this analysis belongs to current session
    if analysis.session_id != session.get('session_id'):
        abort(403)
    
    files = DetectedFile.query.filter_by(session_id=analysis_id).all()
    
    # Group files by type
    grouped_files = {
        'images': [f for f in files if f.file_type == 'image'],
        'videos': [f for f in files if f.file_type == 'video'],
        'audio': [f for f in files if f.file_type == 'audio'],
        'documents': [f for f in files if f.file_type == 'document'],
        'other': [f for f in files if f.file_type == 'other']
    }
    
    return render_template('results.html', analysis=analysis, grouped_files=grouped_files)

@app.route('/download/<int:file_id>')
def download_file(file_id):
    detected_file = DetectedFile.query.get_or_404(file_id)
    
    # Check if this file belongs to current session
    analysis = AnalysisSession.query.get(detected_file.session_id)
    if analysis.session_id != session.get('session_id'):
        abort(403)
    
    try:
        downloader = FileDownloader()
        file_path = downloader.download_file(detected_file)
        
        if file_path and os.path.exists(file_path):
            return send_file(file_path, as_attachment=True, download_name=detected_file.filename)
        else:
            flash('Error downloading file', 'error')
            return redirect(url_for('results', analysis_id=detected_file.session_id))
            
    except Exception as e:
        logging.error(f"Error downloading file: {str(e)}")
        flash(f'Error downloading file: {str(e)}', 'error')
        return redirect(url_for('results', analysis_id=detected_file.session_id))

@app.route('/preview/<int:file_id>')
def preview_file(file_id):
    detected_file = DetectedFile.query.get_or_404(file_id)
    
    # Check if this file belongs to current session
    analysis = AnalysisSession.query.get(detected_file.session_id)
    if analysis.session_id != session.get('session_id'):
        abort(403)
    
    if detected_file.preview_path and os.path.exists(detected_file.preview_path):
        return send_file(detected_file.preview_path)
    else:
        # Return placeholder image
        abort(404)

@app.route('/download_all/<int:analysis_id>')
def download_all(analysis_id):
    analysis = AnalysisSession.query.get_or_404(analysis_id)
    
    # Check if this analysis belongs to current session
    if analysis.session_id != session.get('session_id'):
        abort(403)
    
    files = DetectedFile.query.filter_by(session_id=analysis_id).all()
    
    try:
        downloader = FileDownloader()
        zip_path = downloader.create_zip_download(files, analysis.url)
        
        if zip_path and os.path.exists(zip_path):
            return send_file(zip_path, as_attachment=True, download_name=f"downloaded_files_{analysis_id}.zip")
        else:
            flash('Error creating download archive', 'error')
            return redirect(url_for('results', analysis_id=analysis_id))
            
    except Exception as e:
        logging.error(f"Error creating zip download: {str(e)}")
        flash(f'Error creating download archive: {str(e)}', 'error')
        return redirect(url_for('results', analysis_id=analysis_id))

@app.errorhandler(404)
def not_found_error(error):
    return render_template('base.html', error_message="Page not found"), 404

@app.errorhandler(403)
def forbidden_error(error):
    return render_template('base.html', error_message="Access forbidden"), 403

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('base.html', error_message="Internal server error"), 500
