# Adblock Module

## Purpose

The adblock module provides network-level ad and tracker blocking for HOMESERVER by maintaining DNS blocklists. This protects all devices on your network from advertisements, tracking, and malicious domains without requiring individual device configuration.

## What It Does

- **Network-Wide Protection**: Blocks ads and trackers for every device connected to your HOMESERVER network
- **DNS-Level Blocking**: Intercepts domain requests before they reach external servers
- **Automatic Updates**: Keeps blocklists current with the latest threat intelligence
- **Multiple Sources**: Combines reputable blocklist providers for comprehensive coverage

## Why It Matters

Traditional ad blockers work only on individual devices and applications. HOMESERVER's adblock module protects your entire network infrastructure:

- **IoT Device Protection**: Blocks tracking from smart TVs, tablets, and other devices that can't run ad blockers
- **Guest Network Security**: Automatically protects visitors without requiring software installation
- **Bandwidth Conservation**: Reduces network traffic by blocking unwanted content at the source
- **Privacy Enhancement**: Prevents tracking domains from collecting data across your network

## Integration with HOMESERVER

The adblock module integrates with HOMESERVER's DNS infrastructure (Unbound) to provide transparent, network-level protection. It operates automatically in the background, requiring no user intervention once configured.

## Blocklist Sources

- **Steven Black's Unified Hosts**: Community-maintained compilation of ad and malware domains
- **NoTracking**: Privacy-focused blocklist targeting tracking and analytics domains

The module intelligently combines these sources, removing duplicates and conflicts to create a unified, optimized blocklist for your network. 