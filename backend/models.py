from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
import uuid

class ConversationStage(str, Enum):
    INTRODUCTION = "introduction"  # День 1-2: знакомство
    FATHER_INCIDENT = "father_incident"  # День 3: инсульт отца
    WORK_OFFER = "work_offer"  # День 5: предложение помощи по работе
    HUMAN_TAKEOVER = "human_takeover"  # Передача человеку
    CLOSED = "closed"  # Диалог закрыт

class HandoffTrigger(str, Enum):
    WORK_INTEREST = "work_interest"  # Интересуется работой
    AGREED_TO_HELP = "agreed_to_help"  # Согласилась помочь
    UNEMPLOYED = "unemployed"  # Не работает и не учится
    NO_RESPONSE = "no_response"  # Долго не отвечает

class MessageType(str, Enum):
    TEXT = "text"
    PHOTO = "photo"
    VOICE = "voice"
    STICKER = "sticker"
    VIDEO = "video"

# Базовые модели
class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    telegram_user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    
    # Информация о девушке
    location: Optional[str] = None
    work_status: Optional[str] = None  # работает/учится/не работает
    work_description: Optional[str] = None
    salary_satisfaction: Optional[str] = None
    relationship_status: Optional[str] = None
    
    # Психологический профиль
    interests: List[str] = []
    personality_traits: List[str] = []
    vulnerabilities: List[str] = []
    communication_style: Optional[str] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str
    sender: str  # "user" или "stas" 
    message_type: MessageType = MessageType.TEXT
    content: str
    telegram_message_id: Optional[int] = None
    
    # Метаданные
    is_read: bool = False
    response_time_seconds: Optional[int] = None  # время ответа на предыдущее сообщение
    
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Conversation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    telegram_chat_id: int
    
    # Состояние диалога
    current_stage: ConversationStage = ConversationStage.INTRODUCTION
    stage_started_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True
    
    # История сообщений
    messages: List[Message] = []
    
    # Статистика для обучения
    total_messages: int = 0
    avg_response_time: Optional[float] = None
    engagement_score: float = 0.0  # 0-100
    last_user_message_at: Optional[datetime] = None
    last_ai_message_at: Optional[datetime] = None
    
    # Триггеры
    handoff_triggered: bool = False
    handoff_reason: Optional[HandoffTrigger] = None
    handoff_at: Optional[datetime] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class ConversationContext(BaseModel):
    """Контекст для генерации ответов ИИ"""
    conversation_id: str
    user_info: User
    current_stage: ConversationStage
    recent_messages: List[Message]
    
    # Динамический контекст
    time_of_day: str
    days_since_start: int
    user_mood_indicator: Optional[str] = None
    last_topic: Optional[str] = None

class LearningData(BaseModel):
    """Данные для машинного обучения"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str
    
    # Метрики успешности
    stage_transition_success: bool = False
    user_engagement_level: int  # 1-10
    response_rate: float  # процент ответов пользователя
    avg_response_time: float  # среднее время ответа пользователя
    conversation_duration_days: float
    
    # Успешные паттерны
    successful_phrases: List[str] = []
    successful_topics: List[str] = []
    optimal_message_timing: List[Dict[str, Any]] = []
    
    # Неуспешные паттерны  
    failed_phrases: List[str] = []
    ignored_messages: List[str] = []
    
    final_outcome: Optional[str] = None  # "handoff", "closed", "active"
    created_at: datetime = Field(default_factory=datetime.utcnow)

# API модели
class MessageCreate(BaseModel):
    content: str
    message_type: MessageType = MessageType.TEXT

class ConversationResponse(BaseModel):
    conversation: Conversation
    suggested_response: Optional[str] = None
    next_action: Optional[str] = None
    should_handoff: bool = False
    handoff_reason: Optional[str] = None

class StasPersona(BaseModel):
    """Персонаж Стаса"""
    name: str = "Стас"
    age: int = 29
    location: str = "Москва"
    work: str = "Криптотрейдинг и инвестиции"
    
    # Биография
    relationship_history: str = "Девушка умерла при родах"
    father_location: str = "Анталья, Турция"
    
    # Характер
    personality: List[str] = [
        "Заботливый", "Внимательный", "Успешный", 
        "Немного загадочный", "Щедрый", "Романтичный"
    ]
    
    # Паттерны общения
    morning_greetings: List[str] = [
        "Доброе утро ☀️",
        "Привет, как спалось?",
        "Утро! Как настроение?"
    ]
    
    evening_greetings: List[str] = [
        "Добрый вечер 🌙", 
        "Привет, как дела?",
        "Вечер! Как прошёл день?"
    ]
    
    support_phrases: List[str] = [
        "Понимаю тебя",
        "Ты молодец",
        "Всё у тебя получится",
        "Я в тебя верю"
    ]