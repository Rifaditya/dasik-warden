# Copyright (C) 2026 Dasik (Rifaditya) | GNU GPLv3
"""
Dasik Warden - Dedicated server moderation bot for Dasik Igaijinn Discord server.
Enforces anti-piracy, zero-gatekeeping ("Help or Stay Silent"), and 3-strike disciplinary ladder.
"""

from datetime import datetime, timedelta, timezone
import os
import sys
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from warden_core import (
    evaluate_message_content,
    ViolationType,
    DemeritManager,
)

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()
TOKEN = os.getenv("DISCORD_WARDEN_TOKEN")

if not TOKEN:
    print("CRITICAL: DISCORD_WARDEN_TOKEN not found in environment!")
    sys.exit(1)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!warden_", intents=intents)
demerit_manager = DemeritManager(storage_path="demerits.json")

# Role & Server Constants
GUILD_ID = 1546093898907258933

def format_duration(minutes: int) -> str:
    """Formats minutes into human-readable string like '5 minutes', '2 hours 40 minutes', '28 days'."""
    if minutes < 60:
        return f"{minutes}-minute timeout"
    hours = minutes // 60
    rem_mins = minutes % 60
    if hours < 24:
        if rem_mins == 0:
            return f"{hours}-hour timeout"
        return f"{hours}h {rem_mins}m timeout"
    days = hours // 24
    rem_hours = hours % 24
    if rem_hours == 0:
        return f"{days}-day timeout"
    return f"{days}d {rem_hours}h timeout"

def build_progress_bar(points: int, max_points: int = 12) -> str:
    """Builds visual demerit progress bar e.g. [🟩🟩🟩🟨🟨⬜⬜⬜⬜⬜⬜⬜]"""
    clamped = max(0, min(points, max_points))
    empty = max_points - clamped
    # Colors: green (1-5), yellow (6-8), orange (9-11), red (12+)
    if clamped <= 5:
        filled_emoji = "🟩"
    elif clamped <= 8:
        filled_emoji = "🟨"
    elif clamped <= 11:
        filled_emoji = "🟧"
    else:
        filled_emoji = "🟥"
    return f"[{filled_emoji * clamped}{'⬜' * empty}] **{points}/{max_points}** Demerit Points"

async def notify_and_punish(
    message: discord.Message,
    author: discord.Member,
    reason: str,
    violation_type: ViolationType,
    points_added: int,
    total_active_points: int,
    timeout_minutes: int,
    action_desc: str,
    should_ban: bool = False,
    matched_text: str = ""
):
    """Executes demerit penalty and delivers clear, transparent notification."""
    guild = message.guild
    timeout_duration = timedelta(minutes=timeout_minutes)
    bar = build_progress_bar(total_active_points)

    # Send DM to author
    try:
        dm_embed = discord.Embed(
            title="🛡️ Dasik Warden Demerit Notice",
            color=0xe74c3c if should_ban or total_active_points >= 9 else 0xe67e22,
            timestamp=datetime.now(timezone.utc)
        )
        dm_embed.description = (
            f"Hello {author.mention},\n\n"
            f"An infraction occurred in **{guild.name}**:\n\n"
            f"• **Reason**: {reason}\n"
            f"• **Demerits Incurred**: +{points_added} Point(s)\n"
            f"• **Current Active Status**: {bar}\n"
            f"• **Applied Action**: {action_desc}\n\n"
            "ℹ️ *Points decay and expire automatically after 30 days of good behavior.* "
            "You can run `/demerits` in the server at any time to inspect your active license."
        )
        dm_embed.set_footer(text="Dasik Igaijinn Demerit Moderation System")
        await author.send(embed=dm_embed)
    except Exception:
        pass # DMs may be closed

    # Apply Discord punishment
    try:
        if should_ban:
            await guild.ban(
                author,
                reason=f"Dasik Warden [Demerit Threshold 12 reached 3x]: {reason}",
                delete_message_days=1
            )
        elif timeout_minutes > 0:
            until = discord.utils.utcnow() + timeout_duration
            await author.timeout(until, reason=f"Dasik Warden [{total_active_points} Demerits]: {reason}")
    except Exception as e:
        print(f"[Warden Error] Failed applying moderation action to {author.id}: {e}")

    # Send channel public notice
    try:
        notice_embed = discord.Embed(
            title="🛡️ Dasik Warden Notice",
            description=(
                f"{author.mention} incurred **+{points_added} Demerit Point(s)**.\n"
                f"**Reason**: {reason}\n"
                f"**Status**: {bar}\n"
                f"**Action**: {action_desc}"
            ),
            color=0xe67e22
        )
        notice_embed.set_footer(text="Help or Stay Silent | Demerits decay after 30 days")
        await message.channel.send(embed=notice_embed, delete_after=20)
    except Exception as e:
        print(f"[Warden Error] Failed sending channel notice: {e}")


@bot.event
async def on_ready():
    print(f"=== Dasik Warden Online ===")
    print(f"Logged in as: {bot.user.name} ({bot.user.id})")
    try:
        guild_obj = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild_obj)
        synced = await bot.tree.sync(guild=guild_obj)
        print(f"Synced {len(synced)} slash commands to guild {GUILD_ID}")
    except Exception as e:
        print(f"Slash command sync error: {e}")


@bot.event
async def on_message(message: discord.Message):
    # Ignore bots and DMs
    if message.author.bot or not message.guild:
        return

    # Check content violations
    res = evaluate_message_content(message.content)
    if not res.violation:
        await bot.process_commands(message)
        return

    member: discord.Member = message.author

    # 1. Zero Tolerance (Malware, doxxing, token loggers) -> 12 Demerits
    if res.violation_type == ViolationType.ZERO_TOLERANCE:
        try:
            await message.delete()
        except Exception:
            pass
        active_pts, timeout_mins, action_desc, should_ban = demerit_manager.add_demerit(
            member.id, res.reason, bot.user.id, res.violation_type, points=12
        )
        await notify_and_punish(message, member, res.reason, res.violation_type, 12, active_pts, timeout_mins, action_desc, should_ban, res.matched_pattern)
        return

    # 2. Piracy & Warez -> Immediate Deletion + 3 Demerit Points
    if res.violation_type == ViolationType.PIRACY:
        try:
            await message.delete()
        except Exception:
            pass
        active_pts, timeout_mins, action_desc, should_ban = demerit_manager.add_demerit(
            member.id, res.reason, bot.user.id, res.violation_type, points=3
        )
        await notify_and_punish(message, member, res.reason, res.violation_type, 3, active_pts, timeout_mins, action_desc, should_ban, res.matched_pattern)
        return

    # 3. Gatekeeping ("Help or Stay Silent") -> Polite Direct Message Warning (or 1 Demerit on persistence)
    if res.violation_type == ViolationType.GATEKEEPING:
        _, active_records = demerit_manager.get_active_points(member.id)
        recent_gk = [s for s in active_records if s.get("type") == ViolationType.GATEKEEPING.value]
        
        # If first time, send educational warning directly via DM
        if len(recent_gk) == 0:
            nudge_embed = discord.Embed(
                title="✨ Friendly Warning: Help or Stay Silent",
                description=(
                    f"Hello {member.mention},\n\n"
                    "In the **Dasik Igaijinn** community, **no question is a stupid question**.\n"
                    "If you feel a question is basic or repetitive and don't feel like answering kindly, "
                    "please **stay silent and let others or the developer answer**.\n\n"
                    "Please avoid sarcastic remarks like *'google is free'* or *'just read the wiki'*. "
                    "Let's keep this space welcoming for beginners!\n\n"
                    "ℹ️ *This is a zero-point educational caution. No demerit points were added.*"
                ),
                color=0x3498db
            )
            nudge_embed.set_footer(text="Dasik Igaijinn Zero-Gatekeeping Policy")
            dm_sent = False
            try:
                await member.send(embed=nudge_embed)
                dm_sent = True
            except Exception:
                pass

            # If user's DMs are disabled, reply in channel briefly
            if not dm_sent:
                try:
                    await message.reply(embed=nudge_embed, delete_after=30)
                except Exception:
                    pass

            # Record caution without adding demerit points
            demerit_manager.add_demerit(member.id, "Gatekeeping caution (first notice)", bot.user.id, res.violation_type, points=0)
        else:
            # Repeated offense -> 1 Demerit Point with direct DM notification
            try:
                await message.delete()
            except Exception:
                pass
            active_pts, timeout_mins, action_desc, should_ban = demerit_manager.add_demerit(
                member.id, "Repeated gatekeeping after caution", bot.user.id, res.violation_type, points=1
            )
            await notify_and_punish(message, member, res.reason, res.violation_type, 1, active_pts, timeout_mins, action_desc, should_ban, res.matched_pattern)
        return

    await bot.process_commands(message)


# ==================== SLASH COMMANDS ====================

@bot.tree.command(name="demerits", description="View your current demerit points, decay status, and infraction history.")
@app_commands.describe(member="Optional: The member to inspect (Moderators only)")
async def demerits_cmd(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    # If target member specified and not self, check permissions
    target = member or interaction.user
    is_self = target.id == interaction.user.id

    if not is_self and not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ You can only check your own demerit points.", ephemeral=True)
        return

    active_points, active_records = demerit_manager.get_active_points(target.id)
    bar = build_progress_bar(active_points)

    if active_points == 0 and len(active_records) == 0:
        msg = f"✨ You have a clean driving license with **0 Demerit Points**!" if is_self else f"✨ {target.mention} has a clean record with **0 Demerit Points**."
        await interaction.response.send_message(msg, ephemeral=True)
        return

    embed = discord.Embed(
        title=f"📋 Demerit Points Record: {target.display_name}",
        description=(
            f"**Current Status**: {bar}\n"
            f"*Threshold before suspension*: **{max(0, 12 - active_points)} points remaining**\n"
            f"*Note*: Points automatically expire **30 days** after issuance."
        ),
        color=0x2ecc71 if active_points <= 5 else (0xf1c40f if active_points <= 8 else 0xe74c3c),
        timestamp=datetime.now(timezone.utc)
    )

    for idx, s in enumerate(active_records[-8:], start=1):
        ts = f"<t:{s['timestamp']}:R>" if "timestamp" in s else "Unknown"
        pts = s.get("points", 0)
        embed.add_field(
            name=f"Infraction #{idx} (+{pts} Pts) [{s.get('type', 'manual')}]",
            value=f"• **Reason**: {s.get('reason')}\n• **When**: {ts}\n• **By**: <@{s.get('issuer_id', 0)}>",
            inline=False
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)


# Backwards compatibility alias for /strikes -> redirects to /demerits
@bot.tree.command(name="strikes", description="Alias for /demerits. Check demerit points status.")
@app_commands.describe(member="Optional: The member to inspect")
async def strikes_cmd(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    await demerits_cmd(interaction, member)


@bot.tree.command(name="warn", description="Issue demerit points to a member (Moderators only).")
@app_commands.describe(member="The member to warn", reason="Reason for the warning", points="Demerit points to add (default: 2)")
@app_commands.default_permissions(moderate_members=True)
async def warn_cmd(interaction: discord.Interaction, member: discord.Member, reason: str, points: Optional[int] = 2):
    pts = max(1, min(points or 2, 12))
    active_pts, timeout_minutes, action_desc, should_ban = demerit_manager.add_demerit(
        member.id, reason, interaction.user.id, ViolationType.MANUAL_WARN, points=pts
    )

    bar = build_progress_bar(active_pts)
    timeout_duration = timedelta(minutes=timeout_minutes)

    if should_ban:
        try:
            await interaction.guild.ban(member, reason=f"Dasik Warden [12 Demerits reached 3x]: {reason}", delete_message_days=1)
        except Exception as e:
            print(f"Failed applying ban: {e}")
    elif timeout_minutes > 0:
        try:
            await member.timeout(discord.utils.utcnow() + timeout_duration, reason=f"Manual warn: {reason} (+{pts} pts)")
        except Exception as e:
            print(f"Failed applying timeout: {e}")

    # Send DM
    try:
        dm_embed = discord.Embed(
            title="🛡️ Demerit Points Issued",
            color=0xe74c3c,
            description=(
                f"You received **+{pts} Demerit Point(s)** in **{interaction.guild.name}**.\n\n"
                f"• **Reason**: {reason}\n"
                f"• **Current Status**: {bar}\n"
                f"• **Applied Action**: {action_desc}\n\n"
                "ℹ️ Points automatically decay and expire after 30 days."
            )
        )
        await member.send(embed=dm_embed)
    except Exception:
        pass

    await interaction.response.send_message(
        f"⚠️ Issued **+{pts} Demerit Point(s)** to {member.mention} for: *{reason}*.\nStatus: {bar} ({action_desc}).",
        ephemeral=False
    )


@bot.tree.command(name="cleardemerits", description="Clear all demerits for a member (Admins only).")
@app_commands.describe(member="The member whose demerits will be cleared")
@app_commands.default_permissions(administrator=True)
async def cleardemerits_cmd(interaction: discord.Interaction, member: discord.Member):
    cleared = demerit_manager.clear_demerits(member.id)
    await interaction.response.send_message(
        f"✨ Cleared **{cleared}** demerit infraction(s) for {member.mention}. License restored to clean slate.",
        ephemeral=True
    )


if __name__ == "__main__":
    bot.run(TOKEN)
