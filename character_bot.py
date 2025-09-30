import os
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from config import (
    CHARACTER_INFO,
    CHARACTER_IMAGES,
    SUPPORTED_LANGUAGES,
    CHARACTER_CARD_INFO,
    AFFINITY_LEVELS,
    BASE_DIR,
    AFFINITY_THRESHOLDS,
    OPENAI_API_KEY,
    MILESTONE_COLORS,
    SELECTOR_TOKEN as TOKEN,
    KAGARI_TOKEN,
    EROS_TOKEN,
    ELYSIA_TOKEN,
    STORY_CHAPTERS,
    CARD_PROBABILITIES,
    CHARACTER_PROMPTS,
    get_card_info_by_id,
    CHARACTER_AFFINITY_SPEECH,
    get_combined_prompt,
    CLOUDFLARE_IMAGE_BASE_URL
)
from database_manager import DatabaseManager
from keyword_manager import KeywordManager
from typing import Dict, TYPE_CHECKING, Any
import json
import sys
from datetime import datetime
from pathlib import Path
import re
import langdetect
from deep_translator import GoogleTranslator
import random
from vision_manager import VisionManager
import logging
from story_mode import process_story_message, start_story_stage
import openai
from openai_manager import analyze_emotion_with_gpt_and_pattern
import time
from difflib import SequenceMatcher

# 절대 경로 설정
current_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(current_dir))

print("\n=== Environment Information ===")
print(f"Current file: {__file__}")
print(f"Absolute path: {Path(__file__).resolve()}")
print(f"Parent directory: {current_dir}")
print(f"Working directory: {os.getcwd()}")
print(f"Python path: {sys.path}")
print(f"Files in current directory: {os.listdir(current_dir)}")

# database_manager.py 파일 존재 확인
db_manager_path = current_dir / 'database_manager.py'
print(f"\n=== Database Manager File Check ===")
print(f"Looking for database_manager.py at: {db_manager_path}")
print(f"File exists: {db_manager_path.exists()}")

if not db_manager_path.exists():
    print("Searching in alternative locations...")
    possible_locations = [
        Path.cwd() / 'database_manager.py',
        Path('/home/runner/workspace/database_manager.py'),
        Path(__file__).resolve().parent.parent / 'database_manager.py'
    ]
    for loc in possible_locations:
        print(f"Checking {loc}: {loc.exists()}")
    raise FileNotFoundError(f"database_manager.py not found at {db_manager_path}")

print(f"\n=== Database Manager Content Check ===")
try:
    with open(db_manager_path, 'r') as f:
        content = f.read()
        print(f"File size: {len(content)} bytes")
        print("File contains 'set_channel_language':", 'set_channel_language' in content)
except Exception as e:
    print(f"Error reading file: {e}")

# DatabaseManager 임포트
try:
    print("\n=== Importing DatabaseManager ===")
    from database_manager import DatabaseManager
    db = DatabaseManager()
    print("Successfully imported DatabaseManager")
    print("Available methods:", [method for method in dir(db) if not method.startswith('_')])
except ImportError as e:
    print(f"Error importing DatabaseManager: {e}")
    print(f"Current directory: {current_dir}")
    print(f"Python path: {sys.path}")
    print(f"Files in directory: {os.listdir(current_dir)}")
    raise
except Exception as e:
    print(f"Error initializing DatabaseManager: {e}")
    import traceback
    print(traceback.format_exc())
    raise

print("\n=== Initialization Complete ===\n")

print(f"[DEBUG] character_bot.py loaded from:", __file__)

from config import CHARACTER_INFO
character_choices = [
    app_commands.Choice(name=char, value=char)
    for char in CHARACTER_INFO.keys()
]

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from bot_selector import BotSelector

class LanguageSelect(discord.ui.Select):
    def __init__(self, db, user_id: int, character_name: str):
        self.db = db
        self.user_id = user_id
        self.character_name = character_name

        from config import SUPPORTED_LANGUAGES
        options = []
        for lang_code, lang_info in SUPPORTED_LANGUAGES.items():
            options.append(
                discord.SelectOption(
                    label=lang_info["name"],
                    description=lang_info["native_name"],
                    value=lang_code,
                    emoji=lang_info["emoji"]
                )
            )

        super().__init__(
            placeholder="Select Language",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            selected_language = self.values[0]
            from config import SUPPORTED_LANGUAGES, ERROR_MESSAGES

            # 데이터베이스에 언어 설정 저장
            try:
                self.db.set_channel_language(
                    interaction.channel_id,
                    self.user_id,
                    self.character_name,
                    selected_language
                )

                # 성공 메시지 준비
                success_messages = {
                    "zh": f"(system) Language has been set to {SUPPORTED_LANGUAGES[selected_language]['name']}.",
                    "en": f"(smiling) Hello! Let's start chatting.",
                    "ja": f"(システム) 言語を{SUPPORTED_LANGUAGES[selected_language]['name']}に設定しました。"
                }

                await interaction.response.send_message(
                    success_messages.get(selected_language, success_messages["en"]),
                    ephemeral=True
                )

                # 시작 메시지 전송
                welcome_messages = {
                    "zh": "(微笑) 你好！让我们开始聊天吧。",
                    "en": "(smiling) Hello! Let's start chatting.",
                    "ja": "(微笑みながら) こんにちは！お話を始めましょう。"
                }

                await interaction.channel.send(welcome_messages.get(selected_language, welcome_messages["en"]))

            except Exception as e:
                print(f"Error setting language in database: {e}")
                error_msg = ERROR_MESSAGES["processing_error"].get(
                    selected_language,
                    ERROR_MESSAGES["processing_error"]["en"]
                )
                await interaction.response.send_message(error_msg, ephemeral=True)

        except Exception as e:
            print(f"Error in language selection callback: {e}")
            await interaction.response.send_message(
                "An error occurred while processing your language selection.",
                ephemeral=True
            )

class LanguageSelectView(discord.ui.View):
    def __init__(self, db, user_id: int, character_name: str, timeout: float = None):
        super().__init__(timeout=timeout)
        self.add_item(LanguageSelect(db, user_id, character_name))

class CharacterSelect(discord.ui.Select):
    def __init__(self, bot_selector: Any):
        self.bot_selector = bot_selector
        options = []
        from config import CHARACTER_INFO

        for char in CHARACTER_INFO.keys():
            options.append(discord.SelectOption(
                label=char,
                description=f"Chat with {char}",
                value=char
            ))

        super().__init__(
            placeholder="Select a character to chat with...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            selected_char = self.values[0]

            # 채널 생성 및 설정
            category = discord.utils.get(interaction.guild.categories, name="chatbot")
            if not category:
                try:
                    category = await interaction.guild.create_category("chatbot")
                except Exception as e:
                    print(f"Category creation error: {e}")
                    await interaction.response.send_message(
                        "Please check bot permissions.",
                        ephemeral=True
                    )
                    return

            channel_name = f"{selected_char.lower()}-{interaction.user.name.lower()}"
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }

            try:
                # 채널 생성
                channel = await interaction.guild.create_text_channel(
                    name=channel_name,
                    category=category,
                    overwrites=overwrites
                )

                # 선택된 캐릭터 봇에 채널 추가
                selected_bot = self.bot_selector.character_bots.get(selected_char)
                if selected_bot:
                    try:
                        # 채널 등록
                        print("\n=== Channel Registration Debug ===")
                        print(f"Channel ID: {channel.id}")
                        print(f"User ID: {interaction.user.id}")
                        print(f"Selected bot: {selected_char}")
                        print(f"Bot active_channels before: {selected_bot.active_channels}")

                        success, message = await selected_bot.add_channel(channel.id, interaction.user.id)

                        print(f"Add channel result - Success: {success}, Message: {message}")
                        print(f"Bot active_channels after: {selected_bot.active_channels}")
                        print("=== End Channel Registration Debug ===\n")

                        if success:
                            # 채널 생성 알림 메시지
                            await interaction.response.send_message(
                                f"Channel registration complete",
                                ephemeral=True
                            )
                            print(f"[DEBUG] active_channels after add: {selected_bot.active_channels}")
                        else:
                            await channel.send("An error occurred while registering the channel. Please create the channel again.")
                            await channel.delete()
                            return

                    except Exception as e:
                        print(f"Error registering channel: {e}")
                        import traceback
                        print("Traceback:")
                        print(traceback.format_exc())
                        if not interaction.response.is_done():
                            await interaction.response.send_message(
                                "An error occurred while setting up the channel. Please try again.",
                                ephemeral=True
                            )
                        else:
                            await interaction.followup.send(
                                "An error occurred while setting up the channel. Please try again.",
                                ephemeral=True
                            )
                else:
                    await interaction.response.send_message(
                        "Selected character not found.",
                        ephemeral=True
                    )

            except Exception as e:
                print(f"Error in channel creation: {e}")
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "An error occurred while creating the channel. Please try again.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "An error occurred. Please try again.",
                        ephemeral=True
                    )

        except Exception as e:
            print(f"CharacterSelect error: {e}")
            import traceback
            print(traceback.format_exc())
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "An error occurred. Please try again.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "An error occurred. Please try again.",
                    ephemeral=True
                )

class SettingsManager:
    def __init__(self):
        self.settings_file = "settings.json"
        self.daily_limit = 100
        self.admin_roles = set()
        self.load_settings()

    def load_settings(self):
        if os.path.exists(self.settings_file):
            with open(self.settings_file, 'r') as f:
                data = json.load(f)
                self.daily_limit = data.get('daily_limit', 100)
                self.admin_roles = set(data.get('admin_roles', []))

    def save_settings(self):
        with open(self.settings_file, 'w') as f:
            json.dump({
                'daily_limit': self.daily_limit,
                'admin_roles': list(self.admin_roles)
            }, f)

    def set_daily_limit(self, limit: int):
        self.daily_limit = limit
        self.save_settings()

    def add_admin_role(self, role_id: int):
        self.admin_roles.add(role_id)
        self.save_settings()

    def remove_admin_role(self, role_id: int):
        self.admin_roles.discard(role_id)
        self.save_settings()

    def is_admin(self, user: discord.Member) -> bool:
        return user.guild_permissions.administrator or any(role.id in self.admin_roles for role in user.roles)

class CharacterBot(commands.Bot):
    def __init__(self, character_name: str, bot_selector=None):
        intents = discord.Intents.all()
        super().__init__(command_prefix='/', intents=intents)
        self.character_name = character_name
        self.bot_selector = bot_selector
        self.active_channels = {}
        self.db = DatabaseManager()
        self.keyword_manager = KeywordManager()
        self.story_mode_users = {}  # user_id: {channel_id, character_name}
        self.last_bot_messages = {}  # user_id별 최근 챗봇 메시지 리스트
        self.vision_manager = VisionManager(api_key=OPENAI_API_KEY)
        self.user_message_buffers = {}  # (user_id) -> list of (msg, timestamp)
        self.nickname_setup_sessions = {}  # user_id: {step, nickname}
        self.user_message_counts = {}  # user_id: message_count
        self.memory_summary_interval = 20  # Assuming a default value

    async def setup_hook(self):
        # 기존 setup_hook 코드가 있다면 유지
        try:
            # self.add_view(NicknameInputView(self, 0, ""))  # 글로벌 등록 제거
            print("[DEBUG] NicknameInputView registered globally via add_view (제거됨)")
        except Exception as e:
            print(f"[ERROR] Failed to register NicknameInputView globally: {e}")

    async def on_message(self, message):
        if message.author == self.user:
            return

        # 1:1 채팅이 아닌 경우 처리하지 않음
        if message.channel.id not in self.active_channels:
            print(f"[DEBUG] Channel {message.channel.id} not in active_channels: {self.active_channels}")
            return

        print(f"[DEBUG] on_message called for channel {message.channel.id}, user {message.author.id}, content: '{message.content}'")

        # 채널 활동 시간 업데이트 (자동 삭제 기능용)
        if hasattr(self, 'bot_selector') and self.bot_selector:
            import time
            self.bot_selector.channel_last_activity[message.channel.id] = time.time()

        # 1. 빈 메시지/시스템 메시지/히스토리 임베드 무시
        if not message.content or message.content.strip() == "":
            print(f"[DEBUG] Empty message ignored")
            return
        if message.content.startswith("(system)") or message.content.startswith("(smiling) Hello!"):
            print(f"[DEBUG] System message ignored: {message.content}")
            return
        if message.content.startswith("Previous conversations") or message.content.startswith("Affinity information"):
            print(f"[DEBUG] History embed ignored: {message.content}")
            return
        if message.content.lower() in ["english.", "korean.", "japanese."]:
            print(f"[DEBUG] Language selection message ignored: {message.content}")
            return

        # [추가] 이미지 첨부가 있을 때 Vision API로 분석
        if message.attachments:
            print(f"[DEBUG] Image attachment detected, processing...")
            image_url = message.attachments[0].url
            try:
                vision_result = await self.vision_manager.analyze_image(image_url)
                # description만 추출, dict 전체나 'success': True가 출력되지 않도록 보장
                description = ""
                if isinstance(vision_result, dict):
                    description = vision_result.get("description") or "I couldn't see anything special in the image."
                else:
                    # dict가 아니면, 문자열에서 description만 추출
                    import re
                    match = re.search(r"'description':\s*'([^']+)'", str(vision_result))
                    if match:
                        description = match.group(1)
                    else:
                        # 혹시 success 등 불필요한 키가 포함된 경우 제거
                        description = str(vision_result)
                        description = re.sub(r"'success':\s*True", "", description)
                        description = re.sub(r"[{}]", "", description)
                        description = description.strip()
                char = self.character_name.lower()
                if char == "kagari":
                    reply = f"(eyes widen in surprise) Wow, this picture is really interesting! To me, it looks like {description} (smiles) Could you tell me more about it?"
                elif char == "eros":
                    reply = f"(leans in with curiosity) Fascinating image! From what I see, it's {description} (grins) What do you think about it?"
                elif char == "elysia":
                    reply = f"(softly smiles) This image feels quite lovely. I think it shows {description} (gentle tone) Would you like to share your thoughts about it?"
                else:
                    reply = f"Here's what I see in the image: {description}"
                await message.channel.send(reply)
            except Exception as e:
                await message.channel.send("(a little panicked) There was a problem analyzing the image, can you try again?")
            return

        try:
            # 1:1 대화 모드: 바로 메시지 처리
            user_id = message.author.id
            character = self.character_name

            # 닉네임이 설정되어 있는지 확인
            nickname = self.db.get_user_nickname(user_id, character)
            print(f"[DEBUG] get_user_nickname({user_id}, {character}) -> {nickname}")
            
            if nickname:
                # 닉네임이 있으면 바로 대화 처리
                print(f"[DEBUG] Nickname found, calling process_normal_message")
                await self.process_normal_message(message)
            else:
                # 닉네임이 없으면 무시 (add_channel에서 이미 처리됨)
                print(f"[DEBUG] No nickname found, ignoring message")
                return

        except Exception as e:
            print(f"[ERROR] on_message 오류: {e}")
            import traceback
            print(traceback.format_exc())

    async def process_normal_message(self, message):
        print(f"[DEBUG] process_normal_message called for user {message.author.id}, character {self.character_name}")
        user_id = message.author.id
        character = self.character_name
        now = datetime.utcnow()

        # 첫 대화 체크 및 호감도 레벨별 인사 메시지
        print(f"[DEBUG] Calling check_and_send_greeting")
        await self.check_and_send_greeting(message, user_id, character)

        # 안전장치 확인 (BotSelector에서 가져온 안전장치 사용)
        if (hasattr(self, 'bot_selector') and 
            self.bot_selector is not None and 
            hasattr(self.bot_selector, 'safety_guard') and 
            self.bot_selector.safety_guard is not None):
            try:
                safety_check = await self.bot_selector.safety_guard.is_safe_to_process(
                    user_id, message.guild.id if message.guild else 0, message.content
                )
                
                if not safety_check['safe']:
                    # 안전장치에 의해 차단된 경우
                    blocked_reasons = safety_check['blocked_reasons']
                    if 'spam_detection' in blocked_reasons:
                        await message.channel.send("🚫 Spam detected. Please wait before sending another message.")
                    elif 'user_rate_limit' in blocked_reasons:
                        await message.channel.send("🚫 Too many requests. Please slow down.")
                    elif 'daily_limit' in blocked_reasons:
                        await message.channel.send("🚫 Daily message limit exceeded.")
                    elif 'guild_rate_limit' in blocked_reasons:
                        await message.channel.send("🚫 Server rate limit exceeded.")
                    return
            except Exception as e:
                print(f"Error in safety guard check: {e}")
                # 안전장치 에러가 발생해도 메시지 처리를 계속 진행

        # 메시지 제한 확인
        daily_used = self.db.get_user_daily_message_count(user_id)
        paid_used = self.db.get_user_paid_message_count(user_id)
        paid_balance = self.db.get_user_message_balance(user_id)
        is_admin = self.db.is_user_admin(user_id)
        is_subscribed = self.db.is_user_subscribed(user_id)
        
        # 메시지 사용 가능 여부 확인
        can_send = False
        message_type = None  # 'daily' 또는 'paid'
        
        if is_admin:
            # 관리자는 제한 없음
            can_send = True
            message_type = 'daily'
        elif is_subscribed:
            # 구독 사용자는 일일 20개 + 구독 추가 메시지 사용 가능
            subscription_daily_messages = self.db.get_subscription_daily_messages(user_id)
            max_daily_messages = 20 + subscription_daily_messages
            if daily_used < max_daily_messages:
                can_send = True
                message_type = 'daily'
            else:
                can_send = False
        else:
            # 일반 사용자: 일일 20개 먼저, 그 다음 유료 메시지
            if daily_used < 20:
                # 일일 메시지가 남아있으면 일일 메시지 사용
                can_send = True
                message_type = 'daily'
            elif daily_used >= 20 and paid_balance > 0:
                # 일일 메시지를 모두 사용했지만 유료 메시지가 있으면 유료 메시지 사용
                can_send = True
                message_type = 'paid'
            else:
                # 일일 메시지도 모두 사용하고 유료 메시지도 없으면 사용 불가
                can_send = False
        
        # 메시지 사용 불가능한 경우
        if not can_send:
            if is_subscribed:
                # 구독 사용자 제한
                subscription_daily_messages = self.db.get_subscription_daily_messages(user_id)
                max_daily_messages = 20 + subscription_daily_messages
                embed = discord.Embed(
                    title="🚫 Daily Message Limit",
                    description=f"You have reached your daily message limit.\n\n**Messages used today:** {daily_used}/{max_daily_messages}\n**Remaining messages:** 0\n\n**Daily breakdown:** 20 (base) + {subscription_daily_messages} (subscription) = {max_daily_messages} total",
                    color=discord.Color.red()
                )
                embed.add_field(
                    name="💡 Subscription Benefits",
                    value="Your subscription gives you extra messages daily. Check back tomorrow!",
                    inline=False
                )
            else:
                # 일반 사용자 제한
                embed = discord.Embed(
                    title="🚫 Message Balance Low",
                    description=f"Your message balance is low.\n\n**Daily messages used:** {daily_used}/20\n**Message balance:** {paid_balance}\n\n**Daily messages reset at UTC+0**\n**Purchased messages have no time limit**",
                    color=discord.Color.red()
                )
                embed.add_field(
                    name="💡 Purchase a message pack",
                    value="`/store` You can purchase message packs using commands.",
                    inline=False
                )
            
            await message.channel.send(embed=embed)
            return

        # 언어 감지
        detected_language = self.detect_language(message.content)
        
        # 유저 메시지 DB 저장 (conversations 테이블)
        is_daily = (message_type == 'daily')
        self.db.add_message(
            message.channel.id,   # channel_id
            user_id,              # user_id
            character,            # character_name
            "user",              # role
            message.content,      # content
            detected_language,    # 감지된 언어
            is_daily             # 일일 메시지 여부
        )

        # 메시지 사용 처리
        if not self.db.is_user_admin(user_id):
            if message_type == 'paid':
                # 유료 메시지 사용 시 잔액 차감
                self.db.use_user_message(user_id)
                print(f"Used paid message for user {user_id}, remaining balance: {self.db.get_user_message_balance(user_id)}")
            else:
                # 일일 메시지 사용 시 차감 없음 (자동으로 카운트됨)
                print(f"Used daily message for user {user_id}, daily used: {self.db.get_user_daily_message_count(user_id)}")

        affinity_before = self.db.get_affinity(user_id, character)
        if not affinity_before:
            # 이전에 기록이 없는 신규 사용자일 경우 초기값 설정
            self.db.update_affinity(user_id, character, "", now, 0, 0)
            affinity_before = self.db.get_affinity(user_id, character)

        prev_grade = get_affinity_grade(affinity_before['emotion_score'])
        prev_score = affinity_before['emotion_score']
        highest_milestone_before = affinity_before.get('highest_milestone_achieved', 0)

        try:
            print(f"[DEBUG] Starting emotion analysis and context building")
            # 감정 분석과 컨텍스트 생성을 병렬로 처리
            emotion_task = asyncio.create_task(self.analyze_emotion(message.content))
            context_task = asyncio.create_task(self.build_conversation_context(user_id, character, message.content))
            emotion_score, context = await asyncio.gather(emotion_task, context_task)
            print(f"[DEBUG] Emotion score: {emotion_score}, context length: {len(context)}")

            # [추가] 감정 로그 DB 기록 (모든 캐릭터 공통)
            self.db.add_emotion_log(user_id, character, emotion_score, message.content, now)
            print(f"[DEBUG] Emotion log added to database")

            print(f"[DEBUG] Getting AI response")
            response = await self.get_ai_response(context)
            print(f"[DEBUG] AI response received: {response[:100]}...")
            
            print(f"[DEBUG] Sending bot message")
            await self.send_bot_message(message.channel, response, user_id)
            print(f"[DEBUG] Bot message sent successfully")

            # 새로운 점수 및 마일스톤 계산
            new_score = prev_score + emotion_score
            new_grade = get_affinity_grade(new_score)

            # [추가] 키워드 추출 (Silver, Gold 등급에서만)
            if new_grade in ['Silver', 'Gold']:
                try:
                    keywords = self.keyword_manager.extract_keywords(message.content)
                    if keywords:
                        self.keyword_manager.save_keywords(user_id, character, keywords)
                        print(f"[키워드] {character} - {len(keywords)}개 키워드 추출됨")
                except Exception as e:
                    print(f"[키워드 에러] {e}")
            new_milestone = (new_score // 10) * 10

            # 갱신할 최고 마일스톤 계산 (이전 값과 새 마일스톤 중 더 큰 값)
            highest_milestone_to_update = max(highest_milestone_before, new_milestone)

            # 데이터베이스에 친밀도 및 최고 마일스톤 업데이트
            self.db.update_affinity(
                user_id=user_id,
                character_name=character,
                last_message=message.content,
                last_message_time=now,
                score_change=emotion_score,
                highest_milestone=highest_milestone_to_update
            )

            # 등급 변경 체크
            if prev_grade != new_grade:
                if new_score > prev_score:
                    # 점수가 올랐을 때만 레벨업 메시지 전송
                    embed = self.create_level_up_embed(character, prev_grade, new_grade)
                    await message.channel.send(embed=embed)
                else:
                    # 점수가 내렸을 때 다운그레이드 메시지 전송
                    embed = self.create_level_down_embed(character, prev_grade, new_grade)
                    await message.channel.send(embed=embed)

            # 새로운 최고 마일스톤 달성 시에만 보상 로직 실행
            if new_milestone > highest_milestone_before:
                await self.handle_milestone_reward(message, character, user_id, new_milestone)

            # 호감도 달성 알림 체크 (20, 50 달성 시)
            await self.check_and_send_affinity_notifications(message, character, user_id, prev_score, new_score)

            # [추가] 서머리 생성 (10개 메시지마다)
            try:
                recent_message_count = self.db.get_user_recent_message_count(user_id, character, 10)
                if recent_message_count >= 10:
                    # 10개 메시지마다 서머리 생성
                    await self.create_memory_summary(user_id, character)
            except Exception as e:
                print(f"[서머리 에러] {e}")

        except Exception as e:
            print(f"Error in process_normal_message: {e}")
            import traceback
            traceback.print_exc()
            
            # 에러 핸들러에 에러 기록
            if (hasattr(self, 'bot_selector') and 
                self.bot_selector is not None and 
                hasattr(self.bot_selector, 'error_handler') and 
                self.bot_selector.error_handler is not None):
                await self.bot_selector.error_handler.log_error(e, "process_normal_message")
            
            # 모니터링에 에러 기록
            if (hasattr(self, 'bot_selector') and 
                self.bot_selector is not None and 
                hasattr(self.bot_selector, 'monitor') and 
                self.bot_selector.monitor is not None):
                self.bot_selector.monitor.record_error("process_normal_message")
            
            await message.channel.send("❌ An error occurred while processing the response.")

    async def handle_daily_quest_reward(self, message, character_name: str, user_id: int):
        """[수정된 함수] 일일 퀘스트 보상(선물)을 처리합니다. (대화 횟수 기반)"""
        try:
            # DB 매니저를 통해 랜덤 선물을 지급하고, 선물 이름을 받아옴
            reward_gift_name = self.db.add_random_gift_to_user(user_id, character_name)
            if not reward_gift_name:
                print(f"[Quest Error] Failed to give a random gift.")
                return

            self.db.mark_quest_reward_claimed(user_id, character_name)

            embed = discord.Embed(
                title="🎁 Daily Quest Complete!",
                description=f"You've completed **20 conversations** with **{character_name}** today!",
                color=discord.Color.gold()
            )
            embed.add_field(
                name="Reward",
                value=f"You received **1x {reward_gift_name}**!\nUse the `/inventory` command to check and use your gifts.",
                inline=False
            )
            embed.set_footer(text=f"A special gift for your daily dedication.")

            await message.channel.send(f"Congratulations, {message.author.mention}!", embed=embed)
            print(f"[Quest Success] User {user_id} received a random gift (Quest reward for {character_name})")

        except Exception as e:
            print(f"[ERROR] Daily quest reward processing error: {e}")

    async def handle_milestone_reward(self, message, character, user_id, new_milestone):
        """10, 20, 30, 40, 50, 60 등 10의 배수마다 등급별 확률표로 카드 지급. 중복 지급 방지."""
        try:
            print(f"[DEBUG] handle_milestone_reward 호출: user_id={user_id}, character={character}, new_milestone={new_milestone}")
            
            from config import get_card_tier_by_affinity, get_available_cards
            affinity = self.db.get_affinity(user_id, character)["emotion_score"]
            tier_probs = get_card_tier_by_affinity(affinity)
            import random
            tiers, probs = zip(*tier_probs)
            chosen_tier = random.choices(tiers, weights=probs, k=1)[0]
            
            print(f"[DEBUG] 선택된 티어: {chosen_tier}, 친밀도: {affinity}")
            
            # 사용자가 보유한 카드 목록 가져오기 (카드 ID만)
            user_cards = self.db.get_user_cards(user_id, character)
            user_card_ids = [card[0] for card in user_cards] if user_cards else []
            
            print(f"[DEBUG] 사용자 보유 카드: {user_card_ids}")
            
            # 중복되지 않은 카드만 선택
            available_cards = get_available_cards(character, chosen_tier, user_card_ids)
            if not available_cards:
                print(f"[DEBUG] No available cards for {character} tier {chosen_tier}, user already has all cards")
                return  # 지급할 카드 없음
            
            card_id = random.choice(available_cards)
            print(f"[DEBUG] Selected card {card_id} from {len(available_cards)} available cards for {character} tier {chosen_tier}")

            # 카드 지급 (CardClaimView 사용) - 미리 저장하지 않고 버튼 클릭 시 저장
            from config import get_card_info_by_id
            card_info = get_card_info_by_id(character, card_id)
            print(f"[DEBUG] 카드 정보: {card_info}")
            
            embed = discord.Embed(
                title="🎉 New Card Unlocked!",
                description=f"You've reached a new milestone with {character} and received a special card!\nClick the button to claim it.",
                color=discord.Color.gold()
            )
            
            # 이미지 URL 설정 - get_card_info_by_id에서 이미 올바른 image_url을 설정함
            if card_info.get("image_url"):
                embed.set_image(url=card_info["image_url"])
                print(f"[DEBUG] 카드 이미지 설정: {card_info['image_url']}")
            else:
                print(f"[DEBUG] 카드 이미지 URL 없음: {card_info}")
                
            view = CardClaimView(user_id, character, card_id, self.db)
            await message.channel.send(embed=embed, view=view)
            
            print(f"[DEBUG] 카드 발급 완료: {card_id}")

        except Exception as e:
            print(f"Error in handle_milestone_reward: {e}")
            import traceback
            traceback.print_exc()

    def create_level_down_embed(self, character_name, prev_grade, new_grade):
        char_info = CHARACTER_INFO.get(character_name, {})
        color_value = char_info.get('color', '#992d22')

        if isinstance(color_value, str):
            color = discord.Color(int(color_value.replace("#", "").replace("0x", ""), 16))
        else:
            color = discord.Color(int(color_value))

        messages = {
            ("Gold", "Silver"): "Your relationship has weakened a bit.",
            ("Silver", "Bronze"): "It seems there's a growing distance between you."
        }

        description = messages.get((prev_grade, new_grade), "Your relationship has weakened.")

        embed = discord.Embed(title="💧 Affinity Level Down...", description=description, color=color)
        embed.add_field(name="Level Change", value=f"{prev_grade} → {new_grade}", inline=False)
        embed.set_thumbnail(url=f"{CLOUDFLARE_IMAGE_BASE_URL}/{CHARACTER_IMAGES.get(character_name)}")
        return embed

    def detect_language(self, text: str) -> str:
        try:
            # 시도 1: 괄호 제거 후 언어 감지
            text_without_brackets = re.sub(r'\([^)]*\)', '', text)
            text_to_detect = text_without_brackets
        except re.error:
            # 정규식 오류(짝이 맞지 않는 괄호 등) 발생 시 원본 텍스트 사용
            text_to_detect = text

        try:
            text_clean = re.sub(r'[^a-zA-Z\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\s]', '', text_to_detect)
            text_clean = text_clean.strip()
            if not text_clean:
                return 'en'
            detected = langdetect.detect(text_clean)
            lang_map = {
                'zh-cn': 'zh', 'zh-tw': 'zh', 'zh': 'zh',
                'ja': 'ja',
                'en': 'en'
            }
            return lang_map.get(detected, detected)
        except Exception as e:
            print(f"Language detection error: {e}")
            return 'en'

    def translate_to_target_language(self, text: str, target_language: str) -> str:
        try:
            lang_map = {
                'zh': 'zh-CN',
                'ja': 'ja',
                'en': 'en'
            }
            target = lang_map.get(target_language, target_language)

            translator = GoogleTranslator(source='auto', target=target)
            result = translator.translate(text)
            return result
        except Exception as e:
            print(f"Translation error: {e}")
            return text

    lang_mapping = {
        'en': 'en',
        'ja': 'ja',
        'zh': 'zh-cn'
    }

    async def generate_response(self, user_message: str, channel_language: str, recent_messages: list) -> str:
        # recent_messages 필터링
        filtered_recent = [
            m for m in recent_messages
            if self.detect_language(m["content"]) == channel_language
        ]
        # recent_messages가 비어있으면, 맥락 없이 대화 시작

        # 시스템 메시지 강화
        if channel_language == "ja":
            system_message = {
                "role": "system",
                "content": (
                    "あなたはカガリという明るくて優しい10代の少女です。必ず日本語だけで答えてください。"
                    "感情や行動の描写も日本語でカッコ内に自然に入れてください。"
                    "例：(微笑んで)、(うなずきながら)、(少し恥ずかしそうに) など"
                )
            }
        elif channel_language == "zh":
            system_message = {
                "role": "system",
                "content": (
                    "你是名叫Kagari的开朗温柔的十几岁少女。请务必只用中文回答。"
                    "情感或动作描写也请用中文括号自然地加入。"
                    "例如：（微笑着）、（点头）、（有点害羞地）等"
                )
            }
        else:
            system_message = {
                "role": "system",
                "content": (
                    "You are Kagari, a bright, kind, and slightly shy teenage girl. "
                    "You MUST reply ONLY in English. All actions, feelings, and dialogue must be in English. "
                    "At the end or in the middle of each reply, add a short parenthesis ( ) describing Kagari's current feeling or action, such as (smiling), (blushing), etc."
                )
            }

        # 응답 생성 및 언어 검증
        for attempt in range(3):
            response = await self.get_ai_response(system_message + filtered_recent + [{"role": "user", "content": user_message}])
            response_language = self.detect_language(response)
            if response_language == channel_language:
                return response
        # 3번 모두 실패하면 강제 오류 메시지
        return f"(system error) Only {channel_language.upper()} is allowed."

    def normalize_text(self, text):
        # 괄호, 이모지, 특수문자, 공백 등 제거
        text = re.sub(r'\([^)]*\)', '', text)  # 괄호 내용 제거
        text = re.sub(r'[^\w가-힣a-zA-Z0-9]', '', text)  # 특수문자 제거
        text = text.strip().lower()
        return text

    async def send_bot_message(self, channel, message, user_id=None):
        """봇 메시지를 전송하고, 필요한 경우 최근 메시지 목록을 업데이트합니다."""
        if user_id is not None:
            last_msgs = self.last_bot_messages.get(user_id, [])
            lines = [line.strip() for line in message.split('\n') if line.strip()]
            filtered_lines = []
            for line in lines:
                norm_line = self.normalize_text(line)
                norm_last = [self.normalize_text(msg) for msg in last_msgs]
                if norm_line not in norm_last:
                    filtered_lines.append(line)
                    last_msgs.append(line)
            if len(last_msgs) > 5:
                last_msgs = last_msgs[-5:]
            self.last_bot_messages[user_id] = last_msgs
            if not filtered_lines:
                return
            message = '\n'.join(filtered_lines)
        await channel.send(message)

    def remove_channel(self, channel_id):
        """활성 채널 목록에서 채널을 제거합니다."""
        if channel_id in self.active_channels:
            del self.active_channels[channel_id]
            print(f"Channel {channel_id} removed from active list.")

    async def summarize_messages(self, messages: list) -> str:
        """메시지 목록을 요약합니다."""
        max_retries = 3
        base_delay = 1.0

        for attempt in range(max_retries):
            try:
                messages_text = "\n".join([
                    f"{'User' if msg['role'] == 'user' else self.character_name}: {msg['content']}"
                    for msg in messages
                ])

                prompt = f"""Please summarize the following conversation between User and {self.character_name} in 2-3 sentences.
                Focus on key points, emotional changes, and important information shared.
                Format: [YYYY-MM-DD HH:MM] User: message / Character: message

                Conversation:
                {messages_text}
                """

                response = openai.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "system", "content": prompt}],
                    max_tokens=200,
                    temperature=0.7
                )

                return response.choices[0].message.content.strip()
            except Exception as e:
                print(f"Error in summarize_messages (attempt {attempt + 1}/{max_retries}): {e}")

                # 네트워크 관련 에러인지 확인
                is_network_error = (
                    "Connection reset by peer" in str(e) or
                    "Connection reset" in str(e) or
                    "Connection closed" in str(e) or
                    "Connection timeout" in str(e) or
                    "ClientOSError" in str(e) or
                    "aiohttp.client_exceptions.ClientOSError" in str(e) or
                    "aiohttp.client_exceptions.ClientConnectorError" in str(e) or
                    "aiohttp.client_exceptions.ServerDisconnectedError" in str(e) or
                    "aiohttp.client_exceptions.ClientResponseError" in str(e)
                )

                # 마지막 시도가 아니고 네트워크 에러인 경우 재시도
                if attempt < max_retries - 1 and is_network_error:
                    delay = base_delay * (2 ** attempt)  # 지수 백오프
                    print(f"Network error detected in message summarization, retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    # 네트워크 에러가 아니거나 마지막 시도인 경우
                    print(f"Message summarization failed after {max_retries} attempts")
                    return None

        return None

    async def analyze_emotion(self, text):
        """메시지의 감정을 분석하여 -1, 0, +1 점수를 반환 (70% GPT + 30% 패턴)"""
        return await analyze_emotion_with_gpt_and_pattern(text)

    async def add_channel(self, channel_id: int, user_id: int) -> tuple[bool, str]:
        """채널 활성화 및 닉네임 확인"""
        try:
            print(f"\n=== CharacterBot add_channel Debug ===")
            print(f"Adding channel for {self.character_name}")
            print(f"Channel ID: {channel_id}")
            print(f"User ID: {user_id}")
            print(f"Current active_channels: {self.active_channels}")

            if not isinstance(self.active_channels, dict):
                print(f"Converting active_channels from {type(self.active_channels)} to dict")
                self.active_channels = {}

            if channel_id in self.active_channels:
                print(f"Channel {channel_id} already exists")
                return False, "The channel is already active."

            self.active_channels[channel_id] = {
                "user_id": user_id,
                "history": []
            }

            print(f"Channel added successfully")
            print(f"Updated active_channels: {self.active_channels}")
            print("=== End CharacterBot add_channel Debug ===\n")

            # 닉네임 확인 및 처리
            await self.handle_channel_nickname_setup(channel_id, user_id)

            return True, "채널이 성공적으로 활성화되었습니다."

        except Exception as e:
            print(f"Error in add_channel: {e}")
            import traceback
            print("Traceback:")
            print(traceback.format_exc())
            return False, f"Error activating a channel: {str(e)}"

    async def handle_channel_nickname_setup(self, channel_id: int, user_id: int):
        """채널에서 닉네임 설정을 처리합니다."""
        try:
            # 채널 객체 가져오기
            channel = self.get_channel(channel_id)
            if not channel:
                print(f"Channel {channel_id} not found")
                return

            # 닉네임 확인
            nickname = self.db.get_user_nickname(user_id, self.character_name)
            print(f"[DEBUG] get_user_nickname({user_id}, {self.character_name}) -> {nickname}")

            if nickname:
                # 기존 사용자: 환영 메시지 전송
                welcome_embed = discord.Embed(
                    title="🎉 Welcome back!",
                    description=f"Hi {nickname}, welcome back to {self.character_name}! Let's continue our conversation!",
                    color=discord.Color.gold()
                )
                await channel.send(embed=welcome_embed)
            else:
                # 신규 사용자: 닉네임 입력 임베드 전송
                embed = discord.Embed(
                    title="👤 Set a nickname",
                    description=f"What would you like {self.character_name} to call you?\nMax 15 characters (no emoticons)\nPlease choose carefully as it will be difficult to change later.",
                    color=discord.Color.green()
                )
                view = NicknameInputView(self, user_id, self.character_name)
                await channel.send(embed=embed, view=view)

        except Exception as e:
            print(f"Error in handle_channel_nickname_setup: {e}")
            import traceback
            print(traceback.format_exc())

    async def get_ai_response(self, messages: list) -> str:
        """OpenAI API를 통한 응답 생성"""
        max_retries = 3
        base_delay = 1.0

        for attempt in range(max_retries):
            try:
                client = openai.AsyncOpenAI()
                response = await client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    temperature=0.6,
                    max_tokens=512,
                    presence_penalty=0.3,
                    frequency_penalty=0.1
                )
                return response.choices[0].message.content
            except Exception as e:
                print(f"Error in AI response generation (attempt {attempt + 1}/{max_retries}): {e}")

                # 네트워크 관련 에러인지 확인
                is_network_error = (
                    "Connection reset by peer" in str(e) or
                    "Connection reset" in str(e) or
                    "Connection closed" in str(e) or
                    "Connection timeout" in str(e) or
                    "ClientOSError" in str(e) or
                    "aiohttp.client_exceptions.ClientOSError" in str(e) or
                    "aiohttp.client_exceptions.ClientConnectorError" in str(e) or
                    "aiohttp.client_exceptions.ServerDisconnectedError" in str(e) or
                    "aiohttp.client_exceptions.ClientResponseError" in str(e)
                )

                # 마지막 시도가 아니고 네트워크 에러인 경우 재시도
                if attempt < max_retries - 1 and is_network_error:
                    delay = base_delay * (2 ** attempt)  # 지수 백오프
                    print(f"Network error detected, retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    # 네트워크 에러가 아니거나 마지막 시도인 경우
                    if is_network_error:
                        return "Sorry, there was a temporary network issue. Please try again in a moment."
                    else:
                        return "Sorry, an error occurred while generating a response."

        return "Sorry, an error occurred while generating a response."

    def create_level_up_embed(self, character_name: str, prev_grade: str, new_grade: str) -> discord.Embed:
        """레벨업 시 전송할 임베드를 생성합니다."""
        char_info = CHARACTER_INFO.get(character_name, {})
        color_value = char_info.get('color', '0xffc0cb')

        # Handle both hex string and integer color values
        if isinstance(color_value, str):
            color = discord.Color(int(color_value.replace("#", "").replace("0x", ""), 16))
        else:
            color = discord.Color(int(color_value))

        level_messages = {
            ("Rookie", "Iron"): f"Congratulations! {character_name} has started to take an interest in you!",
            ("Iron", "Bronze"): f"Great job! {character_name} is opening up and becoming a bit more comfortable with you.",
            ("Bronze", "Silver"): f"Nice! {character_name} is now showing real trust and warmth in your conversations!",
            ("Silver", "Gold"): f"Amazing! {character_name} really enjoys talking with you! You could become great friends!"
        }

        # 임베드 생성
        embed = discord.Embed(
            title="🎉 Affinity Level Up!",
            description=level_messages.get((prev_grade, new_grade), "Your relationship has grown stronger!"),
            color=color
        )

        # 레벨 아이콘 설정
        level_icons = {
            "Rookie": "🌱",
            "Iron": "✨",
            "Bronze": "🥉",
            "Silver": "🌟",
            "Gold": "🩷"
        }

        embed.add_field(
            name="Level Change",
            value=f"{level_icons[prev_grade]} {prev_grade} → {level_icons[new_grade]} {new_grade}",
            inline=False
        )

        # 캐릭터 이미지 추가
        char_image_url = CHARACTER_IMAGES.get(character_name)
        if char_image_url:
            embed.set_thumbnail(url=char_image_url)

        return embed

    async def create_memory_summary(self, user_id: int, character: str):
        """메모리 요약을 생성합니다."""
        try:
            # 최근 메시지 가져오기
            recent_messages = self.db.get_user_character_messages(user_id, character, limit=self.memory_summary_interval)
            if not recent_messages:
                return

            # 요약 생성
            summary = await self.summarize_messages(recent_messages)
            if summary:
                # 품질 점수 계산 (간단한 휴리스틱)
                quality_score = min(1.0, len(summary) / 200.0)  # 200자 기준
                token_count = len(summary.split())

                # 요약 저장
                self.db.add_memory_summary(user_id, character, summary, quality_score, token_count)

                # 오래된 요약 삭제
                self.db.delete_old_memory_summaries(user_id, character)

        except Exception as e:
            print(f"Error creating memory summary: {e}")

    async def analyze_user_emotion(self, message: str) -> str:
        """사용자 메시지의 감정을 분석합니다."""
        import re
        
        # 감정 키워드 매칭
        emotion_keywords = {
            "happy": ["happy", "joy", "glad", "cheerful", "excited", "smile", "laugh", "haha", "hehe", "😊", "😄", "😆", "😁", "😃", "great", "wonderful", "amazing", "fantastic"],
            "sad": ["sad", "depressed", "cry", "tears", "hurt", "pain", "sorrow", "grief", "😢", "😭", "😔", "😞", "😟", "upset", "down", "blue"],
            "angry": ["angry", "mad", "furious", "rage", "annoyed", "irritated", "😠", "😡", "🤬", "😤", "frustrated", "pissed"],
            "excited": ["excited", "thrilled", "pumped", "hyped", "wow", "awesome", "😍", "🤩", "😎", "🔥", "✨", "amazing", "incredible", "fantastic"],
            "tired": ["tired", "exhausted", "sleepy", "drowsy", "fatigued", "😴", "😪", "😵", "💤", "worn out", "beat"]
        }
        
        message_lower = message.lower()
        
        for emotion, keywords in emotion_keywords.items():
            for keyword in keywords:
                if keyword in message_lower:
                    return emotion
        
        return "neutral"
    
    async def detect_topic(self, message: str) -> str:
        """메시지의 주제를 감지합니다."""
        import re
        
        topic_keywords = {
            "food": ["food", "eat", "meal", "cook", "delicious", "hungry", "restaurant", "cafe", "drink", "tea", "coffee", "dinner", "lunch", "breakfast", "snack"],
            "weather": ["weather", "rain", "snow", "sun", "cloud", "wind", "hot", "cold", "temperature", "sunny", "cloudy", "storm"],
            "work": ["work", "job", "office", "company", "project", "meeting", "business", "career", "profession", "task"],
            "hobby": ["hobby", "game", "movie", "drama", "book", "music", "exercise", "drawing", "photo", "sport", "art", "craft"],
            "travel": ["travel", "trip", "vacation", "destination", "tour", "abroad", "domestic", "journey", "adventure", "explore"],
            "music": ["music", "song", "singer", "album", "concert", "listen", "melody", "rhythm", "band", "artist", "performance"],
            "book": ["book", "novel", "comic", "read", "reading", "literature", "author", "publish", "story", "fiction"],
            "nature": ["nature", "mountain", "sea", "river", "forest", "flower", "tree", "animal", "bird", "sky", "outdoor", "park"]
        }
        
        message_lower = message.lower()
        
        for topic, keywords in topic_keywords.items():
            for keyword in keywords:
                if keyword in message_lower:
                    return topic
        
        return "general"
    
    async def get_time_period(self, user_id: int = None) -> str:
        """사용자의 시간대를 반환합니다."""
        import datetime
        import pytz
        
        try:
            # 사용자별 시간대가 저장되어 있다면 사용, 없으면 서버 시간대 사용
            if user_id and hasattr(self, 'db'):
                user_timezone = await self.db.get_user_timezone(user_id)
                if user_timezone:
                    user_tz = pytz.timezone(user_timezone)
                    current_time = datetime.datetime.now(user_tz)
                else:
                    # 기본값으로 UTC 사용
                    current_time = datetime.datetime.now(pytz.UTC)
            else:
                # 데이터베이스가 없거나 user_id가 없으면 서버 시간대 사용
                current_time = datetime.datetime.now()
            
            current_hour = current_time.hour
            
            if 5 <= current_hour < 12:
                return "morning"
            elif 12 <= current_hour < 17:
                return "afternoon"
            elif 17 <= current_hour < 21:
                return "evening"
            else:
                return "night"
        except Exception as e:
            print(f"Error getting time period: {e}")
            # 오류 발생 시 서버 시간대 사용
            current_hour = datetime.datetime.now().hour
            if 5 <= current_hour < 12:
                return "morning"
            elif 12 <= current_hour < 17:
                return "afternoon"
            elif 17 <= current_hour < 21:
                return "evening"
            else:
                return "night"
    
    async def get_current_time_info(self, user_id: int = None) -> dict:
        """사용자의 현재 시간 정보를 반환합니다."""
        import datetime
        import pytz
        
        try:
            # 사용자별 시간대가 저장되어 있다면 사용, 없으면 서버 시간대 사용
            if user_id and hasattr(self, 'db'):
                user_timezone = await self.db.get_user_timezone(user_id)
                if user_timezone:
                    user_tz = pytz.timezone(user_timezone)
                    current_time = datetime.datetime.now(user_tz)
                    timezone_name = user_timezone
                else:
                    # 기본값으로 UTC 사용
                    current_time = datetime.datetime.now(pytz.UTC)
                    timezone_name = "UTC"
            else:
                # 데이터베이스가 없거나 user_id가 없으면 서버 시간대 사용
                current_time = datetime.datetime.now()
                timezone_name = "서버 시간대"
            
            # 시간 구간 판단
            current_hour = current_time.hour
            if 5 <= current_hour < 12:
                period = "morning"
                period_kr = "아침"
            elif 12 <= current_hour < 17:
                period = "afternoon"
                period_kr = "오후"
            elif 17 <= current_hour < 21:
                period = "evening"
                period_kr = "저녁"
            else:
                period = "night"
                period_kr = "밤"
            
            # 시간 포맷팅
            time_str = current_time.strftime("%H:%M")
            date_str = current_time.strftime("%Y년 %m월 %d일")
            
            return {
                "time": time_str,
                "date": date_str,
                "period": period,
                "period_kr": period_kr,
                "timezone": timezone_name,
                "full_time": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                "hour": current_hour,
                "minute": current_time.minute
            }
        except Exception as e:
            print(f"Error getting current time info: {e}")
            # 오류 발생 시 서버 시간대 사용
            current_time = datetime.datetime.now()
            current_hour = current_time.hour
            
            if 5 <= current_hour < 12:
                period = "morning"
                period_kr = "아침"
            elif 12 <= current_hour < 17:
                period = "afternoon"
                period_kr = "오후"
            elif 17 <= current_hour < 21:
                period = "evening"
                period_kr = "저녁"
            else:
                period = "night"
                period_kr = "밤"
            
            return {
                "time": current_time.strftime("%H:%M"),
                "date": current_time.strftime("%Y년 %m월 %d일"),
                "period": period,
                "period_kr": period_kr,
                "timezone": "서버 시간대",
                "full_time": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                "hour": current_hour,
                "minute": current_time.minute
            }
    
    async def detect_time_question(self, message: str) -> bool:
        """시간 관련 질문인지 감지합니다."""
        time_keywords = [
            "what time", "what's the time", "current time", "time now", "지금 몇 시", "몇 시야", "시간이", "시간이야",
            "time is it", "what time is it", "현재 시간", "지금 시간", "몇시", "몇시야", "시간", "시계"
        ]
        
        message_lower = message.lower()
        for keyword in time_keywords:
            if keyword in message_lower:
                return True
        return False
    
    async def build_conversation_context(self, user_id: int, character: str, current_message: str, call_nickname: bool = False) -> list:
        """대화 컨텍스트를 구성합니다."""
        context = []
        from config import CHARACTER_INFO, CHARACTER_PROMPTS, CHARACTER_AFFINITY_SPEECH, CHARACTER_PERSONALITIES, CHARACTER_EMOTION_REACTIONS, CHARACTER_TOPIC_REACTIONS, CHARACTER_TIME_REACTIONS
        
        character_info = CHARACTER_INFO.get(character, {})
        character_prompt = CHARACTER_PROMPTS.get(character, "")
        character_personality = CHARACTER_PERSONALITIES.get(character, {})
        nickname = self.db.get_user_nickname(user_id, character)
        affinity_info = self.db.get_affinity(user_id, character)
        affinity_grade = get_affinity_grade(affinity_info['emotion_score'])
        affinity_speech = CHARACTER_AFFINITY_SPEECH.get(character, {}).get(affinity_grade, {})
        tone = affinity_speech.get("tone", "")
        example = affinity_speech.get("example", "")
        
        # 감정 및 주제 분석
        user_emotion = await self.analyze_user_emotion(current_message)
        detected_topic = await self.detect_topic(current_message)
        time_period = await self.get_time_period(user_id)
        
        # 시간 관련 질문 감지
        time_question = await self.detect_time_question(current_message)
        time_info = None
        if time_question:
            time_info = await self.get_current_time_info(user_id)
        
        # 캐릭터 개성 정보 추출
        core_traits = character_personality.get("core_traits", [])
        speech_patterns = character_personality.get("speech_patterns", [])
        interests = character_personality.get("interests", [])
        quirks = character_personality.get("quirks", [])
        response_style = character_personality.get("response_style", "")
        
        # 감정별 반응 정보
        emotion_reactions = CHARACTER_EMOTION_REACTIONS.get(character, {}).get(user_emotion, {})
        emotion_reaction = ""
        if emotion_reactions:
            import random
            emotion_reaction = random.choice(emotion_reactions.get("reactions", [""]))
            emotion_follow_up = emotion_reactions.get("follow_up", "")
        
        # 주제별 반응 정보
        topic_reaction = CHARACTER_TOPIC_REACTIONS.get(character, {}).get(detected_topic, "")
        
        # 시간대별 반응 정보
        time_reactions = CHARACTER_TIME_REACTIONS.get(character, {}).get(time_period, {})
        time_greeting = time_reactions.get("greeting", "")
        time_mood = time_reactions.get("mood", "")
        time_activity = time_reactions.get("activity", "")
        
        nickname_instruction = f"In this response, naturally incorporate the user's nickname '{nickname}' in a way that feels genuine and matches the emotional context. Only use the nickname if it flows naturally with your response." if nickname and call_nickname else "For this response, avoid using the user's nickname and focus on creating a natural conversation flow."
        
        system_message = f"""{character_prompt}

Character Status:
- User's nickname: {nickname if nickname else 'Not set'}
- Affinity grade: {affinity_grade}
- Current tone: {tone}
- Example response: {example}

Character Personality:
- Core traits: {', '.join(core_traits)}
- Speech patterns: {', '.join(speech_patterns)}
- Interests: {', '.join(interests)}
- Quirks: {', '.join(quirks)}
- Response style: {response_style}

Context Analysis:
- User's detected emotion: {user_emotion}
- Detected topic: {detected_topic}
- Current time period: {time_period}
{f"- Current time: {time_info['time']} ({time_info['period_kr']})" if time_info else ""}
{f"- Date: {time_info['date']}" if time_info else ""}
{f"- Timezone: {time_info['timezone']}" if time_info else ""}

Emotion-based Response:
{emotion_reaction if emotion_reaction else "Respond naturally to the user's emotional state"}

Topic-based Response:
{topic_reaction if topic_reaction else "Respond naturally to the conversation topic"}

Time-based Response:
- Time greeting: {time_greeting}
- Time mood: {time_mood}
- Time activity: {time_activity}

{nickname_instruction}

[IMPORTANT] For this conversation:
1. Use the specified tone and nuance based on affinity level
2. Keep responses natural and in character - embody the core traits and quirks
3. Show appropriate emotions and actions in parentheses
4. Maintain the character's unique personality and speech patterns
5. Reference the character's interests when relevant
6. Respond to the user's emotional state with empathy and understanding
7. Incorporate topic-specific responses when relevant
8. Consider the time of day in your response
9. NEVER mention being an AI, bot, or program
10. Always respond in the same language as the user
11. Use informal speech style
12. Add emotional expressions in parentheses like (smiles), (looks away), etc.
13. Follow the character's response style and incorporate their quirks naturally
14. Pay attention to the user's message context and respond appropriately
15. Make the conversation feel personal and engaging
{f"16. TIME QUESTION DETECTED: The user is asking about the current time. Provide the specific time information naturally in your response: {time_info['time']} ({time_info['period_kr']}) on {time_info['date']}" if time_question and time_info else ""}
"""
        context.append({"role": "system", "content": system_message})
        # Silver, Gold, Platinum 등급에서만 최대 3개 메모리 요약
        if affinity_grade.lower() in ['silver', 'gold', 'platinum']:
            memory_summaries = self.db.get_memory_summaries_by_affinity(user_id, character, affinity_grade)
            if memory_summaries:
                memory_context = "Previous conversations:\n"
                for summary, created_at, quality_score in memory_summaries[:3]:
                    date_str = created_at.strftime('%Y-%m-%d %H:%M')
                    memory_context += f"[{date_str}] {summary}\n"
                context.append({"role": "system", "content": memory_context})
        # Silver, Gold 등급에서만 키워드 정보
        if affinity_grade in ['Silver', 'Gold']:
            try:
                keyword_context = self.keyword_manager.format_keywords_for_context(user_id, character)
                if keyword_context:
                    context.append({"role": "system", "content": keyword_context})
            except Exception as e:
                print(f"[ERROR] 키워드 컨텍스트 생성 중 오류: {e}")
        # 최근 메시지 5개만 추가
        recent_messages = self.db.get_user_character_messages(user_id, character, limit=5)
        for msg in recent_messages:
            context.append({
                "role": "user" if msg["role"] == "user" else "assistant",
                "content": msg["content"]
            })
        context.append({"role": "user", "content": current_message})
        return context

    async def validate_nickname(self, nickname: str, interaction_or_channel) -> bool:
        """닉네임 유효성을 검사합니다."""
        is_interaction = hasattr(interaction_or_channel, "response")
        async def send(msg):
            if is_interaction:
                # interaction에서 여러 번 response.send_message를 호출하면 에러가 나므로 followup 사용
                try:
                    await interaction_or_channel.response.send_message(msg, ephemeral=True)
                except Exception:
                    await interaction_or_channel.followup.send(msg, ephemeral=True)
            else:
                await interaction_or_channel.send(msg)

        if not nickname:
            await send("❌ Please enter a nickname.")
            return False
        if len(nickname) > 15:
            await send("❌ Nicknames can be up to 15 characters long.")
            return False
        if len(nickname) < 2:
            await send("❌ Nicknames must be at least 2 characters long.")
            return False
        import re
        if re.search(r'[^\w가-힣\s]', nickname):
            await send("❌ You can't use emoticons and special characters in nicknames.")
            return False
        bad_words = ["fuck", "shit","Sex","buddy","bitch","asshole","ass","agot"]
        if any(bad in nickname.lower() for bad in bad_words):
            await send("❌ Inappropriate nickname.")
            return False
        return True

    async def send_reaction_message(self, channel_id: int, text: str, emoji: str = None):
        """특정 채널에 리액션 메시지를 보냅니다."""
        try:
            channel = self.get_channel(channel_id)
            if channel:
                msg = await channel.send(text)
                if emoji:
                    await msg.add_reaction(emoji)
            else:
                print(f"[ERROR] Channel with ID {channel_id} not found for bot {self.character_name}.")
        except Exception as e:
            print(f"[ERROR] Failed to send reaction message in {self.character_name}: {e}")

    def start_story_mode(self, user_id, channel_id, character_name):
        """스토리 모드를 시작합니다."""
        self.story_mode_users[user_id] = {
            "channel_id": channel_id,
            "character_name": character_name
        }
        start_story_stage(user_id, channel_id, character_name, self.db.get_user_nickname(user_id, character_name))
        print(f"[스토리 모드] User {user_id} started story mode with {character_name} in channel {channel_id}")

    def is_in_story_mode(self, user_id):
        """사용자가 스토리 모드에 있는지 확인합니다."""
        return user_id in self.story_mode_users

    def end_story_mode(self, user_id):
        """스토리 모드를 종료합니다."""
        if user_id in self.story_mode_users:
            del self.story_mode_users[user_id]
            print(f"[스토리 모드] User {user_id} ended story mode with {self.character_name}")

    async def check_and_send_greeting(self, message, user_id: int, character: str):
        """첫 대화인지 확인하고 호감도 레벨별 인사 메시지를 보냅니다."""
        try:
            # 오늘 첫 대화인지 확인 (UTC 기준)
            today = datetime.utcnow().date()
            recent_messages = self.db.get_user_recent_messages(user_id, character, 1)
            
            if not recent_messages:
                # 첫 대화인 경우 호감도 레벨별 인사 메시지 전송
                await self.send_affinity_greeting(message, user_id, character)
        except Exception as e:
            print(f"[ERROR] check_and_send_greeting: {e}")

    async def send_affinity_greeting(self, message, user_id: int, character: str):
        """호감도 레벨에 따른 인사 메시지를 전송합니다."""
        try:
            from config import CHARACTER_AFFINITY_GREETINGS
            from utils import get_affinity_grade
            
            # 호감도 정보 가져오기
            affinity_info = self.db.get_affinity(user_id, character)
            if not affinity_info:
                # 호감도 정보가 없으면 Rookie로 설정
                affinity_grade = "Rookie"
            else:
                affinity_grade = get_affinity_grade(affinity_info['emotion_score'])
            
            # 닉네임 가져오기
            nickname = self.db.get_user_nickname(user_id, character)
            if not nickname:
                nickname = message.author.display_name
            
            # 호감도 레벨별 인사 메시지 가져오기
            greeting_template = CHARACTER_AFFINITY_GREETINGS.get(character, {}).get(affinity_grade, "Hello!")
            
            # 닉네임 치환
            greeting_message = greeting_template.format(nickname=nickname)
            
            # 인사 메시지 전송
            await message.channel.send(greeting_message)
            
        except Exception as e:
            print(f"[ERROR] send_affinity_greeting: {e}")

    async def send_affinity_notification(self, channel, character_name, affinity_level):
        """호감도 달성 시 알림 메시지를 보냅니다."""
        try:
            # CloudFlare 이미지 URL 가져오기
            from config import CLOUDFLARE_IMAGE_BASE_URL
            
            if affinity_level == 20:
                embed = discord.Embed(
                    title="🎭 Roleplay Mode Unlocked!",
                    description="Congratulations! Roleplay mode is now available! Use /roleplay to enjoy various roleplay modes with your character!",
                    color=discord.Color.purple()
                )
                embed.set_thumbnail(url=f"{CLOUDFLARE_IMAGE_BASE_URL}/{character_name.lower()}_profile.png")
                embed.add_field(
                    name="What's New",
                    value="• Interactive roleplay scenarios\n• Character-specific personalities\n• Enhanced conversation depth",
                    inline=False
                )
                embed.set_footer(text="Keep building your bond to unlock more features!")
                
            elif affinity_level == 50:
                embed = discord.Embed(
                    title="📖 Story Mode Unlocked!",
                    description="Congratulations! Story mode is now available! Use /story to discover various hidden stories of your character!",
                    color=discord.Color.gold()
                )
                embed.set_thumbnail(url=f"{CLOUDFLARE_IMAGE_BASE_URL}/{character_name.lower()}_profile.png")
                embed.add_field(
                    name="What's New",
                    value="• Character backstory chapters\n• Interactive story choices\n• Exclusive story rewards",
                    inline=False
                )
                embed.set_footer(text="Your bond has grown strong enough for deeper stories!")
            
            await channel.send(embed=embed)
            
        except Exception as e:
            print(f"Error sending affinity notification: {e}")

    async def check_and_send_affinity_notifications(self, message, character, user_id, prev_score, new_score):
        """호감도 달성 시 알림을 보냅니다."""
        try:
            # 20 달성 체크
            if prev_score < 20 <= new_score:
                if not self.db.check_affinity_notification_sent(user_id, character, 20):
                    await self.send_affinity_notification(message.channel, character, 20)
                    self.db.mark_affinity_notification_sent(user_id, character, 20)
            
            # 50 달성 체크
            if prev_score < 50 <= new_score:
                if not self.db.check_affinity_notification_sent(user_id, character, 50):
                    await self.send_affinity_notification(message.channel, character, 50)
                    self.db.mark_affinity_notification_sent(user_id, character, 50)
                    
        except Exception as e:
            print(f"Error sending affinity notifications: {e}")
            import traceback
            traceback.print_exc()

async def run_all_bots():
    # Import here to avoid circular import
    from bot_selector import BotSelector
    
    db = DatabaseManager()
    character_bots = {}

    # Initialize character bots
    for char_name in CHARACTER_INFO.keys():
        character_bots[char_name] = CharacterBot(char_name, db)

    # Initialize selector bot
    selector_bot = BotSelector()
    selector_bot.character_bots = character_bots

    try:
        print("Starting bot initialization...")
        tasks = []

        # Start selector bot
        tasks.append(run_bot(selector_bot, TOKEN, "Selector"))

        # Start character bots
        for name, bot in character_bots.items():
            token = globals()[f"{name.upper()}_TOKEN"]
            tasks.append(run_bot(bot, token, name))

        # Wait for all bots to start
        await asyncio.gather(*tasks)
        print("All bots started successfully!")

        # Keep the program running
        while True:
            await asyncio.sleep(1)

    except Exception as e:
        print(f"Fatal error in run_all_bots: {e}")
        raise e
    finally:
        # Cleanup in case of error
        if 'selector_bot' in locals():
            await selector_bot.close()
        for bot in character_bots.values():
            await bot.close()

async def run_bot(bot, token, name):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"Starting {name} bot...")
            await bot.start(token)
            print(f"{name} bot started successfully!")
            return
        except Exception as e:
            print(f"Error starting {name} (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in 5 seconds...")
                await asyncio.sleep(5)
            else:
                print(f"Max retries reached. {name} failed to start.")
                raise

print(f"[DEBUG] CharacterBot type:", type(CharacterBot))
print(f"[DEBUG] dir(CharacterBot):", dir(CharacterBot))

class CardClaimButton(discord.ui.Button):
    def __init__(self, user_id: int, milestone: int, character_name: str, db):
        super().__init__(
            label="Claim",
            style=discord.ButtonStyle.green,
            custom_id=f"claim_card_{user_id}_{milestone}"
        )
        self.user_id = user_id
        self.milestone = milestone
        self.character_name = character_name
        self.db = db

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This button can only be clicked by the designated user.", ephemeral=True)
            return

        try:
            # 카드 추가
            success = self.db.add_user_card(self.user_id, self.character_name, self.milestone)

            if success:
                embed = discord.Embed(
                    title="🎉 Card Claimed!",
                    description=f"You have claimed the {self.character_name} {self.milestone} conversation milestone card.\nUse `/info` to check your cards!",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                self.disabled = True
                await interaction.message.edit(view=self)
            else:
                await interaction.response.send_message("You have already claimed this card.", ephemeral=True)
        except Exception as e:
            print(f"Error Please try again later: {e}")
            await interaction.response.send_message("An error occurred while claiming the card.", ephemeral=True)

class CardClaimView(discord.ui.View):
    def __init__(self, user_id, character_name, card_id, db):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.character_name = character_name
        self.card_id = card_id.upper()
        self.db = db

    @discord.ui.button(label="Claim Card", style=discord.ButtonStyle.primary, emoji="🎴")
    async def claim_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This button can only be used by the user who achieved the milestone.", ephemeral=True)
            return

        try:
            # 먼저 즉시 응답하여 Discord 타임아웃 방지
            await interaction.response.defer(ephemeral=True)
            
            # 실제로 카드를 데이터베이스에 추가
            success = self.db.add_user_card(self.user_id, self.character_name, self.card_id)
            
            if success:
                # 카드 정보 가져오기
                from config import get_card_info_by_id
                card_info = get_card_info_by_id(self.character_name, self.card_id)
                
                # 새로운 임베드 생성 (이미지 포함)
                embed = discord.Embed(
                    title="🎉 Card Claimed Successfully!",
                    description=f"You received **{card_info.get('name', self.card_id)}** ({card_info.get('tier', 'Unknown')} tier)!",
                    color=discord.Color.gold()
                )
                
                # 카드 이미지 설정
                if card_info.get('image_url'):
                    print(f"[DEBUG] CardClaimView - 카드 이미지 URL 설정: {card_info['image_url']}")
                    embed.set_image(url=card_info['image_url'])
                else:
                    print(f"[DEBUG] CardClaimView - 카드 이미지 URL 없음: {card_info}")
                
                embed.add_field(
                    name="Card Details",
                    value=f"**Tier:** {card_info.get('tier', 'Unknown')}\n**Character:** {self.character_name}\n**Card ID:** {self.card_id}",
                    inline=False
                )
                
                button.disabled = True
                button.label = "✅ Claimed"
                await interaction.message.edit(embed=embed, view=self)
                await interaction.followup.send("Card successfully claimed! Check your /info.", ephemeral=True)
            else:
                # 이미 카드를 가지고 있는 경우
                await interaction.followup.send("You have already claimed this card.", ephemeral=True)
                
        except Exception as e:
            print(f"Error in claim_card: {e}")
            # 에러가 발생해도 카드가 저장되었을 수 있으므로 확인
            if self.db.has_user_card(self.user_id, self.character_name, self.card_id):
                button.disabled = True
                button.label = "✅ Claimed"
                await interaction.message.edit(view=self)
                await interaction.followup.send("Card successfully claimed! Check your /info.", ephemeral=True)
            else:
                await interaction.followup.send("An error occurred while claiming the card. Please try again.", ephemeral=True)

def get_card_claim_embed_and_view(user_id, character_name, card_id, db):
    from config import get_card_info_by_id
    card_info = get_card_info_by_id(character_name, card_id)
    embed = discord.Embed(
        title=f" {character_name} {card_id} Card",
        description=card_info.get("description", ""),
        color=discord.Color.gold()
    )
    # 이미지 URL 설정 - get_card_info_by_id에서 이미 올바른 image_url을 설정함
    if card_info.get("image_url"):
        embed.set_image(url=card_info["image_url"])
    view = CardClaimView(user_id, character_name, card_id, db)
    return embed, view

def get_card_tier_by_affinity(affinity):
    """호감도에 따른 카드 티어 확률 반환"""
    if affinity < 10:  # Rookie
        return [('C', 1.0)]
    elif affinity < 30:  # Iron
        return [('C', 0.8), ('B', 0.2)]
    elif affinity < 50:  # Bronze
        return [('B', 0.3), ('C', 0.7)]
    elif affinity < 100:  # Silver
        return [('A', 0.2), ('B', 0.3), ('C', 0.5)]
    else:  # Gold+
        return [('S', 0.1), ('A', 0.2), ('B', 0.3), ('C', 0.4)]

def choose_card_tier(affinity):
    """호감도에 따라 카드 티어 선택"""
    tier_probs = get_card_tier_by_affinity(affinity)
    tiers, probs = zip(*tier_probs)
    return random.choices(tiers, weights=probs, k=1)[0]


def get_random_card_id(character_name, tier):
    from config import CHARACTER_CARD_INFO
    card_ids = [cid for cid in CHARACTER_CARD_INFO[character_name] if cid.startswith(tier)]
    return random.choice(card_ids)

def get_affinity_grade(emotion_score: int) -> str:
    """친밀도 점수에 따라 등급 이름을 반환합니다."""
    # 점수가 높은 등급부터 확인하기 위해 역순으로 정렬
    sorted_levels = sorted(AFFINITY_LEVELS.items(), key=lambda item: item[1], reverse=True)
    for grade, threshold in sorted_levels:
        if emotion_score >= threshold:
            return grade
    return "Rookie" # 기본 등급

def check_user_channels(user_id, all_channels):
    story_channels = [ch for ch in all_channels if "story" in ch.name and str(user_id) in ch.name]
    normal_channels = [ch for ch in all_channels if str(user_id) in ch.name and "story" not in ch.name]
    if len(story_channels) > 0 and len(normal_channels) > 0:
        # 안내 메시지 출력
        return "You are currently using both story mode and 1:1 chat. Please use only one channel at a time."
    return None

def get_channel_mode(channel_name: str) -> str:
    if "story" in channel_name.lower():
        return "story"
    return "normal"

class NicknameInputButton(discord.ui.Button):
    def __init__(self, bot, user_id, character):
        super().__init__(
            label="Enter Nickname",
            style=discord.ButtonStyle.primary,
            custom_id="nickname_input_global"
        )
        self.bot = bot
        self.user_id = int(user_id)  # 항상 int로 저장
        self.character = character

    async def callback(self, interaction: discord.Interaction):
        print(f"[DEBUG] NicknameInputButton.callback called (user_id={self.user_id}, character={self.character}, interaction.user.id={interaction.user.id})")
        try:
            if int(interaction.user.id) != self.user_id:
                await interaction.response.send_message("Only you can set your nickname.", ephemeral=True)
                return
            print(f"[DEBUG] NicknameInputModal 생성 직전 (user_id={self.user_id}, character={self.character})")
            modal = NicknameInputModal(self.bot, self.user_id, self.character)
            await interaction.response.send_modal(modal)
        except Exception as e:
            print(f"[ERROR] NicknameInputButton.callback error: {e}")
            import traceback
            print(traceback.format_exc())
            if not interaction.response.is_done():
                await interaction.response.send_message("Server error occurred.", ephemeral=True)

class NicknameInputView(discord.ui.View):
    def __init__(self, bot, user_id, character):
        super().__init__(timeout=None)
        self.bot = bot
        self.user_id = user_id
        self.character = character
        self.add_item(NicknameInputButton(bot, user_id, character))

class NicknameInputModal(discord.ui.Modal, title="Enter Nickname"):
    nickname = discord.ui.TextInput(
        label="Nickname (2-15 chars, no emoticons)",
        min_length=2,
        max_length=15,
        required=True
    )
    def __init__(self, bot, user_id, character):
        super().__init__()
        self.bot = bot
        self.user_id = user_id
        self.character = character

    async def on_submit(self, interaction: discord.Interaction):
        try:
            print(f"[DEBUG] NicknameInputModal.on_submit called: user_id={interaction.user.id}, nickname={self.nickname.value}, character={self.character}")
            nickname = self.nickname.value.strip()
            valid = await self.bot.validate_nickname(nickname, interaction)
            if not valid:
                # validate_nickname에서 이미 interaction에 응답했으므로 여기서는 아무것도 하지 않고 return만 합니다.
                return

            # 닉네임 저장
            self.bot.db.set_user_nickname(self.user_id, self.character, nickname)
            self.bot.db.update_user_conversation_state(
                self.user_id, self.character,
                has_nickname=True,
                language_set=True,
                message_count=0
            )

            # 환영 메시지 전송
            welcome_embed = discord.Embed(
                title="🎉 Start a conversation!",
                description=f"Hi {nickname}, you have been connected to Zerolink {self.character}. Let's have a nice conversation!",
                color=discord.Color.gold()
            )
            await interaction.response.send_message(embed=welcome_embed)
        except Exception as e:
            print(f"[ERROR] NicknameInputModal.on_submit error: {e}")
            import traceback
            print(traceback.format_exc())
            if not interaction.response.is_done():
                await interaction.response.send_message("A server error occurred.", ephemeral=True)

def is_similar(a, b):
    return SequenceMatcher(None, a, b).ratio() > 0.85

def is_spam(user_id, message, now, user_message_buffers):
    # 1. Short interval repeated/similar message
    recent = [msg for msg, ts in user_message_buffers.get(user_id, []) if now - ts < 5]
    if any(is_similar(message, msg) for msg in recent):
        return True, "Spam detected: Repeated or similar message in a short time interval."
    # 2. Same sentence/word repeated 5+ times
    same_count = sum(1 for msg, _ in user_message_buffers.get(user_id, [])[-10:] if message == msg)
    if same_count >= 5:
        return True, "Spam detected: Same message repeated 5 or more times."
    # 3. Short message (1~5 chars)
    if 1 <= len(message.strip()) <= 5:
        return True, "Spam detected: Message too short (1-5 characters)."
    # 4. Emoji/special char repeated 5+ times
    emoji_pattern = re.compile("[\U00010000-\U0010ffff]", flags=re.UNICODE)
    emoji_msgs = [msg for msg, _ in user_message_buffers.get(user_id, [])[-10:] if emoji_pattern.fullmatch(msg.strip())]
    if len(emoji_msgs) >= 5:
        return True, "Spam detected: Emoji or special character repeated 5 or more times."
    return False, ""

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_all_bots())