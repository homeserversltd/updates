# Mkdocs Module

## Purpose

The mkdocs module provides a documentation server for HOMESERVER using MkDocs. It serves static documentation sites with search capabilities and modern theming, automatically synchronized with the latest documentation from GitHub.

## What It Does

- **Documentation Hosting**: Serves MkDocs-generated static sites
- **Search Functionality**: Built-in full-text search for documentation
- **Theme Management**: Supports modern, responsive themes
- **Navigation**: Automatic site navigation and structure
- **Markdown Support**: Renders Markdown files as HTML pages
- **Automatic Updates**: Synchronizes documentation content from GitHub repository

## Why It Matters

Good documentation is crucial for system administration and development. The mkdocs module provides:

- **Centralized Docs**: Single place for all HOMESERVER documentation
- **Searchable Content**: Quickly find information without manual searching
- **Version Control**: Easy updates through Markdown files
- **Accessibility**: Responsive design works on all devices
- **Always Current**: Automatic synchronization with latest documentation updates

## Integration with HOMESERVER

Integrates with HOMESERVER's web infrastructure to provide documentation alongside other services.

## Key Features

- Fast static site generation
- Built-in dev-server for previews
- Plugin ecosystem
- Theme customization
- Full-text search
- **Automatic GitHub synchronization**
- **Version tracking and rollback support**

## Update Process

The module handles two types of updates:

### Software Updates
- Monitors MkDocs and MkDocs Material versions
- Updates Python packages via pip when new versions are available
- Preserves configuration and permissions

### Documentation Updates
- Monitors the [HOMESERVER documentation repository](https://github.com/homeserversltd/documentation)
- Checks for new commits on the main branch
- Automatically downloads and deploys updated documentation
- Maintains version tracking for rollback capability

## Configuration

The module is configured via `index.json`:

- **Software**: GitHub API for MkDocs Material releases
- **Documentation**: GitHub repository and API endpoints
- **Paths**: Local storage locations for docs and version tracking
- **Permissions**: File ownership and access controls

## Backup and Recovery

- **State Management**: Automatic backup before updates
- **Rollback Support**: Restore previous state if updates fail
- **Version Tracking**: Maintains documentation version history
- **Permission Preservation**: Ensures proper file ownership after updates 