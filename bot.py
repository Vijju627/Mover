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

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "vc_moderation.db"

# Screenshot-style custom emojis
SUCCESS_EMOJI = "<a:Sucess:1500864508875243711>"
WRONG_EMOJI = "<:wrong:1513763861520584875>"


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
# SCREENSHOT-STYLE EMBEDS
# ============================================================
def operation_success(message: str):
    # Matches the compact style from the reference screenshot:
    # title: <a:Sucess:...> OPERATION SUCCESS
    # body: blockquote + bullet + bold message
    embed = discord.Embed(
        title=f"{SUCCESS_EMOJI} OPERATION SUCCESS",
        description=f"> - **{message}**",
        color=discord.Color.from_rgb(52, 211, 82),
    )
    return embed


def access_error(message: str):
    # Matches the reference ACCESS DENIED / ERROR style.
    embed = discord.Embed(
        title=f"{WRONG_EMOJI} ACCESS DENIED / ERROR",
        description=f"> - **{message}**",
        color=discord.Color.from_rgb(255, 126, 45),
    )
    return embed


# ============================================================
# PERMISSIONS / HELPERS
# ============================================================
def is_owner(ctx: commands.Context) -> bool:
    return bool(OWNER_ID) and ctx.author.id == OWNER_ID


def can_manage_vc(ctx: commands.Context) -> bool:
    if is_owner(ctx):
        return True
    return ctx.author.guild_permissions.move_members


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
# !vc WITH NO SUBCOMMAND
# Exact requested error style:
# <:wrong:1513763861520584875> ACCESS DENIED / ERROR
# > - **Please provide a member or reply to their message.**
# ============================================================
@bot.group(name="vc", invoke_without_command=True)
async def vc(ctx: commands.Context):
    if ctx.invoked_subcommand is not None:
        return

    await ctx.send(embed=access_error(
        "Please provide a member or reply to their message."
    ))


# ============================================================
# MOVE ALL
# ============================================================
@vc.command(name="moveall")
async def moveall(ctx: commands.Context, channel_id: int):
    if not can_manage_vc(ctx):
        return await ctx.send(embed=access_error(
            "You don't have permission to use voice moderation commands."
        ))

    if ctx.guild is None:
        return

    target = get_voice_channel(ctx.guild, channel_id)
    if target is None:
        return await ctx.send(embed=access_error(
            "Please provide a valid voice channel ID."
        ))

    if ctx.author.voice is None or ctx.author.voice.channel is None:
        return await ctx.send(embed=access_error(
            "You must be in a Voice Channel to use voice moderation commands."
        ))

    source = ctx.author.voice.channel

    if source.id == target.id:
        return await ctx.send(embed=access_error(
            "The source and target voice channels are the same."
        ))

    members = list(source.members)
    if not members:
        return await ctx.send(embed=access_error(
            "There are no members in your current Voice Channel."
        ))

    moved = 0
    failed = 0

    for member in members:
        try:
            await member.move_to(
                target,
                reason=f"VC moveall by {ctx.author}"
            )
            moved += 1
        except (discord.Forbidden, discord.HTTPException):
            failed += 1

    # Exact requested compact screenshot style.
    # Example:
    # <a:Sucess:...> OPERATION SUCCESS
    # > - **🚀 Moved 1 members from General VC to <#123>.**
    await ctx.send(embed=operation_success(
        f"🚀 Moved {moved} members from {source.name} to <#{target.id}>."
    ))

    if failed:
        # Keep the main success embed clean as requested.
        # Errors are only logged in Railway.
        print(
            f"[MOVEALL] Failed to move {failed} member(s) "
            f"in guild {ctx.guild.id}"
        )


# ============================================================
# KICK ALL
# ============================================================
@vc.command(name="kickall")
async def kickall(ctx: commands.Context, channel_id: int):
    if not can_manage_vc(ctx):
        return await ctx.send(embed=access_error(
            "You don't have permission to use voice moderation commands."
        ))

    if ctx.guild is None:
        return

    channel = get_voice_channel(ctx.guild, channel_id)
    if channel is None:
        return await ctx.send(embed=access_error(
            "Please provide a valid voice channel ID."
        ))

    members = list(channel.members)
    if not members:
        return await ctx.send(embed=access_error(
            "There are no members in that Voice Channel."
        ))

    kicked = 0
    failed = 0

    for member in members:
        if await disconnect_member(member):
            kicked += 1
        else:
            failed += 1

    # Same exact OPERATION SUCCESS style as moveall.
    await ctx.send(embed=operation_success(
        f"🚀 Disconnected {kicked} members from <#{channel.id}>."
    ))

    if failed:
        print(
            f"[KICKALL] Failed to disconnect {failed} member(s) "
            f"in guild {ctx.guild.id}"
        )


# ============================================================
# VC BAN
# ============================================================
@vc.command(name="ban")
async def vcban(ctx: commands.Context, member: discord.Member):
    if not can_manage_vc(ctx):
        return await ctx.send(embed=access_error(
            "You don't have permission to use voice moderation commands."
        ))

    if ctx.guild is None:
        return

    if member.id == OWNER_ID:
        return await ctx.send(embed=access_error(
            "The bot owner cannot be VC banned."
        ))

    add_vc_ban(ctx.guild.id, member.id)

    if member.voice and member.voice.channel:
        await disconnect_member(member)

    await ctx.send(embed=operation_success(
        f"🚫 VC banned {member.mention}."
    ))


# ============================================================
# VC UNBAN
# ============================================================
@vc.command(name="unban")
async def vcunban(ctx: commands.Context, member: discord.Member):
    if not can_manage_vc(ctx):
        return await ctx.send(embed=access_error(
            "You don't have permission to use voice moderation commands."
        ))

    if ctx.guild is None:
        return

    removed = remove_vc_ban(ctx.guild.id, member.id)

    if not removed:
        return await ctx.send(embed=access_error(
            f"{member.mention} is not VC banned."
        ))

    await ctx.send(embed=operation_success(
        f"🔓 VC unbanned {member.mention}."
    ))


# ============================================================
# AUTO DISCONNECT VC-BANNED USERS
# ============================================================
@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
):
    if after.channel is None or member.guild is None:
        return

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
        return await ctx.send(embed=access_error(
            "Please provide all required arguments."
        ))

    if isinstance(error, commands.BadArgument):
        return await ctx.send(embed=access_error(
            "Please provide a valid member or channel ID."
        ))

    if isinstance(error, commands.MissingPermissions):
        return await ctx.send(embed=access_error(
            "You don't have permission to use this command."
        ))

    print(f"[COMMAND ERROR] {repr(error)}")
    await ctx.send(embed=access_error(
        "An error occurred while running this command."
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
