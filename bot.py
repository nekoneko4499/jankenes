import discord
from discord.ext import commands
import asyncio
import random
from dotenv import load_dotenv
import os
from flask import Flask
import threading

# ========================
# 環境変数の読み込み
# ========================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
KENNGAKU_ROLE_ID = int(os.getenv("KENNGAKU_ROLE_ID"))
TARGET_BOT_ID = int(os.getenv("TARGET_BOT_ID"))
BLACKLIST_KICK_LOG_CHANNEL_ID = int(os.getenv("BLACKLIST_KICK_LOG_CHANNEL_ID"))

# ========================
# ブラックリスト読み込み関数
# ========================
def load_blacklisted_user_ids():
    try:
        with open("blacklist.txt", "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip().isdigit())
    except FileNotFoundError:
        return set()

BLACKLISTED_USER_IDS = load_blacklisted_user_ids()

# ========================
# Discord Botの準備
# ========================
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.voice_states = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ========================
# Flaskアプリ（Koyeb用）
# ========================
app = Flask("")

@app.route("/")
def home():
    return "Bot is running!", 200

def run_http_server():
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    threading.Thread(target=run_http_server).start()

# ========================
# グローバル辞書でDMメッセージ管理
# ========================
user_messages = {}

@bot.event
async def on_ready():
    print(f"{bot.user.name} is ready!")

# ========================
# ✅ ブラックリストチェック
# ========================
@bot.event
async def on_member_join(member):
    if str(member.id) in BLACKLISTED_USER_IDS:
        try:
            await member.kick(reason="ブラックリスト対象")
            log_channel = bot.get_channel(BLACKLIST_KICK_LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(f"🚫 ブラックリストのため {member.name}（ID: {member.id}）をキックしました。")
        except discord.Forbidden:
            print(f"⚠️ {member.name} をキックできませんでした（権限不足）")
        except Exception as e:
            print(f"⚠️ キックエラー: {e}")

# ========================
# ✅ 見学ロール付与時のDM処理
# ========================
@bot.event
async def on_member_update(before, after):
    new_roles = set(after.roles) - set(before.roles)
    for role in new_roles:
        if role.id == KENNGAKU_ROLE_ID:
            try:
                message = await after.send(
                    f"こんにちは！あなたに '見学' ロールが付与されました！\n"
                    "このロールが付いた人はメッセージを送れなくなり、見ることしかできません。\n"
                    "それがいやな場合、以下にアクセスしてください:\n"
                    "https://discord.com/channels/1165775639798878288/1351191234961604640"
                )
                user_messages[after.id] = message.id
                print(f"{after.name} に見学ロールDMを送信しました")
            except discord.Forbidden:
                print(f"{after.name} へのDM送信ができません")
            break

    removed_roles = set(before.roles) - set(after.roles)
    for role in removed_roles:
        if role.id == KENNGAKU_ROLE_ID and after.id in user_messages:
            try:
                message_id = user_messages.pop(after.id)
                channel = await after.create_dm()
                message = await channel.fetch_message(message_id)
                await message.delete()
                print(f"{after.name} のDMメッセージを削除しました")
            except (discord.Forbidden, discord.NotFound):
                print(f"{after.name} のDM削除に失敗しました")
            break

# ========================
# ✅ VC参加・退出ログ
# ========================
@bot.event
async def on_voice_state_update(member, before, after):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if not log_channel:
        return

    if before.channel is None and after.channel is not None:
        await log_channel.send(f"🔊 {member.display_name} が **{after.channel.name}** に参加しました！")
    elif after.channel is None and before.channel is not None:
        await log_channel.send(f"🔇 {member.display_name} が **{before.channel.name}** から退出しました。")

# ========================
# ✅ 音楽BotをVCから切断
# ========================
@bot.command()
async def 音楽終了(ctx):
    if ctx.author.voice is None or ctx.author.voice.channel is None:
        await ctx.send("まずあなたがボイスチャンネルに参加してください。")
        return

    voice_channel = ctx.author.voice.channel

    for member in voice_channel.members:
        if member.bot and member.id == TARGET_BOT_ID:
            try:
                await member.move_to(None)
                await ctx.send(f"{member.display_name} をボイスチャンネルから切断しました。")
                return
            except discord.Forbidden:
                await ctx.send("そのBotを切断する権限がありません。")
                return

    await ctx.send("指定されたBotはこのボイスチャンネルにいません。")

# ========================
# ✅ ブラックリスト再読み込みコマンド
# ========================
@bot.command()
@commands.has_permissions(administrator=True)
async def reload_blacklist(ctx):
    global BLACKLISTED_USER_IDS
    BLACKLISTED_USER_IDS = load_blacklisted_user_ids()
    await ctx.send("🔄 ブラックリストを再読み込みしました。")

# ========================
# 起動！
# ========================
keep_alive()
bot.run(TOKEN)
