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
bot = commands.Bot(command_prefix="!", intents=intents)

# Flaskアプリケーション（ヘルスチェック用）
app = Flask("")

@app.route("/")
def home():
    return "Bot is running!", 200  # ヘルスチェック用レスポンス

def run_http_server():
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    threading.Thread(target=run_http_server).start()

@bot.event
async def on_ready():
    print(f"{bot.user.name} is ready!")

# じゃんけんゲームコマンド
@bot.command()
async def janken(ctx):
    await ctx.send("じゃんけんを始めます！ボットがDMを送信しますので、リアクションで手を選んでください！")

    player_choices = {}
    reactions = ["👊", "✌️", "✋"]
    hand_map = {"👊": "グー", "✌️": "チョキ", "✋": "パー"}

    async def send_dm_and_wait(player):
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
            await player.send(f"あなたの選択: {reaction.emoji} ({hand_map[reaction.emoji]}) を受け付けました！")
        except asyncio.TimeoutError:
            await player.send("時間切れです。手の選択ができませんでした。")
            player_choices[player.id] = None  # 選択しなかった場合

    tasks = []
    for member in ctx.guild.members:
        if not member.bot:
            tasks.append(send_dm_and_wait(member))

    await asyncio.gather(*tasks)

    # 全てのプレイヤーの選択が揃ったか確認
    if len(player_choices) < len([member for member in ctx.guild.members if not member.bot]):
        await ctx.send("全員が選択を終了していません。タイムアウトまたはエラーが発生しました。")
        return

    # ボットの手を選択
    bot_choice = random.choice(reactions)
    player_choices[bot.user.id] = bot_choice
    await ctx.send(f"ボットの手は {hand_map[bot_choice]} です！")

    win_table = {"👊": "✌️", "✌️": "✋", "✋": "👊"}
    all_choices = set(player_choices.values())

    # 結果の計算と通知
    if len(all_choices) == 3:
        results_message = "ぐー、ちょき、ぱーが揃っているため、全員引き分け（あいこ）です！"
        await ctx.send(results_message)
        return

    results = {player_id: {"wins": 0, "losses": 0} for player_id in player_choices.keys() if player_choices[player_id]}
    for player_id, player_choice in player_choices.items():
        for opponent_id, opponent_choice in player_choices.items():
            if player_id != opponent_id and player_choice and opponent_choice:
                if win_table[player_choice] == opponent_choice:
                    results[player_id]["wins"] += 1
                elif win_table[opponent_choice] == player_choice:
                    results[player_id]["losses"] += 1

    winners = [player_id for player_id, result in results.items() if result["wins"] > 0 and result["losses"] == 0]
    losers = [player_id for player_id, result in results.items() if result["losses"] > 0 and result["wins"] == 0]

    results_message = "各プレイヤーの選択:\n"
    for player_id, player_choice in player_choices.items():
        player = await bot.fetch_user(player_id)
        if player_choice:
            results_message += f"- {player.display_name}: {hand_map[player_choice]}\n"
        else:
            results_message += f"- {player.display_name}: 選択なし\n"

    if winners:
        results_message += "\n**勝者:**\n"
        for winner_id in winners:
            winner = await bot.fetch_user(winner_id)
            results_message += f"- {winner.display_name}\n"

    if losers:
        results_message += "\n**敗者:**\n"
        for loser_id in losers:
            loser = await bot.fetch_user(loser_id)
            results_message += f"- {loser.display_name}\n"

    await ctx.send("結果:\n" + results_message)

# HTTPサーバーを起動しつつ、Discord Botを実行
keep_alive()
bot.run(TOKEN)
