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
ALARM_HOUR = int(os.environ.get("ALARM_HOUR", "11"))    # UTC 01:00 = KST 20:00
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
**전반적인 평가 (Overall Assessment)** 
- Start with positive feedback and briefly summarize strengths.
**문법 (Grammar)**
- Correct all grammar mistakes.  
- Show: (original → corrected)  
- Explain WHY each correction is needed.
**어휘 개선 (Vocabulary Suggestions)** 
- Suggest more natural or advanced words/phrases.  
- Format: "original → improved"  
- Explain nuance differences if needed.
**문장 구조 (Sentence Structure)**
- Identify awkward or unnatural sentences.  
- Suggest more fluent/native-like versions.
**총점 (Score)** 
- 아래와 같은 기준으로 5점 만점으로 평가해주세요. 
<5점>
답안이 질문 주제와 관련이 있고, 일관적인 언어 능력을 보여줌.
  • 설명과 예시, 세부사항 등이 서로 관련성이 있고 명료하게 제시됨
  • 다양한 문장 구조와 정확한 단어, 관용어구를 유능하게 사용함
  • 사소한 오타 도는 철자 오류를 제외하고는 어휘 또는 문법적 오류가 거의 없음
<4점>
답안이 온라인 토론 주제와 관련이 있고, 언어 능력은 답안의 아이디어를 쉽게 이해할 수 있게 함.
  • 설명과 예시, 세부사항 등이 서로 관련성이 있고 적절하게 설명됨
  • 다양한 문장 구조와 적절한 단어를 사용함
  • 어휘 또는 문법적 오류가 많지 않음
<3점>
답안이 질문 주제와 대부분 관련이 있고 이해할 수 있는 수준에서 기여함.
  • 설명과 예시, 세부사항의 일부가 누락되거나 불분명하거나 서로 연관성이 없음
  • 문장 구조와 단어를 다양하게 사용하는 편임
  • 눈에 띄는 어휘 또는 문법적 오류가 몇몇 있음
<2점>
답안이 질문에 관련시키려는 시도를 보이지만, 언어 능력의 한계로 답안의 아이디어를 이해하기 어려움.
  • 설명이 부족하거나 부분적으로만 관련이 있음
  • 문장 구조와 어휘 사용이 제한적임
  • 어휘 또는 문법적 오류가 자주 보임
<1점>
답안이 질문에 관련되지 않으며, 언어 능력의 한계로 아이디어를 표현하지 못함,
  • 아이디어가 일관되지 않음
  • 문장 구조 및 어휘 사용의 범위가 매우 제한적임
  • 심각한 어휘 또는 문법적 오류가 자주 보임
<0점>
답안을 작성하지 않은 경우, 주제에 반하거나 영어로 되어 있지 않은 경우, 또는 문제를 그대로 복사하거나 문제와 전혀 연관성이 없는 경우

**모범 답안 예시 (Sample Answer)**
- Rewrite my entire paragraph

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
        # "Advanced": discord.Color.red(),
    }
    color = level_colors.get(topic_data["level"], discord.Color.blue())

    embed = discord.Embed(
        title="✍️ 오늘의 영어 작문 주제",
        description=f"**{topic_data['topic']}**",
        color=color,
        timestamp=datetime.now()
    )
    embed.add_field(name="📊 난이도", value=topic_data["level"], inline=True)
    # embed.add_field(name="💡 힌트", value=topic_data["hint"], inline=False)
    embed.add_field(
        name="📝 참여 방법",
        value="이 채널에 영어로 작문을 보내주세요!\n`!write` 명령어로 언제든지 새 주제를 받을 수 있어요.",
        inline=False
    )
    embed.set_footer(text="멋있게 영어하는 그날까지 꾸준히 나아가세요! 💪")
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
    
    # ─── 자유 대화 함수 추가 ──────────────────────────────────
def get_ai_chat(user_message: str) -> str:
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        max_tokens=500,
        messages=[
            {
                "role": "system",
                "content": "You are a friendly English learning assistant. Chat naturally in Korean. If the user writes in English, praise them and respond naturally. Keep responses concise."
            },
            {
                "role": "user",
                "content": user_message
            }
        ]
    )
    return response.choices[0].message.content


# ─── 메시지 수신 처리 ──────────────────────────────────────
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    await bot.process_commands(message)

    if message.content.startswith("!"):
        return

    user_id = message.author.id
    session = user_sessions.get(user_id, {})

    # 작문 대기 중일 때만 피드백
    if session.get("waiting_for_writing"):
        topic = session.get("topic") or getattr(bot, "today_topic", random.choice(random_topics))

        if len(message.content.split()) < 5:
            await message.reply("✏️ 조금 더 길게 작성해 주세요! (최소 5단어 이상)")
            return

        async with message.channel.typing():
            thinking_msg = await message.reply("🤔 도우미가 글을 분석하고 있어요... 잠시만 기다려주세요!")
            try:
                feedback = get_ai_feedback(topic["topic"], message.content)
                feedback_embed = discord.Embed(
                    title="📊 AI 라이팅 피드백",
                    description=feedback,
                    color=discord.Color.purple(),
                    timestamp=datetime.now()
                )
                feedback_embed.set_author(
                    name=f"{message.author.display_name}의 작문 분석",
                    icon_url=message.author.display_avatar.url
                )
                feedback_embed.set_footer(text="내일은 더 나은 글을 쓰시게 될 것 같아요! 🌟")
                await thinking_msg.delete()
                await message.reply(embed=feedback_embed)

                # 피드백 후 → 자유 대화 모드로 전환
                user_sessions[user_id] = {"chat_mode": True}

            except Exception as e:
                await thinking_msg.edit(content=f"❌ 피드백 생성 중 오류가 발생했습니다: {str(e)}")

    # 자유 대화 모드
    elif session.get("chat_mode") and message.channel.id == ALARM_CHANNEL_ID:
        async with message.channel.typing():
            try:
                reply = get_ai_chat(message.content)
                await message.reply(reply)
            except Exception as e:
                await message.reply(f"❌ 오류: {str(e)}")


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
    await ctx.send(f"{ctx.author.mention} **{level_key}** 주제를 받았어요! 영어로 글을 써서 보내주시면 제가 분석해드릴게요! ✍️")


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
    embed.add_field(name="⏰ 자동 알람", value="매일 오후 8시에 오늘의 작문 주제가 자동으로 발송됩니다.", inline=False)
    await ctx.send(embed=embed)


# ─── 봇 실행 ─────────────────────────────────────────────
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
