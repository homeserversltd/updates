"""
HOMESERVER Website Update Module

This module handles updating the HOMESERVER web interface from the GitHub repository.
It supports selective component updates, automatic rollback on failure, and comprehensive
backup management.

Key Features:
- GitHub repository integration
- Selective component updates (frontend, backend, premium, config, public)
- Automatic backup and rollback capabilities
- npm build process management
- Service restart and health checking
- Configurable update policies per component

Usage:
    from modules.website import WebsiteUpdater
    
    updater = WebsiteUpdater()
    success = updater.update()
"""

from .index import WebsiteUpdater

__all__ = ['WebsiteUpdater']

# Module metadata
__version__ = '1.0.0'
__author__ = 'HOMESERVER Development Team'
__description__ = 'Website update module for HOMESERVER platform'
