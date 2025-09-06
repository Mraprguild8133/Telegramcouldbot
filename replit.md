# Telegram File Bot with Wasabi Cloud Storage

## Overview

This project is a comprehensive Telegram file bot that provides cloud storage and streaming capabilities through Wasabi S3-compatible storage. The bot handles large file uploads and downloads (up to 4GB), offers direct streaming links, and integrates with popular media players like MX Player and VLC. It serves as a bridge between Telegram's messaging platform and cloud storage, enabling users to store, retrieve, and stream files through a conversational interface.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Bot Framework
- **Pyrogram Client**: Utilizes Pyrogram as the primary Telegram MTProto API client for handling bot interactions, file operations, and message processing
- **Async/Await Pattern**: Implements asynchronous programming throughout the application to handle non-blocking file operations and concurrent user requests
- **Event-Driven Architecture**: Uses decorators and filters to handle different types of Telegram messages and callback queries

### Cloud Storage Integration
- **Wasabi S3 Compatibility**: Leverages Boto3 client to interact with Wasabi cloud storage using S3-compatible APIs
- **WasabiStorage Class**: Encapsulates all cloud storage operations including upload, download, and file management
- **Large File Support**: Implements chunked upload mechanisms to handle files up to 4GB in size
- **Progress Tracking**: Provides real-time upload/download progress updates through callback mechanisms

### File Management System
- **Multi-Format Support**: Handles various file types including documents, videos, audio files, and photos
- **MIME Type Detection**: Uses Python's mimetypes module for automatic file type identification
- **File Metadata Storage**: Maintains file information and generates unique identifiers for stored files
- **Streaming Capabilities**: Generates direct streaming URLs for media files compatible with external players

### User Interface Design
- **Command-Based Interaction**: Implements a comprehensive set of bot commands for file operations (/upload, /download, /stream, etc.)
- **Inline Keyboards**: Uses Telegram's inline keyboard markup for interactive buttons and player integration
- **Mobile Optimization**: Designed with mobile-first approach for optimal smartphone and tablet usage
- **Cross-Platform Player Support**: Provides direct integration links for MX Player and VLC media players

### Error Handling and Logging
- **Comprehensive Error Management**: Implements robust error handling for network issues, storage failures, and invalid user inputs
- **Structured Logging**: Uses Python's logging module with timestamp and level-based formatting for debugging and monitoring
- **Graceful Degradation**: Ensures bot continues functioning even when certain features encounter issues

### Security and Configuration
- **Environment-Based Configuration**: Uses dotenv for secure management of API keys, tokens, and sensitive configuration data
- **Access Control**: Implements channel-based storage options for backup and access management
- **Secure File Transfer**: All file operations use encrypted connections and secure authentication methods

## External Dependencies

### Cloud Storage Service
- **Wasabi Cloud Storage**: Primary storage backend providing S3-compatible object storage with high performance and cost efficiency
- **Boto3 Library**: AWS SDK for Python enabling S3-compatible API interactions with Wasabi

### Telegram Platform
- **Telegram Bot API**: Core messaging and file transfer capabilities through official Telegram Bot API
- **Pyrogram Framework**: Third-party Python library for advanced Telegram MTProto API access
- **Bot Token Authentication**: Requires bot token from @BotFather for Telegram platform integration

### File Processing Libraries
- **aiofiles**: Asynchronous file I/O operations for non-blocking file handling
- **mimetypes**: Built-in Python module for MIME type detection and file classification
- **hashlib**: Cryptographic hashing for file integrity verification and unique ID generation

### Development and Deployment
- **python-dotenv**: Environment variable management for configuration and secrets
- **asyncio**: Python's built-in asynchronous I/O framework for concurrent operations

### Optional Integrations
- **Telegram Channels**: Optional backup storage mechanism using Telegram channels for file redundancy
- **MX Player**: Android media player integration for direct video/audio playback
- **VLC Media Player**: Cross-platform media player support for enhanced streaming capabilities