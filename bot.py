import discord
from discord.ext import commands
import asyncio
import random
from dotenv import load_dotenv
import os
from flask import Flask
import threading

# 環境変数の読み込み
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))

# Discord Botの準備
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True  # ロール取得に必要
bot = commands.Bot(command_prefix="!", intents=intents)

# Flaskアプリケーション（ヘルスチェック用）
app = Flask("")

@app.route("/")
def home():
    return "Bot is running!", 200

def run_http_server():
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    threading.Thread(target=run_http_server).start()

# Bot準備完了イベント
@bot.event
async def on_ready():
    print(f"{bot.user.name} が起動しました！")

# じゃんけんコマンド
@bot.command()
async def janken(ctx, role: discord.Role = None):
    if role is None:
        await ctx.send("参加させたいロールをメンションしてね！例: `!janken @参加ロール`")
        return

    participants = [member for member in role.members if not member.bot]

    if not participants:
        await ctx.send(f"{role.name} ロールにメンバーがいません！")
        return

    await ctx.send(f"{role.mention} ロールのメンバーでじゃんけんを始めます！")

    player_choices = {}
    reactions = ["👊", "✌️", "✋"]
    hand_map = {"👊": "グー", "✌️": "チョキ", "✋": "パー"}

    # DMを送ってリアクションで手を選ばせる関数
    async def send_dm_and_wait(player):
        try:
            dm_message = await player.send(
                f"{role.name} ロール限定のじゃんけん！\n"
                "リアクションで手を選んでね！\n"
                "👊: グー\n"
                "✌️: チョキ\n"
                "✋: パー"
            )
            for reaction in reactions:
                await dm_message.add_reaction(reaction)

            def check(reaction, user):
                return user == player and str(reaction.emoji) in reactions

            reaction, _ = await bot.wait_for("reaction_add", timeout=30.0, check=check)
            player_choices[player.id] = str(reaction.emoji)
            await player.send(f"あなたの選択 `{hand_map[reaction.emoji]}` を受け付けたよ！")
        except asyncio.TimeoutError:
            await player.send("時間切れ！手の選択ができなかったよ…")

    # DM送信と選択待ちを全員に
    tasks = [send_dm_and_wait(member) for member in participants]
    await asyncio.gather(*tasks)

    # ボットの手も決める
    bot_choice = random.choice(reactions)
    player_choices[bot.user.id] = bot_choice
    await ctx.send(f"ボットの手は `{hand_map[bot_choice]}` でした！")

    # 勝敗判定
    win_table = {"👊": "✌️", "✌️": "✋", "✋": "👊"}
    all_choices = set(player_choices.values())

    # あいこ判定（全種類出てる場合）
    if len(all_choices) == 3:
        results_message = "ぐー、ちょき、ぱーが揃っているので、全員あいこ（引き分け）です！\n\n"
        results_message += "**各プレイヤーの選択:**\n"
        for player_id, player_choice in player_choices.items():
            player = await bot.fetch_user(player_id)
            results_message += f"- {player.display_name}: {hand_map[player_choice]}\n"
        await ctx.send(results_message)
        return

    # 個別判定
    results = {player_id: {"wins": 0, "losses": 0} for player_id in player_choices.keys()}

    for player_id, player_choice in player_choices.items():
        for opponent_id, opponent_choice in player_choices.items():
            if player_id == opponent_id:
                continue
            if win_table[player_choice] == opponent_choice:
                results[player_id]["wins"] += 1
            elif win_table[opponent_choice] == player_choice:
                results[player_id]["losses"] += 1

    # 勝者、敗者を抽出
    winners = [pid for pid, res in results.items() if res["wins"] > 0 and res["losses"] == 0]
    losers = [pid for pid, res in results.items() if res["losses"] > 0 and res["wins"] == 0]

    # 結果メッセージ構築
    results_message = "**各プレイヤーの選択:**\n"
    for player_id, player_choice in player_choices.items():
        player = await bot.fetch_user(player_id)
        results_message += f"- {player.display_name}: {hand_map[player_choice]}\n"

    if winners:
        results_message += "\n🏆 **勝者:**\n"
        for winner_id in winners:
            winner = await bot.fetch_user(winner_id)
            results_message += f"- {winner.display_name}\n"

    if losers:
        results_message += "\n😢 **敗者:**\n"
        for loser_id in losers:
            loser = await bot.fetch_user(loser_id)
            results_message += f"- {loser.display_name}\n"

    if not winners and not losers:
        results_message += "\n今回は勝ち負けがつかないあいこでした！"

    await ctx.send(results_message)

# HTTPサーバーを起動しつつ、Discord Botを実行
keep_alive()
bot.run(TOKEN)
