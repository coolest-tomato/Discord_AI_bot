import discord
from discord.ext import commands, tasks
from openai import OpenAI
import os
import random
from datetime import datetime, time
from dotenv import load_dotenv
from topics import WRITING_TOPICS

load_dotenv()


# ─── 설정 ───────────────────────────────────────────────
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ALARM_CHANNEL_ID = int(os.environ.get("ALARM_CHANNEL_ID", "0"))

# 알람 시간 설정 (UTC 기준 / KST = UTC+9)
ALARM_HOUR = int(os.environ.get("ALARM_HOUR", "1"))    # UTC 01:00 = KST 10:00
ALARM_MINUTE = int(os.environ.get("ALARM_MINUTE", "0"))

# ─── 작문 주제 목록 from topics.py ──────────────────────────────────────
random_topics = WRITING_TOPICS

# ─── Bot 및 OpenAI 클라이언트 설정 ───────────────────────
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
openai_client = OpenAI(api_key= OPENAI_API_KEY)

# 사용자 세션 저장 (메모리)
user_sessions = {}  # {user_id: {"topic": ..., "waiting_for_writing": bool}}


# ─── AI 피드백 생성 함수 (OpenAI) ────────────────────────
def get_ai_feedback(topic: str, user_writing: str) -> str:
    response = openai_client.chat.completions.create(
        model="gpt-4o", 
        max_tokens=1500,
        messages=[
            {
                "role": "system",
                "content": """You are a friendly and encouraging English writing tutor. 
Analyze the student's writing and provide structured feedback in Korean (한국어로 피드백 작성).

Your feedback should include:
1. 전반적인 평가 (Overall Assessment) - 칭찬으로 시작하세요
2. 문법 오류 (Grammar Errors) - 구체적인 수정 예시 포함
3. 어휘 개선 (Vocabulary Suggestions) - 더 나은 단어 제안
4. 문장 구조 (Sentence Structure) - 개선할 점
5. 총점 (Score) - 10점 만점으로 평가
6. 모범 답안 예시 (Sample Answer) - 수정 예시 포함한 최종 수정본 제공

Be encouraging and constructive. Always end with positive motivation."""
            },
            {
                "role": "user",
                "content": f"주제: {topic}\n\n학생의 작문:\n{user_writing}"
            }
        ]
    )
    return response.choices[0].message.content


# ─── 오늘의 주제 embed 생성 ───────────────────────────────
def create_topic_embed(topic_data: dict) -> discord.Embed:
    level_colors = {
        "Beginner": discord.Color.green(),
        "Intermediate": discord.Color.gold(),
        "Advanced": discord.Color.red(),
    }
    color = level_colors.get(topic_data["level"], discord.Color.blue())

    embed = discord.Embed(
        title="✍️ 오늘의 영어 작문 주제",
        description=f"**{topic_data['topic']}**",
        color=color,
        timestamp=datetime.now()
    )
    embed.add_field(name="📊 난이도", value=topic_data["level"], inline=True)
    embed.add_field(name="💡 힌트", value=topic_data["hint"], inline=False)
    embed.add_field(
        name="📝 참여 방법",
        value="이 채널에 영어로 작문을 보내주세요!\n`!write` 명령어로 언제든지 새 주제를 받을 수 있어요.",
        inline=False
    )
    embed.set_footer(text="English Writing Practice Bot | 매일 꾸준히 연습해요! 💪")
    return embed


# ─── 일일 알람 태스크 ─────────────────────────────────────
@tasks.loop(time=time(hour=ALARM_HOUR, minute=ALARM_MINUTE))
async def daily_writing_alarm():
    channel = bot.get_channel(ALARM_CHANNEL_ID)
    if channel is None:
        print(f"❌ 채널을 찾을 수 없습니다: {ALARM_CHANNEL_ID}")
        return

    topic_data = random.choice(random_topics)
    bot.today_topic = topic_data

    alarm_embed = discord.Embed(
        title="🔔 영어 작문 연습 시간이에요!",
        description="안녕하세요! 오늘의 영어 작문 주제가 도착했어요. 매일 꾸준한 연습이 실력 향상의 지름길입니다! 💪",
        color=discord.Color.blue()
    )
    await channel.send(embed=alarm_embed)
    await channel.send(embed=create_topic_embed(topic_data))
    await channel.send(
        "📌 작문을 완성했다면 이 채널에 바로 보내주세요. AI가 즉시 피드백을 드립니다!\n"
        "`!write` - 새로운 주제 받기 | `!topic` - 오늘의 주제 다시 보기 | `!help_writing` - 도움말"
    )


# ─── 봇 준비 완료 ─────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ {bot.user} 봇이 시작되었습니다!")
    bot.today_topic = random.choice(random_topics)
    daily_writing_alarm.start()


# ─── 메시지 수신 처리 (작문 피드백) ──────────────────────
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    await bot.process_commands(message)

    # 명령어는 건너뜀
    if message.content.startswith("!"):
        return

    user_id = message.author.id
    session = user_sessions.get(user_id, {})

    # 작문 대기 중이거나 알람 채널에서 메시지를 보낸 경우
    if session.get("waiting_for_writing") or (message.channel.id == ALARM_CHANNEL_ID and not message.content.startswith("!")):
        topic = session.get("topic") or getattr(bot, "today_topic", random.choice(random_topics))

        # 최소 길이 체크
        if len(message.content.split()) < 5:
            await message.reply("✏️ 조금 더 길게 작성해 주세요! (최소 5단어 이상)")
            return

        async with message.channel.typing():
            thinking_msg = await message.reply("🤔 AI가 작문을 분석하고 있어요... 잠시만 기다려주세요!")
            try:
                feedback = get_ai_feedback(topic["topic"], message.content)

                feedback_embed = discord.Embed(
                    title="📊 AI 작문 피드백",
                    description=feedback,
                    color=discord.Color.purple(),
                    timestamp=datetime.now()
                )
                feedback_embed.set_author(
                    name=f"{message.author.display_name}의 작문 분석",
                    icon_url=message.author.display_avatar.url
                )
                feedback_embed.set_footer(text="계속 연습하면 반드시 실력이 늘어요! 🌟")

                await thinking_msg.delete()
                await message.reply(embed=feedback_embed)

                # 세션 초기화
                if user_id in user_sessions:
                    del user_sessions[user_id]

            except Exception as e:
                await thinking_msg.edit(content=f"❌ 피드백 생성 중 오류가 발생했습니다: {str(e)}")


# ─── 명령어: 새 주제 받기 ─────────────────────────────────
@bot.command(name="write")
async def new_topic(ctx):
    """새로운 작문 주제를 받습니다."""
    topic_data = random.choice(random_topics)
    user_sessions[ctx.author.id] = {
        "topic": topic_data,
        "waiting_for_writing": True
    }
    await ctx.send(embed=create_topic_embed(topic_data))
    await ctx.send(f"{ctx.author.mention} 주제를 받았어요! 이 채널에 영어로 작문을 보내주세요. ✍️")


# ─── 명령어: 오늘의 주제 보기 ────────────────────────────
@bot.command(name="topic")
async def show_topic(ctx):
    """오늘의 작문 주제를 다시 보여줍니다."""
    topic = getattr(bot, "today_topic", None)
    if topic:
        await ctx.send(embed=create_topic_embed(topic))
    else:
        await ctx.send("📭 오늘의 주제가 아직 없어요. `!write`로 새 주제를 받아보세요!")


# ─── 명령어: 난이도별 주제 ────────────────────────────────
@bot.command(name="level")
async def topic_by_level(ctx, level: str = "beginner"):
    """난이도별 주제를 받습니다. 사용법: !level [beginner/intermediate/advanced]"""
    level_map = {"beginner": "Beginner", "intermediate": "Intermediate", "advanced": "Advanced"}
    level_key = level_map.get(level.lower())

    if not level_key:
        await ctx.send("❌ 올바른 난이도를 입력해주세요: `beginner`, `intermediate`, `advanced`")
        return

    filtered = [t for t in random_topics if t["level"] == level_key]
    topic_data = random.choice(filtered)
    user_sessions[ctx.author.id] = {"topic": topic_data, "waiting_for_writing": True}
    await ctx.send(embed=create_topic_embed(topic_data))
    await ctx.send(f"{ctx.author.mention} **{level_key}** 주제를 받았어요! 작문을 보내주세요. ✍️")


# ─── 명령어: 알람 즉시 테스트 ────────────────────────────
@bot.command(name="test_alarm")
async def test_alarm(ctx):
    """알람을 즉시 테스트합니다."""
    topic_data = random.choice(random_topics)
    bot.today_topic = topic_data
    alarm_embed = discord.Embed(
        title="🔔 영어 작문 연습 시간이에요! (테스트)",
        description="매일 꾸준한 연습이 실력 향상의 지름길입니다! 💪",
        color=discord.Color.blue()
    )
    await ctx.send(embed=alarm_embed)
    await ctx.send(embed=create_topic_embed(topic_data))


# ─── 명령어: 도움말 ───────────────────────────────────────
@bot.command(name="help_writing")
async def help_command(ctx):
    """봇 사용법을 보여줍니다."""
    embed = discord.Embed(title="📖 영어 작문 봇 사용법", color=discord.Color.blue())
    embed.add_field(name="!write", value="랜덤 작문 주제 받기", inline=False)
    embed.add_field(name="!topic", value="오늘의 주제 다시 보기", inline=False)
    embed.add_field(name="!level [난이도]", value="난이도별 주제 받기\n예: `!level beginner`", inline=False)
    embed.add_field(name="!test_alarm", value="알람 즉시 테스트", inline=False)
    embed.add_field(name="✍️ 피드백 받기", value="주제를 받은 후 채널에 영어 작문을 보내면 AI가 자동으로 피드백을 드려요!", inline=False)
    embed.add_field(name="⏰ 자동 알람", value="매일 KST 10:00에 오늘의 주제가 자동으로 발송됩니다.", inline=False)
    await ctx.send(embed=embed)


# ─── 봇 실행 ─────────────────────────────────────────────
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
