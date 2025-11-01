# MyRedCogs - Red-Bot Discord Cogs Collection

A collection of Red-Bot cogs for Discord community management, created for the Parents That Game (PA) community but now configurable for any Discord server.

## Cogs Included

### 1. Karaoke - Interactive Karaoke Video Downloader
Search and download karaoke videos through an interactive DM-based interface with emoji reactions.

### 2. Wiki - Community Helper & LFG System
Comprehensive community management tool with slash commands for rules, hosting guidelines, game-specific LFG routing, and moderation tools.

---

## Installation

### Prerequisites
- Red-Bot v3.5.0 or higher
- Python 3.8 or higher
- discord.py 2.0+

### Install via Red-Bot

```bash
[p]repo add MyRedCogs https://github.com/ShadyTidus/ShadyCogs
[p]cog install MyRedCogs karaoke
[p]cog install MyRedCogs wiki
[p]load karaoke
[p]load wiki
```

### Manual Installation

1. Clone this repository to your Red-Bot cogs folder
2. Install dependencies: `pip install -r requirements.txt`
3. Load the cogs: `[p]load karaoke` and `[p]load wiki`

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

###Features
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

## Security Features

### Karaoke Cog
- **No hardcoded API tokens** - Stored securely in Red-Bot's encrypted config
- **Owner-only token management** - Only bot owner can set/change API token
- **Auto-deletion of token commands** - Token setup messages are deleted automatically

### Wiki Cog
- **Role-based authorization** - Commands restricted to configured roles only
- **Per-guild configuration** - Each server has isolated settings
- **No exposed credentials** - All sensitive data stored in Red-Bot config

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
