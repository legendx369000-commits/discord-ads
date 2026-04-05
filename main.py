import os
import random
from datetime import datetime, timedelta
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
    "https://www.profitablecpmratenetwork.com/y8ky78pi?key=4281ae9af8218801eeec7dac89fbc662"
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
        description=f"🔗 {random.choice(ADS)}",
        color=discord.Color.blurple()
    ).set_footer(text="Sponsored • limited frequency")


def is_temporary_voice_channel(channel):
    return isinstance(channel, discord.VoiceChannel) and channel.id not in PERMANENT_VC


async def create_temp_voice_text_channel(voice_channel):
    if voice_channel.id in handled_vc:
        return None

    handled_vc.add(voice_channel.id)

    try:
        kwargs = {
            "name": f"{voice_channel.name}-chat",
            "topic": f"Chat for {voice_channel.name}"
        }

        if voice_channel.category is not None:
            kwargs["category"] = voice_channel.category

        text_channel = await voice_channel.guild.create_text_channel(**kwargs)
        await text_channel.send(
            embed=create_ad(),
            allowed_mentions=discord.AllowedMentions.none()
        )
        return text_channel
    except Exception as e:
        print(f"Temp VC error: {e}")
        return None


def can_send(guild_id):
    now = datetime.utcnow()
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
            if datetime.utcnow() - last < timedelta(hours=1):
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
                embed=create_ad(),
                allowed_mentions=discord.AllowedMentions.none()
            )
            settings.update_one(
                {"guild": guild.id},
                {"$set": {"last_sent": datetime.utcnow()}}
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

    text_channel = await create_temp_voice_text_channel(channel)
    if not text_channel:
        return

    config = get_config(channel.guild.id)
    if text_channel.id not in config["channels"]:
        settings.update_one(
            {"guild": channel.guild.id},
            {"$push": {"channels": text_channel.id}}
        )


@bot.event
async def on_voice_state_update(member, before, after):
    if not after.channel or after.channel.id not in PERMANENT_VC:
        return

    if not can_send(member.guild.id):
        return

    try:
        for ch in after.channel.guild.text_channels:
            if ch.category == after.channel.category:
                await ch.send(
                    embed=create_ad(),
                    allowed_mentions=discord.AllowedMentions.none()
                )
                break
    except Exception as e:
        print(f"Voice trigger error: {e}")


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


bot.run(TOKEN)
