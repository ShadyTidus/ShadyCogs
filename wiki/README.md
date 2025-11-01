# Wiki Cog - Community Helper & LFG System

A comprehensive Discord bot cog for community management with an intelligent LFG (Looking For Group) system, server rules reference, and customizable wiki commands.

Created for the Parental Advisory (PA) Discord - "Parents That Game" - but fully configurable for any community.

## Features

- ✅ **LFG System** - Auto-detect games and route users to correct channels
- ✅ **90+ Game Aliases** - Recognizes game nicknames (cod, wow, mc, etc.)
- ✅ **Smart Channel Routing** - Automatically redirects to game-specific channels
- ✅ **Auto-Role Assignment** - Gives users game roles when needed
- ✅ **Server Rules Reference** - Quick `/rule <number>` command
- ✅ **Wiki Links** - Customizable commands for hosting, guides, etc.
- ✅ **Slash Commands** - Modern Discord slash command support
- ✅ **Easy JSON Configuration** - No Python coding required
- ✅ **Role-Based Authorization** - Control who can use commands
- ✅ **Enable/Disable Commands** - Turn individual commands on/off

---

## Installation

### Via Red-Bot Repository

```bash
[p]repo add ShadyCogs https://github.com/ShadyTidus/ShadyCogs
[p]cog install ShadyCogs wiki
[p]load wiki
```

### Manual Installation

1. Copy the `wiki` folder to your Red-Bot cogs directory
2. Load the cog: `[p]load wiki`
3. Sync slash commands: `[p]slash sync`

---

## Quick Start

### First Time Setup

1. **Copy example configs** (see `config/examples/`)
2. **Edit config files** in `wiki/config/`
3. **Reload configs**: `[p]wikireload`
4. **Sync slash commands**: `[p]slash sync`
5. **Test**: `/rule 1`

### Configuration Files

All configuration is stored in `wiki/config/`:

```
wiki/config/
├── roles.json          # Authorized roles
├── games.json          # Game aliases (e.g., "cod" → "Call of Duty")
├── channels.json       # Role-to-channel mappings
├── commands.json       # Command text and URLs
└── rules.json          # Server rules (1-10)
```

**Example configs are in `wiki/config/examples/`** - copy and customize these for your server!

---

## Commands

### Slash Commands (Recommended)

- `/lfg <user> <game>` - Direct user to correct LFG channel
- `/host` - Show hosting/advertising guidelines
- `/biweekly` - Display D&D or event info
- `/rule <number>` - Show specific server rule (1-10)
- `/wow` - Link to game-specific guide
- `/fafo` - Post warning with self-timeout button
- `/hosted` - Show list of hosted servers

### Prefix Commands

All slash commands also work with prefix:
- `[p]lfg` - Reply to message to detect game and route
- `[p]host` - Hosting guidelines
- `[p]biweekly` - Event info
- `[p]rule <number>` - Server rules
- `[p]wow` - Game guide
- `[p]fafo` - Warning button
- `[p]hosted` - Hosted servers
- `[p]wikireload` - Reload config files (owner only)

---

## Configuration Guide

### 1. Authorized Roles (`roles.json`)

Control who can use wiki commands:

```json
{
  "authorized_roles": [
    "Moderators",
    "Admins",
    "Community Managers"
  ]
}
```

**Role names must match Discord exactly (case-sensitive)!**

### 2. Game Aliases (`games.json`)

Map game nicknames to Discord role names:

```json
{
  "alias_to_role": {
    "cod": "Call of Duty",
    "wow": "World of Warcraft",
    "mc": "Minecraft",
    "valorant": "Valorant",
    "val": "Valorant"
  }
}
```

- **Keys**: Lowercase nicknames users type
- **Values**: Exact Discord role name

### 3. Channel Mappings (`channels.json`)

Map roles to specific channel IDs:

```json
{
  "role_to_channel": {
    "Call of Duty": 1234567890123456789,
    "Minecraft": 9876543210987654321
  }
}
```

**How to get channel ID:**
1. Enable Developer Mode (Discord Settings → Advanced)
2. Right-click channel → Copy ID

### 4. Commands (`commands.json`)

Customize text and URLs for each command:

```json
{
  "host": {
    "enabled": true,
    "text": "Want to host something? Check our rules:",
    "url": "https://your-wiki.com/hosting",
    "url_text": "Hosting Guide",
    "emoji": "📌"
  }
}
```

**Disable a command:**
```json
{
  "biweekly": {
    "enabled": false
  }
}
```

### 5. Server Rules (`rules.json`)

Define your server rules (1-10):

```json
{
  "rules": {
    "1": {
      "title": "1️⃣ Be Respectful",
      "text": "Treat everyone with respect. No toxic behavior."
    },
    "2": {
      "title": "2️⃣ No Spam",
      "text": "Don't spam messages or channels."
    }
  }
}
```

---

## LFG System Usage

### How It Works

1. User posts message mentioning a game: "Anyone want to play cod?"
2. Staff member replies to message and runs: `/lfg @user cod`
3. Bot detects game from alias ("cod" → "Call of Duty")
4. Bot checks if user is in correct channel
5. **If wrong channel:**
   - Bot tells user to go to correct channel
   - Bot gives user the game role (if missing)
   - Bot posts LFG ping in the correct channel
6. **If correct channel:**
   - Bot posts LFG ping with role mention

### Example Workflow

**User in #general:**
> "Anyone playing COD tonight?"

**Staff:**
> (Replies to message) `/lfg @user cod`

**Bot response:**
> "Detected game role: Call of Duty. This is not the correct channel, we have a dedicated channel here: #call-of-duty"
>
> (Also posts in #call-of-duty): "@Call of Duty @user Looking for a group? Check out the LFG guide!"

### Adding New Games

1. Edit `wiki/config/games.json`:
   ```json
   "valorant": "Valorant",
   "val": "Valorant"
   ```

2. Edit `wiki/config/channels.json`:
   ```json
   "Valorant": 1234567890123456789
   ```

3. Reload: `[p]wikireload`

---

## Applying Configuration Changes

After editing any config file:

```
[p]wikireload
```

**No bot restart needed!** Changes apply instantly.

---

## Troubleshooting

### Commands don't work
- Check user has an authorized role (in `roles.json`)
- Verify role names match Discord exactly
- Run `[p]wikireload` after config changes
- Run `[p]slash sync` for slash commands

### LFG not detecting games
- Check game alias exists in `games.json`
- Verify alias is lowercase
- Check role name matches Discord exactly

### Channel routing not working
- Verify channel ID is correct (18-19 digits)
- Check bot has access to the channel
- Ensure role name matches exactly

### Config won't reload
- Check JSON syntax (use https://jsonlint.com)
- Look for missing commas or quotes
- Check file encoding is UTF-8
- View bot logs: `[p]logs`

### "Role not found" error
- Role name in config must match Discord exactly
- Check spelling and capitalization
- Verify role exists in your server

---

## Example Configurations

See `wiki/config/examples/` for:
- Small server setup (5 roles, 10 games)
- Medium server setup (15 roles, 30 games)
- Large server setup (30 roles, 90+ games)

Copy an example that fits your server size and customize it!

---

## Advanced Features

### Enable/Disable Commands

In `commands.json`, set `"enabled": false`:

```json
{
  "biweekly": {
    "enabled": false
  }
}
```

Users won't be able to use `/biweekly` until you re-enable it.

### Custom FAFO Timeout Duration

In `commands.json`:

```json
{
  "fafo": {
    "timeout_duration_minutes": 10
  }
}
```

Changes the self-timeout duration from 5 to 10 minutes.

### Multiple Aliases for Same Game

```json
{
  "cod": "Call of Duty",
  "callofduty": "Call of Duty",
  "warzone": "Call of Duty",
  "mw": "Call of Duty"
}
```

All these aliases will map to the same "Call of Duty" role.

---

## Support

- **Documentation**: See main [README.md](../README.md) and [CONFIGURATION.md](../CONFIGURATION.md)
- **Issues**: https://github.com/ShadyTidus/ShadyCogs/issues
- **Author**: ShadyTidus

---

## Changelog

### v2.1.0 (2025)
- JSON configuration system
- Enable/disable individual commands
- Customizable command text and URLs
- `[p]wikireload` command

### v2.0.0 (2025)
- Slash command support
- Security improvements
- Configurable per-server

### v1.0.0 (Original)
- Initial release
- LFG system
- Server rules
- Wiki links
