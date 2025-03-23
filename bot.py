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

# Discord Botの準備
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Flaskアプリケーション（ヘルスチェック用）
app = Flask("")

@app.route("/")
def home():
    return "Bot is running!", 200  # ヘルスチェック用レスポンス

def run_http_server():
    # Koyebで提供されるPORT環境変数を使用
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    threading.Thread(target=run_http_server).start()

# グローバル辞書でDMメッセージを管理
user_messages = {}

@bot.event
async def on_ready():
    print(f"{bot.user.name} is ready!")

@bot.event
async def on_member_update(before, after):
    # 新しいロールが追加された場合をチェック
    new_roles = set(after.roles) - set(before.roles)
    for role in new_roles:
        if role.name == "見学":  # 対象のロール名を指定
            try:
                # メンバーにDMを送信
                message = await after.send(
                    f"こんにちは！あなたに '{role.name}' が付与されました！\n"
                    "このロールが付いた人はメッセージを送れなくなり、見ることしかできません。\n"
                    "それがいやな場合、以下にアクセスしてください:\n"
                    "https://discord.com/channels/1165775639798878288/1351191234961604640"
                )
                # メッセージを記録
                user_messages[after.id] = message.id
                print(f"Message sent to {after.name}")
            except discord.Forbidden:
                print(f"Could not send message to {after.name} (DM disabled or permission denied)")
            break

    # 削除されたロールがある場合のチェック
    removed_roles = set(before.roles) - set(after.roles)
    for role in removed_roles:
        if role.name == "YourRoleName":  # 対象のロール名を指定
            # 該当ユーザーの送信済みメッセージを削除
            if after.id in user_messages:
                try:
                    message_id = user_messages.pop(after.id)
                    channel = await after.create_dm()  # DMチャンネルを取得
                    message = await channel.fetch_message(message_id)
                    await message.delete()
                    print(f"Message deleted for {after.name}")
                except discord.Forbidden:
                    print(f"Could not delete message for {after.name} (DM disabled or permission denied)")
                except discord.NotFound:
                    print(f"Message not found for {after.name}")
            break

# じゃんけんゲームコマンド
@bot.command()
async def janken(ctx):
    await ctx.send("じゃんけんを始めます！ボットがDMを送信しますので、リアクションで手を選んでください！")

    # プレイヤー全員にDMを送信し、リアクションで選択を受け取る
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

    tasks = []
    for member in ctx.guild.members:
        if not member.bot:
            tasks.append(send_dm_and_wait(member))

    await asyncio.gather(*tasks)

    bot_choice = random.choice(reactions)
    player_choices[bot.user.id] = bot_choice
    await ctx.send(f"ボットの手は {hand_map[bot_choice]} です！")

    win_table = {"👊": "✌️", "✌️": "✋", "✋": "👊"}
    all_choices = set(player_choices.values())

    if len(all_choices) == 3:
        results_message = "各プレイヤーの選択:\n"
        for player_id, player_choice in player_choices.items():
            player = await bot.fetch_user(player_id)
            results_message += f"- {player.display_name}: {hand_map[player_choice]}\n"
        results_message += "\nぐー、ちょき、ぱーが揃っているため、全員引き分け（あいこ）です！"
        await ctx.send("結果:\n" + results_message)
        return

    results = {player_id: {"wins": 0, "losses": 0} for player_id in player_choices.keys()}
    for player_id, player_choice in player_choices.items():
        for opponent_id, opponent_choice in player_choices.items():
            if player_id != opponent_id:
                if win_table[player_choice] == opponent_choice:
                    results[player_id]["wins"] += 1
                elif win_table[opponent_choice] == player_choice:
                    results[player_id]["losses"] += 1

    winners = [player_id for player_id, result in results.items() if result["wins"] > 0 and result["losses"] == 0]
    losers = [player_id for player_id, result in results.items() if result["losses"] > 0 and result["wins"] == 0]

    results_message = "各プレイヤーの選択:\n"
    for player_id, player_choice in player_choices.items():
        player = await bot.fetch_user(player_id)
        results_message += f"- {player.display_name}: {hand_map[player_choice]}\n"

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
