# Example Configuration Files

These are **example/template** configuration files for the Wiki cog. Use these as a starting point for your own server.

## Quick Setup

### Option 1: Copy All Examples

```bash
# From the wiki/config/examples/ directory
cp roles_example.json ../roles.json
cp games_small_example.json ../games.json
cp channels_example.json ../channels.json
cp commands_example.json ../commands.json
cp rules_example.json ../rules.json
```

Then edit each file to match your server.

### Option 2: Pick Your Server Size

Choose the games config that matches your server size:

- **Small Server (10 games):** `games_small_example.json`
- **Medium Server (30+ games):** Use the default `games.json` in parent directory and trim
- **Large Server (90+ games):** Use the default `games.json` in parent directory

## Files Included

### roles_example.json
Basic role authorization setup. Lists which Discord roles can use wiki commands.

**Customize:**
- Add your server's staff role names
- Role names must match Discord exactly (case-sensitive)

### games_small_example.json
10 popular games with aliases.

**Good for:**
- Small gaming communities
- Focused on specific games
- Just starting out

**Includes:**
Minecraft, Call of Duty, Valorant, Apex Legends, League of Legends, Fortnite, World of Warcraft, Counter-Strike, Rocket League, Overwatch

### channels_example.json
Maps game roles to channel IDs.

**Customize:**
1. Get your channel IDs (Developer Mode → Right-click channel → Copy ID)
2. Replace the example IDs
3. Add/remove games to match your server

### commands_example.json
All command configurations with placeholder URLs.

**Customize:**
- Replace `your-wiki-url.com` with your actual wiki/website
- Change command text to match your community's tone
- Disable commands you don't need with `"enabled": false`

### rules_example.json
Generic 10-rule template.

**Customize:**
- Replace with your actual server rules
- Keep the number format (1-10)
- Use `\n` for line breaks
- Can include markdown links: `[Text](URL)`

## After Copying

1. **Edit all files** with your server's info
2. **Reload configs:** `[p]wikireload`
3. **Test:** `/rule 1` and `/lfg`

## Need More Help?

- See parent directory's README.md for full configuration guide
- Check ../../CONFIGURATION.md for detailed instructions
- Check ../../README.md for complete documentation

## Tips

### Finding Channel IDs
1. Discord Settings → Advanced → Enable Developer Mode
2. Right-click any channel
3. "Copy ID"
4. Paste into channels.json (must be a number, not a string)

### Role Names
Must match Discord **exactly**:
- ✅ "Community Managers"
- ❌ "community managers" (wrong case)
- ❌ "CommunityManagers" (no space)

### JSON Syntax
- Use double quotes `"` not single `'`
- Commas between items (but not after the last one)
- Validate at https://jsonlint.com if you get errors
