import os
import random
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from pymongo import MongoClient
import discord
from discord.ext import commands, tasks

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
MONGO_URI = os.getenv("MONGODB_URI")

if not TOKEN or not MONGO_URI:
    raise ValueError("DISCORD_TOKEN and MONGODB_URI must be set in the environment")

client = MongoClient(MONGO_URI)
db = client["adbot"]
settings = db["settings"]

intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

ADS = [
    "https://www.profitablecpmratenetwork.com/s8n5nysw?key=5127cd2a6d1edb030c3b6fac2d8fa35c",
    "https://www.profitablecpmratenetwork.com/y8ky78pi?key=4281ae9af8218801eeec7dac89fbc662",
    "https://amzn.to/4mcqZXJ",
    "https://amzn.to/4cq5eAq"
]

PERMANENT_VC = [
    1455906399262605457,
    1428762702414872636,
    1428762820585062522,
    1455386337040404703,
    1456959255742775437,
    1489892078816067685
]

handled_vc = set()
voice_cooldown = {}
ad_index = 0


def get_next_ad():
    global ad_index
    ad = ADS[ad_index]
    ad_index = (ad_index + 1) % len(ADS)
    return ad


def get_config(guild_id):
    config = settings.find_one({"guild": guild_id})
    if not config:
        config = {
            "guild": guild_id,
            "channels": [],
            "last_sent": None
        }
        settings.insert_one(config)
    return config


def create_ad():
    return discord.Embed(
        description=f"🔗 {get_next_ad()}",
        color=discord.Color.blurple()
    ).set_footer(text="Sponsored • limited frequency")


def is_temporary_voice_channel(channel):
    return isinstance(channel, discord.VoiceChannel) and channel.id not in PERMANENT_VC


async def send_ad_to_voice_chat(voice_channel):
    if voice_channel.id in handled_vc:
        return None

    handled_vc.add(voice_channel.id)

    try:
        if not voice_channel.permissions_for(voice_channel.guild.me).send_messages:
            return None

        await voice_channel.send(
            f"🔗 {get_next_ad()}",
            allowed_mentions=discord.AllowedMentions.none()
        )
    except Exception as e:
        print(f"VC chat error: {e}")
        return None


def can_send(guild_id):
    now = datetime.now(timezone.utc)
    if guild_id not in voice_cooldown:
        voice_cooldown[guild_id] = now
        return True

    if now - voice_cooldown[guild_id] > timedelta(minutes=30):
        voice_cooldown[guild_id] = now
        return True

    return False


@tasks.loop(minutes=30)
async def ad_loop():
    for guild in bot.guilds:
        config = get_config(guild.id)

        if config["last_sent"]:
            last = config["last_sent"]
            # Ensure retrieved datetime is timezone-aware
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - last < timedelta(hours=1):
                continue

        channels = config["channels"]
        if not channels:
            continue

        channel_id = random.choice(channels)
        channel = guild.get_channel(channel_id)

        if not channel:
            continue

        if not channel.permissions_for(guild.me).send_messages:
            continue

        try:
            await channel.send(
                f"🔗 {get_next_ad()}",
                allowed_mentions=discord.AllowedMentions.none()
            )
            settings.update_one(
                {"guild": guild.id},
                {"$set": {"last_sent": datetime.now(timezone.utc)}}
            )
        except Exception as e:
            print(f"Ad loop error: {e}")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    if not ad_loop.is_running():
        ad_loop.start()


@bot.event
async def on_guild_channel_create(channel):
    if not is_temporary_voice_channel(channel):
        return

    await send_ad_to_voice_chat(channel)


@bot.event
async def on_voice_state_update(member, before, after):
    if not after.channel:
        return

    if after.channel.id not in PERMANENT_VC:
        return

    if not can_send(member.guild.id):
        return

    try:
        vc = after.channel

        # Send directly in VC chat
        if vc.permissions_for(vc.guild.me).send_messages:
            await vc.send(
                f"🔗 {get_next_ad()}",
                allowed_mentions=discord.AllowedMentions.none()
            )

    except Exception as e:
        print(f"VC error: {e}")


@bot.command()
@commands.has_permissions(administrator=True)
async def adadd(ctx):
    config = get_config(ctx.guild.id)
    if ctx.channel.id not in config["channels"]:
        settings.update_one(
            {"guild": ctx.guild.id},
            {"$push": {"channels": ctx.channel.id}}
        )
        await ctx.send("✅ This channel added for ads.")
    else:
        await ctx.send("Already added.")


@bot.command()
@commands.has_permissions(administrator=True)
async def adremove(ctx):
    settings.update_one(
        {"guild": ctx.guild.id},
        {"$pull": {"channels": ctx.channel.id}}
    )
    await ctx.send("❌ Channel removed from ads.")


@bot.command()
@commands.has_permissions(administrator=True)
async def adlist(ctx):
    config = get_config(ctx.guild.id)
    channels = config["channels"]

    if not channels:
        await ctx.send("No ad channels set.")
        return

    msg = "\n".join([f"<#{cid}>" for cid in channels])
    await ctx.send(f"Ad channels:\n{msg}")


@bot.command()
async def testad(ctx):
    """Test ad sending - verify bot can send messages"""
    await ctx.send(f"🔗 {get_next_ad()}")


bot.run(TOKEN)
