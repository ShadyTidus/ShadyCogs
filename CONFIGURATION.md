# Wiki Cog Configuration Guide

The Wiki cog uses **easy-to-edit JSON files** for all configuration. No Python knowledge required!

## Configuration Files

All config files are located in `wiki/config/`:

```
wiki/config/
├── roles.json          # Authorized roles
├── games.json          # Game aliases for LFG
├── channels.json       # Role-to-channel mappings
├── commands.json       # Command text and URLs
└── rules.json          # Server rules (1-10)
```

---

## 1. roles.json - Authorized Roles

Controls which Discord roles can use wiki commands.

```json
{
  "authorized_roles": [
    "Game Server Team",
    "Advisors",
    "Moderators"
  ]
}
```

**How to edit:**
1. Open `wiki/config/roles.json`
2. Add or remove role names from the `authorized_roles` array
3. Role names must match **exactly** (case-sensitive)
4. Run `[p]wikireload` to apply changes

---

## 2. games.json - Game Aliases

Maps game nicknames to Discord role names for the LFG system.

```json
{
  "alias_to_role": {
    "cod": "Call of Duty",
    "wow": "World of Warcraft",
    "mc": "Minecraft",
    "apex": "Apex Legends"
  }
}
```

**How to add a game:**
1. Open `wiki/config/games.json`
2. Add a new line in `alias_to_role`:
   ```json
   "nickname": "Exact Discord Role Name"
   ```
3. Use lowercase for the nickname
4. Role name must match Discord exactly
5. Run `[p]wikireload` to apply

**Example:**
```json
"ff14": "Final Fantasy XIV",
"ffxiv": "Final Fantasy XIV",
"valorant": "Valorant",
"val": "Valorant"
```

---

## 3. channels.json - Channel Mappings

Maps Discord roles to specific channel IDs for LFG routing.

```json
{
  "role_to_channel": {
    "Call of Duty": 1067440688737820683,
    "Minecraft": 1109614662594613298,
    "World of Warcraft": 1067440649479131187
  }
}
```

**How to add a channel mapping:**
1. Get the channel ID:
   - Enable Developer Mode in Discord
   - Right-click channel → Copy ID
2. Open `wiki/config/channels.json`
3. Add the mapping:
   ```json
   "Role Name": 1234567890123456789
   ```
4. Run `[p]wikireload`

---

## 4. commands.json - Command Configuration

Customize text, URLs, and behavior for each command.

### Command Structure

```json
"commandname": {
  "enabled": true,
  "text": "Your custom message here",
  "url": "https://your-wiki-url.com",
  "url_text": "Link Text",
  "emoji": "📌"
}
```

### Available Commands

#### host
```json
"host": {
  "enabled": true,
  "text": "Interested in hosting? Check our guidelines:",
  "url": "https://wiki.example.com/hosting",
  "url_text": "Hosting Guide",
  "emoji": "📌"
}
```

#### biweekly
```json
"biweekly": {
  "enabled": true,
  "text": "Join our D&D sessions!",
  "url": "https://wiki.example.com/dnd",
  "url_text": "D&D Guide",
  "emoji": "🧙"
}
```

#### wow
```json
"wow": {
  "enabled": true,
  "text": "World of Warcraft info:",
  "url": "https://wiki.example.com/wow",
  "url_text": "WoW Guide",
  "emoji": "🐉"
}
```

#### hosted
```json
"hosted": {
  "enabled": true,
  "text": "Check out our game servers:",
  "url": "https://wiki.example.com/servers",
  "url_text": "Server List",
  "emoji": "🖥️"
}
```

#### lfg
```json
"lfg": {
  "enabled": true,
  "guide_url": "https://wiki.example.com/lfg",
  "guide_text": "LFG Guide",
  "correct_channel_text": "Looking for a group? Check out LFG!",
  "wrong_channel_text": "Detected game role: **{role}**. Wrong channel! Go to: {channel}",
  "no_channel_text": "Looking for a group? Tag your game!",
  "no_game_detected": "No game found in message.",
  "role_not_found": "Role not found: {role}",
  "emoji": "📌"
}
```

**Note:** `{role}`, `{channel}`, and `{customize_link}` are placeholders that get replaced automatically.

#### rule
```json
"rule": {
  "enabled": true,
  "rules_url": "https://wiki.example.com/rules",
  "embed_title": "Server Rules",
  "embed_color": "orange",
  "invalid_rule_text": "Invalid rule number. Use 1-10."
}
```

#### fafo
```json
"fafo": {
  "enabled": true,
  "warning_title": "⚠️ WARNING",
  "warning_text": "Click the button to time yourself out.",
  "button_label": "FAFO",
  "timeout_duration_minutes": 5,
  "timeout_message": "You've been timed out for {duration} minutes.",
  "no_permission_message": "I can't timeout you.",
  "member_not_found": "Member not found."
}
```

### Disabling Commands

Set `"enabled": false` to disable any command:

```json
"biweekly": {
  "enabled": false
}
```

---

## 5. rules.json - Server Rules

Configure your server's rules (1-10).

```json
{
  "rules": {
    "1": {
      "title": "1️⃣ Be Respectful",
      "text": "Treat everyone with respect."
    },
    "2": {
      "title": "2️⃣ 18+ Only",
      "text": "You must be 18 or older."
    }
  }
}
```

**How to edit:**
1. Open `wiki/config/rules.json`
2. Edit the `title` and `text` for each rule
3. Keep numbers 1-10
4. Use `\n` for line breaks in text
5. You can include markdown links: `[Text](URL)`
6. Run `[p]wikireload`

**Example with links:**
```json
"6": {
  "title": "6️⃣ Use Proper Channels",
  "text": "Use the right channels.\n📌 [Channel Guide](https://wiki.example.com/channels)"
}
```

---

## Applying Changes

After editing any config file:

```
[p]wikireload
```

This reloads all configurations without restarting the bot!

---

## Quick Setup for New Servers

1. **Copy the config folder** from the default setup
2. **Edit roles.json** - Add your staff role names
3. **Edit games.json** - Add your game roles and nicknames
4. **Edit channels.json** - Map roles to your channel IDs
5. **Edit commands.json** - Update URLs to your wiki/guides
6. **Edit rules.json** - Write your server rules
7. **Run** `[p]wikireload`
8. **Test** with `/rule 1` or `/host`

---

## Tips

### Finding Channel IDs
1. Enable Developer Mode (Discord Settings → Advanced)
2. Right-click any channel
3. Click "Copy ID"

### Finding Role Names
Role names in configs must match Discord **exactly**:
- ✅ "Game Server Team"
- ❌ "game server team" (wrong case)
- ❌ "GameServerTeam" (missing spaces)

### JSON Syntax
- Use double quotes `"` not single quotes `'`
- Don't forget commas between items
- Last item in a list/object should NOT have a trailing comma
- Use online JSON validators if you get errors

### Testing Changes
After `[p]wikireload`:
1. Test a simple command: `/host`
2. Test LFG: Reply to a message with game name, run `/lfg`
3. Test rules: `/rule 1`

---

## Troubleshooting

### "Config failed to load"
- Check JSON syntax (missing quotes, commas, brackets)
- Use a JSON validator: https://jsonlint.com
- Check file encoding is UTF-8

### "Role not found"
- Check role name matches Discord exactly (case-sensitive)
- Check role exists in your server

### "Channel not found"
- Verify channel ID is correct (18-19 digits)
- Make sure bot has access to the channel

### Commands don't update
- Run `[p]wikireload` after editing configs
- Check bot logs for errors

---

## Default Configuration

The default configs are set up for the PA (Parents That Game) Discord server. If you're setting up for a different server, you'll need to customize:

- All role names in `roles.json`
- All role names and channel IDs in `games.json` and `channels.json`
- All URLs in `commands.json`
- All rules in `rules.json`

---

## Need Help?

- Check bot logs: `[p]logs`
- Test config reload: `[p]wikireload`
- Report issues: https://github.com/ShadyTidus/ShadyCogs/issues
