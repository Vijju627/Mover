import os
import sqlite3
from pathlib import Path

import discord
from discord.ext import commands

# ============================================================
# CONFIG
# ============================================================
TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
PREFIX = "!"

# Railway Volume: set DATA_DIR=/data and mount a volume there.
# Locally it defaults to ./data.
DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "vc_moderation.db"


# ============================================================
# DATABASE
# ============================================================
def init_db():
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS vc_bans (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        db.commit()


def is_vc_banned(guild_id: int, user_id: int) -> bool:
    with sqlite3.connect(DB_PATH) as db:
        row = db.execute(
            "SELECT 1 FROM vc_bans WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ).fetchone()
    return row is not None


def add_vc_ban(guild_id: int, user_id: int):
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            "INSERT OR IGNORE INTO vc_bans (guild_id, user_id) VALUES (?, ?)",
            (guild_id, user_id),
        )
        db.commit()


def remove_vc_ban(guild_id: int, user_id: int) -> bool:
    with sqlite3.connect(DB_PATH) as db:
        cur = db.execute(
            "DELETE FROM vc_bans WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        db.commit()
        return cur.rowcount > 0


# ============================================================
# INTENTS / BOT
# ============================================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(
    command_prefix=PREFIX,
    intents=intents,
    help_command=None,
)


# ============================================================
# EMBEDS
# ============================================================
PURPLE = discord.Color.from_rgb(88, 28, 255)
RED = discord.Color.from_rgb(237, 66, 69)
GREEN = discord.Color.from_rgb(46, 204, 113)


def success_embed(title: str, description: str, *, member=None):
    embed = discord.Embed(
        title="✅  OPERATION SUCCESS",
        description=f"**{title}**\n{description}",
        color=PURPLE,
    )
    if member is not None:
        avatar = member.display_avatar.url
        embed.set_thumbnail(url=avatar)
    embed.set_footer(text="VC Moderation • Team GBL")
    return embed


def error_embed(description: str):
    embed = discord.Embed(
        title="❌  OPERATION FAILED",
        description=description,
        color=RED,
    )
    embed.set_footer(text="VC Moderation • Team GBL")
    return embed


def info_embed(title: str, description: str):
    embed = discord.Embed(
        title=f"🎙️  {title}",
        description=description,
        color=PURPLE,
    )
    embed.set_footer(text="VC Moderation • Team GBL")
    return embed


# ============================================================
# PERMISSIONS
# ============================================================
def is_owner(ctx: commands.Context) -> bool:
    return bool(OWNER_ID) and ctx.author.id == OWNER_ID


def can_manage_vc(ctx: commands.Context) -> bool:
    # Owner gets command-level authorization without needing a Discord
    # moderator role, but the BOT itself still needs Move Members.
    if is_owner(ctx):
        return True
    return ctx.author.guild_permissions.move_members


# ============================================================
# HELPERS
# ============================================================
def get_voice_channel(guild: discord.Guild, channel_id: int):
    channel = guild.get_channel(channel_id)
    if isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
        return channel
    return None


async def disconnect_member(member: discord.Member) -> bool:
    try:
        await member.move_to(None, reason="VC moderation")
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False


# ============================================================
# VC COMMAND GROUP
# ============================================================
@bot.group(name="vc", invoke_without_command=True)
async def vc(ctx: commands.Context):
    if ctx.invoked_subcommand is not None:
        return

    await ctx.send(embed=info_embed(
        "VC MODERATION",
        "```text\n"
        "!vc moveall <channel_id>\n"
        "!vc kickall <channel_id>\n"
        "!vc ban @user\n"
        "!vc unban @user\n"
        "```\n"
        "**Owner:** `vc ...` can be used without the `!` prefix."
    ))


# ============================================================
# MOVE ALL
# ============================================================
@vc.command(name="moveall")
async def moveall(ctx: commands.Context, channel_id: int):
    if not can_manage_vc(ctx):
        return await ctx.send(embed=error_embed(
            "You need **Move Members** permission to use this command."
        ))

    if ctx.guild is None:
        return

    target = get_voice_channel(ctx.guild, channel_id)
    if target is None:
        return await ctx.send(embed=error_embed(
            f"Invalid voice/stage channel ID: `{channel_id}`"
        ))

    if ctx.author.voice is None or ctx.author.voice.channel is None:
        return await ctx.send(embed=error_embed(
            "You must be connected to a voice channel first."
        ))

    source = ctx.author.voice.channel
    if source.id == target.id:
        return await ctx.send(embed=error_embed(
            "The source and target voice channels are the same."
        ))

    members = list(source.members)
    if not members:
        return await ctx.send(embed=error_embed(
            f"No members are currently in **{source.name}**."
        ))

    moved = 0
    failed = 0

    for member in members:
        try:
            await member.move_to(target, reason=f"VC moveall by {ctx.author}")
            moved += 1
        except (discord.Forbidden, discord.HTTPException):
            failed += 1

    extra = f"\n⚠️ Failed: **{failed}**" if failed else ""
    await ctx.send(embed=success_embed(
        "MOVE ALL",
        f"🚀 Moved **{moved}** member(s) from **{source.name}** "
        f"to **{target.name}**.{extra}"
    ))


# ============================================================
# KICK ALL
# ============================================================
@vc.command(name="kickall")
async def kickall(ctx: commands.Context, channel_id: int):
    if not can_manage_vc(ctx):
        return await ctx.send(embed=error_embed(
            "You need **Move Members** permission to use this command."
        ))

    if ctx.guild is None:
        return

    channel = get_voice_channel(ctx.guild, channel_id)
    if channel is None:
        return await ctx.send(embed=error_embed(
            f"Invalid voice/stage channel ID: `{channel_id}`"
        ))

    members = list(channel.members)
    if not members:
        return await ctx.send(embed=error_embed(
            f"No members are currently in **{channel.name}**."
        ))

    kicked = 0
    failed = 0

    for member in members:
        if await disconnect_member(member):
            kicked += 1
        else:
            failed += 1

    extra = f"\n⚠️ Failed: **{failed}**" if failed else ""
    await ctx.send(embed=success_embed(
        "KICK ALL",
        f"🚀 Disconnected **{kicked}** member(s) from **{channel.name}**.{extra}"
    ))


# ============================================================
# VC BAN
# ============================================================
@vc.command(name="ban")
async def vcban(ctx: commands.Context, member: discord.Member):
    if not can_manage_vc(ctx):
        return await ctx.send(embed=error_embed(
            "You need **Move Members** permission to use this command."
        ))

    if ctx.guild is None:
        return

    if member.id == OWNER_ID:
        return await ctx.send(embed=error_embed(
            "The bot owner cannot be VC banned."
        ))

    add_vc_ban(ctx.guild.id, member.id)

    disconnected = False
    if member.voice and member.voice.channel:
        disconnected = await disconnect_member(member)

    status = (
        "They were also disconnected from their current VC."
        if disconnected
        else "If they join a VC, the bot will automatically disconnect them."
    )

    await ctx.send(embed=success_embed(
        "VC BAN",
        f"🚫 {member.mention} is now **VC banned**.\n{status}",
        member=member,
    ))


# ============================================================
# VC UNBAN
# ============================================================
@vc.command(name="unban")
async def vcunban(ctx: commands.Context, member: discord.Member):
    if not can_manage_vc(ctx):
        return await ctx.send(embed=error_embed(
            "You need **Move Members** permission to use this command."
        ))

    if ctx.guild is None:
        return

    removed = remove_vc_ban(ctx.guild.id, member.id)
    if not removed:
        return await ctx.send(embed=error_embed(
            f"{member.mention} is not currently VC banned."
        ))

    await ctx.send(embed=success_embed(
        "VC UNBAN",
        f"🔓 {member.mention} has been removed from the VC ban list.",
        member=member,
    ))


# ============================================================
# AUTO-DISCONNECT VC BANNED USERS
# ============================================================
@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
):
    # Only act when the user is connected/moved into a VC.
    if after.channel is None or member.guild is None:
        return

    # Never disconnect the owner.
    if member.id == OWNER_ID:
        return

    if not is_vc_banned(member.guild.id, member.id):
        return

    await disconnect_member(member)


# ============================================================
# OWNER NO-PREFIX SUPPORT
# ============================================================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Owner can use:
    # vc moveall 123
    # vc kickall 123
    # vc ban @user
    # vc unban @user
    #
    # Everyone else must use:
    # !vc ...
    if (
        OWNER_ID
        and message.author.id == OWNER_ID
        and message.content.strip().lower().startswith("vc ")
    ):
        message.content = "!" + message.content.strip()

    await bot.process_commands(message)


# ============================================================
# COMMAND ERROR HANDLER
# ============================================================
@bot.event
async def on_command_error(ctx: commands.Context, error: Exception):
    if isinstance(error, commands.CommandNotFound):
        return

    if isinstance(error, commands.MissingRequiredArgument):
        return await ctx.send(embed=error_embed(
            "Missing argument. Use `!vc` to see the command format."
        ))

    if isinstance(error, commands.BadArgument):
        return await ctx.send(embed=error_embed(
            "I couldn't find that member/channel. "
            "For users, use a mention such as `@username`."
        ))

    if isinstance(error, commands.MissingPermissions):
        return await ctx.send(embed=error_embed(
            "You don't have permission to use this command."
        ))

    if isinstance(error, commands.NoPrivateMessage):
        return await ctx.send(embed=error_embed(
            "This command can only be used inside a server."
        ))

    print(f"[COMMAND ERROR] {repr(error)}")
    await ctx.send(embed=error_embed(
        "Something went wrong while running that command."
    ))


# ============================================================
# READY
# ============================================================
@bot.event
async def on_ready():
    print("==============================================")
    print(f"Logged in as: {bot.user} (ID: {bot.user.id})")
    print(f"Owner ID: {OWNER_ID}")
    print(f"Database: {DB_PATH}")
    print("VC Moderation Bot is ONLINE")
    print("==============================================")


# ============================================================
# START
# ============================================================
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is missing.")

if OWNER_ID == 0:
    raise RuntimeError("OWNER_ID environment variable is missing.")

init_db()
bot.run(TOKEN)
