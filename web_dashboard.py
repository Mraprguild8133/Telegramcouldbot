#!/usr/bin/env python3
"""
Web Dashboard for Telegram File Bot
A simple web interface to monitor bot status and file statistics
"""

from flask import Flask, render_template, jsonify
import json
import os
from datetime import datetime
import asyncio
import aiohttp

app = Flask(__name__)

class BotMonitor:
    def __init__(self):
        self.files_db = "files.json"
    
    def load_files(self):
        """Load files database"""
        try:
            if os.path.exists(self.files_db):
                with open(self.files_db, 'r') as f:
                    return json.load(f)
        except:
            pass
        return {}
    
    def get_stats(self):
        """Get bot statistics"""
        files = self.load_files()
        
        total_files = len(files)
        total_size = sum(file_data.get('file_size', 0) for file_data in files.values())
        
        # File type breakdown
        file_types = {}
        for file_data in files.values():
            file_type = file_data.get('file_type', 'unknown')
            file_types[file_type] = file_types.get(file_type, 0) + 1
        
        # Recent uploads (last 24 hours)
        recent_count = 0
        now = datetime.now()
        for file_data in files.values():
            try:
                upload_date = datetime.fromisoformat(file_data.get('upload_date', ''))
                if (now - upload_date).days == 0:
                    recent_count += 1
            except:
                pass
        
        return {
            'total_files': total_files,
            'total_size': self.format_bytes(total_size),
            'file_types': file_types,
            'recent_uploads': recent_count,
            'wasabi_region': os.getenv('WASABI_REGION', 'Unknown'),
            'channel_id': os.getenv('STORAGE_CHANNEL_ID', 'Not configured')
        }
    
    def format_bytes(self, bytes_size):
        """Format bytes to human readable"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} PB"
    
    def get_recent_files(self, limit=10):
        """Get recent files"""
        files = self.load_files()
        file_list = []
        
        for file_id, file_data in files.items():
            file_list.append({
                'file_id': file_id,
                'name': file_data.get('file_name', 'Unknown'),
                'size': self.format_bytes(file_data.get('file_size', 0)),
                'type': file_data.get('file_type', 'unknown'),
                'date': file_data.get('upload_date', ''),
                'user_id': file_data.get('user_id', 0)
            })
        
        # Sort by date, most recent first
        file_list.sort(key=lambda x: x['date'], reverse=True)
        return file_list[:limit]

monitor = BotMonitor()

@app.route('/')
def dashboard():
    """Main dashboard"""
    stats = monitor.get_stats()
    recent_files = monitor.get_recent_files()
    
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🚀 Telegram File Bot Dashboard</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}
        
        .header {{
            text-align: center;
            color: white;
            margin-bottom: 30px;
        }}
        
        .header h1 {{
            font-size: 2.5rem;
            margin-bottom: 10px;
        }}
        
        .header p {{
            font-size: 1.1rem;
            opacity: 0.9;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .stat-card {{
            background: white;
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            text-align: center;
            transition: transform 0.3s ease;
        }}
        
        .stat-card:hover {{
            transform: translateY(-5px);
        }}
        
        .stat-icon {{
            font-size: 2.5rem;
            margin-bottom: 15px;
        }}
        
        .stat-number {{
            font-size: 2rem;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 5px;
        }}
        
        .stat-label {{
            color: #666;
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .section {{
            background: white;
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        }}
        
        .section h2 {{
            margin-bottom: 20px;
            color: #333;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }}
        
        .file-list {{
            display: grid;
            gap: 15px;
        }}
        
        .file-item {{
            display: flex;
            align-items: center;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 10px;
            border-left: 4px solid #667eea;
        }}
        
        .file-icon {{
            font-size: 1.5rem;
            margin-right: 15px;
        }}
        
        .file-info {{
            flex: 1;
        }}
        
        .file-name {{
            font-weight: bold;
            margin-bottom: 5px;
        }}
        
        .file-meta {{
            color: #666;
            font-size: 0.9rem;
        }}
        
        .config-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }}
        
        .config-item {{
            padding: 15px;
            background: #f8f9fa;
            border-radius: 10px;
            border-left: 4px solid #28a745;
        }}
        
        .config-label {{
            font-weight: bold;
            color: #333;
            margin-bottom: 5px;
        }}
        
        .config-value {{
            color: #666;
            font-family: monospace;
        }}
        
        .status-indicator {{
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #28a745;
            margin-right: 10px;
            animation: pulse 2s infinite;
        }}
        
        @keyframes pulse {{
            0% {{ opacity: 1; }}
            50% {{ opacity: 0.5; }}
            100% {{ opacity: 1; }}
        }}
        
        .refresh-btn {{
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 25px;
            cursor: pointer;
            font-size: 1rem;
            transition: background 0.3s ease;
        }}
        
        .refresh-btn:hover {{
            background: #5a6fd8;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Telegram File Bot Dashboard</h1>
            <p><span class="status-indicator"></span>Bot is running and operational</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-icon">📁</div>
                <div class="stat-number">{stats['total_files']}</div>
                <div class="stat-label">Total Files</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-icon">💾</div>
                <div class="stat-number">{stats['total_size']}</div>
                <div class="stat-label">Storage Used</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-icon">⚡</div>
                <div class="stat-number">{stats['recent_uploads']}</div>
                <div class="stat-label">Today's Uploads</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-icon">🌐</div>
                <div class="stat-number">{len(stats['file_types'])}</div>
                <div class="stat-label">File Types</div>
            </div>
        </div>
        
        <div class="section">
            <h2>📊 Recent Files</h2>
            <div class="file-list">
                {"".join([f'''
                <div class="file-item">
                    <div class="file-icon">{'🎥' if file['type'] == 'video' else '🎵' if file['type'] == 'audio' else '🖼️' if file['type'] == 'photo' else '📄'}</div>
                    <div class="file-info">
                        <div class="file-name">{file['name'][:50]}{'...' if len(file['name']) > 50 else ''}</div>
                        <div class="file-meta">{file['size']} • {file['type'].title()} • ID: {file['file_id']}</div>
                    </div>
                </div>
                ''' for file in recent_files]) if recent_files else '<p>No files uploaded yet.</p>'}
            </div>
        </div>
        
        <div class="section">
            <h2>⚙️ Configuration</h2>
            <div class="config-grid">
                <div class="config-item">
                    <div class="config-label">Wasabi Region</div>
                    <div class="config-value">{stats['wasabi_region']}</div>
                </div>
                
                <div class="config-item">
                    <div class="config-label">Backup Channel</div>
                    <div class="config-value">{stats['channel_id']}</div>
                </div>
                
                <div class="config-item">
                    <div class="config-label">File Size Limit</div>
                    <div class="config-value">4 GB</div>
                </div>
                
                <div class="config-item">
                    <div class="config-label">Streaming Expiry</div>
                    <div class="config-value">24 hours</div>
                </div>
            </div>
        </div>
        
        <div class="section">
            <h2>📈 File Type Distribution</h2>
            <div class="config-grid">
                {"".join([f'''
                <div class="config-item">
                    <div class="config-label">{file_type.title()} Files</div>
                    <div class="config-value">{count} files</div>
                </div>
                ''' for file_type, count in stats['file_types'].items()]) if stats['file_types'] else '<p>No file types to display.</p>'}
            </div>
        </div>
        
        <div style="text-align: center; margin-top: 30px;">
            <button class="refresh-btn" onclick="location.reload()">🔄 Refresh Dashboard</button>
        </div>
    </div>
    
    <script>
        // Auto-refresh every 30 seconds
        setTimeout(() => location.reload(), 30000);
    </script>
</body>
</html>
    """

@app.route('/api/stats')
def api_stats():
    """API endpoint for statistics"""
    return jsonify(monitor.get_stats())

@app.route('/api/files')
def api_files():
    """API endpoint for recent files"""
    return jsonify(monitor.get_recent_files())

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'bot': 'running',
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)