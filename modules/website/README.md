# HOMESERVER Website - The Digital Command Center

## Purpose
The beating heart of HOMESERVER. Everything you see, touch, and control flows through this sophisticated web interface. This is your digital sovereignty made tangible.

## What It Is
The HOMESERVER website isn't just another web app - it's your **complete digital command center**. Every service, every feature, every capability of your HOMESERVER is accessed, monitored, and controlled through this unified interface.

## Automatic Updates
The website module now includes intelligent dual-version update system that distinguishes between schema and content updates:

### Version Types
- **Schema Version**: Module configuration changes (in `index.json`) - affects update behavior, component settings, etc.
- **Content Version**: Actual website code changes (in `homeserver.json`) - affects frontend/backend functionality

### Update Logic Step-by-Step

#### 1. Version Detection Phase
1. **Clone Repository**: Download latest code from GitHub to temporary directory
2. **Check Critical Files**: Verify `homeserver.json` and `/src` directory exist (nuclear restore if missing)
3. **Schema Version Check**: Compare module's `index.json` schema_version (local vs repo)
4. **Content Version Check**: Compare website's `homeserver.json` version (local vs repo)
5. **Determine Update Type**: Schema-only, content-only, both, or neither

#### 2. Update Decision Matrix
```
Schema Newer + Content Newer = Full Update (both schema + content)
Schema Newer + Content Same  = Schema-Only Update
Schema Same  + Content Newer = Content-Only Update  
Schema Same  + Content Same  = No Update Needed
```

#### 3. Update Execution Phase
**Schema-Only Updates:**
- Updates module configuration files
- Preserves user's `homeserver.json` content version
- Updates only `index.json` schema_version
- No npm rebuild required

**Content Updates:**
- Updates actual website files (src/, backend/, etc.)
- Updates user's `homeserver.json` version + timestamp
- Updates module's content_version to match
- Requires full npm build + service restart

**Nuclear Restore:**
- Triggered when critical files missing/corrupted
- Complete repository copy + full rebuild
- Updates both schema and content versions

#### 4. Version Preservation Logic
- **Schema updates NEVER modify** user's `homeserver.json` version
- **Content version only updated** when actual website code changes
- **User's configuration always preserved** during schema-only updates
- **Module tracking stays accurate** to actual deployed content

### Safety Features
- **Backup Before Changes**: StateManager creates restore points before content updates
- **Rollback on Failure**: Automatic restoration if build/deployment fails
- **Permission Restoration**: Ensures correct file ownership after all operations
- **Service Validation**: Confirms services are running before marking success

### Continuous Maintenance (Agnostic of Builds)
- **Browserslist DB Refresh**: On every module run, the updater executes `npx update-browserslist-db@latest` (non-interactive) from `/var/www/homeserver` to keep `caniuse-lite` data current. This runs even when no content update or build occurs, ensuring modern browser coverage and avoiding outdated target lists.

### Practical Examples

**Scenario 1: Schema-Only Update**
```
Local:  schema_version="0.1.15", content_version="0.9.0" 
Repo:   schema_version="0.1.16", content_version="0.9.0"
Result: Updates index.json to 0.1.16, preserves homeserver.json at 0.9.0
Action: Configuration update only, no website rebuild
```

**Scenario 2: Content-Only Update**
```
Local:  schema_version="0.1.16", content_version="0.9.0"
Repo:   schema_version="0.1.16", content_version="0.9.1" 
Result: Updates homeserver.json to 0.9.1, updates index.json content_version to 0.9.1
Action: Full website update + npm build + service restart
```

**Scenario 3: Full Update**
```
Local:  schema_version="0.1.15", content_version="0.9.0"
Repo:   schema_version="0.1.16", content_version="0.9.1"
Result: Updates both schema to 0.1.16 and content to 0.9.1
Action: Configuration + website update + rebuild
```

**Scenario 4: No Update Needed**
```
Local:  schema_version="0.1.16", content_version="0.9.1"
Repo:   schema_version="0.1.16", content_version="0.9.1"
Result: No changes made, all versions current
Action: Skip update process entirely
```

This ensures your `homeserver.json` version always reflects the actual website code deployed, never artificially incremented by module configuration changes.

- **Unified Control Panel**: Single interface for all 14+ enterprise services
- **Real-time Monitoring**: Live system stats, service status, network activity
- **Administrative Dashboard**: Complete server management from anywhere
- **Service Integration**: Seamless access to Jellyfin, Vaultwarden, Gogs, and more
- **Mobile-Responsive**: Full functionality on tablets, phones, and desktops
- **Secure Access**: Protected admin features with session management

## Why It's Everything
Without this interface, HOMESERVER would just be a collection of services running in the dark. The website transforms raw server power into an intuitive, powerful platform you actually want to use.

**This is where digital sovereignty becomes real:**
- **No more SSH required** - Everything manageable through beautiful web interface
- **No more scattered logins** - One dashboard for your entire digital life
- **No more guesswork** - Real-time visibility into every aspect of your server
- **No more complexity** - Enterprise-grade power with consumer-friendly experience

## The Complete Experience
Every HOMESERVER capability flows through this interface:

**System Management**
- Live system statistics and performance monitoring
- Service status and health indicators
- Network configuration and monitoring
- File management and uploads
- System updates and maintenance

**Service Access**
- Direct integration with all HOMESERVER services
- Unified authentication across platforms
- Seamless service switching and management
- Real-time status updates via WebSocket

**Administrative Control**
- Complete server administration without terminal access
- User management and access control
- Configuration management for all services
- Backup and restore operations

## Integration with HOMESERVER
This isn't just a frontend - it's the **nervous system** of your entire HOMESERVER:

- **React Frontend**: Modern, responsive interface built for power users
- **Flask Backend**: Robust API handling all server operations
- **Premium Features**: Advanced functionality for enhanced control
- **Real-time Updates**: WebSocket integration for live system monitoring
- **Mobile Optimization**: Full functionality on any device

## Why This Matters
Your HOMESERVER could run every service perfectly, but without this interface, you'd be managing 14+ separate web panels, SSH sessions, and configuration files. 

The website **unifies everything** into one coherent experience:
- **Single Sign-On**: One login for your entire digital infrastructure
- **Contextual Navigation**: Intelligent interface that adapts to your needs
- **Visual System Status**: Instantly understand your server's health
- **Integrated Workflows**: Complex operations simplified into guided experiences

This is what transforms HOMESERVER from "server software" into a **complete digital sovereignty platform**. Everything else exists to support this central command experience.

Perfect for users who want the power of enterprise infrastructure with the elegance of consumer technology - all accessible through one beautiful, unified interface.
