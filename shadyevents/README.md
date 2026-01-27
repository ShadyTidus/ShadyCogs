# ShadyEvents

Tournament and bracket management system for Discord gaming communities.

## Features

- **Solo Tournaments**: 1v1 or FFA-style tournaments
- **Team Tournaments**: Support for 2v2, 3v3, 5v5, 6v6, etc.
- **Random Team Mode**: All participants join individually, teams auto-assigned at start
- **Pre-Made Team Mode**: Captains register teams + pickup player pool
- **Pickup Players**: Individuals can join as "pickups" to fill incomplete teams
- **Automatic Team Filling**: Pickup players randomly assigned to incomplete teams when tournament starts
- **Role Authorization**: Only authorized staff can create/manage tournaments

## Installation

```
[p]repo add ShadyRepo <repo_url>
[p]cog install ShadyRepo shadyevents
[p]load shadyevents
```

**Optional:** Install Pillow for bracket image generation:
```
[p]pipinstall pillow
```

## Commands

### `/tournament create`
Opens a modal to create a tournament:
- **Tournament Name**: e.g., "Marvel Rivals Championship"
- **Game/Category**: e.g., "Marvel Rivals", "Rocket League"
- **Type**: `solo` or `team`
- **Team Size**: For team tournaments (2-10)
- **Team Mode**: `random` or `premade` (for team tournaments)

### `/tournament list`
Shows all active (not started) tournaments with participant counts

### `/tournament start` (Coming Soon)
Finalizes signups and generates brackets

### `/tournament bracket` (Coming Soon)
Views current bracket status

## Tournament Types

### Solo Tournament
Perfect for 1v1 games or FFA (Free-For-All) competitions.

**Example:**
```
Type: solo
```
Players click "Join Tournament" button to enter individually.

### Team Tournament - Random Mode
All participants join individually, bot randomly creates balanced teams when tournament starts.

**Example:**
```
Type: team
Team Size: 6
Team Mode: random
```
Bot will create teams of 6 from all participants (e.g., 48 players → 8 teams).

### Team Tournament - Pre-Made Mode
Teams register with their roster, individuals can join as "pickups" to fill incomplete teams.

**Example:**
```
Type: team
Team Size: 3
Team Mode: premade
```

Players see two signup options:
- **⭐ Register Team**: Opens modal for captain to enter team name + player mentions
- **🎲 Join as Pickup**: Individual signup for random team assignment

## How Pre-Made Teams Work

### Registering a Full Team

Captain clicks "⭐ Register Team", modal opens:
- **Team Name**: "The Champions"
- **Players**: @player1 @player2 @player3

Bot confirms: "✅ Team The Champions registered! Roster (3/3): @player1, @player2, @player3"

### Registering an Incomplete Team
Captain clicks "⭐ Register Team":
- **Team Name**: "Team Alpha"
- **Players**: @player1 @player2

Bot confirms:
```
✅ Team Alpha registered!

Roster (2/3):
@player1, @player2

⚠️ Incomplete Team: Your team needs 1 more player(s).
Pickup players will be randomly assigned to fill your roster when the tournament starts.
```

### Joining as Pickup Player
Individual clicks "🎲 Join as Pickup":
```
✅ You've joined as a pickup player!

⚠️ Note: You will be randomly assigned to a team that needs players 
when the tournament starts. (5 pickup players)
```

### What Happens at Tournament Start
When staff runs `/tournament start`:

1. **Incomplete teams are filled:**
   - Team Alpha (2/3) gets 1 random pickup player
   - Team Bravo (1/3) gets 2 random pickup players
   
2. **Excess pickups form new teams:**
   - If 6 pickup players remain and team size is 3, creates 2 new teams
   
3. **Bracket is generated:**
   - All complete teams enter the bracket
   - Match pairings are announced

### Example Scenario: 3v3 Tournament

**Signups:**
- Team Alpha: @alice, @bob (needs 1)
- Team Bravo: @charlie (needs 2)
- Team Champions: @david, @emma, @frank (complete)
- Pickup Players: @grace, @henry, @iris, @jack, @kate, @leo

**After `/tournament start`:**
- Team Alpha: @alice, @bob, **@grace** ✅
- Team Bravo: @charlie, **@henry**, **@iris** ✅
- Team Champions: @david, @emma, @frank ✅
- **Pickup Team 1**: @jack, @kate, @leo ✅

**Result:** 4 teams → Single elimination bracket (2 rounds)

## Signup Flow Examples

### Solo Tournament
```
[Tournament Post]
🏆 Fortnite Solo Championship
Type: Solo (1v1 or FFA)
Participants: 12

[Join Tournament] ← Click to enter
```

### Random Team Tournament
```
[Tournament Post]
🏆 COD 6v6 Random Teams
Type: Team (6v6)
Team Mode: Random
Teams will be randomly assigned when bracket starts
Participants: 24

[Join Tournament] ← Click to enter
```

### Pre-Made Team Tournament
```
[Tournament Post]
🏆 Marvel Rivals Championship
Type: Team (6v6)
Team Mode: Premade

⚠️ Signup Options:
⭐ Register Team: Captain registers full team
🎲 Join as Pickup: Individuals randomly assigned to incomplete teams

Registered Teams: 3
Pickup Players: 8

[⭐ Register Team] [🎲 Join as Pickup] ← Two buttons
```

## Authorization

Only users with the following can create/manage tournaments:
- Administrator permission
- Role ID listed in `E:/wiki/config/roles.json`

## Technical Details

- **Storage**: Uses Red's Config system (guild-scoped)
- **Persistent Views**: Signup buttons persist through bot restarts
- **Player Validation**: Prevents duplicate players across teams
- **Pickup Pool**: Automatically removes players from pickup pool when they join a team

## Future Features

Phase 2 (Coming Soon):
- Bracket generation (single elimination, double elimination, round robin)
- Match reporting and tracking
- Automatic progression through rounds
- Winner announcements

Phase 3 (Planned):
- Bracket images with Pillow
- Tournament seeding
- Best-of-3/5 series support
- Tournament templates
- Statistics and history

## Notes

- Pickup players can switch to team registration (automatically removed from pickup pool)
- Team names must be unique within a tournament
- Players can only be on one team per tournament
- Incomplete teams are clearly marked with warnings
- Random assignment is truly random (uses Python's random.choice)

## Examples

### Quick 1v1 Tournament
```
/tournament create channel:#tournaments
Name: Apex 1v1 Tournament
Type: solo
```

### Random 3v3 Rocket League
```
/tournament create channel:#events
Name: RL Random 3s
Game: Rocket League
Type: team
Team Size: 3
Team Mode: random
```

### Pre-Made 6v6 Marvel Rivals
```
/tournament create channel:#tournaments
Name: Marvel Rivals Championship
Game: Marvel Rivals
Type: team
Team Size: 6
Team Mode: premade
```
Result: Teams can register with 1-6 players, pickups fill the gaps!
