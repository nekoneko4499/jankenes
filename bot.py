import discord
from discord.ext import commands
import asyncio
import random
from dotenv import load_dotenv
import os
from flask import Flask
import threading
import unicodedata

# ========================
# 環境変数の読み込み
# ========================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
BLACKLIST_LOG_CHANNEL_ID = int(os.getenv("BLACKLIST_LOG_CHANNEL_ID"))
KENNGAKU_ROLE_ID = int(os.getenv("KENNGAKU_ROLE_ID"))
TARGET_BOT_ID = int(os.getenv("TARGET_BOT_ID"))  # TARGET_USER_IDはそのままTARGET_BOT_IDに
TARGET_USER_ID = TARGET_BOT_ID  # これを使う

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

# ========================
# ブラックリスト読み込み関数
# ========================
def load_blacklist():
    ids = set()
    for file in ["blacklist.txt", "blacklist_extra.txt"]:
        if os.path.exists(file):
            with open(file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.isdigit():
                        ids.add(int(line))
    return ids

blacklist_ids = load_blacklist()

# ========================
# ブラックリストのチェックとVCキック機能
# ========================
with open('blacktxt.txt', 'r', encoding='utf-8') as f:
    keywords = [line.strip() for line in f.readlines()]

@bot.event
async def on_message(message):
    if message.author.bot:
        return  # bot自身のメッセージは無視

    if message.author.id != TARGET_USER_ID:
        return  # ターゲット以外は無視

    # メッセージ内容を小文字にして、スペースを削除
    cleaned_message = message.content.lower().replace(" ", "")
    
    # 正規化（全角文字を半角にしたり、特殊文字を統一）
    cleaned_message = unicodedata.normalize('NFKC', cleaned_message)

    # ブラックリストキーワードを正規化
    normalized_keywords = [unicodedata.normalize('NFKC', keyword.lower().replace(" ", "")) for keyword in keywords]

    if any(keyword in cleaned_message for keyword in normalized_keywords):
        # ユーザーがボイスチャンネルにいるか確認
        if message.author.voice and message.author.voice.channel:
            await message.author.move_to(None)  # VCから切断
            await message.channel.send(f"```違反行為が見つかったため、対象のユーザー（{message.author.mention}）をキックしました。```")

    await bot.process_commands(message)

# ========================
# ✅ 起動時に既存メンバーをチェック
# ========================
@bot.event
async def on_ready():
    print(f"{bot.user.name} is ready!")
    for guild in bot.guilds:
        for member in guild.members:
            if member.id in blacklist_ids:
                try:
                    await member.kick(reason="Blacklisted user")
                    log_channel = bot.get_channel(BLACKLIST_LOG_CHANNEL_ID)
                    if log_channel:
                        await log_channel.send(f"⛔ 起動時にブラックリストID: `{member.id}` をキックしました。")
                except discord.Forbidden:
                    print(f"{member.name} をキックできませんでした。")

# ========================
# ✅ 新メンバー参加時のチェック
# ========================
@bot.event
async def on_member_join(member):
    if member.id in blacklist_ids:
        try:
            await member.kick(reason="Blacklisted user")
            log_channel = bot.get_channel(BLACKLIST_LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(f"⛔ ブラックリストID: `{member.id}` のユーザーをキックしました。")
        except discord.Forbidden:
            print(f"{member.name} をキックできませんでした。")

# ========================
# ✅ 見学ロール付与時にDM送信
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
        if role.id == KENNGAKU_ROLE_ID:
            if after.id in user_messages:
                try:
                    message_id = user_messages.pop(after.id)
                    channel = await after.create_dm()
                    message = await channel.fetch_message(message_id)
                    await message.delete()
                    print(f"{after.name} のDMメッセージを削除しました")
                except discord.Forbidden:
                    print(f"{after.name} のDM削除ができません")
                except discord.NotFound:
                    print(f"{after.name} のメッセージが見つかりませんでした")
            break

# ========================
# ✅ VC参加・退出ログを送信
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
# ✅ 音楽終了コマンド
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
# ✅ じゃんけんコマンド
# ========================
@bot.command()
async def janken(ctx, *args):
    participants = []

    if args:
        role_mentions = ctx.message.role_mentions
        if not role_mentions:
            await ctx.send("ロールが指定されていません！")
            return

        role = role_mentions[0]
        participants = [member for member in role.members if not member.bot]
        if not participants:
            await ctx.send(f"ロール {role.name} に該当するメンバーがいません！")
            return

        await ctx.send(f"{role.name} のメンバーにDMを送ります！")
    else:
        recruit_message = await ctx.send(
            "じゃんけん大会を開催します！参加する方は✋のリアクションを押してください！（15秒間）"
        )
        await recruit_message.add_reaction("✋")

        def reaction_check(reaction, user):
            return (
                user != bot.user
                and reaction.message.id == recruit_message.id
                and str(reaction.emoji) == "✋"
            )

        try:
            while True:
                reaction, user = await bot.wait_for("reaction_add", timeout=15.0, check=reaction_check)
                if user not in participants:
                    participants.append(user)
        except asyncio.TimeoutError:
            if not participants:
                await ctx.send("参加者がいませんでした！")
                return
            await ctx.send(f"{len(participants)}人の参加者が集まりました！")

    participants.append(bot.user)

    player_choices = {}
    reactions = ["👊", "✌️", "✋"]
    hand_map = {"👊": "グー", "✌️": "チョキ", "✋": "パー"}

    async def send_dm_and_wait(player):
        if player.bot:
            choice = random.choice(reactions)
            player_choices[player.id] = choice
            return

        try:
            dm_message = await player.send(
                "じゃんけんの手をリアクションで選んでください！\n"
                "👊: グー\n"
                "✌️: チョキ\n"
                "✋: パー"
            )
            for reaction in reactions:
                await dm_message.add_reaction(reaction)

            def check(reaction, user):
                return user == player and str(reaction.emoji) in reactions

            reaction, user = await bot.wait_for("reaction_add", timeout=30.0, check=check)
            player_choices[player.id] = str(reaction.emoji)
            await player.send(f"あなたの選択「{hand_map[reaction.emoji]}」を受け付けました！")

        except asyncio.TimeoutError:
            await player.send("時間切れになりました。今回は不参加とさせていただきます。")

    tasks = [send_dm_and_wait(member) for member in participants]
    await asyncio.gather(*tasks)

    active_players = {pid: choice for pid, choice in player_choices.items()}

    if len(active_players) < 2:
        await ctx.send("参加者が不足しています。じゃんけんを中止します。")
        return

    choices_set = set(active_players.values())

    results_message = "結果:\n各プレイヤーの選択:\n"
    for player_id, choice in active_players.items():
        player = bot.get_user(player_id)
        results_message += f"- {player.display_name if player else '不明'}: {hand_map[choice]}\n"

    if len(choices_set) == 1 or len(choices_set) == 3:
        results_message += "\n**あいこ（引き分け）です！**"
    else:
        win_table = {"👊": "✌️", "✌️": "✋", "✋": "👊"}
        hands_list = list(choices_set)
        if win_table[hands_list[0]] == hands_list[1]:
            winning_hand = hands_list[0]
        else:
            winning_hand = hands_list[1]

        winners = []
        losers = []

        for pid, choice in active_players.items():
            if choice == winning_hand:
                winners.append(pid)
            else:
                losers.append(pid)

        if winners:
            results_message += "\n\n**勝者:**\n"
            for winner_id in winners:
                player = bot.get_user(winner_id)
                results_message += f"- {player.display_name if player else '不明'}\n"
        if losers:
            results_message += "\n\n**敗者:**\n"
            for loser_id in losers:
                player = bot.get_user(loser_id)
                results_message += f"- {player.display_name if player else '不明'}\n"

    await ctx.send(results_message)

# ========================
# 起動！
# ========================
keep_alive()
bot.run(TOKEN)
