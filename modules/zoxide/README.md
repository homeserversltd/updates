# Zoxide Module

## Purpose

The zoxide module manages zoxide installation and updates for HOMESERVER administrators. Zoxide provides intelligent directory navigation that learns your habits and makes jumping between directories fast and intuitive.

## What It Does

- **Smart Directory Jumper**: Replaces `cd` with intelligent directory navigation
- **Learning Algorithm**: Tracks directory usage frequency and recency
- **Fuzzy Matching**: Quickly jump to directories by typing partial names
- **Cross-Shell Support**: Works with bash, zsh, fish, and other shells
- **Automatic Updates**: Keeps zoxide current with latest features and fixes

## Why It Matters

System administrators working with HOMESERVER navigate complex directory structures frequently. Traditional `cd` requires typing full paths or navigating step-by-step. Zoxide transforms directory navigation:

- **Productivity Enhancement**: Jump to frequently used directories with just a few keystrokes
- **Time Savings**: Reduce time spent typing long paths or navigating directory trees
- **Habit Learning**: Automatically learns which directories you use most
- **Seamless Integration**: Works transparently with existing shell workflows

## Integration with HOMESERVER

The zoxide module integrates with HOMESERVER's shell environment (zsh) to provide enhanced directory navigation for system administration tasks. It operates transparently, tracking directory usage and providing fast access to frequently visited locations.

## Key Features

- **Intelligent Ranking**: Directories are ranked by frequency and recency of use
- **Partial Matching**: Type part of a directory name to jump there
- **Interactive Mode**: Browse and select from matching directories
- **Shell Hooks**: Automatically tracks directory changes
- **Automatic Updates**: Keeps the tool current with latest features and security fixes

## Installation Location

Zoxide installs to `~/.local/bin/zoxide` by default, with configuration in `~/.config/zoxide` and data in `~/.local/share/zoxide`.

This module ensures HOMESERVER administrators have powerful directory navigation tools that match the sophistication of the platform they're managing.

