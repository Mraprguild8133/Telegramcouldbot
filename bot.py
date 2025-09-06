#!/usr/bin/env python3
"""
Telegram File Bot with Wasabi Cloud Storage
A comprehensive file storage and streaming solution with 4GB support,
MX Player integration, and mobile optimization.
"""

import asyncio
import os
import json
import hashlib
import mimetypes
from datetime import datetime
from typing import Optional, Dict, Any, List
import logging

import boto3
from botocore.exceptions import ClientError
import aiofiles
from pyrogram import filters
from pyrogram.client import Client
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, Document, Video, Audio, Photo
)
from dotenv import load_dotenv

# Add for Render support
from aiohttp import web
import threading

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class WasabiStorage:
    """Wasabi cloud storage client for file operations"""
    
    def __init__(self):
        self.access_key = os.getenv('WASABI_ACCESS_KEY')
        self.secret_key = os.getenv('WASABI_SECRET_KEY')
        self.bucket_name = os.getenv('WASABI_BUCKET')
        self.region = os.getenv('WASABI_REGION', 'us-east-1')
        
        # Clean up region if it has s3. prefix
        if self.region.startswith('s3.'):
            self.region = self.region.replace('s3.', '')
        
        if not all([self.access_key, self.secret_key, self.bucket_name]):
            raise ValueError("Missing required Wasabi credentials")
        
        # Initialize boto3 client for Wasabi
        self.s3_client = boto3.client(
            's3',
            endpoint_url=f'https://s3.{self.region}.wasabisys.com',
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region
        )
    
    async def upload_file(self, file_path: str, key: str, progress_callback=None) -> str:
        """Upload file to Wasabi storage"""
        try:
            # Get file size for progress tracking
            file_size = os.path.getsize(file_path)
            uploaded = 0
            last_reported = 0
            
            def upload_callback(bytes_transferred):
                nonlocal uploaded, last_reported
                uploaded += bytes_transferred
                if progress_callback:
                    progress = (uploaded / file_size) * 100
                    # Only report progress every 5% to avoid too many calls
                    if progress - last_reported >= 5 or progress >= 100:
                        last_reported = progress
                        # Schedule the async callback safely
                        try:
                            import asyncio
                            loop = asyncio.get_running_loop()
                            loop.call_soon_threadsafe(
                                lambda: asyncio.create_task(progress_callback(progress))
                            )
                        except:
                            pass  # Ignore if no event loop
            
            # Upload file in thread executor to avoid blocking
            import asyncio
            import concurrent.futures
            
            def sync_upload():
                self.s3_client.upload_file(
                    file_path, 
                    self.bucket_name, 
                    key,
                    Callback=upload_callback
                )
            
            # Run upload in thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, sync_upload)
            
            # Generate download URL
            url = f"https://s3.{self.region}.wasabisys.com/{self.bucket_name}/{key}"
            return url
            
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            raise
    
    async def generate_presigned_url(self, key: str, expiration: int = 3600) -> str:
        """Generate presigned URL for streaming"""
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': key},
                ExpiresIn=expiration
            )
            return url
        except Exception as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            raise
    
    async def delete_file(self, key: str) -> bool:
        """Delete file from Wasabi storage"""
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
            return True
        except Exception as e:
            logger.error(f"Failed to delete file: {e}")
            return False
    
    async def test_connection(self) -> bool:
        """Test Wasabi connection"""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False

class FileManager:
    """File management and metadata storage"""
    
    def __init__(self):
        self.files_db = "files.json"
        self.files = self.load_files()
    
    def load_files(self) -> Dict[str, Any]:
        """Load files database"""
        try:
            if os.path.exists(self.files_db):
                with open(self.files_db, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load files database: {e}")
        return {}
    
    def save_files(self):
        """Save files database"""
        try:
            with open(self.files_db, 'w') as f:
                json.dump(self.files, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save files database: {e}")
    
    def add_file(self, file_id: str, metadata: Dict[str, Any]):
        """Add file to database"""
        self.files[file_id] = metadata
        self.save_files()
    
    def get_file(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Get file metadata"""
        return self.files.get(file_id)
    
    def list_files(self, user_id: int) -> List[Dict[str, Any]]:
        """List files for user"""
        user_files = []
        for file_id, metadata in self.files.items():
            if metadata.get('user_id') == user_id:
                user_files.append({**metadata, 'file_id': file_id})
        return sorted(user_files, key=lambda x: x.get('upload_date', ''), reverse=True)
    
    def delete_file(self, file_id: str) -> bool:
        """Delete file from database"""
        if file_id in self.files:
            del self.files[file_id]
            self.save_files()
            return True
        return False

class TelegramFileBot:
    """Main bot class with all functionality"""
    
    def __init__(self):
        # Initialize Telegram client
        api_id = os.getenv('API_ID')
        api_hash = os.getenv('API_HASH')
        bot_token = os.getenv('BOT_TOKEN')
        
        if not all([api_id, api_hash, bot_token]):
            raise ValueError("Missing required Telegram credentials")
        
        self.app = Client(
            "filebot",
            api_id=int(api_id) if api_id else 0,
            api_hash=str(api_hash) if api_hash else "",
            bot_token=str(bot_token) if bot_token else ""
        )
        
        # Initialize storage and file manager
        self.storage = WasabiStorage()
        self.file_manager = FileManager()
        
        # Storage channel for backup
        self.storage_channel_id = os.getenv('STORAGE_CHANNEL_ID')
        
        # Web server for Render
        self.web_app = web.Application()
        self.setup_web_routes()
        
        # Register handlers
        self.register_handlers()
    
    def setup_web_routes(self):
        """Setup web routes for Render"""
        self.web_app.router.add_get('/', self.handle_web_root)
        self.web_app.router.add_get('/health', self.handle_health_check)
    
    async def handle_web_root(self, request):
        """Handle web root request"""
        return web.Response(text="Telegram File Bot is running! Use /start in Telegram to begin.")
    
    async def handle_health_check(self, request):
        """Handle health check request"""
        return web.json_response({"status": "ok", "bot": "running"})
    
    def register_handlers(self):
        """Register all bot handlers"""
        
        @self.app.on_message(filters.command("start"))
        async def start_command(client, message: Message):
            await self.handle_start(message)
        
        @self.app.on_message(filters.command("help"))
        async def help_command(client, message: Message):
            await self.handle_help(message)
        
        @self.app.on_message(filters.command("upload"))
        async def upload_command(client, message: Message):
            await self.handle_upload_command(message)
        
        @self.app.on_message(filters.command("download"))
        async def download_command(client, message: Message):
            await self.handle_download(message)
        
        @self.app.on_message(filters.command("list"))
        async def list_command(client, message: Message):
            await self.handle_list(message)
        
        @self.app.on_message(filters.command("stream"))
        async def stream_command(client, message: Message):
            await self.handle_stream(message)
        
        @self.app.on_message(filters.command("web"))
        async def web_command(client, message: Message):
            await self.handle_web_player(message)
        
        @self.app.on_message(filters.command("setchannel"))
        async def setchannel_command(client, message: Message):
            await self.handle_set_channel(message)
        
        @self.app.on_message(filters.command("test"))
        async def test_command(client, message: Message):
            await self.handle_test(message)
        
        # Handle file uploads
        @self.app.on_message(filters.document | filters.video | filters.audio | filters.photo)
        async def handle_file_upload(client, message: Message):
            await self.handle_file_message(message)
        
        # Handle callback queries
        @self.app.on_callback_query()
        async def handle_callback(client, query: CallbackQuery):
            await self.handle_callback_query(query)
    
    async def handle_start(self, message: Message):
        """Handle /start command"""
        welcome_text = """
🚀 **ULTRA-FAST FILE BOT** ⚡

╭──────────── **FEATURES** ────────────╮
│ 🎯 **4GB** Ultra Files • ☁️ **Cloud** Storage   │
│ 🎬 **Instant** Streaming • 📱 **Mobile** Ready  │
│ 🔥 **MX Player** • 🎯 **VLC** • 🌐 **Web**      │
│ 📊 **Real-time** Progress • 🛡️ **Secure**       │
╰─────────────────────────────────────╯

🎮 **POWER COMMANDS:**
⚡ `/upload` • 📋 `/list` • 🎬 `/stream <id>`
📥 `/download <id>` • 🌐 `/web <id>` • ⚙️ `/test`

🔥 **INSTANT UPLOAD:** Drop any file here!

💡 **Pro Tip:** Files up to 4GB with lightning speeds!
        """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Ultra Upload", callback_data="upload_file")],
            [InlineKeyboardButton("📁 My Cloud Files", callback_data="list_files")],
            [InlineKeyboardButton("⚡ Speed Test", callback_data="test_connection")]
        ])
        
        await message.reply_text(welcome_text, reply_markup=keyboard)
    
    async def handle_help(self, message: Message):
        """Handle /help command"""
        help_text = """
📖 **Detailed Help & Commands**

**📤 Upload Commands:**
• `/upload` - Start upload process
• Send any file directly to upload

**📥 Download Commands:**
• `/download <file_id>` - Get download link
• `/stream <file_id>` - Get streaming URL
• `/web <file_id>` - Open web player

**📱 Player Integration:**
• **MX Player:** Optimized for Android devices
• **VLC Player:** Cross-platform support
• **Web Player:** Browser-based streaming

**📋 Management Commands:**
• `/list` - Show all your uploaded files
• `/setchannel <channel_id>` - Set Telegram backup channel
• `/test` - Test Wasabi storage connection

**💡 Tips:**
• Files up to 4GB are supported
• All files are stored securely in Wasabi cloud
• Streaming works on mobile and desktop
• Progress tracking for large uploads
• Automatic backup to Telegram channels (optional)

**🔗 Direct Streaming URLs:**
Files can be streamed directly in supported players with one-click integration.
        """
        
        await message.reply_text(help_text)
    
    async def handle_upload_command(self, message: Message):
        """Handle /upload command"""
        upload_text = """
📤 **File Upload**

Please send the file you want to upload. Supported formats:

📄 **Documents:** PDF, DOC, TXT, ZIP, etc.
🎥 **Videos:** MP4, AVI, MKV, MOV, etc.
🎵 **Audio:** MP3, WAV, FLAC, AAC, etc.
🖼️ **Images:** JPG, PNG, GIF, WEBP, etc.

**📊 Upload Limits:**
• Maximum file size: 4GB
• Progress tracking enabled
• Cloud storage backup
• Automatic streaming optimization

Just send your file as a message!
        """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 View My Files", callback_data="list_files")]
        ])
        
        await message.reply_text(upload_text, reply_markup=keyboard)
    
    async def handle_file_message(self, message: Message):
        """Handle file upload messages"""
        # Determine file type and get file info
        file_obj = None
        file_type = "document"
        
        if message.document:
            file_obj = message.document
            file_type = "document"
        elif message.video:
            file_obj = message.video
            file_type = "video"
        elif message.audio:
            file_obj = message.audio
            file_type = "audio"
        elif message.photo:
            file_obj = message.photo
            file_type = "photo"
        
        if not file_obj:
            await message.reply_text("❌ No valid file found!")
            return
        
        # Check file size (4GB limit)
        file_size = getattr(file_obj, 'file_size', 0)
        if file_size > 4 * 1024 * 1024 * 1024:  # 4GB
            await message.reply_text("❌ File too large! Maximum size is 4GB.")
            return
        
        # Start upload process
        progress_msg = await message.reply_text("📤 Starting upload...", quote=True)
        temp_file = None
        
        try:
            # Create temp directory if it doesn't exist
            import tempfile
            import os
            temp_dir = "temp_files"
            os.makedirs(temp_dir, exist_ok=True)
            
            # Create safe temp file path
            safe_file_id = file_obj.file_id.replace("/", "_").replace("\\", "_")
            temp_file = os.path.join(temp_dir, f"temp_{safe_file_id}")
            
            last_progress = 0
            async def download_progress(current, total):
                progress = (current / total) * 50  # First 50% for download
                # Only update if progress changed by at least 5%
                nonlocal last_progress
                if abs(progress - last_progress) >= 5 or progress == 0 or progress >= 50:
                    last_progress = progress
                    try:
                        await progress_msg.edit_text(
                            f"⚡ **Fast Download** {progress:.0f}%\n{'▓' * int(progress/5)}{'░' * (10-int(progress/5))}"
                        )
                    except:
                        pass  # Ignore edit errors
            
            # Download file directly with our temp name
            await message.download(file_name=temp_file, progress=download_progress)
            
            # Generate unique file ID and metadata
            file_id = hashlib.md5(f"{file_obj.file_id}{datetime.now()}".encode()).hexdigest()[:16]
            file_name = getattr(file_obj, 'file_name', f"file_{file_id}")
            
            # Upload to Wasabi with improved progress
            upload_last_progress = 50
            async def upload_progress(progress):
                total_progress = 50 + (progress / 2)  # Second 50% for upload
                nonlocal upload_last_progress
                if abs(total_progress - upload_last_progress) >= 5 or total_progress >= 100:
                    upload_last_progress = total_progress
                    try:
                        bars_filled = int(total_progress/5)
                        await progress_msg.edit_text(
                            f"🚀 **Ultra Fast Upload** {total_progress:.0f}%\n{'🔥' * bars_filled}{'⭕' * (20-bars_filled)}\n💾 Optimizing for streaming..."
                        )
                    except:
                        pass  # Ignore edit errors
            
            wasabi_key = f"files/{file_id}_{file_name}"
            download_url = await self.storage.upload_file(temp_file, wasabi_key, upload_progress)
            
            # Store metadata
            metadata = {
                'file_name': file_name,
                'file_size': file_size,
                'file_type': file_type,
                'mime_type': getattr(file_obj, 'mime_type', 'application/octet-stream'),
                'user_id': message.from_user.id,
                'upload_date': datetime.now().isoformat(),
                'download_url': download_url,
                'wasabi_key': wasabi_key,
                'telegram_file_id': file_obj.file_id
            }
            
            # Backup to Telegram channel if configured
            if self.storage_channel_id:
                try:
                    # Make sure bot is added to the channel first
                    channel_id = int(self.storage_channel_id)
                    backup_msg = await self.app.send_document(
                        chat_id=channel_id,
                        document=temp_file,
                        caption=f"Backup: {file_name}\nFile ID: {file_id}"
                    )
                    metadata['backup_message_id'] = backup_msg.id
                    logger.info(f"File backed up to channel: {channel_id}")
                except Exception as e:
                    logger.warning(f"Backup to channel failed (bot may not be admin): {e}")
                    # Continue without backup - not critical for main functionality
            
            self.file_manager.add_file(file_id, metadata)
            
            # Clean up temp file
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    logger.info(f"Successfully cleaned up temp file: {temp_file}")
                except Exception as cleanup_error:
                    logger.error(f"Failed to cleanup temp file: {cleanup_error}")
            
            # Modern success message with enhanced styling
            success_text = f"""
🎉 **UPLOAD COMPLETE!** 🚀

╭─────────────────────╮
│ 📁 **{file_name[:25]}{'...' if len(file_name) > 25 else ''}**
│ 📊 **{self.format_file_size(file_size)}** • 🆔 `{file_id}`
│ ☁️ **Cloud Storage** ✅ **Ready**
╰─────────────────────╯

⚡ **LIGHTNING FAST ACCESS:**
🎬 Stream instantly • 📱 Mobile optimized
🔗 Direct links • 🌐 Cross-platform

**💡 Quick Commands:**
`/stream {file_id}` • `/download {file_id}` • `/web {file_id}`
            """
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⚡ Download", callback_data=f"download_{file_id}")],
                [InlineKeyboardButton("🎬 Instant Stream", callback_data=f"stream_{file_id}"),
                 InlineKeyboardButton("🌐 Web Player", callback_data=f"web_{file_id}")],
                [InlineKeyboardButton("📱 MX Player", callback_data=f"mx_{file_id}"),
                 InlineKeyboardButton("🎯 VLC Player", callback_data=f"vlc_{file_id}")]
            ])
            
            await progress_msg.edit_text(success_text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            try:
                await progress_msg.edit_text(f"❌ Upload failed: {str(e)}")
            except:
                # If edit fails, send new message
                await message.reply_text(f"❌ Upload failed: {str(e)}")
            
            # Clean up temp file
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    logger.info(f"Cleaned up temp file: {temp_file}")
                except Exception as cleanup_error:
                    logger.error(f"Failed to cleanup temp file: {cleanup_error}")
    
    async def handle_download(self, message: Message):
        """Handle /download command"""
        if len(message.command) < 2:
            await message.reply_text("❌ Please provide file ID: `/download <file_id>`")
            return
        
        file_id = message.command[1]
        file_data = self.file_manager.get_file(file_id)
        
        if not file_data:
            await message.reply_text("❌ File not found!")
            return
        
        if file_data['user_id'] != message.from_user.id:
            await message.reply_text("❌ You can only download your own files!")
            return
        
        download_text = f"""
📥 **Download Ready**

📄 **File:** {file_data['file_name']}
📊 **Size:** {self.format_file_size(file_data['file_size'])}
📅 **Uploaded:** {self.format_date(file_data['upload_date'])}

🔗 **Direct Download Link:**
{file_data['download_url']}

📱 **Mobile Users:** Use the buttons below for optimized download experience.
        """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Direct Download", url=file_data['download_url'])],
            [InlineKeyboardButton("🎬 Stream Instead", callback_data=f"stream_{file_id}"),
             InlineKeyboardButton("🌐 Web Player", callback_data=f"web_{file_id}")]
        ])
        
        await message.reply_text(download_text, reply_markup=keyboard)
    
    async def handle_stream(self, message: Message):
        """Handle /stream command"""
        if len(message.command) < 2:
            await message.reply_text("❌ Please provide file ID: `/stream <file_id>`")
            return
        
        file_id = message.command[1]
        file_data = self.file_manager.get_file(file_id)
        
        if not file_data:
            await message.reply_text("❌ File not found!")
            return
        
        if file_data['user_id'] != message.from_user.id:
            await message.reply_text("❌ You can only stream your own files!")
            return
        
        try:
            # Generate streaming URL (24 hour expiry)
            streaming_url = await self.storage.generate_presigned_url(file_data['wasabi_key'], 86400)
            
            stream_text = f"""
🎬 **Streaming Ready**

📄 **File:** {file_data['file_name']}
📊 **Size:** {self.format_file_size(file_data['file_size'])}
⏱️ **Link Expires:** 24 hours

🔗 **Streaming URL:**
{streaming_url}

📱 **Quick Launch:** Use the player buttons below!
            """
            
            # Generate player-specific URLs
            mx_url = f"intent:{streaming_url}#Intent;package=com.mxtech.videoplayer.ad;type=video/*;end"
            vlc_url = f"vlc://{streaming_url}"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🎬 Direct Stream", url=streaming_url)],
                [InlineKeyboardButton("📱 MX Player", url=mx_url),
                 InlineKeyboardButton("🎯 VLC Player", url=vlc_url)],
                [InlineKeyboardButton("🌐 Web Player", callback_data=f"web_{file_id}")]
            ])
            
            await message.reply_text(stream_text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Streaming URL generation failed: {e}")
            await message.reply_text("❌ Failed to generate streaming URL!")
    
    async def handle_web_player(self, message: Message):
        """Handle /web command for web player interface"""
        if len(message.command) < 2:
            await message.reply_text("❌ Please provide file ID: `/web <file_id>`")
            return
        
        file_id = message.command[1]
        file_data = self.file_manager.get_file(file_id)
        
        if not file_data:
            await message.reply_text("❌ File not found!")
            return
        
        if file_data['user_id'] != message.from_user.id:
            await message.reply_text("❌ You can only access your own files!")
            return
        
        try:
            # Generate streaming URL for web player
            streaming_url = await self.storage.generate_presigned_url(file_data['wasabi_key'], 86400)
            
            # Create web player HTML (simplified version)
            web_player_text = f"""
🌐 **Web Player Interface**

📄 **File:** {file_data['file_name']}
📊 **Size:** {self.format_file_size(file_data['file_size'])}

**🎬 Browser Streaming:**
Compatible with all modern browsers including mobile devices.

**📱 Mobile Optimized:**
• Touch controls
• Full-screen support
• Adaptive quality
• Background playback

🔗 **Stream URL:** {streaming_url}

**💡 Tip:** Copy the URL above and paste in any media player for direct streaming!
            """
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🌐 Open in Browser", url=streaming_url)],
                [InlineKeyboardButton("📱 MX Player", callback_data=f"mx_{file_id}"),
                 InlineKeyboardButton("🎯 VLC Player", callback_data=f"vlc_{file_id}")],
                [InlineKeyboardButton("📥 Download Instead", callback_data=f"download_{file_id}")]
            ])
            
            await message.reply_text(web_player_text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Web player generation failed: {e}")
            await message.reply_text("❌ Failed to generate web player interface!")
    
    async def handle_list(self, message: Message):
        """Handle /list command"""
        user_files = self.file_manager.list_files(message.from_user.id)
        
        if not user_files:
            await message.reply_text("""
📂 **No Files Found**

You haven't uploaded any files yet!

📤 **Get Started:**
• Send any file to upload
• Use `/upload` command
• Files up to 4GB supported

💡 **Tip:** All your files are stored securely in the cloud!
            """)
            return
        
        # Show files in batches of 10
        files_text = f"📋 **Your Files** ({len(user_files)} total)\n\n"
        
        for i, file_data in enumerate(user_files[:10]):
            files_text += f"""
**{i+1}.** {file_data['file_name']}
📊 {self.format_file_size(file_data['file_size'])} • 📅 {self.format_date(file_data['upload_date'])}
🆔 `{file_data['file_id']}`

"""
        
        if len(user_files) > 10:
            files_text += f"\n... and {len(user_files) - 10} more files"
        
        files_text += "\n💡 **Quick Actions:** Use file ID with commands like `/stream <file_id>`"
        
        # Create inline keyboard for quick actions
        keyboard_buttons = []
        for i, file_data in enumerate(user_files[:5]):  # Show first 5 files as buttons
            keyboard_buttons.append([
                InlineKeyboardButton(
                    f"📄 {file_data['file_name'][:20]}...", 
                    callback_data=f"file_info_{file_data['file_id']}"
                )
            ])
        
        keyboard_buttons.append([
            InlineKeyboardButton("🔄 Refresh List", callback_data="list_files")
        ])
        
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        await message.reply_text(files_text, reply_markup=keyboard)
    
    async def handle_set_channel(self, message: Message):
        """Handle /setchannel command"""
        if len(message.command) < 2:
            await message.reply_text("""
🔧 **Set Storage Channel**

Usage: `/setchannel <channel_id>`

**Example:** `/setchannel -1001234567890`

**📋 Requirements:**
• Bot must be admin in the channel
• Channel ID should start with -100
• Used for backup storage of files

**💡 Benefits:**
• Automatic backup of uploaded files
• Additional redundancy
• Easy recovery option
            """)
            return
        
        channel_id = message.command[1]
        
        try:
            # Test if bot can access the channel
            await self.app.get_chat(int(channel_id))
            
            # Update environment (in production, this would be saved to config)
            os.environ['STORAGE_CHANNEL_ID'] = channel_id
            self.storage_channel_id = channel_id
            
            await message.reply_text(f"""
✅ **Storage Channel Set Successfully!**

🆔 **Channel ID:** `{channel_id}`
📂 **Status:** Backup enabled

**📋 Features Enabled:**
• Automatic file backup
• Redundant storage
• Easy file recovery
• Channel-based access

💡 **Note:** All future uploads will be backed up to this channel.
            """)
            
        except Exception as e:
            logger.error(f"Set channel failed: {e}")
            await message.reply_text(f"❌ Failed to set channel: {str(e)}")
    
    async def handle_test(self, message: Message):
        """Handle /test command"""
        test_msg = await message.reply_text("🔧 Testing connections...")
        
        # Test Wasabi connection
        wasabi_status = await self.storage.test_connection()
        
        # Test Telegram channel (if configured)
        channel_status = False
        if self.storage_channel_id:
            try:
                await self.app.get_chat(int(self.storage_channel_id))
                channel_status = True
            except:
                pass
        
        status_text = f"""
🔧 **Connection Test Results**

☁️ **Wasabi Storage:** {'✅ Connected' if wasabi_status else '❌ Failed'}
📱 **Telegram Channel:** {'✅ Connected' if channel_status else '❌ Not configured' if not self.storage_channel_id else '❌ Failed'}

**📊 Storage Info:**
• Bucket: {self.storage.bucket_name}
• Region: {self.storage.region}
• Files stored: {len(self.file_manager.files)}

**🔗 Status:**
{'✅ All systems operational!' if wasabi_status else '⚠️ Check your Wasabi credentials!'}
        """
        
        await test_msg.edit_text(status_text)
    
    async def handle_callback_query(self, query: CallbackQuery):
        """Handle inline keyboard callbacks"""
        data = str(query.data) if query.data else ""
        
        if data == "upload_file":
            await query.message.edit_text("""
📤 **Upload File**

Please send the file you want to upload!

**Supported formats:**
• Documents, Videos, Audio, Images
• Maximum size: 4GB
• Progress tracking enabled
            """)
        
        elif data == "list_files":
            user_files = self.file_manager.list_files(query.from_user.id)
            if not user_files:
                await query.message.edit_text("📂 No files found. Upload some files first!")
                return
            
            # Show simplified file list
            files_text = f"📋 **Your Files** ({len(user_files)} total)\n\n"
            for i, file_data in enumerate(user_files[:5]):
                files_text += f"{i+1}. {file_data['file_name']}\n"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Upload New", callback_data="upload_file")]
            ])
            
            await query.message.edit_text(files_text, reply_markup=keyboard)
        
        elif data == "test_connection":
            await query.message.edit_text("🔧 Testing connection...")
            wasabi_status = await self.storage.test_connection()
            status = "✅ Connected successfully!" if wasabi_status else "❌ Connection failed!"
            await query.message.edit_text(f"☁️ **Wasabi Storage:** {status}")
        
        elif data.startswith("download_"):
            file_id = data.replace("download_", "")
            file_data = self.file_manager.get_file(file_id)
            if file_data and file_data['user_id'] == query.from_user.id:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📥 Download", url=file_data['download_url'])]
                ])
                await query.message.edit_text(
                    f"📥 **Download:** {file_data['file_name']}\n\n🔗 Click button to download!",
                    reply_markup=keyboard
                )
        
        elif data.startswith("stream_"):
            file_id = data.replace("stream_", "")
            file_data = self.file_manager.get_file(file_id)
            if file_data and file_data['user_id'] == query.from_user.id:
                try:
                    streaming_url = await self.storage.generate_presigned_url(file_data['wasabi_key'], 86400)
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🎬 Stream", url=streaming_url)]
                    ])
                    await query.message.edit_text(
                        f"🎬 **Stream:** {file_data['file_name']}\n\n🔗 Click to stream!",
                        reply_markup=keyboard
                    )
                except Exception as e:
                    await query.message.edit_text("❌ Failed to generate streaming URL!")
        
        elif data.startswith("web_"):
            file_id = data.replace("web_", "")
            file_data = self.file_manager.get_file(file_id)
            if file_data and file_data['user_id'] == query.from_user.id:
                try:
                    streaming_url = await self.storage.generate_presigned_url(file_data['wasabi_key'], 86400)
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🌐 Web Player", url=streaming_url)]
                    ])
                    await query.message.edit_text(
                        f"🌐 **Web Player:** {file_data['file_name']}\n\n🔗 Browser-optimized streaming!",
                        reply_markup=keyboard
                    )
                except Exception as e:
                    await query.message.edit_text("❌ Failed to generate web player!")
        
        elif data.startswith("mx_"):
            file_id = data.replace("mx_", "")
            file_data = self.file_manager.get_file(file_id)
            if file_data and file_data['user_id'] == query.from_user.id:
                try:
                    streaming_url = await self.storage.generate_presigned_url(file_data['wasabi_key'], 86400)
                    
                    mx_text = f"""
📱 **MX Player Ready!**

📄 **File:** {file_data['file_name']}
📊 **Size:** {self.format_file_size(file_data['file_size'])}

🚀 **Android Optimized:**
• Hardware acceleration
• Subtitle support
• Gesture controls

📋 **Instructions:**
1. Copy the streaming URL below
2. Open MX Player on your Android device
3. Select "Stream" or "Network Stream"
4. Paste the URL and enjoy!

🔗 **Streaming URL:**
`{streaming_url}`

💡 **Tip:** Long press to copy the URL!
                    """
                    
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔗 Direct Stream", url=streaming_url)],
                        [InlineKeyboardButton("📋 Copy Instructions", callback_data=f"mx_help_{file_id}")],
                        [InlineKeyboardButton("🔙 Back", callback_data=f"file_info_{file_id}")]
                    ])
                    await query.message.edit_text(mx_text, reply_markup=keyboard)
                except Exception as e:
                    logger.error(f"MX Player link generation failed: {e}")
                    await query.message.edit_text(f"❌ Failed to generate MX Player link: {str(e)}")
        
        elif data.startswith("vlc_"):
            file_id = data.replace("vlc_", "")
            file_data = self.file_manager.get_file(file_id)
            if file_data and file_data['user_id'] == query.from_user.id:
                try:
                    streaming_url = await self.storage.generate_presigned_url(file_data['wasabi_key'], 86400)
                    
                    vlc_text = f"""
🎯 **VLC Player Ready!**

📄 **File:** {file_data['file_name']}
📊 **Size:** {self.format_file_size(file_data['file_size'])}

🚀 **Cross-Platform Support:**
• Windows, Mac, Linux
• Android, iOS
• Advanced playback controls

📋 **Instructions:**
1. Copy the streaming URL below
2. Open VLC Media Player
3. Select "Media" → "Open Network Stream"
4. Paste the URL and enjoy!

🔗 **Streaming URL:**
`{streaming_url}`

💡 **Tip:** VLC supports most video formats!
                    """
                    
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔗 Direct Stream", url=streaming_url)],
                        [InlineKeyboardButton("📋 Copy Instructions", callback_data=f"vlc_help_{file_id}")],
                        [InlineKeyboardButton("🔙 Back", callback_data=f"file_info_{file_id}")]
                    ])
                    await query.message.edit_text(vlc_text, reply_markup=keyboard)
                except Exception as e:
                    logger.error(f"VLC Player link generation failed: {e}")
                    await query.message.edit_text(f"❌ Failed to generate VLC Player link: {str(e)}")
        
        elif data.startswith("file_info_"):
            file_id = data.replace("file_info_", "")
            file_data = self.file_manager.get_file(file_id)
            if file_data and file_data['user_id'] == query.from_user.id:
                file_info_text = f"""
📄 **File Information**

📁 **Name:** {file_data['file_name']}
📊 **Size:** {self.format_file_size(file_data['file_size'])}
📅 **Uploaded:** {self.format_date(file_data['upload_date'])}
🆔 **ID:** `{file_id}`

⚡ **Quick Actions:**
                """
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📥 Download", callback_data=f"download_{file_id}")],
                    [InlineKeyboardButton("🎬 Stream", callback_data=f"stream_{file_id}"),
                     InlineKeyboardButton("🌐 Web", callback_data=f"web_{file_id}")],
                    [InlineKeyboardButton("📱 MX Player", callback_data=f"mx_{file_id}"),
                     InlineKeyboardButton("🎯 VLC Player", callback_data=f"vlc_{file_id}")],
                    [InlineKeyboardButton("🔙 Back to List", callback_data="list_files")]
                ])
                
                await query.message.edit_text(file_info_text, reply_markup=keyboard)
        
        await query.answer()
    
    def format_file_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format"""
        if size_bytes == 0:
            return "0B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.2f} {size_names[i]}"
    
    def format_date(self, date_str: str) -> str:
        """Format ISO date string to readable format"""
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime("%Y-%m-%d %H:%M")
        except:
            return date_str
    
    async def run_web_server(self):
        """Run the web server for Render compatibility"""
        runner = web.AppRunner(self.web_app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 5000)
        await site.start()
        logger.info("Web server started on port 5000")
    
    async def start(self):
        """Start the bot with web server"""
        # Start web server in background
        web_task = asyncio.create_task(self.run_web_server())
        
        # Start the Telegram bot
        await self.app.start()
        
        # Test Wasabi connection
        logger.info("Testing Wasabi connection...")
        if await self.storage.test_connection():
            logger.info("✅ Wasabi connection successful!")
        else:
            logger.warning("⚠️ Wasabi connection failed - check credentials")
        
        logger.info("Bot started successfully!")
        
        # Keep both running
        try:
            await asyncio.gather(web_task, self.app.idle())
        finally:
            await self.app.stop()

# Run the bot
if __name__ == "__main__":
    try:
        bot = TelegramFileBot()
        asyncio.run(bot.start())
    except Exception as e:
        logger.error(f"Bot failed to start: {e}")
        import sys
        sys.exit(1)
