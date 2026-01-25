# ShadyCogs - Red-Bot Discord Cogs Collection

A collection of Red-Bot cogs for Discord community management, created for the Parental Advisory (PA) Discord community - "Parents That Game" - but now configurable for any Discord server.

## Cogs Included

### 1. Karaoke - Interactive Karaoke Video Downloader
Search and download karaoke videos through an interactive DM-based interface with emoji reactions.

### 2. Wiki - Community Helper & LFG System
Comprehensive community management tool with slash commands for rules, hosting guidelines, game-specific LFG routing, and moderation tools.

### 3. ShadyVoiceMod - Voice Moderation System
Advanced voice moderation with timed voice mutes, automatic expiry tracking, DM notifications, and comprehensive audit logging.

### 4. ShadyCheatSheet - D&D 5e Skill Check Reference Guide
Comprehensive DM reference guide for D&D 5e skill checks. Includes when to call for checks, DC guidelines, contested checks, group checks, common skill confusions, and pro tips. Works in DMs and servers.

---

## Installation

### Prerequisites
- Red-Bot v3.5.0 or higher
- Python 3.8 or higher
- discord.py 2.0+

### Install via Red-Bot

```bash
[p]repo add ShadyCogs https://github.com/ShadyTidus/ShadyCogs
[p]cog install ShadyCogs karaoke
[p]cog install ShadyCogs wiki
[p]cog install ShadyCogs shadyvoicemod
[p]cog install ShadyCogs shadycheatsheet
[p]load karaoke
[p]load wiki
[p]load shadyvoicemod
[p]load shadycheatsheet
```

### Manual Installation

1. Clone this repository to your Red-Bot cogs folder
2. Install dependencies: `pip install -r requirements.txt`
3. Load the cogs: `[p]load karaoke`, `[p]load wiki`, `[p]load shadyvoicemod`, and `[p]load shadycheatsheet`

---

## Karaoke Cog Setup

### Initial Configuration (Required)

**Bot Owner Must Set API Token:**
```
[p]setkaraoketoken <your_api_token>
```

This securely stores the API token in Red-Bot's config system. The token is **never** exposed in code or logs.

### Usage

**Slash Command (Recommended):**
```
/ksearch <song title>
```

**Example:**
- User types: `/ksearch Bohemian Rhapsody`
- Bot DMs the user with top 5 results
- User reacts with 1️⃣-5️⃣ to select
- Bot triggers download for selected video

### Features
- ✅ Secure API token storage
- ✅ Interactive DM-based selection
- ✅ 60-second timeout for user response
- ✅ Emoji reaction interface (1️⃣-5️⃣)
- ✅ Slash command support

---

## Wiki Cog Setup

### Easy JSON Configuration! 🎉

The Wiki cog now uses **simple JSON files** for all configuration - **no Python coding required!**

All configs are in `wiki/config/`:
- `roles.json` - Authorized roles
- `games.json` - Game aliases for LFG (90+ games included!)
- `channels.json` - Role-to-channel mappings (50+ channels mapped!)
- `commands.json` - Command text and URLs
- `rules.json` - Server rules (1-10)

### Quick Start

**For PA Server:** Everything is pre-configured! Just load and use.

**For Other Servers:**
1. Edit `wiki/config/roles.json` - Add your staff roles
2. Edit `wiki/config/games.json` - Add your game roles
3. Edit `wiki/config/channels.json` - Map roles to channel IDs
4. Edit `wiki/config/commands.json` - Update URLs to your wiki
5. Edit `wiki/config/rules.json` - Write your rules
6. Run `[p]wikireload` to apply changes

### Reload Configuration

After editing any config file:
```
[p]wikireload
```

No bot restart needed! Changes apply instantly.

### Full Configuration Guide

See **[CONFIGURATION.md](CONFIGURATION.md)** for detailed instructions on:
- How to edit each config file
- Examples for every command
- Tips for finding channel IDs
- Troubleshooting guide
- JSON syntax help

### Example: Adding a New Game

Edit `wiki/config/games.json`:
```json
"valorant": "Valorant",
"val": "Valorant"
```

Edit `wiki/config/channels.json`:
```json
"Valorant": 1234567890123456789
```

Run `[p]wikireload` - Done!

### Available Commands

#### Slash Commands (Recommended)
- `/lfg <user> <game>` - Direct user to correct LFG channel based on game
- `/host` - Show hosting/advertising guidelines
- `/biweekly` - Display D&D biweekly session info
- `/rule <number>` - Show specific server rule (1-10)
- `/wow` - Link to World of Warcraft guide
- `/fafo` - Post warning message with self-timeout button (5 min)
- `/hosted` - Show list of hosted game servers

#### Legacy Prefix Commands
All slash commands also work with prefix commands:
- `[p]lfg` - Reply to a message to detect game and route to LFG channel
- `[p]host` - Host guidelines
- `[p]biweekly` - D&D info
- `[p]rule <number>` - Server rules
- `[p]wow` - WoW guide
- `[p]fafo` - Warning with FAFO button
- `[p]hosted` - Hosted servers list

### Authorization System

Only users with configured roles can use Wiki commands. Default authorized roles (PA server):
- Game Server Team, Advisors, Wardens, Sentinels
- Community Managers (Helldivers, Book Club, Call of Duty, D&D, WoW, Minecraft)
- Specific users: Skye, Librarian Raccoon, Zara, BadgerSnacks, Donnie, Captain Sawbones, Captain Soulo

**To customize for your server:** Use config commands to add/remove authorized roles.

### LFG System

The LFG (Looking For Group) system features:
- **90+ game aliases** - Detects game mentions in messages
- **Auto-role assignment** - Gives users game roles automatically
- **Channel routing** - Redirects LFG posts to correct channels
- **Smart detection** - Word matching + regex pattern detection

**How it works:**
1. Staff member replies to a user's message with `/lfg` command
2. Bot detects game from message content (e.g., "cod", "wow", "minecraft")
3. Bot checks if user is in the correct channel
4. If wrong channel: Bot redirects user and posts LFG in correct channel
5. If correct channel: Bot posts LFG ping with role mention

**Customizing Game Mappings:**

Simply edit the JSON files:

`wiki/config/games.json`:
```json
{
  "alias_to_role": {
    "cod": "Call of Duty",
    "wow": "World of Warcraft",
    "mc": "Minecraft"
  }
}
```

`wiki/config/channels.json`:
```json
{
  "role_to_channel": {
    "Call of Duty": 1067440688737820683,
    "World of Warcraft": 1067440649479131187
  }
}
```

Run `[p]wikireload` to apply changes. See [CONFIGURATION.md](CONFIGURATION.md) for full guide!

### Features
- ✅ Role-based command authorization
- ✅ Configurable per-server settings
- ✅ Slash command support
- ✅ Intelligent LFG game detection
- ✅ Auto-role assignment
- ✅ Channel routing for 50+ games
- ✅ Server rules reference (configurable)
- ✅ Multiple wiki/guide links
- ✅ FAFO self-timeout moderation tool

---

## ShadyVoiceMod Cog Setup

### Overview

ShadyVoiceMod provides comprehensive voice channel moderation with timed mutes that automatically expire. Perfect for managing disruptive voice channel behavior without permanent punishments.

### Authorization System

**Important:** ShadyVoiceMod uses the **same role authorization system as the Wiki cog**. Commands are restricted to users with roles listed in `wiki/config/roles.json`.

**Authorized roles include:**
- Roles listed in `wiki/config/roles.json`
- Server administrators (always authorized)
- Server owner (always authorized)

To modify authorized roles, edit `wiki/config/roles.json`. No reload needed for ShadyVoiceMod - changes apply on next command use.

### Initial Configuration

**Set Audit Log Channel (Optional but Recommended):**
```
[p]vmodset logchannel #mod-logs
```

This enables detailed audit logging for all voice moderation actions.

### Available Commands

**Prefix Commands:**
- `[p]vmute <user> <duration> <reason>` - Voice mute a user for a specified duration
- `[p]vunmute <user> [reason]` - Manually remove a voice mute
- `[p]vmutes` - List all active and pending voice mutes
- `[p]vmodset logchannel <channel>` - Set audit log channel
- `[p]vmodinfo` - Show help and information

### Duration Formats

Flexible duration parsing supports:
- `30s` - 30 seconds
- `5m` - 5 minutes
- `2h` - 2 hours
- `1d` - 1 day
- `1w` - 1 week
- Combined: `1h30m`, `2d12h`, `1w3d`

### Usage Examples

**Basic Voice Mute:**
```
[p]vmute @User 30m Being disruptive in voice chat
```

**Longer Mute:**
```
[p]vmute @User 2h Mic spamming and ignoring warnings
```

**Unmute Early:**
```
[p]vmute @User Appealed successfully
```

**Check Active Mutes:**
```
[p]vmutes
```

### How It Works

1. **Instant Application**: If the user is in a voice channel, the mute applies immediately
2. **Pending Mutes**: If the user is offline, the mute applies when they join a voice channel
3. **Auto-Expiry**: Background task checks every 30 seconds and automatically lifts expired mutes
4. **DM Notifications**: Users receive DMs when muted, when mutes are extended, and when mutes expire
5. **Audit Logging**: All actions are logged to the configured channel with detailed embeds

### Advanced Features

**Mute Extension UI:**
When a moderator tries to mute an already-muted user, an interactive UI appears with options to:
- Cancel (if it was an error)
- Extend the existing mute (opens a modal for additional time/reason)

**Automatic Tracking:**
- Tracks mute status (applied vs pending)
- Handles users rejoining voice channels
- Persists across bot restarts
- Cleans up expired mutes automatically

### Permissions Required

**Bot Permissions:**
- `Mute Members` - Required to apply voice mutes
- `Send Messages` - For command responses
- `Embed Links` - For audit logs and formatted responses

**User Permissions:**
- Must have a role listed in `wiki/config/roles.json` OR be a server administrator/owner
- Administrator permission required for configuration commands (`vmodset`)

### Features
- ✅ Timed voice mutes with auto-expiry
- ✅ Flexible duration parsing (seconds to weeks)
- ✅ DM notifications to affected users
- ✅ Comprehensive audit logging with embeds
- ✅ Mute extension system via interactive modals
- ✅ Pending mute system for offline users
- ✅ Background task for automatic expiry
- ✅ Role hierarchy enforcement
- ✅ Prevention of self-muting and bot muting
- ✅ Detailed mute tracking and status reporting

---

## ShadyCheatSheet Cog Setup

### Overview

ShadyCheatSheet provides a comprehensive D&D 5e skill check reference guide for DMs. Perfect for new and experienced DMs who need quick access to skill check guidelines, DC recommendations, and common skill confusions.

### Authorization System

**In Guilds:** Commands are restricted to users with roles listed in `wiki/config/roles.json`, server administrators, or the server owner.

**In DMs:** Anyone can use all commands - perfect for quick reference during game prep or sessions!

### No Configuration Required

ShadyCheatSheet works out of the box! Just load the cog and start using commands.

### Available Commands

All commands use the `/` slash command prefix:

**Main Commands:**
- `/skillcheatsheet` - Complete guide with all sections (6 embeds)
- `/whentocall` - When to call for skill checks vs when not to
- `/settingdcs` - DC reference table and guidelines
- `/contestedchecks` - Opposed rolls (Stealth vs Perception, social contests, etc.)
- `/groupchecks` - Party cooperation checks (when to use and when not to)
- `/skillconfusions` - Common skill confusions explained (Athletics vs Acrobatics, etc.)
- `/skillreference` - Complete skill list organized by category
- `/protips` - DM best practices and tips

### Usage Examples

**Quick Reference in DM:**
```
/skillcheatsheet
```
Sends the full guide - perfect for prep or during sessions!

**Specific Question:**
```
/skillconfusions
```
Shows detailed explanations of Athletics vs Acrobatics, Perception vs Investigation, etc.

**Setting a DC:**
```
/settingdcs
```
Reference table: DC 5 (very easy) to DC 30 (nearly impossible)

### What's Covered

**When to Call for Checks:**
- Don't call: Trivial tasks, no consequences, impossible tasks
- Do call: Meaningful stakes, time pressure, real risk

**Setting DCs:**
- DC 5: Very Easy (climb a knotted rope)
- DC 10: Easy (hear loud conversation through door)
- DC 15: Medium (pick simple lock, track footprints)
- DC 20: Hard (climb slippery cliff)
- DC 25: Very Hard (swim in stormy sea)
- DC 30: Nearly Impossible (convince king to abdicate)

**Contested Checks:**
- Stealth vs Perception (with environmental modifiers)
- Creature abilities that counter stealth
- Grapple/shove mechanics
- Social contests (when NPCs resist)

**Group Checks:**
- When to use (party sneaking together, rowing boat)
- How they work (half or more succeed = group succeeds)
- When NOT to use (individual tasks, one person doing the work)

**Common Confusions:**
- STR check vs Athletics
- Athletics vs Acrobatics
- Perception vs Investigation
- Insight vs Perception
- Survival vs Nature
- Persuasion vs Deception vs Intimidation

**Pro Tips:**
- Advantage/Disadvantage is better than +5/-5
- Fail forward (complications, not dead stops)
- Contest or DC? (active opposition vs difficulty)
- Use passive perception to maintain tension

### Features
- ✅ Works in DMs and servers
- ✅ No configuration required
- ✅ Clean, organized embeds
- ✅ Multiple viewing options (full guide or specific sections)
- ✅ Role-based authorization in guilds
- ✅ Covers all common DM skill check questions
- ✅ Quick reference tables and examples

---

## Security Features

### Karaoke Cog
- **No hardcoded API tokens** - Stored securely in Red-Bot's encrypted config
- **Owner-only token management** - Only bot owner can set/change API token
- **Auto-deletion of token commands** - Token setup messages are deleted automatically

### Wiki Cog
- **Role-based authorization** - Commands restricted to configured roles only
- **Per-guild configuration** - Each server has isolated settings
- **No exposed credentials** - All sensitive data stored in Red-Bot config

### ShadyVoiceMod Cog
- **Per-guild configuration** - Each server has isolated mute tracking
- **Secure data storage** - All mute data stored in Red-Bot's encrypted config
- **Permission-based access** - Commands restricted to moderators with appropriate permissions
- **Role hierarchy enforcement** - Prevents moderators from muting higher-ranked users

### ShadyCheatSheet Cog
- **No data storage** - Reference guide only, stores no user or guild data
- **DM-friendly** - Works in private messages for personal reference
- **Role-based in guilds** - Uses Wiki cog's authorization system for server use

---

## Migration from Original Version

If you're upgrading from the original hardcoded version:

1. **Back up your current configuration**
2. **Reload the updated cogs:**
   ```
   [p]reload karaoke
   [p]reload wiki
   ```
3. **For Karaoke:** Set your API token with `[p]setkaraoketoken <token>`
4. **For Wiki (PA Server):** No action needed - defaults match your current setup!
5. **Sync slash commands:**
   ```
   [p]slash sync
   ```

### What Changed
- ✅ Added secure Config system
- ✅ Converted to slash commands
- ✅ Made configurable per-server
- ✅ Removed hardcoded API tokens
- ✅ Improved error logging
- ✅ Better authorization checks
- ✅ Added requirements.txt

---

## Troubleshooting

### Slash Commands Not Appearing
```
[p]slash sync
```
Wait 1-2 minutes for Discord to update.

### Karaoke Says "API token not configured"
Bot owner must run: `[p]setkaraoketoken <your_token>`

### Wiki Commands Not Working
1. Check if user has an authorized role
2. Verify roles are configured: `[p]wikicfg`
3. Ensure slash commands are synced

### LFG Not Detecting Games
1. Check that game alias exists in `alias_to_role` dict
2. Verify role name matches exactly (case-sensitive)
3. Check logs for detection errors

---

## Support & Contributing

**Original Author:** ShadyTidus
**GitHub:** https://github.com/ShadyTidus/ShadyCogs

**Issues:** Please report bugs or request features on the GitHub repository.

**Contributing:** Pull requests welcome! Please ensure:
- Code follows existing style
- No hardcoded credentials
- Slash commands preferred over prefix commands
- Per-guild configuration supported

---

## License

This project is provided as-is for community use. See repository for license details.

---

## Changelog

### v2.3.0 (2025) - D&D Reference Guide
- **🎉 NEW:** ShadyCheatSheet cog for D&D 5e skill check reference
- **NEW:** 8 slash commands covering all skill check scenarios
- **NEW:** Works in DMs and servers (DM-friendly for game prep)
- **NEW:** Complete coverage: when to call checks, DCs, contested checks, group checks
- **NEW:** Common skill confusions explained (Athletics vs Acrobatics, etc.)
- **NEW:** Pro tips for running smooth skill checks
- Integrated authorization using Wiki cog's role system

### v2.2.0 (2025) - Voice Moderation System
- **🎉 NEW:** ShadyVoiceMod cog for comprehensive voice channel moderation
- **NEW:** Timed voice mutes with automatic expiry system
- **NEW:** Interactive mute extension UI with modals
- **NEW:** DM notifications for muted users
- **NEW:** Comprehensive audit logging for all voice mod actions
- **NEW:** Pending mute system for offline users
- **NEW:** Background task for automatic mute expiry
- **NEW:** Integrated authorization using Wiki cog's role system
- Fixed critical syntax error in config identifier

### v2.1.0 (2025) - JSON Config System
- **🎉 NEW:** Easy JSON configuration files - no Python needed!
- **NEW:** Separate config files for roles, games, channels, commands, and rules
- **NEW:** `[p]wikireload` command to apply config changes instantly
- **NEW:** Enable/disable individual commands via config
- **NEW:** Fully customizable command text and URLs
- **NEW:** Comprehensive CONFIGURATION.md guide
- Made all commands configurable without code changes
- Improved config organization and maintainability

### v2.0.0 (2025) - Slash Commands & Security
- Added slash command support for all commands
- Implemented secure Config system for API tokens
- Made Wiki cog configurable per-server
- Removed hardcoded API tokens (security fix)
- Added requirements.txt
- Improved error logging throughout
- Updated info.json files with detailed descriptions

### v1.0.0 (Original)
- Initial release with prefix commands
- Hardcoded configuration for PA server
- Basic karaoke search functionality
- LFG system with game detection
