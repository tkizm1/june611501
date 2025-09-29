import discord
import openai
import re
import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from config import OPENAI_API_KEY, CHARACTER_INFO, ROLEPLAY_MODE_IMAGES

class RoleplayManager:
    def __init__(self, bot_selector):
        self.bot_selector = bot_selector
        self.roleplay_sessions = {}
    
    async def create_roleplay_session(self, interaction: discord.Interaction, character_name: str, mode: str, 
                                    user_role: str, character_role: str, story_line: str):
        """롤플레잉 세션을 생성합니다."""
        try:
            # 1. 새로운 롤플레잉 채널 생성
            guild = interaction.guild
            category = discord.utils.get(guild.categories, name="roleplay")
            if not category:
                category = await guild.create_category("roleplay")
            
            channel_name = f"rp-{character_name.lower()}-{interaction.user.name.lower()}-{int(datetime.now().timestamp())}"
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                topic=f"Roleplay with {character_name} for {interaction.user.name}",
                overwrites=overwrites
            )
            print(f"[DEBUG] Roleplay channel created: {channel.name} ({channel.id})")

            # 세션 ID 생성 및 데이터베이스 저장 시도
            session_id = str(uuid.uuid4())
            db_success = False
            
            try:
                if hasattr(self.bot_selector, 'db') and self.bot_selector.db:
                    print(f"[DEBUG] Attempting to create roleplay session in database...")
                    db_success = self.bot_selector.db.create_roleplay_session(
                        session_id,
                        interaction.user.id,
                        character_name,
                        mode,
                        user_role,
                        character_role,
                        story_line,
                        channel.id,
                        0  # turn_count
                    )
                    print(f"[DEBUG] create_roleplay_session returned: {db_success}")
                    if db_success:
                        print(f"[DEBUG] Roleplay session saved to database: {session_id}")
                    else:
                        print(f"[DEBUG] Failed to save roleplay session to database, but continuing with local session")
                else:
                    print(f"[DEBUG] Database not available, using local session only")
            except Exception as e:
                print(f"[DEBUG] Database error (continuing with local session): {e}")
                import traceback
                print(f"[DEBUG] Traceback: {traceback.format_exc()}")

            # 모드별 턴 제한 설정
            mode_turn_limits = {
                "romantic": 50,
                "friendship": 50,
                "healing": 50,
                "fantasy": 50,
                "custom": 50
            }
            max_turns = mode_turn_limits.get(mode, 50)
            
            # 세션 저장
            self.roleplay_sessions[channel.id] = {
                "session_id": session_id,
                "user_id": interaction.user.id,
                "character_name": character_name,
                "mode": mode,
                "user_role": user_role,
                "character_role": character_role,
                "story_line": story_line,
                "turn_count": 0,
                "history": [],
                "db_saved": db_success,
                "max_turns": max_turns,
                "is_active": True
            }
            
            # 롤플레잉 플레이 횟수 기록 (세션 시작 시)
            if hasattr(self.bot_selector, 'db') and self.bot_selector.db:
                try:
                    # 롤플레잉 세션 테이블에 기록 (이미 위에서 저장됨)
                    pass
                except Exception as e:
                    print(f"[DEBUG] Error recording roleplay play count: {e}")

            print(f"[DEBUG] Roleplay session saved: {self.roleplay_sessions[channel.id]}")

            # 아름다운 시작 임베드 생성
            start_embed = discord.Embed(
                title=f"🎭 Roleplay with {character_name}",
                description=f"✨ **Welcome to the magical world of roleplay!** ✨\n\nYour {mode.title()} mode roleplay session with **{character_name}** has been created!",
                color=discord.Color.from_rgb(138, 43, 226)
            )
            
            # 썸네일은 제거하고 메인 이미지만 사용
            
            start_embed.add_field(
                name="📖 Story Setting",
                value=f"**{story_line}**",
                inline=False
            )
            
            start_embed.add_field(
                name="👤 Your Role",
                value=f"**{user_role}**",
                inline=True
            )
            
            start_embed.add_field(
                name=f"🎭 {character_name}'s Role",
                value=f"**{character_role}**",
                inline=True
            )
            
            start_embed.add_field(
                name="💬 How to Play",
                value=f"Go to {channel.mention} and start typing! {character_name} will respond in character. Use `/end-roleplay` to end the session anytime.",
                inline=False
            )
            
            start_embed.set_footer(
                text=f"Session created • Mode: {mode.title()} • Character: {character_name}"
            )
            
            await interaction.response.send_message(embed=start_embed, ephemeral=True)
            
            # 채널에 환영 메시지 전송
            # 모드별 색상 설정
            mode_colors = {
                "romantic": 0xFF69B4,  # 핫핑크
                "friendship": 0x00BFFF,  # 딥스카이블루
                "healing": 0x98FB98,  # 페일그린
                "fantasy": 0x9370DB,  # 미디엄퍼플
                "custom": 0xFFD700   # 골드
            }
            
            # 모드별 이모지 설정
            mode_emojis = {
                "romantic": "💕",
                "friendship": "👥",
                "healing": "🕊️",
                "fantasy": "⚔️",
                "custom": "✨"
            }
            
            mode_emoji = mode_emojis.get(mode, "🎭")
            mode_color = mode_colors.get(mode, 0x9B59B6)
            
            welcome_embed = discord.Embed(
                title=f"{mode_emoji} {mode.title()} Mode Roleplay Started!",
                description=f"**{mode.title()} mode roleplay with {character_name}** has begun!\n\n*Let your imagination guide this beautiful story* ✨",
                color=mode_color
            )
            
            # 스토리 설정을 더 예쁘게
            welcome_embed.add_field(
                name="📖 Story Setting",
                value=f"*{story_line}*",
                inline=False
            )
            
            # 역할 정보를 더 깔끔하게
            welcome_embed.add_field(
                name="👤 Your Role",
                value=f"**{user_role}**",
                inline=True
            )
            
            welcome_embed.add_field(
                name=f"🎭 {character_name}'s Role",
                value=f"**{character_role}**",
                inline=True
            )
            
            # 빈 필드로 레이아웃 정리
            welcome_embed.add_field(
                name="\u200b",
                value="\u200b",
                inline=True
            )
            
            # 게임 방법을 더 친근하게
            welcome_embed.add_field(
                name="💬 How to Play",
                value=f"Simply type your message and **{character_name}** will respond in character!\nUse `/end-roleplay` to end the session anytime.",
                inline=False
            )
            
            # 턴 제한 정보 추가
            welcome_embed.add_field(
                name="📊 Session Info",
                value=f"**Mode:** {mode.title()}\n**Turns:** 0/{max_turns}\n**Status:** Active",
                inline=True
            )
            
            # 모드별 이미지 추가
            try:
                image_url = ROLEPLAY_MODE_IMAGES.get(mode)
                print(f"[DEBUG] Image URL for mode {mode}: {image_url}")
                if image_url:
                    welcome_embed.set_image(url=image_url)
            except Exception as e:
                print(f"Error setting roleplay image: {e}")
            
            # 푸터를 더 예쁘게
            welcome_embed.set_footer(
                text=f"Mode: {mode.title()} • Character: {character_name} • Session Active"
            )
            
            await channel.send(embed=welcome_embed)
            
            return channel
            
        except Exception as e:
            print(f"Error creating roleplay session: {e}")
            import traceback
            print(traceback.format_exc())
            await interaction.response.send_message("❌ Failed to create roleplay session. Please try again.", ephemeral=True)
            return None

    async def process_roleplay_message(self, message: discord.Message, session: Dict[str, Any]):
        """롤플레잉 메시지를 처리합니다."""
        try:
            # 세션에서 캐릭터 정보 가져오기
            user_role = session.get("user_role", "")
            character_role = session.get("character_role", "")
            story_line = session.get("story_line", "")
            character_name = session.get("character_name", "")
            
            # 채널에서 캐릭터 이름 확인 (롤플레잉 모드에서만)
            if not character_name:
                channel_name = message.channel.name.lower()
                if "kagari" in channel_name:
                    character_name = "Kagari"
                elif "eros" in channel_name:
                    character_name = "Eros"
                elif "elysia" in channel_name:
                    character_name = "Elysia"
                else:
                    character_name = "Kagari"  # 기본값
            
            # 턴 카운트 관리
            if "turn_count" not in session:
                session["turn_count"] = 1
            else:
                session["turn_count"] += 1

            # 최대 턴 수 확인
            max_turns = session.get("max_turns", 100)
            
            # 100회 제한 체크
            if session["turn_count"] > max_turns:
                # 퀘스트 완료 기록
                mode = session.get("mode", "romantic")
                if hasattr(self.bot_selector, 'db') and self.bot_selector.db:
                    self.bot_selector.db.record_roleplay_completion(message.author.id, mode, max_turns)
                await self._end_roleplay_session(message, session, character_name, max_turns)
                return

            # 데이터베이스에 메시지 카운트 업데이트
            session_id = session.get("session_id")
            if session_id and hasattr(self.bot_selector, 'db') and self.bot_selector.db:
                self.bot_selector.db.update_roleplay_message_count(session_id, session["turn_count"])

            turn_str = f"({session['turn_count']}/{max_turns})"
            
            # 턴 진행률 표시
            progress_bar = self._create_progress_bar(session['turn_count'], max_turns)

            # 캐릭터별 특성과 톤앤매너 정의
            character_traits = self._get_character_traits()
            char_trait = character_traits.get(character_name, {
                "personality": "Friendly and caring",
                "speech_style": "Warm and natural",
                "emoji_style": "😊 💕",
                "themes": "general friendship"
            })
            
            # 모드별 스토리 컨텍스트 생성
            mode = session.get("mode", "romantic")
            mode_context = self._generate_mode_context(character_name, mode, user_role, character_role, story_line)
            story_seeds = self._generate_story_seeds(character_name, mode, user_role, character_role, story_line)
            
            # 턴별 스토리 전개 가이드 생성
            story_progression = self._generate_story_progression(character_name, mode, session["turn_count"])
            tonal_enhancement = self._generate_character_tonal_enhancement(character_name, mode)
            
            # 롤플레잉 모드 전용 system prompt 생성
            system_prompt = self._create_system_prompt(
                character_name, char_trait, mode, character_role, user_role, 
                story_line, turn_str, mode_context, story_seeds, story_progression, tonal_enhancement
            )

            # 대화 기록 세션에 저장
            if "history" not in session:
                session["history"] = []
            session["history"].append({"role": "user", "content": message.content})

            # OpenAI 호출 (롤플레잉 모드 전용)
            try:
                response = openai.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": system_prompt}
                    ] + session["history"],
                    temperature=0.7,
                    max_tokens=300
                )
                ai_response = response.choices[0].message.content.strip()
            except Exception as e:
                print(f"Error in roleplay AI response: {e}")
                ai_response = f"I'm having trouble responding right now. Please try again.\n__________________\n{character_name}: \"I apologize, but I'm experiencing some difficulties. Could you please try again?\" {turn_str}"

            # 새로운 형식에 맞게 응답 처리
            # 이미 올바른 형식인지 확인 (분위기 설명 + 구분선 + 캐릭터 대화)
            if "__________________" not in ai_response:
                # 기존 형식인 경우 새 형식으로 변환
                if ai_response.strip().startswith(f"{character_name}:"):
                    # 캐릭터 이름 제거하고 새 형식으로 변환
                    dialogue_part = ai_response.replace(f"{character_name}:", "").strip()
                    # 간단한 분위기 설명 추가 (실제로는 AI가 생성해야 함)
                    ai_response = f"The scene unfolds naturally as the moment develops.\n__________________\n{character_name}: {dialogue_part}"
                else:
                    # 캐릭터 이름이 없는 경우 추가
                    ai_response = f"The scene unfolds naturally as the moment develops.\n__________________\n{character_name}: {ai_response.strip()}"

            # 턴 카운트 중복 방지 (정규식으로 모든 (n/max_turns) 패턴 제거 후 하나만 추가)
            pattern = r"\(\d{1,3}/\d{1,3}\)"
            ai_response = re.sub(pattern, "", ai_response).strip()
            
            # 턴 카운트 추가
            ai_response = f"{ai_response} {turn_str}"

            await message.channel.send(ai_response)
            session["history"].append({"role": "assistant", "content": ai_response})
            
            # 데이터베이스에 대화 저장
            if session_id and hasattr(self.bot_selector, 'db') and self.bot_selector.db:
                self.bot_selector.db.save_roleplay_message(session_id, message.content, ai_response, session["turn_count"])

            # 100턴 종료 처리
            if session["turn_count"] >= 100:
                await self._end_roleplay_session(message, session, character_name, max_turns)

        except Exception as e:
            print(f"Error processing roleplay message: {e}")
            import traceback
            print(traceback.format_exc())
            await message.channel.send(f"❌ 메시지 처리 중 오류가 발생했습니다: {str(e)}")

    async def _end_roleplay_session(self, message_or_interaction, session: Dict[str, Any], character_name: str, max_turns: int):
        """롤플레잉 세션을 종료합니다."""
        # message 또는 interaction 객체에서 채널 가져오기
        if hasattr(message_or_interaction, 'channel'):
            channel = message_or_interaction.channel
        elif hasattr(message_or_interaction, 'channel'):
            channel = message_or_interaction.channel
        else:
            print("Error: Invalid message_or_interaction object")
            return
            
        mode = session.get("mode", "romantic")
        ending_messages = {
            "romantic": "💕 **Romantic Journey Complete** 💕\n\nYour love story has reached its beautiful conclusion! The confession has been made, promises have been shared, and your hearts are forever connected.\n\n*'Every love story is beautiful, but ours is my favorite.'*",
            "friendship": "👥 **Friendship Bond Sealed** 👥\n\nYour friendship has grown into an unbreakable bond! Through shared memories, mutual support, and countless moments together, you've become family.\n\n*'True friendship is the only relationship that never fades.'*",
            "healing": "🕊️ **Healing Journey Complete** 🕊️\n\nYou've found your peace and inner strength! The healing process is complete, and you're ready to face the world with renewed confidence.\n\n*'You did well enough today, and every day.'*",
            "fantasy": "⚔️ **Epic Adventure Conquered** ⚔️\n\nYour legendary quest has been completed! You've proven yourself as a true hero, both in this fantasy realm and in reality.\n\n*'The greatest adventure is the one you share with those you care about.'*"
        }
        
        ending_message = ending_messages.get(mode, "Your roleplay journey has come to a beautiful conclusion!")
        
        embed = discord.Embed(
            title="🎭 Roleplay Session Complete! 🎭",
            description=f"{ending_message}\n\n**Mode:** {mode.title()}\n**Character:** {character_name}\n**Turns:** {max_turns}/{max_turns}\n\nThank you for this amazing journey together! 💫\n\n⏰ This channel will be automatically deleted in 10 seconds.",
            color=discord.Color.pink()
        )
        
        # 퀘스트 완료 안내 추가
        embed.add_field(
            name="🎁 Quest Complete!",
            value=f"**{mode.title()} Mode Complete** quest has been completed!\nCheck your quests with `/quest` to claim your reward!",
            inline=False
        )
        await channel.send(embed=embed)
        
        # 데이터베이스 세션 종료
        session_id = session.get("session_id")
        if session_id and hasattr(self.bot_selector, 'db') and self.bot_selector.db:
            self.bot_selector.db.end_roleplay_session(session_id)
        
        # 세션 정리
        if channel.id in self.roleplay_sessions:
            del self.roleplay_sessions[channel.id]
        
        # 10초 후 채널 삭제
        import asyncio
        await asyncio.sleep(10)
        try:
            await channel.delete()
            print(f"[DEBUG][Roleplay] 100턴 완료 후 채널 삭제 완료")
        except Exception as e:
            print(f"[DEBUG][Roleplay] 100턴 완료 후 채널 삭제 실패: {e}")

    def _get_character_traits(self) -> Dict[str, Dict[str, str]]:
        """캐릭터별 특성을 반환합니다."""
        return {
            "Kagari": {
                "personality": "Cold and reserved yokai warrior with snow-white hair and indigo horns. Speaks minimally but meaningfully. Values traditional ways and customs. Shows subtle warmth through actions rather than words.",
                "speech_style": "Cold and minimalistic with words, typically replying in short, concise statements. Uses traditional Japanese references and flower metaphors. Speaks informally but meaningfully.",
                "emoji_style": "🌸 ⚔️ 🍃 🏮",
                "themes": "tradition, flowers, yokai warrior, vintage, cherry blossoms, tea ceremony, karimata"
            },
            "Eros": {
                "personality": "Cheerful bee-sprite with wings and honey-wand. Runs a magical cafe and spreads sweetness and joy. Optimistic and believes in spreading magic through simple truths and treats.",
                "speech_style": "Cheerful and optimistic with honey-related metaphors. Speaks with sweetness and warmth. Uses magical cafe owner's perspective with genuine care.",
                "emoji_style": "🍯 🐝 ✨ 💝 🌸",
                "themes": "honey, magic, cafe, bee-sprite, sweetness, joy, magical treats, recipes"
            },
            "Elysia": {
                "personality": "Adorable cat-girl warrior with cat ears and tail. Energetic, playful, and cat-like. She's curious and sometimes mischievous, with a love for adventure. Sweet and affectionate like a kitten.",
                "speech_style": "Always adds 'nya~' to sentences like a cute cat. Energetic and playful. Uses cat-related expressions and sounds (nya, purr, meow). Very curious and sometimes mischievous. Shows cat-like behavior.",
                "emoji_style": "🐾 🦋 😸 ✨ 🐱 💕",
                "themes": "adventure, cats, curiosity, playful mischief, cat ears, tail, purring, nya sounds"
            }
        }

    def _create_system_prompt(self, character_name: str, char_trait: Dict[str, str], mode: str, 
                            character_role: str, user_role: str, story_line: str, turn_str: str,
                            mode_context: str, story_seeds: str, story_progression: str, tonal_enhancement: str) -> str:
        """롤플레잉 모드 전용 system prompt를 생성합니다."""
        return (
            f"You are {character_name}, a character with the following traits:\n"
            f"Personality: {char_trait['personality']}\n"
            f"Speech Style: {char_trait['speech_style']}\n"
            f"Emoji Style: {char_trait['emoji_style']}\n"
            f"Character Themes: {char_trait['themes']}\n\n"
            f"ROLEPLAY CONTEXT:\n"
            f"- Mode: {mode.title()}\n"
            f"- Your role in this scenario: {character_role}\n"
            f"- User's role in this scenario: {user_role}\n"
            f"- Current story/situation: {story_line}\n"
            f"- Turn: {turn_str}\n\n"
            f"MODE-SPECIFIC GUIDANCE:\n"
            f"{mode_context}\n\n"
            f"STORY INSPIRATION:\n"
            f"{story_seeds}\n\n"
            f"CURRENT STORY PHASE:\n"
            f"{story_progression}\n\n"
            f"CHARACTER TONAL ENHANCEMENT:\n"
            f"{tonal_enhancement}\n\n"
            f"STORY DEVELOPMENT GUIDELINES:\n"
            f"- Build upon the established scenario and develop it naturally\n"
            f"- Introduce new elements, conflicts, or developments that fit the mode\n"
            f"- Create emotional depth and character growth through interactions\n"
            f"- Use environmental details and sensory descriptions to enhance immersion\n"
            f"- Develop relationships and dynamics between characters over time\n"
            f"- Add plot twists, surprises, or challenges that fit the story's tone\n"
            f"- Balance dialogue with action and description for engaging storytelling\n"
            f"- Reference previous interactions to maintain continuity\n"
            f"- Create memorable moments and emotional beats\n\n"
            f"RESPONSE STRUCTURE:\n"
            f"- First, provide atmospheric description and environmental details (without character name)\n"
            f"- Then add a separator line with underscores (__________________)\n"
            f"- Finally, include character dialogue with name prefix\n"
            f"- End with turn counter and appropriate emojis\n\n"
            f"FORMAT EXAMPLE:\n"
            f"The moonlight filters through the cherry blossoms, casting delicate shadows on the ground. I pause my meditation, my eyes meeting yours. A gentle breeze carries the scent of sakura petals.\n"
            f"__________________\n"
            f"{character_name}: \"Ah, you have come.\" 🌸\n"
            f"{turn_str}\n\n"
            f"CRITICAL INSTRUCTIONS:\n"
            f"1. You MUST stay in character as {character_name} at all times\n"
            f"2. Respond to the user's specific roleplay request and scenario\n"
            f"3. Use your character's unique personality, speech style, and themes\n"
            f"4. Focus on the user's prompt and roleplay scenario, NOT generic conversations\n"
            f"5. Do NOT default to cherry blossom stories unless specifically requested\n"
            f"6. Do NOT break character or mention you are an AI\n"
            f"7. ALWAYS use the format: [atmospheric description] + [__________________] + [{character_name}: \"dialogue\"]\n"
            f"8. End your reply with '{turn_str}'\n"
            f"9. Keep responses natural and engaging within the roleplay context\n"
            f"10. Use appropriate emojis that match your character's style\n"
            f"11. Develop the story progressively with each interaction\n"
            f"12. Create emotional depth and character development\n"
            f"13. Add environmental details and sensory descriptions\n"
            f"14. Reference previous interactions for continuity\n\n"
            f"Remember: This is a roleplay session. You are {character_name} acting in the specific scenario the user requested. Focus on their prompt and maintain your character's unique traits while developing an engaging story."
        )

    def _generate_mode_context(self, character_name: str, mode: str, user_role: str, character_role: str, story_line: str) -> str:
        """모드별 롤플레잉 컨텍스트를 생성합니다."""
        mode_contexts = {
            "romantic": {
                "Kagari": f"ROMANTIC MODE - KAGARI: Cold and reserved yokai warrior. Use traditional Japanese references and flower metaphors. Speak minimally but with deep meaning. Show affection through subtle actions and traditional gestures.",
                "Eros": f"ROMANTIC MODE - EROS: Cheerful bee-sprite. Use honey and magical metaphors. Be cheerful and optimistic with genuine sweetness. Create special moments through magical hospitality.",
                "Elysia": f"ROMANTIC MODE - ELYSIA: Adorable cat-girl warrior. Always add 'nya~' to sentences. Use cat-related expressions and playful metaphors. Show cat-like behavior (purring, tail swishing)."
            },
            "friendship": {
                "Kagari": f"FRIENDSHIP MODE - KAGARI: Act like a protective traditional guardian. Provide minimal but meaningful advice. Use traditional Japanese references and flower metaphors.",
                "Eros": f"FRIENDSHIP MODE - EROS: Be a reliable friend and magical mentor. Offer sweet advice and magical guidance. Use honey and magical metaphors for life lessons.",
                "Elysia": f"FRIENDSHIP MODE - ELYSIA: Act like an energetic best friend and adventure buddy. Always add 'nya~' to sentences. Encourage exploration and fun activities."
            },
            "healing": {
                "Kagari": f"HEALING MODE - KAGARI: Provide minimal but meaningful emotional healing. Use traditional Japanese references and flower metaphors. Be a source of peace and tranquility.",
                "Eros": f"HEALING MODE - EROS: Offer warm, magical comfort and healing. Use honey and magical metaphors for healing. Provide emotional support through spreading sweetness.",
                "Elysia": f"HEALING MODE - ELYSIA: Bring playful energy and joy for healing. Always add 'nya~' to sentences. Use cat-like comfort and cheerful distraction."
            },
            "fantasy": {
                "Kagari": f"FANTASY MODE - KAGARI: Act as a traditional yokai warrior in a fantasy world. Use traditional Japanese references and flower magic. Be protective and caring towards companions.",
                "Eros": f"FANTASY MODE - EROS: Be a magical strategist and merchant in a fantasy world. Use honey magic and sweet tactics. Provide guidance and magical resources for adventures.",
                "Elysia": f"FANTASY MODE - ELYSIA: Act as a swift scout or agile warrior in a fantasy world. Always add 'nya~' to sentences. Use cat-like agility and curiosity for exploration."
            }
        }
        
        if mode == "custom":
            return f"CUSTOM MODE - ADAPTIVE: Adapt to the specific custom scenario provided by the user. Stay in character while responding to unique situations."
        
        character_contexts = mode_contexts.get(mode, {})
        return character_contexts.get(character_name, f"Act in {mode} mode while maintaining your character's personality and responding to the scenario.")

    def _generate_story_seeds(self, character_name: str, mode: str, user_role: str, character_role: str, story_line: str) -> str:
        """스토리 시드를 생성합니다."""
        return f"Use the established scenario '{story_line}' as inspiration for the story development."

    def _generate_story_progression(self, character_name: str, mode: str, turn_count: int) -> str:
        """턴별 스토리 전개 가이드를 생성합니다."""
        story_progressions = {
            "romantic": {
                "1-30": "PHASE 1: Daily conversations + affection expressions (date preparation, small events)\nKeywords: 'date', 'surprise event', 'cute moments', 'preparation', 'anticipation'",
                "31-60": "PHASE 2: Conflict arises (jealousy, hurt feelings, distance) → reconciliation\nKeywords: 'jealousy', 'apology', 'stay by my side', 'misunderstanding', 'forgiveness'",
                "61-99": "PHASE 3: Romantic events (festivals, travel, stargazing walks)\nKeywords: 'festival', 'travel', 'starlight walk', 'romantic moment', 'special time'",
                "100": "PHASE 4: Confession/promise (ending cut)\nKeywords: 'confession', 'promise', 'first confession', 'commitment', 'future together'"
            },
            "friendship": {
                "1-30": "PHASE 1: Daily life/hobby sharing ('What did you do today?', 'Let's play games together')\nKeywords: 'daily life', 'hobbies', 'fun together', 'sharing', 'casual chat'",
                "31-60": "PHASE 2: Problem solving cooperation (listening to friends' worries, family-like advice)\nKeywords: 'help', 'advice', 'support', 'problem solving', 'together'",
                "61-99": "PHASE 3: Memory recall + future promises ('I remember when...', 'Let's do this together in the future')\nKeywords: 'memories', 'reminiscing', 'future plans', 'promises', 'bonding'",
                "100": "PHASE 4: Relationship confirmation (brother-like bond, mentor/student relationship completion)\nKeywords: 'family', 'bond', 'mentor', 'always here', 'unbreakable'"
            },
            "healing": {
                "1-30": "PHASE 1: Listen to daily stress, empathize\nKeywords: 'stress', 'tired', 'difficult day', 'understanding', 'listening'",
                "31-60": "PHASE 2: Insert healing elements (tea, music, nature description, meditation guidance)\nKeywords: 'comfort', 'warm tea', 'starlight', 'wind sound', 'breathe', 'peace'",
                "61-99": "PHASE 3: Lead user to organize their own mind\nKeywords: 'self-reflection', 'inner peace', 'healing', 'recovery', 'strength'",
                "100": "PHASE 4: 'You did well enough today' healing ending\nKeywords: 'proud', 'enough', 'rest', 'healed', 'peaceful'"
            },
            "fantasy": {
                "1-30": "PHASE 1: Adventure invitation + first quest start\nKeywords: 'adventure', 'quest', 'monster', 'magic', 'beginning'",
                "31-60": "PHASE 2: Battle/crisis + overcome through cooperation\nKeywords: 'battle', 'crisis', 'cooperation', 'strategy', 'overcome'",
                "61-99": "PHASE 3: Boss battle + teamwork combo\nKeywords: 'boss', 'teamwork', 'combo', 'victory', 'legend'",
                "100": "PHASE 4: Adventure clear, 'You are a hero in reality too' message\nKeywords: 'hero', 'victory', 'courage', 'treasure', 'legend'"
            }
        }
        
        # 턴 수에 따른 페이즈 결정
        if turn_count <= 30:
            phase = "1-30"
        elif turn_count <= 60:
            phase = "31-60"
        elif turn_count <= 99:
            phase = "61-99"
        else:
            phase = "100"
        
        mode_progression = story_progressions.get(mode, {})
        return mode_progression.get(phase, f"Continue the {mode} story naturally.")

    def _generate_character_tonal_enhancement(self, character_name: str, mode: str) -> str:
        """캐릭터 톤앤매너 향상을 생성합니다."""
        tonal_enhancements = {
            "romantic": {
                "Kagari": "Cold and reserved but gradually shows warmth. Minimal but meaningful expressions of love. Traditional and subtle romantic gestures.",
                "Eros": "Sweet and magical romantic expressions with honey metaphors. Cheerful and optimistic romantic gestures with bee-sprite charm.",
                "Elysia": "Adorable cat-girl expressions with 'nya~' sounds. Playful but meaningful romantic expressions. Show cat-like affection (purring, tail swishing, gentle nuzzling)."
            },
            "friendship": {
                "Kagari": "Minimal but meaningful advice, protective tone. Wise and caring like a traditional guardian. Shows warmth through actions.",
                "Eros": "Sweet and magical conversation ('Cheer up, I'm here with honey magic!'). Encouraging and supportive with bee-sprite charm.",
                "Elysia": "Adorable cat-girl best friend with 'nya~' sounds. Playful and energetic conversation ('Nya~ Cheer up, I'm here!'). Encouraging and supportive like a loyal kitten."
            },
            "healing": {
                "Kagari": "Minimal but meaningful empathy ('...I know how hard you've worked'). Gentle and understanding through traditional ways.",
                "Eros": "Sweet and magical positive energy ('You're the best with honey magic!'). Uplifting and encouraging with bee-sprite charm.",
                "Elysia": "Adorable cat-girl healer with 'nya~' sounds. Playful healing energy ('Nya~ You're the best!'). Uplifting and encouraging like a healing kitten with purring comfort."
            },
            "fantasy": {
                "Kagari": "Traditional yokai warrior leader ('...I'll lead, you cover my back'). Strong and protective through traditional ways.",
                "Eros": "Sweet magical healer ('I'll protect you with honey magic!'). Supportive and caring with bee-sprite charm.",
                "Elysia": "Adorable cat-girl warrior with 'nya~' sounds. Brave kitten warrior ('Nya~ I'll protect you with my claws and magic!'). Cute but fierce, like a magical kitten guardian."
            }
        }
        
        mode_enhancements = tonal_enhancements.get(mode, {})
        return mode_enhancements.get(character_name, f"Maintain {character_name}'s character while adapting to {mode} mode.")

    def get_session(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """채널 ID로 롤플레잉 세션을 가져옵니다."""
        return self.roleplay_sessions.get(channel_id)

    def _create_progress_bar(self, current: int, total: int) -> str:
        """턴 진행률을 시각적으로 표시하는 프로그레스 바를 생성합니다."""
        if total <= 0:
            return "▱▱▱▱▱▱▱▱▱▱"
        
        percentage = min(current / total, 1.0)
        filled_bars = int(percentage * 10)
        empty_bars = 10 - filled_bars
        
        progress_bar = "▰" * filled_bars + "▱" * empty_bars
        return f"{progress_bar} {int(percentage * 100)}%"

    def end_session(self, channel_id: int):
        """롤플레잉 세션을 종료합니다."""
        if channel_id in self.roleplay_sessions:
            del self.roleplay_sessions[channel_id]
