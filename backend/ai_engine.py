import asyncio
import random
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from emergentintegrations.llm.chat import LlmChat, UserMessage
import os
from dotenv import load_dotenv

from models import (
    Conversation, ConversationContext, ConversationStage, 
    Message, User, MessageType, HandoffTrigger, StasPersona
)

load_dotenv()

class AIConversationEngine:
    def __init__(self):
        self.llm_key = os.environ.get('EMERGENT_LLM_KEY')
        self.stas_persona = StasPersona()
        
        # Системный промпт для разных стадий
        self.stage_prompts = {
            ConversationStage.INTRODUCTION: self._get_introduction_prompt(),
            ConversationStage.FATHER_INCIDENT: self._get_father_incident_prompt(),
            ConversationStage.WORK_OFFER: self._get_work_offer_prompt()
        }
        
        # Паузы между сообщениями (в секундах)
        self.min_response_delay = 30  # минимум 30 сек
        self.max_response_delay = 180  # максимум 3 мин
        
        # Пороги перехода между этапами (количество сообщений)
        self.stage_thresholds = {
            ConversationStage.INTRODUCTION: 8,  # 3-8 сообщений
            ConversationStage.FATHER_INCIDENT: 15,  # 8-15 сообщений  
            ConversationStage.WORK_OFFER: 999  # 15+ сообщений до триггера
        }
        
    def _get_introduction_prompt(self) -> str:
        return f"""Ты - {self.stas_persona.name}, {self.stas_persona.age} лет, живешь в {self.stas_persona.location}.

БИОГРАФИЯ:
- Родился в Греции в русско-греческой семье (отец грек, мама русская)
- Детство провел в путешествиях - семья работала в гостиничном бизнесе
- Учился в 6 школах в разных странах, что сделало тебя открытым и адаптивным
- Образование: МГУ, юридический факультет
- Работа: 6 лет в криптосфере, до этого промышленный альпинизм и стройка
- Семья: отец сейчас в Анталье (Турция), мать в Мадриде (Испания)
- Личное: отношения длились 6 лет, девушка забеременела и умерла при родах, после этого пауза 2 года

ЭТАП 1: ЗНАКОМСТВО (3-8 сообщений)
Цель: Познакомиться, выяснить работает ли/учится, вызвать симпатию.

Что делать:
- Спроси как дела, чем занимается
- Расскажи что работаешь криптотрейдером
- Узнай про её работу (КРИТИЧЕСКИ ВАЖНО!)
- Общайся легко, флиртуй немного

Стиль:
- Копируй её стиль общения (эмодзи, длина сообщений)
- Будь заинтересованным в её жизни
- Поддерживай её эмоции

ТРИГГЕРЫ ОСТАНОВКИ (передать человеку):
- "Расскажи, чем занимаешься" 
- "Что такое трейдинг?"
- "Можешь научить?"
- "Хочу тоже зарабатывать"
- "Не работаю нигде" / "Не учусь" (закрыть диалог)

Отвечай ТОЛЬКО как Стас, коротко и естественно (1-2 предложения)."""

    def _get_father_incident_prompt(self) -> str:
        return f"""Ты - {self.stas_persona.name}. Переходим ко второму этапу.

ЭТАП 2: УГЛУБЛЕНИЕ + ИСТОРИЯ С ОТЦОМ (8-15 сообщений)
Ситуация: Ты уже немного знаком с девушкой, пора углублять отношения.

Что делать:
- Задавай личные вопросы (семья, планы, мечты)
- В определенный момент ИСЧЕЗНИ на несколько минут (не отвечай)
- Потом вернись с: "Извини что не писал, отец попал в больницу в Турции"
- Если спросит подробности: инсульт, сейчас в больнице в Анталье

ВАЖНО:
- НЕ драматизируй сильно
- Это способ вызвать сочувствие и углубить доверие  
- Благодари за поддержку
- Продолжай узнавать о её работе и жизни

Твоё настроение: немного встревоженный, но держишься, благодарен за её поддержку.

ТРИГГЕРЫ ОСТАНОВКИ:
- Любые вопросы о твоей работе/криптовалютах
- "Расскажи, чем занимаешься"
- "Хочу тоже зарабатывать"

Отвечай коротко, по-человечески."""

    def _get_work_offer_prompt(self) -> str:
        return f"""Ты - {self.stas_persona.name}. Через 2 дня после истории с отцом.

ЭТАП 3: ПРЕДЛОЖЕНИЕ ПОМОЩИ ПО РАБОТЕ (День 5)
Цель: Предложить помощь по работе, если она работает/учится.

Сценарий:
- "Слушай, ты сейчас не занята? Можешь помочь кое в чём по работе?"
- Делай это когда она свободна (после работы)
- Если соглашается - уточни: "Наберёшь тогда?"

ТРИГГЕРЫ ПЕРЕДАЧИ ЧЕЛОВЕКУ:
- Любой ответ на предложение помощи (да/нет) - ОСТАНОВИСЬ
- Вопросы о твоей работе - ОСТАНОВИСЬ

Если не работает/не учится - СВЕРНИ общение вежливо.

Отвечай коротко."""

    async def generate_response(self, context: ConversationContext) -> Dict[str, Any]:
        """Генерирует ответ ИИ на основе контекста"""
        
        # Проверяем триггеры передачи человеку
        handoff_check = self._check_handoff_triggers(context)
        if handoff_check["should_handoff"]:
            return handoff_check
            
        # Определяем системный промпт
        system_prompt = self.stage_prompts.get(
            context.current_stage, 
            self.stage_prompts[ConversationStage.INTRODUCTION]
        )
        
        # Строим контекст сообщений
        messages_context = self._build_messages_context(context.recent_messages)
        user_info_context = self._build_user_info_context(context.user_info)
        
        # Добавляем временной контекст
        time_context = f"Время: {context.time_of_day}, {context.days_since_start} день общения"
        
        full_prompt = f"{system_prompt}\n\n{user_info_context}\n{time_context}\n{messages_context}"
        
        try:
            # Создаем чат с LLM
            chat = LlmChat(
                api_key=self.llm_key,
                session_id=context.conversation_id,
                system_message=system_prompt
            ).with_model("openai", "gpt-3.5-turbo")
            
            # Отправляем запрос
            user_message = UserMessage(text=full_prompt)
            response = await chat.send_message(user_message)
            
            # Определяем следующее действие
            next_action = self._determine_next_action(context)
            
            return {
                "response": response.strip(),
                "should_handoff": False,
                "next_action": next_action,
                "delay_seconds": random.randint(self.min_response_delay, self.max_response_delay)
            }
            
        except Exception as e:
            # Fallback ответы
            fallback_response = self._get_fallback_response(context)
            return {
                "response": fallback_response,
                "should_handoff": False,
                "next_action": "continue",
                "delay_seconds": 60,
                "error": str(e)
            }
    
    def _check_handoff_triggers(self, context: ConversationContext) -> Dict[str, Any]:
        """Проверяет условия передачи человеку"""
        
        if not context.recent_messages:
            return {"should_handoff": False}
            
        last_message = context.recent_messages[-1]
        if last_message.sender != "user":
            return {"should_handoff": False}
            
        content = last_message.content.lower()
        
        # Проверяем ключевые фразы
        work_interest_phrases = [
            "расскажи, чем занимаешься", "хочу попробовать", "научи", 
            "можно тоже так зарабатывать", "как ты зарабатываешь", 
            "что за работа", "криптовалюта", "трейдинг", "инвестиции"
        ]
        
        help_agreement_phrases = [
            "да, помогу", "конечно", "наберу", "да", "согласна", 
            "хорошо", "давай", "буду рада помочь"
        ]
        
        # Триггер: интерес к работе
        for phrase in work_interest_phrases:
            if phrase in content:
                return {
                    "should_handoff": True,
                    "handoff_reason": HandoffTrigger.WORK_INTEREST,
                    "message": "🔄 Девушка заинтересовалась работой. Передаю человеку."
                }
        
        # Триггер: согласие помочь (только на этапе предложения работы)
        if context.current_stage == ConversationStage.WORK_OFFER:
            for phrase in help_agreement_phrases:
                if phrase in content:
                    return {
                        "should_handoff": True,
                        "handoff_reason": HandoffTrigger.AGREED_TO_HELP,
                        "message": "🔄 Девушка согласилась помочь. Передаю человеку."
                    }
        
        # Триггер: не работает и не учится
        if context.user_info.work_status == "unemployed":
            return {
                "should_handoff": True,
                "handoff_reason": HandoffTrigger.UNEMPLOYED,
                "message": "❌ Девушка не работает и не учится. Сворачиваю общение."
            }
            
        return {"should_handoff": False}
    
    def _build_messages_context(self, messages: List[Message]) -> str:
        """Строит контекст последних сообщений"""
        context = "Последние сообщения:\n"
        
        for msg in messages[-10:]:  # берем последние 10 сообщений
            sender = "Девушка" if msg.sender == "user" else "Ты"
            context += f"{sender}: {msg.content}\n"
            
        return context
    
    def _build_user_info_context(self, user: User) -> str:
        """Строит контекст информации о пользователе"""
        info = f"Информация о девушке:\n"
        
        if user.first_name:
            info += f"Имя: {user.first_name}\n"
        if user.location:
            info += f"Город: {user.location}\n"
        if user.work_status:
            info += f"Работа/учеба: {user.work_status}\n"
        if user.work_description:
            info += f"Описание работы: {user.work_description}\n"
        if user.interests:
            info += f"Интересы: {', '.join(user.interests)}\n"
        if user.communication_style:
            info += f"Стиль общения: {user.communication_style}\n"
            
        return info
    
    def _determine_next_action(self, context: ConversationContext) -> str:
        """Определяет следующее действие"""
        
        # Проверяем прогрессию по стадиям
        days_passed = context.days_since_start
        
        if context.current_stage == ConversationStage.INTRODUCTION and days_passed >= 3:
            return "transition_to_father_incident"
        elif context.current_stage == ConversationStage.FATHER_INCIDENT and days_passed >= 5:
            if context.user_info.work_status and context.user_info.work_status != "unemployed":
                return "transition_to_work_offer"
            else:
                return "close_conversation"
        
        return "continue_conversation"
    
    def _get_fallback_response(self, context: ConversationContext) -> str:
        """Возвращает резервный ответ при ошибке LLM"""
        
        time_of_day = context.time_of_day.lower()
        
        if "утро" in time_of_day:
            return random.choice(self.stas_persona.morning_greetings)
        elif "вечер" in time_of_day or "ночь" in time_of_day:
            return random.choice(self.stas_persona.evening_greetings)
        else:
            return random.choice([
                "Как дела? 😊",
                "Что делаешь?",
                "Как настроение?",
                "Расскажи, как проходит день"
            ])
    
    async def should_send_proactive_message(self, conversation: Conversation) -> Dict[str, Any]:
        """Определяет, нужно ли отправить проактивное сообщение"""
        
        now = datetime.utcnow()
        
        # Утреннее сообщение (6:00-10:00)
        if 6 <= now.hour <= 10:
            if not conversation.last_ai_message_at or \
               conversation.last_ai_message_at.date() < now.date():
                return {
                    "should_send": True,
                    "message_type": "morning_greeting",
                    "content": random.choice(self.stas_persona.morning_greetings)
                }
        
        # Вечернее сообщение (20:00-24:00)
        elif 20 <= now.hour <= 23:
            if not conversation.last_ai_message_at or \
               (now - conversation.last_ai_message_at).total_seconds() > 3600*4:  # 4 часа
                return {
                    "should_send": True,
                    "message_type": "evening_greeting", 
                    "content": random.choice(self.stas_persona.evening_greetings)
                }
        
        # Проверка на прочитанное сообщение без ответа
        if conversation.last_user_message_at:
            time_since_last = (now - conversation.last_user_message_at).total_seconds()
            if time_since_last > 3600:  # 1 час
                return {
                    "should_send": True,
                    "message_type": "follow_up",
                    "content": "Занята? 🤔"
                }
        
        return {"should_send": False}