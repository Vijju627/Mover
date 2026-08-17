# VC Moderation Bot

A Discord voice moderation bot with:

- `!vc moveall <channel_id>`
- `!vc kickall <channel_id>`
- `!vc ban @user`
- `!vc unban @user`
- Bot owner can use the same commands **without `!`**
- Screenshot-inspired purple `OPERATION SUCCESS` embeds
- VC-ban persistence using SQLite
- Automatically disconnects VC-banned users whenever they join/move into a voice channel

## 1. Discord Developer Portal

Create a bot application and copy its bot token.

In **Bot → Privileged Gateway Intents**, enable:

- Message Content Intent
- Server Members Intent

Voice State Intent is available through the normal gateway intents used by the library.

When inviting the bot, give it at least:

- View Channels
- Send Messages
- Embed Links
- Connect
- Move Members

For moderation commands, the bot's role must be high enough to move/disconnect the target members.

## 2. Find your Discord User ID

Enable Developer Mode in Discord, then copy your own user ID.

Put that value into `OWNER_ID`.

## 3. Railway deployment

### Option A — GitHub

1. Upload this folder to a GitHub repository.
2. Create a new Railway project.
3. Deploy the GitHub repository.
4. Add these Variables:

```text
DISCORD_TOKEN=your_bot_token
OWNER_ID=your_discord_user_id
DATA_DIR=/data
```

5. Deploy/redeploy.

### Persistent VC bans

Railway containers have ephemeral storage. To keep the SQLite ban database across redeploys:

1. Add a Railway Volume.
2. Mount it at:

```text
/data
```

3. Keep:

```text
DATA_DIR=/data
```

Without a volume, the bot still works, but the VC-ban database can be lost when the service is recreated.

## 4. Commands

Normal moderator:

```text
!vc moveall 123456789012345678
!vc kickall 123456789012345678
!vc ban @username
!vc unban @username
```

Owner:

```text
vc moveall 123456789012345678
vc kickall 123456789012345678
vc ban @username
vc unban @username
```

## Important behavior

### moveall

The bot takes everyone from the command user's current VC and moves them into the specified target VC.

### kickall

The specified VC channel ID is used directly. Everyone currently in that VC is disconnected.

### ban

The user is added to a server-specific VC ban list. If they are currently in a VC, they are disconnected immediately. If they join/move into a VC later, `on_voice_state_update` disconnects them automatically.

### unban

Removes that user from the server's VC ban list.

## Troubleshooting

### "Missing Move Members permission"

Give the bot role **Move Members** permission.

### Bot cannot move a particular member

Discord role hierarchy and channel permissions can prevent a bot from moving members. Put the bot's role above the roles of users it needs to moderate.

### Commands do not work

Make sure Message Content Intent is enabled in the Developer Portal and that the bot can read/send messages in the channel.

### Owner no-prefix command does not work

Check that `OWNER_ID` is your exact Discord user ID and that the command starts with:

```text
vc
```

Example:

```text
vc ban @username
```
