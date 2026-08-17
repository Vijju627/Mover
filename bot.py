import os
import sqlite3
from pathlib import Path

import discord
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
SERVER_INVITE = os.getenv("SERVER_INVITE", "")
PREFIX = "!"

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "vc_moderation.db"

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

def is_vc_banned(guild_id, user_id):
    with sqlite3.connect(DB_PATH) as db:
        row = db.execute(
            "SELECT 1 FROM vc_bans WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        ).fetchone()
    return row is not None

def add_vc_ban(guild_id, user_id):
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            "INSERT OR IGNORE INTO vc_bans (guild_id, user_id) VALUES (?, ?)",
            (guild_id, user_id)
        )
        db.commit()

def remove_vc_ban(guild_id, user_id):
    with sqlite3.connect(DB_PATH) as db:
        cur = db.execute(
            "DELETE FROM vc_bans WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        )
        db.commit()
        return cur.rowcount > 0

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

SUCCESS_EMOJI = "<a:Sucess:1500864508875243711>"
ERROR_EMOJI = "<:wrong:1513763861520584875>"

def success_embed(description):
    return discord.Embed(
        title=f"{SUCCESS_EMOJI} OPERATION SUCCESS",
        description=f"> - **{description}**",
        color=discord.Color.green()
    )

def error_embed(description):
    return discord.Embed(
        title=f"{ERROR_EMOJI} ACCESS DENIED / ERROR",
        description=f"> - **{description}**",
        color=discord.Color.orange()
    )

def is_owner(ctx):
    return OWNER_ID != 0 and ctx.author.id == OWNER_ID

def can_manage_vc(ctx):
    return is_owner(ctx) or ctx.author.guild_permissions.move_members

def get_voice_channel(guild, channel_id):
    channel = guild.get_channel(channel_id)
    if isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
        return channel
    return None

@bot.group(name="vc", invoke_without_command=True)
async def vc(ctx):
    if ctx.invoked_subcommand is not None:
        return

    # `vc` is a voice-moderation help command, but it is only valid
    # while the caller is connected to a Voice Channel.
    if ctx.guild is None or ctx.author.voice is None or ctx.author.voice.channel is None:
        return await ctx.send(embed=error_embed(
            "You must be in a Voice Channel to use voice moderation commands."
        ))

    embed = discord.Embed(
        title="Voice Moderation Control",
        description=(
            "**Voice Moderation:**\n"
            "• `voice mute [user]` - Mute a user (supports reply)\n"
            "• `voice unmute [user]` - Unmute a user (supports reply)\n"
            "• `voice muteall` - Mute everyone in your VC\n"
            "• `voice unmuteall` - Unmute everyone in your VC\n"
            "• `voice kick [user]` - Kick user from VC (supports reply)\n"
            "• `voice kickall` - Kick everyone from your VC\n"
            "• `voice deafen [user]` - Deafen a user (supports reply)\n"
            "• `voice undeafen [user]` - Undeafen a user (supports reply)\n"
            "• `voice deafenall` - Deafen everyone in your VC\n"
            "• `voice undeafenall` - Undeafen everyone in your VC\n"
            "• `voice move [user] [vc]` - Move user to VC (supports reply)\n"
            "• `voice moveall [target_vc] [source_vc]` - Mass movement"
        ),
        color=discord.Color.purple(),
    )
    await ctx.send(embed=embed)

@vc.command(name="moveall")
async def moveall(ctx, channel_id: int):
    if not can_manage_vc(ctx):
        return await ctx.send(embed=error_embed(
            "You don't have permission to use voice moderation."
        ))

    if ctx.guild is None:
        return

    target = get_voice_channel(ctx.guild, channel_id)
    if target is None:
        return await ctx.send(embed=error_embed(
            "Please provide a valid voice channel ID."
        ))

    if ctx.author.voice is None or ctx.author.voice.channel is None:
        return await ctx.send(embed=error_embed(
            "You must be in a Voice Channel to use voice moderation commands."
        ))

    source = ctx.author.voice.channel

    if source.id == target.id:
        return await ctx.send(embed=error_embed(
            "The source and target Voice Channels are the same."
        ))

    members = list(source.members)
    moved = 0

    for member in members:
        try:
            await member.move_to(target, reason=f"VC moveall by {ctx.author}")
            moved += 1
        except (discord.Forbidden, discord.HTTPException):
            pass

    await ctx.send(embed=success_embed(
        f"🚀 Moved **{moved}** members from **{source.name}** to <#{target.id}>."
    ))

@vc.command(name="kickall")
async def kickall(ctx, channel_id: int):
    if not can_manage_vc(ctx):
        return await ctx.send(embed=error_embed(
            "You don't have permission to use voice moderation."
        ))

    if ctx.guild is None:
        return

    channel = get_voice_channel(ctx.guild, channel_id)
    if channel is None:
        return await ctx.send(embed=error_embed(
            "Please provide a valid voice channel ID."
        ))

    members = list(channel.members)

    if not members:
        return await ctx.send(embed=error_embed(
            "There are no members in that Voice Channel."
        ))

    kicked = 0
    for member in members:
        try:
            await member.move_to(None, reason=f"VC kickall by {ctx.author}")
            kicked += 1
        except (discord.Forbidden, discord.HTTPException):
            pass

    await ctx.send(embed=success_embed(
        f"🚀 Disconnected **{kicked}** members from <#{channel.id}>."
    ))

@vc.command(name="ban")
async def vcban(ctx, member: discord.Member):
    if not can_manage_vc(ctx):
        return await ctx.send(embed=error_embed(
            "You don't have permission to use voice moderation."
        ))

    if ctx.guild is None:
        return

    if member.id == OWNER_ID:
        return await ctx.send(embed=error_embed(
            "The bot owner cannot be VC banned."
        ))

    add_vc_ban(ctx.guild.id, member.id)

    if member.voice and member.voice.channel:
        try:
            await member.move_to(None, reason=f"VC ban by {ctx.author}")
        except (discord.Forbidden, discord.HTTPException):
            pass

    await ctx.send(embed=success_embed(
        f"🚫 {member.mention} has been **VC banned**."
    ))

@vc.command(name="unban")
async def vcunban(ctx, member: discord.Member):
    if not can_manage_vc(ctx):
        return await ctx.send(embed=error_embed(
            "You don't have permission to use voice moderation."
        ))

    if ctx.guild is None:
        return

    removed = remove_vc_ban(ctx.guild.id, member.id)

    if not removed:
        return await ctx.send(embed=error_embed(
            f"{member.mention} is not VC banned."
        ))

    await ctx.send(embed=success_embed(
        f"🔓 {member.mention} has been **VC unbanned**."
    ))

@bot.command(name="link")
async def link(ctx):
    if not SERVER_INVITE:
        return await ctx.send(embed=error_embed(
            "Server invite link is not configured."
        ))
    await ctx.send(SERVER_INVITE)


# ============================================================
# SAFE OWNER-ONLY SPAM FEATURE
# ============================================================

import asyncio

spam_tasks = {}
MAX_SPAM_MESSAGES = 5
SPAM_DELAY = 1.0

async def run_safe_spam(ctx, member, text):
    key = (ctx.guild.id if ctx.guild else 0, ctx.channel.id)
    try:
        for _ in range(MAX_SPAM_MESSAGES):
            if key not in spam_tasks:
                break
            await ctx.send(f"{member.mention} {text}")
            await asyncio.sleep(SPAM_DELAY)
    except asyncio.CancelledError:
        pass
    finally:
        spam_tasks.pop(key, None)

@bot.command(name="spam")
async def spam(ctx, member: discord.Member, *, text: str):
    if not is_owner(ctx):
        return await ctx.send(embed=error_embed("You do not have permission to use this command."))

    if ctx.guild is None:
        return

    key = (ctx.guild.id, ctx.channel.id)
    old_task = spam_tasks.get(key)

    if old_task and not old_task.done():
        old_task.cancel()

    spam_tasks[key] = asyncio.create_task(
        run_safe_spam(ctx, member, text)
    )

@bot.command(name="stopspam")
async def stopspam(ctx):
    if not is_owner(ctx):
        return await ctx.send(embed=error_embed("You do not have permission to use this command."))

    key = (ctx.guild.id if ctx.guild else 0, ctx.channel.id)
    task = spam_tasks.pop(key, None)

    if task and not task.done():
        task.cancel()
        await ctx.send("Spam stopped.")
    else:
        await ctx.send("No active spam is running.")


# ============================================================
# AUTO VC BAN
# ============================================================

@bot.event
async def on_voice_state_update(member, before, after):
    if after.channel is None:
        return
    if member.id == OWNER_ID:
        return
    if not is_vc_banned(member.guild.id, member.id):
        return
    try:
        await member.move_to(None, reason="VC banned user auto-disconnect")
    except (discord.Forbidden, discord.HTTPException):
        pass

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.strip()
    lower = content.lower()

    # Allow the owner to use every currently registered text command
    # without the ! prefix.  Spam/Stopspam are intentionally recognized
    # for everyone so non-owners receive the explicit permission error.
    if lower == "vc" or lower.startswith("vc "):
        if is_owner_simple(message.author.id):
            message.content = "!" + content
    elif lower == "link":
        if is_owner_simple(message.author.id):
            message.content = "!link"
    elif lower == "stopspam" or lower.startswith("spam "):
        # Prefixless spam commands are parsed for everyone; the command
        # itself enforces owner-only permission.
        message.content = "!" + content

    await bot.process_commands(message)

def is_owner_simple(user_id: int) -> bool:
    return bool(OWNER_ID) and user_id == OWNER_ID

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return

    if isinstance(error, commands.MissingRequiredArgument):
        return await ctx.send(embed=error_embed(
            "Please provide the required information."
        ))

    if isinstance(error, commands.BadArgument):
        return await ctx.send(embed=error_embed(
            "Please provide a valid member or channel."
        ))

    print(f"[COMMAND ERROR] {repr(error)}")

    try:
        await ctx.send(embed=error_embed(
            "Something went wrong while processing the command."
        ))
    except Exception:
        pass

@bot.event
async def on_ready():
    print("==========================================")
    print(f"Logged in as: {bot.user}")
    print(f"Owner ID: {OWNER_ID}")
    print(f"Database: {DB_PATH}")
    print("VC Moderation Bot is ONLINE")
    print("==========================================")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is missing.")

if OWNER_ID == 0:
    raise RuntimeError("OWNER_ID environment variable is missing.")

init_db()
bot.run(TOKEN)
