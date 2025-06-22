# Linker Module

## Purpose

The linker module provides a Terminal User Interface (TUI) tool for efficiently managing hard links on HOMESERVER's NAS storage. It enables users to create and manage hard links across multiple directories, maximizing storage efficiency while maintaining data accessibility across different services.

## What It Does

- **Hard Link Management**: Creates and manages hard links between files across different NAS directories
- **TUI Interface**: Provides an intuitive terminal-based interface for file linking operations
- **Storage Optimization**: Eliminates duplicate files by linking content across multiple locations
- **Safety Protection**: Prevents accidental deletion of files that have hard links elsewhere
- **Cross-Service Sharing**: Enables content sharing between different HOMESERVER services

## Why It Matters

NAS systems often need the same content accessible from multiple services and directories. Traditional file copying wastes storage space and creates synchronization problems. HOMESERVER's linker module solves this elegantly:

- **Storage Efficiency**: Share files across multiple directories without duplicating storage space
- **Service Integration**: Make content available to multiple services (Jellyfin, Piwigo, etc.) simultaneously
- **Data Integrity**: Hard links ensure all references point to the same physical data
- **Cost Optimization**: Maximize storage utilization on expensive NAS drives
- **Simplified Management**: Single source of truth for shared content across services

## Integration with HOMESERVER

The linker module integrates with HOMESERVER's file management system to provide intelligent hard link management across the NAS infrastructure. It works seamlessly with media services, photo galleries, and file browsers to optimize storage without compromising functionality.

## Key Features

- **Cross-Directory Linking**: Link files between `/media` (Jellyfin), `/photos` (Piwigo), and other service directories
- **Safety-First Design**: Prevents deletion of files that have active hard links elsewhere
- **Intuitive TUI**: Easy-to-use terminal interface for browsing and linking files
- **Link Visualization**: Shows existing hard links and their relationships
- **Batch Operations**: Efficiently create multiple hard links in a single operation
- **Conflict Prevention**: Detects and prevents problematic linking scenarios

## Common Use Cases

- **Media Sharing**: Link video files between Jellyfin's `/media` directory and general file storage
- **Photo Organization**: Share photos between Piwigo's `/photos` directory and family albums
- **Document Access**: Make documents available to multiple services without duplication
- **Backup Efficiency**: Create space-efficient backup structures using hard links
- **Content Distribution**: Organize content for different users while sharing the same files

This module transforms HOMESERVER's NAS into an intelligent storage system where content can exist in multiple logical locations while consuming minimal physical storage space, all managed through a user-friendly interface that prioritizes data safety. 