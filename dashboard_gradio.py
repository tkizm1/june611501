import gradio as gr
import pandas as pd
import psycopg2
import os
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import plotly.express as px
from wordcloud import WordCloud

DATABASE_URL = os.environ.get("DATABASE_URL")

# PostgreSQL 연결 함수
def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def get_user_cards():
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT user_id, character_name, card_id, acquired_at
        FROM user_cards
        ORDER BY acquired_at DESC
    """, conn)
    conn.close()
    return df

def get_user_info():
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT user_id, character_name, emotion_score, daily_message_count
        FROM affinity
    """, conn)
    conn.close()
    return df

def get_user_summary(user_id):
    conn = get_conn()
    # 유저 기본 정보
    user_info = pd.read_sql_query(f"""
        SELECT
            %s as user_id,
            MIN(timestamp) as joined_at,
            SUM(CASE WHEN message_role='user' THEN 1 ELSE 0 END) as total_messages
        FROM conversations
        WHERE user_id = %s
    """, conn, params=(user_id, user_id))
    # 친밀도 등급
    affinity = pd.read_sql_query("""
        SELECT character_name, emotion_score, daily_message_count
        FROM affinity
        WHERE user_id = %s
    """, conn, params=(user_id,))
    # 카드 정보
    cards = pd.read_sql_query("""
        SELECT card_id, character_name, acquired_at
        FROM user_cards
        WHERE user_id = %s
        ORDER BY acquired_at DESC
    """, conn, params=(user_id,))
    # 카드 등급 비율
    card_tiers = pd.read_sql_query("""
        SELECT
            SUBSTRING(card_id, 1, 1) as tier,
            COUNT(*) as count
        FROM user_cards
        WHERE user_id = %s
        GROUP BY tier
    """, conn, params=(user_id,))
    # 캐릭터별 카드 분류
    char_cards = pd.read_sql_query("""
        SELECT character_name, COUNT(*) as count
        FROM user_cards
        WHERE user_id = %s
        GROUP BY character_name
    """, conn, params=(user_id,))
    # 최근 획득 카드
    recent_card = cards.head(1)
    # 주간 활동량
    week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    week_msgs = pd.read_sql_query("""
        SELECT COUNT(*) as week_messages
        FROM conversations
        WHERE user_id = %s AND timestamp >= %s AND message_role = 'user'
    """, conn, params=(user_id, week_ago))
    week_cards = pd.read_sql_query("""
        SELECT COUNT(*) as week_cards
        FROM user_cards
        WHERE user_id = %s AND acquired_at >= %s
    """, conn, params=(user_id, week_ago))
    # 스토리 진행 현황
    story_progress = get_user_story_progress(user_id)
    # 로그인 정보
    login_info = pd.read_sql_query("""
        SELECT current_streak, last_login_date
        FROM user_login_streaks
        WHERE user_id = %s
    """, conn, params=(user_id,))
    # 선물 정보
    gifts = pd.read_sql_query("""
        SELECT gift_id, quantity
        FROM user_gifts
        WHERE user_id = %s
    """, conn, params=(user_id,))
    # 키워드 정보
    keywords = pd.read_sql_query("""
        SELECT keyword_value, context
        FROM user_keywords
        WHERE user_id = %s
    """, conn, params=(user_id,))
    # 닉네임 정보
    nicknames = pd.read_sql_query("""
        SELECT character_name, nickname
        FROM user_nicknames
        WHERE user_id = %s
    """, conn, params=(user_id,))
    # 에피소드 정보
    episodes = pd.read_sql_query("""
        SELECT character, summary, timestamp
        FROM episodes
        WHERE user_id = %s
        ORDER BY timestamp DESC LIMIT 10
    """, conn, params=(user_id,))
    conn.close()
    # 결과 딕셔너리로 반환
    return {
        "기본 정보": user_info,
        "친밀도": affinity,
        "카드 목록": cards,
        "카드 등급 비율": card_tiers,
        "캐릭터별 카드 분류": char_cards,
        "최근 획득 카드": recent_card,
        "주간 대화 수": week_msgs,
        "주간 카드 획득": week_cards,
        "스토리 진행 현황": story_progress,
        "로그인 정보": login_info,
        "선물 정보": gifts,
        "키워드 정보": keywords,
        "닉네임 정보": nicknames,
        "에피소드 정보": episodes
    }

def user_dashboard(user_id):
    info = get_user_summary(user_id)
    return (
        info["기본 정보"],
        info["친밀도"],
        info["카드 목록"],
        info["카드 등급 비율"],
        info["캐릭터별 카드 분류"],
        info["최근 획득 카드"],
        info["주간 대화 수"],
        info["주간 카드 획득"],
        info["스토리 진행 현황"],
        info["로그인 정보"],
        info["선물 정보"],
        info["키워드 정보"],
        info["닉네임 정보"],
        info["에피소드 정보"]
    )

def get_daily_affinity_gain(character_name=None):
    conn = get_conn()
    today = datetime.now().strftime('%Y-%m-%d')
    if character_name:
        df = pd.read_sql_query("""
            SELECT user_id, SUM(score_change) as today_gain
            FROM affinity_log
            WHERE character_name = %s AND DATE(timestamp AT TIME ZONE 'Asia/Seoul') = %s
            GROUP BY user_id
            ORDER BY today_gain DESC
        """, conn, params=(character_name, today))
    else:
        df = pd.read_sql_query("""
            SELECT user_id, character_name, SUM(score_change) as today_gain
            FROM affinity_log
            WHERE DATE(timestamp AT TIME ZONE 'Asia/Seoul') = %s
            GROUP BY user_id, character_name
            ORDER BY today_gain DESC
        """, conn, params=(today,))
    conn.close()
    return df

def get_quest_completion_rate(quest_type):
    conn = get_conn()
    total_users = pd.read_sql_query("SELECT COUNT(DISTINCT user_id) as total FROM affinity", conn)["total"][0]
    completed = pd.read_sql_query("""
        SELECT COUNT(DISTINCT user_id) as completed
        FROM quest_claims
        WHERE quest_id = %s AND DATE(claimed_at AT TIME ZONE 'Asia/Seoul') = CURRENT_DATE
    """, conn, params=(quest_type,))["completed"][0]
    conn.close()
    percent = (completed / total_users * 100) if total_users else 0
    return pd.DataFrame({"달성 유저 수": [completed], "전체 유저 수": [total_users], "달성률(%)": [round(percent,2)]})

# --- 퀘스트 달성률 일괄 조회 함수 추가 ---
def get_quest_completion_all():
    daily_conv = get_quest_completion_rate("daily_conversation")
    daily_aff = get_quest_completion_rate("daily_affinity_gain")
    weekly_login = get_quest_completion_rate("weekly_login")
    weekly_share = get_quest_completion_rate("weekly_share")
    return daily_conv, daily_aff, weekly_login, weekly_share

def get_user_gifts(user_id):
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT gift_id, quantity
        FROM user_gifts
        WHERE user_id = %s
    """, conn, params=(user_id,))
    conn.close()
    return df

def get_login_streak_ranking():
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT user_id, current_streak
        FROM user_login_streaks
        ORDER BY current_streak DESC
    """, conn)
    conn.close()
    return df

def get_card_ranking():
    """카드 획득 랭킹을 반환합니다."""
    conn = get_conn()
    
    # 각 유저별 카드 통계
    df = pd.read_sql_query("""
        SELECT 
            uc.user_id,
            uc.character_name,
            CASE 
                WHEN UPPER(uc.card_id) LIKE 'KAGARI%' THEN 'Kagari'
                WHEN UPPER(uc.card_id) LIKE 'EROS%' THEN 'Eros'
                WHEN UPPER(uc.card_id) LIKE 'ELYSIA%' THEN 'Elysia'
                ELSE 'Unknown'
            END as character_name_clean,
            CASE 
                WHEN UPPER(uc.card_id) LIKE '%S%' THEN 'S'
                WHEN UPPER(uc.card_id) LIKE '%A%' THEN 'A'
                WHEN UPPER(uc.card_id) LIKE '%B%' THEN 'B'
                WHEN UPPER(uc.card_id) LIKE '%C%' THEN 'C'
                ELSE 'Unknown'
            END as card_tier,
            COUNT(*) as card_count
        FROM user_cards uc
        GROUP BY uc.user_id, uc.character_name, uc.card_id
    """, conn)
    
    # 유저별 총 카드 수
    total_cards = pd.read_sql_query("""
        SELECT 
            user_id,
            COUNT(*) as total_cards
        FROM user_cards
        GROUP BY user_id
        ORDER BY total_cards DESC
    """, conn)
    
    # 캐릭터별 카드 수
    character_cards = pd.read_sql_query("""
        SELECT 
            user_id,
            CASE 
                WHEN UPPER(card_id) LIKE 'KAGARI%' THEN 'Kagari'
                WHEN UPPER(card_id) LIKE 'EROS%' THEN 'Eros'
                WHEN UPPER(card_id) LIKE 'ELYSIA%' THEN 'Elysia'
                ELSE 'Unknown'
            END as character_name,
            COUNT(*) as character_card_count
        FROM user_cards
        GROUP BY user_id, 
            CASE 
                WHEN UPPER(card_id) LIKE 'KAGARI%' THEN 'Kagari'
                WHEN UPPER(card_id) LIKE 'EROS%' THEN 'Eros'
                WHEN UPPER(card_id) LIKE 'ELYSIA%' THEN 'Elysia'
                ELSE 'Unknown'
            END
    """, conn)
    
    # 티어별 카드 수
    tier_cards = pd.read_sql_query("""
        SELECT 
            user_id,
            CASE 
                WHEN UPPER(card_id) LIKE '%S%' THEN 'S'
                WHEN UPPER(card_id) LIKE '%A%' THEN 'A'
                WHEN UPPER(card_id) LIKE '%B%' THEN 'B'
                WHEN UPPER(card_id) LIKE '%C%' THEN 'C'
                ELSE 'Unknown'
            END as card_tier,
            COUNT(*) as tier_card_count
        FROM user_cards
        GROUP BY user_id, 
            CASE 
                WHEN UPPER(card_id) LIKE '%S%' THEN 'S'
                WHEN UPPER(card_id) LIKE '%A%' THEN 'A'
                WHEN UPPER(card_id) LIKE '%B%' THEN 'B'
                WHEN UPPER(card_id) LIKE '%C%' THEN 'C'
                ELSE 'Unknown'
            END
    """, conn)
    
    conn.close()
    
    return {
        'total_cards': total_cards,
        'character_cards': character_cards,
        'tier_cards': tier_cards,
        'detailed_cards': df
    }

def get_gift_usage_ranking():
    """선물 소비 랭킹을 반환합니다."""
    conn = get_conn()
    
    # 유저별 총 선물 소비 수량
    total_gift_usage = pd.read_sql_query("""
        SELECT 
            user_id,
            SUM(quantity) as total_gifts_used
        FROM user_gifts
        GROUP BY user_id
        ORDER BY total_gifts_used DESC
    """, conn)
    
    # 캐릭터별 선물 소비 수량 (gift_id에서 캐릭터 추출)
    character_gift_usage = pd.read_sql_query("""
        SELECT 
            user_id,
            CASE 
                WHEN gift_id LIKE 'kagari%' OR gift_id LIKE 'KAGARI%' THEN 'Kagari'
                WHEN gift_id LIKE 'eros%' OR gift_id LIKE 'EROS%' THEN 'Eros'
                WHEN gift_id LIKE 'elysia%' OR gift_id LIKE 'ELYSIA%' THEN 'Elysia'
                ELSE 'Unknown'
            END as character_name,
            SUM(quantity) as character_gifts_used
        FROM user_gifts
        GROUP BY user_id, 
            CASE 
                WHEN gift_id LIKE 'kagari%' OR gift_id LIKE 'KAGARI%' THEN 'Kagari'
                WHEN gift_id LIKE 'eros%' OR gift_id LIKE 'EROS%' THEN 'Eros'
                WHEN gift_id LIKE 'elysia%' OR gift_id LIKE 'ELYSIA%' THEN 'Elysia'
                ELSE 'Unknown'
            END
        HAVING 
            CASE 
                WHEN gift_id LIKE 'kagari%' OR gift_id LIKE 'KAGARI%' THEN 'Kagari'
                WHEN gift_id LIKE 'eros%' OR gift_id LIKE 'EROS%' THEN 'Eros'
                WHEN gift_id LIKE 'elysia%' OR gift_id LIKE 'ELYSIA%' THEN 'Elysia'
                ELSE 'Unknown'
            END != 'Unknown'
    """, conn)
    
    # 선물 종류별 소비 수량
    gift_type_usage = pd.read_sql_query("""
        SELECT 
            user_id,
            CASE 
                WHEN gift_id LIKE '%rare%' OR gift_id LIKE '%RARE%' THEN 'Rare'
                WHEN gift_id LIKE '%common%' OR gift_id LIKE '%COMMON%' THEN 'Common'
                WHEN gift_id LIKE '%special%' OR gift_id LIKE '%SPECIAL%' THEN 'Special'
                ELSE 'Other'
            END as gift_type,
            SUM(quantity) as gift_type_used
        FROM user_gifts
        GROUP BY user_id, 
            CASE 
                WHEN gift_id LIKE '%rare%' OR gift_id LIKE '%RARE%' THEN 'Rare'
                WHEN gift_id LIKE '%common%' OR gift_id LIKE '%COMMON%' THEN 'Common'
                WHEN gift_id LIKE '%special%' OR gift_id LIKE '%SPECIAL%' THEN 'Special'
                ELSE 'Other'
            END
    """, conn)
    
    conn.close()
    
    return {
        'total_gift_usage': total_gift_usage,
        'character_gift_usage': character_gift_usage,
        'gift_type_usage': gift_type_usage
    }

def get_message_trend():
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT DATE(timestamp AT TIME ZONE 'Asia/Seoul') as date, COUNT(*) as messages
        FROM conversations
        WHERE message_role = 'user'
        GROUP BY DATE(timestamp AT TIME ZONE 'Asia/Seoul')
        ORDER BY date
    """, conn)
    conn.close()
    return df

def get_user_keywords(user_id):
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT character_name, keyword_value, context
        FROM user_keywords
        WHERE user_id = %s
    """, conn, params=(user_id,))
    conn.close()
    return df

def get_user_nicknames(user_id):
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT character_name, nickname
        FROM user_nicknames
        WHERE user_id = %s
    """, conn, params=(user_id,))
    conn.close()
    return df

def get_user_episodes(user_id):
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT character, summary, timestamp
        FROM episodes
        WHERE user_id = %s
        ORDER BY timestamp DESC LIMIT 10
    """, conn, params=(user_id,))
    conn.close()
    return df

def get_dashboard_stats():
    conn = get_conn()
    # 1. 총 유저 메시지 수
    total_user_messages = pd.read_sql_query(
        "SELECT COUNT(*) as total_user_messages FROM conversations WHERE LOWER(message_role)='user';", conn
    )["total_user_messages"][0]
    # 2. 챗봇 총 친밀도 점수
    total_affinity = pd.read_sql_query(
        "SELECT SUM(emotion_score) as total_affinity FROM affinity;", conn
    )["total_affinity"][0]
    # 3. OpenAI 토큰 소비량
    try:
        total_tokens = pd.read_sql_query(
            "SELECT SUM(token_count) as total_tokens FROM conversations WHERE message_role='assistant';", conn
        )["total_tokens"][0]
        if total_tokens is None:
            total_tokens = 0
    except Exception:
        total_tokens = 0
    # 4. 카드 등급별 출하량 및 백분율
    card_tiers = pd.read_sql_query(
        "SELECT SUBSTRING(card_id, 1, 1) as tier, COUNT(*) as count FROM user_cards GROUP BY tier;", conn
    )
    total_cards = card_tiers["count"].sum()
    card_tiers["percent"] = (card_tiers["count"] / total_cards * 100).round(2).astype(str) + "%"
    # 레벨 통계 추가
    level_stats = get_level_statistics()
    conn.close()
    return {
        "총 유저 메시지 수": total_user_messages,
        "총 친밀도 점수": total_affinity,
        "OpenAI 토큰 소비량": f"{total_tokens:,} 토큰",
        "카드 등급별 출하량": card_tiers,
        "레벨별 현황": level_stats
    }

def show_dashboard_stats():
    stats = get_dashboard_stats()
    # 표/카드 형태로 반환
    return (
        f"총 유저 메시지 수: {stats['총 유저 메시지 수']}",
        f"총 친밀도 점수: {stats['총 친밀도 점수']}",
        f"OpenAI 토큰 소비량: {stats['OpenAI 토큰 소비량']}",
        stats["카드 등급별 출하량"],
        stats["레벨별 현황"]
    )

def get_full_character_ranking(character_name):
    conn = get_conn()
    df = pd.read_sql_query(f'''
        SELECT a.user_id, a.emotion_score, COALESCE(cc.message_count, 0) as message_count
        FROM affinity a
        LEFT JOIN (
            SELECT user_id, character_name, COUNT(*) as message_count
            FROM conversations
            WHERE message_role = 'user'
            GROUP BY user_id, character_name
        ) cc ON a.user_id = cc.user_id AND a.character_name = cc.character_name
        WHERE a.character_name = %s
        ORDER BY a.emotion_score DESC, message_count DESC
    ''', conn, params=(character_name,))
    conn.close()
    return df

def get_full_total_ranking():
    conn = get_conn()
    df = pd.read_sql_query('''
        SELECT a.user_id, COALESCE(a.total_affinity, 0) as total_affinity, COALESCE(m.total_messages, 0) as total_messages
        FROM (
            SELECT user_id, SUM(emotion_score) as total_affinity
            FROM affinity
            GROUP BY user_id
        ) a
        LEFT JOIN (
            SELECT user_id, COUNT(*) as total_messages
            FROM conversations
            WHERE message_role = 'user'
            GROUP BY user_id
        ) m ON a.user_id = m.user_id
        UNION
        SELECT m.user_id, COALESCE(a.total_affinity, 0) as total_affinity, COALESCE(m.total_messages, 0) as total_messages
        FROM (
            SELECT user_id, COUNT(*) as total_messages
            FROM conversations
            WHERE message_role = 'user'
            GROUP BY user_id
        ) m
        LEFT JOIN (
            SELECT user_id, SUM(emotion_score) as total_affinity
            FROM affinity
            GROUP BY user_id
        ) a ON m.user_id = a.user_id
        ORDER BY total_affinity DESC, total_messages DESC
    ''', conn)
    conn.close()
    return df

def show_all_rankings():
    kagari = get_full_character_ranking("Kagari")
    eros = get_full_character_ranking("Eros")
    elysia = get_full_character_ranking("Elysia")
    total = get_full_total_ranking()
    return kagari, eros, elysia, total

def show_card_ranking():
    """카드 획득 랭킹을 표시합니다."""
    card_data = get_card_ranking()
    
    # 총 카드 수 랭킹 (상위 20명)
    total_ranking = card_data['total_cards'].head(20).copy()
    total_ranking['rank'] = range(1, len(total_ranking) + 1)
    total_ranking = total_ranking[['rank', 'user_id', 'total_cards']]
    
    # 캐릭터별 카드 수 랭킹
    character_ranking = card_data['character_cards'].copy()
    character_ranking = character_ranking.pivot_table(
        index='user_id', 
        columns='character_name', 
        values='character_card_count', 
        fill_value=0
    ).reset_index()
    
    # 티어별 카드 수 랭킹
    tier_ranking = card_data['tier_cards'].copy()
    tier_ranking = tier_ranking.pivot_table(
        index='user_id', 
        columns='card_tier', 
        values='tier_card_count', 
        fill_value=0
    ).reset_index()
    
    # 상세 통계 (상위 10명)
    detailed_stats = []
    for user_id in total_ranking['user_id'].head(10):
        user_char_cards = character_ranking[character_ranking['user_id'] == user_id]
        user_tier_cards = tier_ranking[tier_ranking['user_id'] == user_id]
        
        if not user_char_cards.empty and not user_tier_cards.empty:
            char_stats = user_char_cards.iloc[0]
            tier_stats = user_tier_cards.iloc[0]
            
            detailed_stats.append({
                'user_id': user_id,
                'total_cards': total_ranking[total_ranking['user_id'] == user_id]['total_cards'].iloc[0],
                'Kagari': char_stats.get('Kagari', 0),
                'Eros': char_stats.get('Eros', 0),
                'Elysia': char_stats.get('Elysia', 0),
                'S_tier': tier_stats.get('S', 0),
                'A_tier': tier_stats.get('A', 0),
                'B_tier': tier_stats.get('B', 0),
                'C_tier': tier_stats.get('C', 0)
            })
    
    detailed_df = pd.DataFrame(detailed_stats)
    
    return total_ranking, character_ranking, tier_ranking, detailed_df

def show_gift_usage_ranking():
    """선물 소비 랭킹을 표시합니다."""
    gift_data = get_gift_usage_ranking()
    
    # 총 선물 소비 랭킹 (상위 20명)
    total_ranking = gift_data['total_gift_usage'].head(20).copy()
    total_ranking['rank'] = range(1, len(total_ranking) + 1)
    total_ranking = total_ranking[['rank', 'user_id', 'total_gifts_used']]
    
    # 캐릭터별 선물 소비 랭킹
    character_ranking = gift_data['character_gift_usage'].copy()
    character_ranking = character_ranking.pivot_table(
        index='user_id', 
        columns='character_name', 
        values='character_gifts_used', 
        fill_value=0
    ).reset_index()
    
    # 선물 종류별 소비 랭킹
    gift_type_ranking = gift_data['gift_type_usage'].copy()
    gift_type_ranking = gift_type_ranking.pivot_table(
        index='user_id', 
        columns='gift_type', 
        values='gift_type_used', 
        fill_value=0
    ).reset_index()
    
    # 상세 통계 (상위 10명)
    detailed_stats = []
    for user_id in total_ranking['user_id'].head(10):
        user_char_gifts = character_ranking[character_ranking['user_id'] == user_id]
        user_gift_types = gift_type_ranking[gift_type_ranking['user_id'] == user_id]
        
        if not user_char_gifts.empty and not user_gift_types.empty:
            char_stats = user_char_gifts.iloc[0]
            type_stats = user_gift_types.iloc[0]
            
            detailed_stats.append({
                'user_id': user_id,
                'total_gifts_used': total_ranking[total_ranking['user_id'] == user_id]['total_gifts_used'].iloc[0],
                'Kagari_gifts': char_stats.get('Kagari', 0),
                'Eros_gifts': char_stats.get('Eros', 0),
                'Elysia_gifts': char_stats.get('Elysia', 0),
                'Rare_gifts': type_stats.get('Rare', 0),
                'Common_gifts': type_stats.get('Common', 0),
                'Special_gifts': type_stats.get('Special', 0),
                'Other_gifts': type_stats.get('Other', 0)
            })
    
    detailed_df = pd.DataFrame(detailed_stats)
    
    return total_ranking, character_ranking, gift_type_ranking, detailed_df

def get_level_statistics():
    conn = get_conn()
    # 전체 유저 수 계산
    total_users = pd.read_sql_query("""
        SELECT COUNT(DISTINCT user_id) as total_users
        FROM affinity
    """, conn)["total_users"][0]

    # 레벨별 유저 수 계산
    level_stats = pd.read_sql_query("""
        WITH user_levels AS (
            SELECT 
                user_id,
                CASE 
                    WHEN SUM(emotion_score) < 10 THEN 'Rookie'
                    WHEN SUM(emotion_score) < 30 THEN 'Iron'
                    WHEN SUM(emotion_score) < 50 THEN 'Bronze'
                    WHEN SUM(emotion_score) < 100 THEN 'Silver'
                    ELSE 'Gold'
                END as level
            FROM affinity
            GROUP BY user_id
        )
        SELECT 
            level,
            COUNT(*) as user_count,
            ROUND(COUNT(*) * 100.0 / ?, 2) as percentage
        FROM user_levels
        GROUP BY level
        ORDER BY 
            CASE level
                WHEN 'Rookie' THEN 1
                WHEN 'Iron' THEN 2
                WHEN 'Bronze' THEN 3
                WHEN 'Silver' THEN 4
                WHEN 'Gold' THEN 5
            END
    """, conn, params=(total_users,))
    conn.close()
    return level_stats

def get_user_story_progress(user_id):
    conn = get_conn()
    # 스토리 챕터 진행 현황
    chapter_progress = pd.read_sql_query("""
        SELECT 
            character_name,
            chapter_number,
            completed_at,
            selected_choice,
            ending_type
        FROM story_progress
        WHERE user_id = %s
        ORDER BY character_name, chapter_number
    """, conn, params=(user_id,))
    conn.close()
    return chapter_progress

def get_all_story_progress():
    conn = get_conn()
    # 전체 스토리 진행 현황
    story_stats = pd.read_sql_query("""
        SELECT 
            character_name,
            chapter_number,
            COUNT(DISTINCT user_id) as completed_users,
            COUNT(DISTINCT CASE WHEN ending_type = 'Good' THEN user_id END) as good_endings,
            COUNT(DISTINCT CASE WHEN ending_type = 'Bad' THEN user_id END) as bad_endings,
            COUNT(DISTINCT CASE WHEN ending_type = 'Normal' THEN user_id END) as normal_endings
        FROM story_progress
        GROUP BY character_name, chapter_number
        ORDER BY character_name, chapter_number
    """, conn)
    conn.close()
    return story_stats

def get_basic_stats():
    conn = get_conn()
    total_turns = pd.read_sql_query("SELECT COUNT(*) FROM conversations WHERE message_role='user'", conn).iloc[0,0]
    total_cards = pd.read_sql_query("SELECT COUNT(*) FROM user_cards", conn).iloc[0,0]
    card_tiers = pd.read_sql_query("SELECT SUBSTRING(card_id,1,1) as tier, COUNT(*) as count FROM user_cards GROUP BY tier", conn)
    total_users = pd.read_sql_query("SELECT COUNT(DISTINCT user_id) FROM conversations", conn).iloc[0,0]
    rank_dist = pd.read_sql_query("""WITH user_levels AS (
        SELECT user_id,
            CASE 
                WHEN SUM(emotion_score) < 10 THEN 'Rookie'
                WHEN SUM(emotion_score) < 30 THEN 'Iron'
                WHEN SUM(emotion_score) < 50 THEN 'Bronze'
                WHEN SUM(emotion_score) < 100 THEN 'Silver'
                ELSE 'Gold'
            END as level
        FROM affinity GROUP BY user_id
    ) SELECT level, COUNT(*) as count FROM user_levels GROUP BY level ORDER BY level""", conn)
    total_gifts = pd.read_sql_query("SELECT SUM(quantity) FROM user_gifts", conn).iloc[0,0]
    conn.close()
    return total_turns, total_cards, card_tiers, total_users, rank_dist, total_gifts

def plot_card_distribution_by_character():
    conn = get_conn()
    df = pd.read_sql_query('''
        SELECT character_name, COUNT(*) as count
        FROM user_cards
        GROUP BY character_name
        ORDER BY character_name
    ''', conn)
    conn.close()
    fig = px.pie(df, names='character_name', values='count', title='캐릭터별 카드 획득 분포')
    return fig

def plot_rank_dist(rank_dist):
    fig = px.pie(rank_dist, names='level', values='count', title='랭킹 분포')
    return fig

def plot_keyword_distribution():
    conn = get_conn()
    df = pd.read_sql_query("SELECT keyword_value, COUNT(*) as count FROM user_keywords GROUP BY keyword_value ORDER BY count DESC", conn)
    conn.close()
    fig = px.bar(df, x='keyword_value', y='count', title='키워드 분포')
    return fig

def plot_gift_distribution():
    conn = get_conn()
    df = pd.read_sql_query("SELECT gift_id, SUM(quantity) as total FROM user_gifts GROUP BY gift_id ORDER BY total DESC", conn)
    conn.close()
    fig = px.bar(df, x='gift_id', y='total', title='선물 지급 분포')
    return fig

def plot_story_completion():
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT character_name, chapter_number, COUNT(DISTINCT user_id) as completed_users
        FROM story_progress
        WHERE completed_at IS NOT NULL
        GROUP BY character_name, chapter_number
        ORDER BY character_name, chapter_number
    """, conn)
    conn.close()
    fig = px.bar(df, x='character_name', y='completed_users', color='chapter_number', barmode='group', title='스토리 챕터별 완성 유저수')
    return fig

def get_card_total_by_character():
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT character_name, COUNT(*) as total_cards
        FROM user_cards
        GROUP BY character_name
        ORDER BY character_name
    """, conn)
    conn.close()
    return df

def get_card_tier_by_character():
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT character_name, UPPER(SUBSTRING(card_id, LENGTH(character_name)+1, 1)) as tier, COUNT(*) as count
        FROM user_cards
        GROUP BY character_name, tier
        ORDER BY character_name, tier
    """, conn)
    conn.close()
    return df

def get_message_trend_all():
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT DATE(timestamp) as date, COUNT(*) as total_messages
        FROM conversations
        WHERE message_role = 'user'
        GROUP BY date
        ORDER BY date
    """, conn)
    conn.close()
    return df

def get_user_card_total_by_character(user_id):
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT character_name, COUNT(*) as total_cards
        FROM user_cards
        WHERE user_id = %s
        GROUP BY character_name
        ORDER BY character_name
    """, conn, params=(user_id,))
    conn.close()
    return df

def get_user_card_tier_by_character(user_id):
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT character_name, UPPER(SUBSTRING(card_id, 1, 1)) as tier, COUNT(*) as count
        FROM user_cards
        WHERE user_id = %s
        GROUP BY character_name, tier
        ORDER BY character_name, tier
    """, conn, params=(user_id,))
    conn.close()
    return df

def get_active_user_count(days=1):
    conn = get_conn()
    df = pd.read_sql_query(f'''
        SELECT COUNT(DISTINCT user_id) as active_users
        FROM conversations
        WHERE message_role = 'user' AND timestamp >= NOW() - INTERVAL '{days} days'
    ''', conn)
    conn.close()
    return int(df['active_users'][0])

def get_total_message_user_count():
    conn = get_conn()
    df = pd.read_sql_query('''
        SELECT COUNT(DISTINCT user_id) as total_users
        FROM conversations
        WHERE message_role = 'user'
    ''', conn)
    conn.close()
    return int(df['total_users'][0])

def get_retention(days=1):
    # 1일/7일/30일 리텐션: N일 전 메시지 보낸 유저 중 오늘도 메시지 보낸 유저 비율
    conn = get_conn()
    df = pd.read_sql_query(f'''
        WITH prev AS (
            SELECT DISTINCT user_id
            FROM conversations
            WHERE message_role = 'user' AND DATE(timestamp) = CURRENT_DATE - INTERVAL '{days} days'
        ), today AS (
            SELECT DISTINCT user_id
            FROM conversations
            WHERE message_role = 'user' AND DATE(timestamp) = CURRENT_DATE
        )
        SELECT COUNT(*) as retained, (SELECT COUNT(*) FROM prev) as base
        FROM today WHERE user_id IN (SELECT user_id FROM prev)
    ''', conn)
    conn.close()
    base = df['base'][0] if df['base'][0] else 1
    return round(df['retained'][0] / base * 100, 2) if base else 0.0

def get_active_user_trend(days=30):
    conn = get_conn()
    df = pd.read_sql_query(f'''
        SELECT DATE(timestamp) as date, COUNT(DISTINCT user_id) as active_users
        FROM conversations
        WHERE message_role = 'user' AND timestamp >= NOW() - INTERVAL '{days} days'
        GROUP BY date
        ORDER BY date
    ''', conn)
    conn.close()
    return df

def get_active_user_trend_days(days=30):
    conn = get_conn()
    df = pd.read_sql_query(f'''
        SELECT DATE(timestamp) as date, COUNT(DISTINCT user_id) as active_users
        FROM conversations
        WHERE message_role = 'user' AND timestamp >= NOW() - INTERVAL '{days} days'
        GROUP BY date
        ORDER BY date
    ''', conn)
    conn.close()
    df = df.reset_index(drop=True)
    df['day'] = range(1, len(df)+1)
    return df

def get_keyword_distribution():
    conn = get_conn()
    df = pd.read_sql_query('''
        SELECT keyword_type, keyword_value, COUNT(*) as total_count
        FROM user_keywords
        GROUP BY keyword_type, keyword_value
        ORDER BY total_count DESC
    ''', conn)
    conn.close()
    return df

def get_keyword_user_count():
    conn = get_conn()
    df = pd.read_sql_query('''
        SELECT keyword_type, keyword_value, COUNT(DISTINCT user_id) as user_count
        FROM user_keywords
        GROUP BY keyword_type, keyword_value
        ORDER BY user_count DESC
    ''', conn)
    conn.close()
    return df

def get_user_summaries_table():
    conn = get_conn()
    df = pd.read_sql_query('''
        SELECT user_id, character_name, summary
        FROM memory_summaries
        ORDER BY user_id, character_name
    ''', conn)
    conn.close()
    return df

def get_user_summary_stats():
    conn = get_conn()
    df = pd.read_sql_query('''
        SELECT user_id, COUNT(*) as summary_count
        FROM memory_summaries
        GROUP BY user_id
        ORDER BY summary_count DESC
    ''', conn)
    conn.close()
    return df

def get_monthly_active_users():
    conn = get_conn()
    df = pd.read_sql_query('''
        SELECT DATE_TRUNC('month', timestamp) AS month, COUNT(DISTINCT user_id) AS active_users
        FROM conversations
        WHERE message_role = 'user'
        GROUP BY month
        ORDER BY month
    ''', conn)
    conn.close()
    return df

def get_monthly_new_users():
    conn = get_conn()
    df = pd.read_sql_query('''
        SELECT DATE_TRUNC('month', first_message) AS month, COUNT(*) AS new_users
        FROM (
            SELECT user_id, MIN(timestamp) AS first_message
            FROM conversations
            WHERE message_role = 'user'
            GROUP BY user_id
        ) t
        GROUP BY month
        ORDER BY month
    ''', conn)
    conn.close()
    return df

def get_retention_trend():
    conn = get_conn()
    # 1일, 7일, 30일 리텐션 계산
    retention = []
    for days in [1, 7, 30]:
        df = pd.read_sql_query(f'''
            WITH prev AS (
                SELECT DISTINCT user_id
                FROM conversations
                WHERE message_role = 'user' AND DATE(timestamp) = CURRENT_DATE - INTERVAL '{days} day'
            ), today AS (
                SELECT DISTINCT user_id
                FROM conversations
                WHERE message_role = 'user' AND DATE(timestamp) = CURRENT_DATE
            )
            SELECT
                (SELECT COUNT(*) FROM today WHERE user_id IN (SELECT user_id FROM prev))::float /
                GREATEST((SELECT COUNT(*) FROM prev), 1) * 100 AS retention
        ''', conn)
        retention.append({'days': days, 'retention': float(df['retention'][0])})
    conn.close()
    return pd.DataFrame(retention)

def get_story_chapter_completion():
    conn = get_conn()
    # 전체 스토리 플레이 유저 수
    total_users = pd.read_sql_query('''
        SELECT COUNT(DISTINCT user_id) as total_users
        FROM story_progress
        WHERE completed_at IS NOT NULL
    ''', conn)["total_users"][0]
    # 캐릭터별 챕터별 완료 유저수
    df = pd.read_sql_query('''
        SELECT character_name, chapter_number, COUNT(DISTINCT user_id) as completed_users
        FROM story_progress
        WHERE completed_at IS NOT NULL
        GROUP BY character_name, chapter_number
        ORDER BY character_name, chapter_number
    ''', conn)
    conn.close()
    # 퍼센트 컬럼 추가
    df["percent"] = (df["completed_users"] / total_users * 100).round(2).astype(str) + "%"
    return total_users, df

def get_roleplay_user_count():
    conn = get_conn()
    # 롤플레이 모드 플레이한 유저 총수 (story_mode_users 테이블이 있다고 가정)
    try:
        df = pd.read_sql_query('''
            SELECT COUNT(DISTINCT user_id) as roleplay_users
            FROM roleplay_sessions
        ''', conn)
        count = int(df["roleplay_users"][0])
    except Exception:
        count = 0
    conn.close()
    return count

def get_spam_messages():
    conn = get_conn()
    df = pd.read_sql_query('''
        SELECT user_id, character_name, message, reason, timestamp
        FROM spam_messages
        ORDER BY timestamp DESC
    ''', conn)
    conn.close()
    return df

# === 결제 관련 함수들 ===

def get_payment_user_list():
    """결제 유저 정보 리스트를 반환합니다."""
    conn = get_conn()
    df = pd.read_sql_query('''
        SELECT 
            pt.user_id,
            pt.product_id,
            pt.amount,
            pt.currency,
            pt.payment_method,
            pt.status,
            pt.created_at,
            SUM(pt.amount) OVER (PARTITION BY pt.user_id) as total_user_amount
        FROM payment_transactions pt
        WHERE pt.status = 'completed'
        ORDER BY pt.created_at DESC
    ''', conn)
    conn.close()
    return df

def get_most_purchased_items():
    """가장 많이 구매한 아이템 내역을 반환합니다."""
    conn = get_conn()
    df = pd.read_sql_query('''
        SELECT 
            product_id,
            COUNT(*) as purchase_count,
            SUM(amount) as total_revenue,
            AVG(amount) as avg_price,
            MIN(amount) as min_price,
            MAX(amount) as max_price
        FROM payment_transactions
        WHERE status = 'completed'
        GROUP BY product_id
        ORDER BY purchase_count DESC
    ''', conn)
    conn.close()
    return df

def get_payment_user_stats():
    """결제 유저 통계를 반환합니다."""
    conn = get_conn()
    
    # 총 사용 유저 수
    total_users = pd.read_sql_query('''
        SELECT COUNT(DISTINCT user_id) as total_users
        FROM conversations
        WHERE message_role = 'user'
    ''', conn)["total_users"][0]
    
    # 1회라도 결제한 유저 수
    paying_users = pd.read_sql_query('''
        SELECT COUNT(DISTINCT user_id) as paying_users
        FROM payment_transactions
        WHERE status = 'completed'
    ''', conn)["paying_users"][0]
    
    # 결제 유저 비율
    payment_ratio = (paying_users / total_users * 100) if total_users > 0 else 0
    
    # ARPU (Average Revenue Per User)
    total_revenue = pd.read_sql_query('''
        SELECT SUM(amount) as total_revenue
        FROM payment_transactions
        WHERE status = 'completed'
    ''', conn)["total_revenue"][0] or 0
    
    arpu = total_revenue / paying_users if paying_users > 0 else 0
    
    # ARPPU (Average Revenue Per Paying User)
    arppu = total_revenue / paying_users if paying_users > 0 else 0
    
    conn.close()
    
    return {
        "total_users": total_users,
        "paying_users": paying_users,
        "payment_ratio": round(payment_ratio, 2),
        "total_revenue": total_revenue,
        "arpu": round(arpu, 2),
        "arppu": round(arppu, 2)
    }

def get_daily_payment_trend(days=30):
    """일별 결제 횟수 및 금액을 반환합니다."""
    conn = get_conn()
    df = pd.read_sql_query(f'''
        SELECT 
            DATE(created_at) as payment_date,
            COUNT(*) as payment_count,
            SUM(amount) as daily_revenue,
            COUNT(DISTINCT user_id) as unique_payers
        FROM payment_transactions
        WHERE status = 'completed' 
        AND created_at >= NOW() - INTERVAL '{days} days'
        GROUP BY DATE(created_at)
        ORDER BY payment_date
    ''', conn)
    conn.close()
    return df

def get_payment_method_distribution():
    """결제 방법별 분포를 반환합니다."""
    conn = get_conn()
    df = pd.read_sql_query('''
        SELECT 
            payment_method,
            COUNT(*) as count,
            SUM(amount) as total_amount,
            AVG(amount) as avg_amount
        FROM payment_transactions
        WHERE status = 'completed'
        GROUP BY payment_method
        ORDER BY count DESC
    ''', conn)
    conn.close()
    return df

def get_currency_distribution():
    """통화별 분포를 반환합니다."""
    conn = get_conn()
    df = pd.read_sql_query('''
        SELECT 
            currency,
            COUNT(*) as count,
            SUM(amount) as total_amount,
            AVG(amount) as avg_amount
        FROM payment_transactions
        WHERE status = 'completed'
        GROUP BY currency
        ORDER BY count DESC
    ''', conn)
    conn.close()
    return df

def get_user_payment_history(user_id):
    """특정 유저의 결제 내역을 반환합니다."""
    conn = get_conn()
    df = pd.read_sql_query('''
        SELECT 
            product_id,
            amount,
            currency,
            payment_method,
            status,
            created_at
        FROM payment_transactions
        WHERE user_id = %s
        ORDER BY created_at DESC
    ''', conn, params=(user_id,))
    conn.close()
    return df

def get_monthly_revenue_trend():
    """월별 수익 추이를 반환합니다."""
    conn = get_conn()
    df = pd.read_sql_query('''
        SELECT 
            DATE_TRUNC('month', created_at) as month,
            COUNT(*) as payment_count,
            SUM(amount) as monthly_revenue,
            COUNT(DISTINCT user_id) as unique_payers
        FROM payment_transactions
        WHERE status = 'completed'
        GROUP BY DATE_TRUNC('month', created_at)
        ORDER BY month
    ''', conn)
    conn.close()
    return df

def plot_daily_payment_trend(days=30):
    """일별 결제 추이 그래프를 생성합니다."""
    df = get_daily_payment_trend(days)
    fig = px.line(df, x='payment_date', y='daily_revenue', 
                  title=f'최근 {days}일 일별 결제 금액 추이',
                  labels={'payment_date': '날짜', 'daily_revenue': '일일 수익'})
    return fig

def plot_daily_payment_count(days=30):
    """일별 결제 횟수 그래프를 생성합니다."""
    df = get_daily_payment_trend(days)
    fig = px.bar(df, x='payment_date', y='payment_count',
                 title=f'최근 {days}일 일별 결제 횟수',
                 labels={'payment_date': '날짜', 'payment_count': '결제 횟수'})
    return fig

def plot_payment_method_distribution():
    """결제 방법별 분포 그래프를 생성합니다."""
    df = get_payment_method_distribution()
    fig = px.pie(df, names='payment_method', values='count',
                 title='결제 방법별 분포')
    return fig

def plot_most_purchased_items():
    """가장 많이 구매한 아이템 그래프를 생성합니다."""
    df = get_most_purchased_items()
    fig = px.bar(df.head(10), x='product_id', y='purchase_count',
                 title='가장 많이 구매한 아이템 TOP 10',
                 labels={'product_id': '상품 ID', 'purchase_count': '구매 횟수'})
    return fig

def plot_monthly_revenue():
    """월별 수익 그래프를 생성합니다."""
    df = get_monthly_revenue_trend()
    fig = px.line(df, x='month', y='monthly_revenue',
                  title='월별 수익 추이',
                  labels={'month': '월', 'monthly_revenue': '월별 수익'})
    return fig

if __name__ == "__main__":
    with gr.Blocks(title="디스코드 챗봇 통합 대시보드") as demo:
        gr.Markdown("# 디스코드 챗봇 통합 대시보드")

        with gr.Tab("기본 데이터/현황"):
            gr.Markdown("## 기본 데이터 및 현황")
            total_turns, total_cards, card_tiers, total_users, rank_dist, total_gifts = get_basic_stats()
            gr.Markdown(f"총 턴 수(전체 대화 수): {total_turns}")
            gr.Markdown(f"총 카드 수: {total_cards}")
            gr.Markdown(f"총 유저 수: {total_users}")
            gr.Markdown(f"총 선물 지급 수: {total_gifts}")
            gr.Plot(plot_card_distribution_by_character())
            gr.Plot(plot_rank_dist(rank_dist))
            gr.Plot(plot_gift_distribution())
            # --- 추가된 표/그래프 ---
            gr.Dataframe(get_card_total_by_character(), label="캐릭터별 총 카드 획득 현황")
            gr.Dataframe(get_card_tier_by_character(), label="캐릭터별 등급별 카드 획득 현황 (C/B/A/S)")
            gr.Plot(lambda: px.line(get_message_trend_all(), x='date', y='total_messages', title='전체 메시지/대화량 추이'))

        with gr.Tab("랭킹"):
            gr.Markdown("## 캐릭터별 호감도/대화수/로그인 랭킹")
            kagari = get_full_character_ranking("Kagari")
            eros = get_full_character_ranking("Eros")
            elysia = get_full_character_ranking("Elysia")
            gr.Dataframe(kagari, label="Kagari 호감도 랭킹")
            gr.Dataframe(eros, label="Eros 호감도 랭킹")
            gr.Dataframe(elysia, label="Elysia 호감도 랭킹")
            gr.Dataframe(get_login_streak_ranking(), label="연속 로그인 랭킹")
            
            gr.Markdown("## 🎴 카드 획득 랭킹")
            total_ranking, character_ranking, tier_ranking, detailed_df = show_card_ranking()
            gr.Dataframe(total_ranking, label="📊 총 카드 수 랭킹 (상위 20명)")
            gr.Dataframe(detailed_df, label="🎯 상위 10명 상세 통계 (캐릭터별/티어별)")
            gr.Dataframe(character_ranking, label="👥 캐릭터별 카드 수 분포")
            gr.Dataframe(tier_ranking, label="⭐ 티어별 카드 수 분포")
            
            gr.Markdown("## 🎁 선물 소비 랭킹")
            gift_total_ranking, gift_character_ranking, gift_type_ranking, gift_detailed_df = show_gift_usage_ranking()
            gr.Dataframe(gift_total_ranking, label="📊 총 선물 소비 랭킹 (상위 20명)")
            gr.Dataframe(gift_detailed_df, label="🎯 상위 10명 상세 통계 (캐릭터별/선물종류별)")
            gr.Dataframe(gift_character_ranking, label="👥 캐릭터별 선물 소비 분포")
            gr.Dataframe(gift_type_ranking, label="🎁 선물 종류별 소비 분포")

        with gr.Tab("AI/키워드/서머리"):
            gr.Markdown("## 키워드/AI/서머리 데이터")
            gr.Dataframe(get_user_summary_stats(), label="유저 대화 서머리 수치")
            gr.Dataframe(get_keyword_distribution(), label="키워드 분포도 (keyword_type, keyword_value)")
            gr.Dataframe(get_keyword_user_count(), label="키워드별 대화 유저수")
            gr.Dataframe(get_user_summaries_table(), label="유저별 대화 서머리 (user_id, character_name, summary)")

        with gr.Tab("퀘스트/스토리/선물"):
            gr.Markdown("## 퀘스트/스토리/선물 현황")
            daily_conv, daily_aff, weekly_login, weekly_share = get_quest_completion_all()
            gr.Dataframe(daily_conv, label="일일 대화 퀘스트 달성률")
            gr.Dataframe(daily_aff, label="일일 호감도 퀘스트 달성률")
            gr.Dataframe(weekly_login, label="주간 로그인 퀘스트 달성률")
            gr.Dataframe(weekly_share, label="주간 카드 공유 퀘스트 달성률")
            gr.Plot(plot_story_completion())
            gr.Plot(plot_gift_distribution())
            # --- 추가: 스토리 챕터별 완성 유저수 및 롤플레잉 유저수 ---
            total_story_users, story_df = get_story_chapter_completion()
            gr.Markdown(f"스토리 플레이 유저(토탈): {total_story_users}")
            gr.Dataframe(story_df, label="캐릭터별 챕터별 완료 유저수 및 퍼센트")
            gr.Markdown(f"롤플레잉 모드 플레이 유저(토탈): {get_roleplay_user_count()}")

        with gr.Tab("운영 데이터"):
            gr.Markdown("## 운영 데이터 (운영/지표)")
            gr.Markdown(f"메시지를 1번이라도 보낸 유저수 총합: {get_total_message_user_count()}")
            gr.Markdown(f"1일 리텐션: {get_retention(1)}%  |  7일 리텐션: {get_retention(7)}%  |  30일 리텐션: {get_retention(30)}%")
            gr.Markdown(f"최근 1일 엑티브 유저: {get_active_user_count(1)}  |  7일: {get_active_user_count(7)}  |  30일: {get_active_user_count(30)}")
            gr.Plot(lambda: px.line(get_active_user_trend_days(30), x='day', y='active_users', title='최근 30일(일수 기준) 엑티브 유저 추이'))
            # --- 추가: 월별 활성 유저, 신규 유저, 리텐션 ---
            gr.Dataframe(get_monthly_active_users(), label="월별 활성 유저")
            gr.Plot(lambda: px.bar(get_monthly_active_users(), x='month', y='active_users', title='월별 활성 유저'))
            gr.Dataframe(get_monthly_new_users(), label="월별 신규 유저")
            gr.Plot(lambda: px.bar(get_monthly_new_users(), x='month', y='new_users', title='월별 신규 유저'))
            gr.Dataframe(get_retention_trend(), label="1/7/30일 리텐션(%)")
            gr.Plot(lambda: px.bar(get_retention_trend(), x='days', y='retention', title='1/7/30일 리텐션(%)'))

        with gr.Tab("유저 검색"):
            gr.Markdown("## 유저 정보 검색")
            user_id = gr.Textbox(label="디스코드 유저 ID 입력", value="")
            btn = gr.Button("유저 정보 조회")
            outs = [gr.Dataframe(label=label) for label in [
                "기본 정보", "캐릭터별 친밀도", "카드 목록", "카드 등급 비율", "캐릭터별 카드 분류", "최근 획득 카드", "주간 대화 수", "주간 카드 획득", "스토리 진행 현황", "로그인 정보", "선물 정보", "키워드 정보", "닉네임 정보", "에피소드 정보"
            ]]
            # 추가: 캐릭터별 카드 현황 표
            card_total_out = gr.Dataframe(label="[유저] 캐릭터별 총 카드 획득 현황")
            card_tier_out = gr.Dataframe(label="[유저] 캐릭터별 등급별 카드 획득 현황 (C/B/A/S)")
            btn.click(user_dashboard, inputs=user_id, outputs=outs)
            btn.click(get_user_card_total_by_character, inputs=user_id, outputs=card_total_out)
            btn.click(get_user_card_tier_by_character, inputs=user_id, outputs=card_tier_out)

        with gr.Tab("스팸 메시지 관리"):
            gr.Markdown("## Spam Message Management")
            gr.Dataframe(get_spam_messages(), label="Spam Messages (user_id, character_name, message, reason, timestamp)")

        with gr.Tab("Payment"):
            gr.Markdown("## 💳 결제 분석 대시보드")
            
            # 결제 통계 요약
            with gr.Row():
                payment_stats = get_payment_user_stats()
                gr.Markdown(f"""
                ### 📊 결제 통계 요약
                - **총 사용 유저**: {payment_stats['total_users']:,}명
                - **결제 유저**: {payment_stats['paying_users']:,}명 ({payment_stats['payment_ratio']}%)
                - **총 수익**: ${payment_stats['total_revenue']:,.2f}
                - **ARPU**: ${payment_stats['arpu']:,.2f}
                - **ARPPU**: ${payment_stats['arppu']:,.2f}
                """)
            
            # 1. 결제 유저 정보 리스트
            gr.Markdown("### 👥 결제 유저 정보 리스트")
            gr.Dataframe(get_payment_user_list(), label="결제 유저 목록 (디스코드 ID, 상품, 금액, 총 결제 금액)")
            
            # 2. 가장 많이 구매한 아이템
            gr.Markdown("### 🏆 가장 많이 구매한 아이템")
            gr.Dataframe(get_most_purchased_items(), label="아이템별 구매 통계")
            gr.Plot(plot_most_purchased_items())
            
            # 3. 결제 방법 및 통화 분포
            with gr.Row():
                gr.Dataframe(get_payment_method_distribution(), label="결제 방법별 분포")
                gr.Dataframe(get_currency_distribution(), label="통화별 분포")
                gr.Plot(plot_payment_method_distribution())
            
            # 4. 일별 결제 추이
            gr.Markdown("### 📈 일별 결제 추이")
            with gr.Row():
                gr.Plot(plot_daily_payment_trend(30))
                gr.Plot(plot_daily_payment_count(30))
            
            # 5. 월별 수익 추이
            gr.Markdown("### 📊 월별 수익 추이")
            gr.Plot(plot_monthly_revenue())
            
            # 6. 유저별 결제 내역 검색
            gr.Markdown("### 🔍 유저별 결제 내역 검색")
            with gr.Row():
                payment_user_id = gr.Textbox(label="디스코드 유저 ID 입력", value="")
                payment_search_btn = gr.Button("결제 내역 조회")
                payment_user_out = gr.Dataframe(label="유저 결제 내역")
                payment_search_btn.click(get_user_payment_history, inputs=payment_user_id, outputs=payment_user_out)

    demo.launch(share=True)