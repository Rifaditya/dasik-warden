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
    StrikeManager,
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
strike_manager = StrikeManager(storage_path="strikes.json")

# Role & Server Constants
GUILD_ID = 1546093898907258933

async def notify_and_punish(
    message: discord.Message,
    author: discord.Member,
    reason: str,
    violation_type: ViolationType,
    strike_count: int,
    action: str,
    matched_text: str = ""
):
    """Executes discipline ladder and delivers solo-developer voiced notification."""
    guild = message.guild
    # Escalation actions
    action_desc = ""
    timeout_duration: Optional[timedelta] = None

    if action == "timeout_10m":
        timeout_duration = timedelta(minutes=10)
        action_desc = "10-minute timeout"
    elif action == "timeout_1h":
        timeout_duration = timedelta(hours=1)
        action_desc = "1-hour timeout"
    elif action == "ban_permanent" or violation_type == ViolationType.ZERO_TOLERANCE:
        action_desc = "Permanent Ban"

    # Send DM to author
    try:
        dm_embed = discord.Embed(
            title="🛡️ Dasik Warden Moderation Notice",
            color=0xe74c3c,
            timestamp=datetime.now(timezone.utc)
        )
        dm_embed.description = (
            f"Hello {author.mention},\n\n"
            f"Your message in **{guild.name}** triggered a server guideline infraction:\n\n"
            f"• **Reason**: {reason}\n"
            f"• **Current Strike Count**: {strike_count}/3\n"
            f"• **Applied Action**: {action_desc}\n\n"
            "Please review our `#rules` and `#community-support` guidelines. "
            "We foster a welcoming, supportive, and zero-gatekeeping community."
        )
        dm_embed.set_footer(text="Dasik Igaijinn Moderation System")
        await author.send(embed=dm_embed)
    except Exception:
        pass # DMs may be closed

    # Apply Discord punishment
    try:
        if timeout_duration:
            until = discord.utils.utcnow() + timeout_duration
            await author.timeout(until, reason=f"Dasik Warden [Strike {strike_count}]: {reason}")
        elif action == "ban_permanent" or violation_type == ViolationType.ZERO_TOLERANCE:
            await guild.ban(author, reason=f"Dasik Warden [Strike {strike_count}]: {reason}", delete_message_days=1)
    except Exception as e:
        print(f"[Warden Error] Failed applying moderation action to {author.id}: {e}")

    # Send channel public notice
    try:
        notice_embed = discord.Embed(
            title="🛡️ Dasik Warden Action",
            description=(
                f"{author.mention} received a strike (**{strike_count}/3**).\n"
                f"**Reason**: {reason}\n"
                f"**Action**: {action_desc}"
            ),
            color=0xe67e22
        )
        notice_embed.set_footer(text="Help or Stay Silent | Zero-Gatekeeping Policy")
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

    # 1. Zero Tolerance (Malware, doxxing, token loggers) -> Immediate Ban
    if res.violation_type == ViolationType.ZERO_TOLERANCE:
        try:
            await message.delete()
        except Exception:
            pass
        strike_count, _ = strike_manager.add_strike(member.id, res.reason, bot.user.id, res.violation_type)
        await notify_and_punish(message, member, res.reason, res.violation_type, strike_count, "ban_permanent", res.matched_pattern)
        return

    # 2. Piracy & Warez -> Immediate Deletion + Strike Ladder
    if res.violation_type == ViolationType.PIRACY:
        try:
            await message.delete()
        except Exception:
            pass
        strike_count, action = strike_manager.add_strike(member.id, res.reason, bot.user.id, res.violation_type)
        await notify_and_punish(message, member, res.reason, res.violation_type, strike_count, action, res.matched_pattern)
        return

    # 3. Gatekeeping ("Help or Stay Silent") -> Polite Reminder Nudge (or Strike on persistence)
    if res.violation_type == ViolationType.GATEKEEPING:
        existing_strikes = strike_manager.get_strikes(member.id)
        recent_gk = [s for s in existing_strikes if s.get("type") == ViolationType.GATEKEEPING.value]
        
        # If first time, send educational nudge without deleting message
        if len(recent_gk) == 0:
            nudge_embed = discord.Embed(
                title="✨ Friendly Reminder: Help or Stay Silent",
                description=(
                    f"Hey {member.mention},\n\n"
                    "In our community, **no question is a stupid question**.\n"
                    "If you feel a question is basic or repetitive and don't feel like answering kindly, "
                    "please **stay silent and let others or the dev answer**.\n\n"
                    "Avoid sarcastic remarks like *'google is free'* or *'read the wiki'*. "
                    "Let's keep this space welcoming for beginners!"
                ),
                color=0x3498db
            )
            nudge_embed.set_footer(text="Dasik Igaijinn Zero-Gatekeeping Policy")
            await message.reply(embed=nudge_embed, delete_after=30)
            # Record warning with 0 action escalation
            strike_manager.add_strike(member.id, "Gatekeeping warning (first notice)", bot.user.id, res.violation_type)
        else:
            # Repeated offense -> escalate
            try:
                await message.delete()
            except Exception:
                pass
            strike_count, action = strike_manager.add_strike(member.id, "Repeated gatekeeping after warning", bot.user.id, res.violation_type)
            await notify_and_punish(message, member, res.reason, res.violation_type, strike_count, action, res.matched_pattern)
        return

    await bot.process_commands(message)


# ==================== SLASH COMMANDS ====================

@bot.tree.command(name="strikes", description="View moderation strike history for a member.")
@app_commands.describe(member="The member to inspect")
@app_commands.default_permissions(moderate_members=True)
async def strikes_cmd(interaction: discord.Interaction, member: discord.Member):
    strikes = strike_manager.get_strikes(member.id)
    if not strikes:
        await interaction.response.send_message(f"✅ **{member.display_name}** has 0 strikes on record.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"📋 Strike History: {member.display_name}",
        description=f"Total strikes: **{len(strikes)}/3**",
        color=0xe67e22,
        timestamp=datetime.now(timezone.utc)
    )
    for idx, s in enumerate(strikes, 1):
        ts = f"<t:{s['timestamp']}:R>" if "timestamp" in s else "Unknown"
        embed.add_field(
            name=f"Strike #{idx} [{s.get('type', 'manual')}]",
            value=f"• **Reason**: {s.get('reason')}\n• **When**: {ts}\n• **By**: <@{s.get('issuer_id', 0)}>",
            inline=False
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="warn", description="Issue a formal strike to a member.")
@app_commands.describe(member="The member to warn", reason="Reason for the warning")
@app_commands.default_permissions(moderate_members=True)
async def warn_cmd(interaction: discord.Interaction, member: discord.Member, reason: str):
    strike_count, action = strike_manager.add_strike(member.id, reason, interaction.user.id, ViolationType.MANUAL_WARN)

    action_desc = "Warning logged"
    timeout_duration = None
    if action == "timeout_10m":
        timeout_duration = timedelta(minutes=10)
        action_desc = "10-minute timeout"
    elif action == "timeout_1h":
        timeout_duration = timedelta(hours=1)
        action_desc = "1-hour timeout"
    elif action == "ban_permanent":
        action_desc = "Permanent Ban"

    if timeout_duration:
        try:
            await member.timeout(discord.utils.utcnow() + timeout_duration, reason=f"Manual warn: {reason}")
        except Exception as e:
            print(f"Failed applying timeout: {e}")
    elif action == "ban_permanent":
        try:
            await interaction.guild.ban(member, reason=f"Strike 3 reached: {reason}", delete_message_days=0)
        except Exception as e:
            print(f"Failed applying ban: {e}")

    # Send DM
    try:
        dm_embed = discord.Embed(
            title="🛡️ Warning Issued",
            color=0xe74c3c,
            description=(
                f"You received a strike in **{interaction.guild.name}**.\n\n"
                f"• **Reason**: {reason}\n"
                f"• **Strike Count**: {strike_count}/3\n"
                f"• **Applied Action**: {action_desc}"
            )
        )
        await member.send(embed=dm_embed)
    except Exception:
        pass

    await interaction.response.send_message(
        f"⚠️ Issued Strike **{strike_count}/3** to {member.mention} for: *{reason}* ({action_desc}).",
        ephemeral=False
    )


@bot.tree.command(name="clearstrikes", description="Clear all strikes for a member.")
@app_commands.describe(member="The member whose strikes will be cleared")
@app_commands.default_permissions(administrator=True)
async def clearstrikes_cmd(interaction: discord.Interaction, member: discord.Member):
    cleared = strike_manager.clear_strikes(member.id)
    await interaction.response.send_message(
        f"✨ Cleared **{cleared}** strike(s) for {member.mention}.",
        ephemeral=True
    )


if __name__ == "__main__":
    bot.run(TOKEN)
