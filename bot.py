import discord
from discord.ext import commands, tasks
import os
from typing import Optional, Dict
import asyncio
import random
import sqlite3
import requests
from discord import app_commands

# 캐릭터 이미지 경로
CLOUDFLARE_IMAGE_BASE_URL = "https://imagedelivery.net/ZQ-g2Ke3i84UnMdCSDAkmw"
CHARACTER_IMAGES = {
    "kagari": f"{CLOUDFLARE_IMAGE_BASE_URL}/kagari/public",
    "eros": f"{CLOUDFLARE_IMAGE_BASE_URL}/eros/public",
    "elysia": f"{CLOUDFLARE_IMAGE_BASE_URL}/elysia/public"
}

# OpenAI API 키 로드
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

class CharacterBot(commands.Bot):
    # Suppress error on the User attribute being None since it fills up later
    user: discord.ClientUser
    def __init__(self, character_name: str):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )

        # Active channels for auto-questions
        self.active_channels: Dict[int, bool] = {}
        self.question_interval = 300  # 5 minutes
        self.character_name = character_name
        self.image_url = CHARACTER_IMAGES.get(self.character_name.lower())

    async def setup_hook(self):
        """Initial setup after the bot is ready"""
        self.auto_question.start()
        await self.tree.sync()

    @tasks.loop(seconds=300)
    async def auto_question(self):
        """Automatically send questions to active channels"""
        for channel_id, is_active in self.active_channels.items():
            if is_active:
                channel = self.get_channel(channel_id)
                if channel:
                    questions = [
                        "오늘 하루는 어땠나요?",
                        "지금 기분이 어떠신가요?",
                        "가장 좋아하는 음식은 무엇인가요?",
                        "최근에 본 영화나 드라마가 있나요?",
                        "오늘 가장 기억에 남는 순간은 무엇인가요?"
                    ]
                    question = random.choice(questions)
                    await channel.send(question)

    @commands.command()
    async def start(self, ctx):
        """Start auto-questions in the channel"""
        self.active_channels[ctx.channel.id] = True
        await ctx.send("자동 질문 기능이 활성화되었습니다!")

    @commands.command()
    async def stop(self, ctx):
        """Stop auto-questions in the channel"""
        self.active_channels[ctx.channel.id] = False
        await ctx.send("자동 질문 기능이 비활성화되었습니다!")

    @commands.command()
    async def character(self, ctx):
        """Show character information with image"""
        if self.image_url:
            embed = discord.Embed(title=f"{self.character_name.capitalize()} 캐릭터", color=discord.Color.blue())
            embed.set_image(url=self.image_url)
            await ctx.send(embed=embed)
        else:
            await ctx.send("해당 캐릭터를 찾을 수 없습니다.")
    

    def set_user_language(self, user_id: int, character_name: str, language: str) -> bool:
        """사용자의 특정 캐릭터와의 대화 언어를 설정합니다."""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()

                # conversations 테이블의 language 컬럼 업데이트
                cursor.execute('''
                    UPDATE conversations
                    SET language = ?
                    WHERE user_id = ? AND character_name = ?
                ''', (language, user_id, character_name))

                # user_context 테이블에 언어 설정 저장
                cursor.execute('''
                    INSERT OR REPLACE INTO user_context 
                    (user_id, character_name, last_language, last_interaction)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ''', (user_id, character_name, language))

                conn.commit()
                return True
        except Exception as e:
            print(f"Error setting user language: {e}")
            return False 

    async def callback(self, interaction: discord.Interaction):
        try:
            selected_char = self.values[0]

            # 새로운 채널 생성
            category = discord.utils.get(interaction.guild.categories, name="chatbot")
            if not category:
                try:
                    category = await interaction.guild.create_category("chatbot")
                except Exception as e:
                    print(f"Category creation error: {e}")
                    await interaction.response.send_message(
                        "Please check the bot's permissions..",
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
                channel = await interaction.guild.create_text_channel(
                    name=channel_name,
                    category=category,
                    overwrites=overwrites
                )

                # 채널 생성 성공 메시지 전송
                await interaction.response.send_message(
                    f"{channel.mention}에서 {selected_char}와(과) 대화를 시작하세요!",
                    ephemeral=True
                )

                # 언어 선택 임베드 생성
                embed = discord.Embed(
                    title="🌍 언어 선택 / Language Selection",
                    description="Spot zero 캐릭터와 어떤 언어로 대화하시겠습니까?\nWhich language would you like to chat in?",
                    color=discord.Color.blue()
                )

                embed.add_field(
                    name="사용 가능한 언어 / Available Languages",
                    value="🇰🇷 한국어 (Korean)\n🇺🇸 English\n🇯🇵 日本語 (Japanese)\n🇨🇳 中文 (Chinese)",
                    inline=False
                )

                embed.set_footer(text="원하시는 언어를 선택해주세요 / Please select your preferred language")

                # 선택된 캐릭터 봇에 채널 추가
                selected_bot = self.bot_selector.character_bots.get(selected_char)
                if selected_bot:
                    try:
                        success, message = await selected_bot.add_channel(channel.id, interaction.user.id)

                        if success:
                            await interaction.response.send_message(
                                f"{channel.mention}에서 {selected_char}와(과) 대화를 시작하세요!",
                                ephemeral=True
                            )

                            # 언어 선택 임베드 생성 및 전송
                            embed = discord.Embed(
                                title="🌍 언어 선택 / Language Selection",
                                description="Spot zero 캐릭터와 어떤 언어로 대화하시겠습니까?\nWhich language would you like to chat in?",
                                color=discord.Color.blue()
                            )

                            embed.add_field(
                                name="사용 가능한 언어 / Available Languages",
                                value="🇰🇷 한국어 (Korean)\n🇺🇸 English\n🇯🇵 日本語 (Japanese)\n🇨🇳 中文 (Chinese)",
                                inline=False
                            )

                            embed.set_footer(text="원하시는 언어를 선택해주세요 / Please select your preferred language")

                            # DatabaseManager 인스턴스 확인
                            if not hasattr(selected_bot, 'db'):
                                selected_bot.db = DatabaseManager()  # DatabaseManager 인스턴스 생성

                            # 언어 선택 뷰 생성 및 전송
                            view = LanguageSelectView(selected_bot.db, interaction.user.id, selected_char, timeout=None)
                            await channel.send(embed=embed, view=view)

                    except Exception as e:
                        print(f"Error in channel creation: {e}")
                        await interaction.followup.send(
                            "채널 생성 중 오류가 발생했습니다. 다시 시도해주세요.",
                            ephemeral=True
                        )

            except Exception as e:
                print(f"Error in channel creation: {e}")
                await interaction.followup.send(
                    "채널 생성 중 오류가 발생했습니다. 다시 시도해주세요.",
                    ephemeral=True
                )

        except Exception as e:
            print(f"CharacterSelect error: {e}")
            await interaction.response.send_message(
                "오류가 발생했습니다. 다시 시도해주세요.",
                ephemeral=True
            ) 