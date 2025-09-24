import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
import random

from models import (
    Conversation, User, Message, ConversationContext, ConversationStage,
    MessageType, HandoffTrigger, LearningData
)
from ai_engine import AIConversationEngine
from telegram_client import TelegramManager

logger = logging.getLogger(__name__)

class ConversationService:
    """Основной сервис для управления диалогами"""
    
    def __init__(self, db: AsyncIOMotorDatabase, telegram_manager: TelegramManager):
        self.db = db
        self.telegram = telegram_manager
        self.ai_engine = AIConversationEngine()
        
        # Активные диалоги
        self.active_conversations: Dict[int, str] = {}  # chat_id -> conversation_id
        
        # Обработчики событий
        self.telegram.add_message_handler('new_message', self.handle_incoming_message)
        
    async def handle_incoming_message(self, msg_data: Dict[str, Any]):
        """Обрабатывает входящее сообщение от пользователя"""
        try:
            chat_id = msg_data['telegram_chat_id']
            user_id = msg_data['telegram_user_id']
            
            # Получаем или создаем пользователя
            user = await self.get_or_create_user(msg_data)
            
            # Получаем или создаем диалог
            conversation = await self.get_or_create_conversation(user.id, chat_id)
            
            # Проверяем, активен ли диалог
            if not conversation.is_active or conversation.handoff_triggered:
                logger.info(f"Conversation {conversation.id} is not active, skipping AI response")
                return
            
            # Сохраняем сообщение пользователя
            user_message = Message(
                conversation_id=conversation.id,
                sender="user",
                content=msg_data['content'],
                message_type=msg_data['message_type'],
                telegram_message_id=msg_data['telegram_message_id']
            )
            
            await self.save_message(user_message)
            
            # Обновляем статистику диалога
            await self.update_conversation_stats(conversation.id, user_message)
            
            # Генерируем ответ ИИ
            await self.generate_and_send_ai_response(conversation.id, user.id)
            
        except Exception as e:
            logger.error(f"Error handling incoming message: {e}")
    
    async def get_or_create_user(self, msg_data: Dict[str, Any]) -> User:
        """Получает существующего или создает нового пользователя"""
        user_id = msg_data['telegram_user_id']
        
        # Ищем существующего пользователя
        existing_user = await self.db.users.find_one({"telegram_user_id": user_id})
        
        if existing_user:
            return User(**existing_user)
        
        # Создаем нового пользователя
        new_user = User(
            telegram_user_id=user_id,
            username=msg_data.get('sender_username'),
            first_name=msg_data.get('sender_first_name'),
            last_name=msg_data.get('sender_last_name')
        )
        
        await self.db.users.insert_one(new_user.dict())
        logger.info(f"Created new user: {new_user.id}")
        
        return new_user
    
    async def get_or_create_conversation(self, user_id: str, chat_id: int) -> Conversation:
        """Получает существующий или создает новый диалог"""
        
        # Ищем активный диалог
        existing_conv = await self.db.conversations.find_one({
            "user_id": user_id,
            "telegram_chat_id": chat_id,
            "is_active": True
        })
        
        if existing_conv:
            return Conversation(**existing_conv)
        
        # Создаем новый диалог
        new_conversation = Conversation(
            user_id=user_id,
            telegram_chat_id=chat_id,
            current_stage=ConversationStage.INTRODUCTION
        )
        
        await self.db.conversations.insert_one(new_conversation.dict())
        self.active_conversations[chat_id] = new_conversation.id
        
        logger.info(f"Created new conversation: {new_conversation.id}")
        
        return new_conversation
    
    async def save_message(self, message: Message):
        """Сохраняет сообщение в базе данных"""
        await self.db.messages.insert_one(message.dict())
        
        # Обновляем диалог с новым сообщением и счетчиками
        update_data = {
            "$push": {"messages": message.dict()},
            "$inc": {
                "total_messages": 1,
                "stage_message_count": 1 if message.sender == "user" else 0  # считаем только сообщения пользователя
            },
            "$set": {
                "last_user_message_at" if message.sender == "user" else "last_ai_message_at": message.created_at,
                "updated_at": datetime.utcnow()
            }
        }
        
        await self.db.conversations.update_one(
            {"id": message.conversation_id},
            update_data
        )
    
    async def generate_and_send_ai_response(self, conversation_id: str, user_id: str):
        """Генерирует и отправляет ответ ИИ"""
        try:
            # Получаем контекст для ИИ
            context = await self.build_conversation_context(conversation_id, user_id)
            
            # Генерируем ответ
            ai_response = await self.ai_engine.generate_response(context)
            
            # Проверяем, нужна ли передача человеку
            if ai_response.get("should_handoff"):
                await self.trigger_handoff(
                    conversation_id, 
                    ai_response.get("handoff_reason"),
                    ai_response.get("message", "Передача человеку")
                )
                return
            
            # Ждем задержку для натуральности
            delay = ai_response.get("delay_seconds", 60)
            await asyncio.sleep(delay)
            
            # Отправляем сообщение через Telegram
            conversation = await self.get_conversation(conversation_id)
            
            send_result = await self.telegram.send_message(
                conversation.telegram_chat_id,
                ai_response["response"]
            )
            
            if send_result["success"]:
                # Сохраняем сообщение ИИ
                ai_message = Message(
                    conversation_id=conversation_id,
                    sender="stas",
                    content=ai_response["response"],
                    telegram_message_id=send_result.get("message_id")
                )
                
                await self.save_message(ai_message)
                
                # Обрабатываем следующие действия
                await self.process_next_action(conversation_id, ai_response.get("next_action"))
                
            else:
                logger.error(f"Failed to send AI response: {send_result.get('error')}")
                
        except Exception as e:
            logger.error(f"Error generating AI response: {e}")
    
    async def build_conversation_context(self, conversation_id: str, user_id: str) -> ConversationContext:
        """Строит контекст для генерации ответа ИИ"""
        
        # Получаем данные
        conversation = await self.get_conversation(conversation_id)
        user = await self.get_user(user_id)
        recent_messages = await self.get_recent_messages(conversation_id, limit=20)
        
        # Определяем время суток
        now = datetime.utcnow()
        if 6 <= now.hour < 12:
            time_of_day = "утро"
        elif 12 <= now.hour < 18:
            time_of_day = "день"
        elif 18 <= now.hour < 22:
            time_of_day = "вечер"
        else:
            time_of_day = "ночь"
        
        # Считаем дни с начала общения
        days_since_start = (now - conversation.created_at).days + 1
        
        return ConversationContext(
            conversation_id=conversation_id,
            user_info=user,
            current_stage=conversation.current_stage,
            recent_messages=recent_messages,
            time_of_day=time_of_day,
            days_since_start=days_since_start
        )
    
    async def process_next_action(self, conversation_id: str, action: Optional[str]):
        """Обрабатывает следующие действия в диалоге"""
        if not action:
            return
            
        if action == "transition_to_father_incident":
            await self.transition_to_stage(conversation_id, ConversationStage.FATHER_INCIDENT)
            
        elif action == "transition_to_work_offer":
            await self.transition_to_stage(conversation_id, ConversationStage.WORK_OFFER)
            
        elif action == "close_conversation":
            await self.close_conversation(conversation_id, "Девушка не работает/не учится")
    
    async def transition_to_stage(self, conversation_id: str, new_stage: ConversationStage):
        """Переводит диалог на новую стадию"""
        await self.db.conversations.update_one(
            {"id": conversation_id},
            {
                "$set": {
                    "current_stage": new_stage.value,
                    "stage_started_at": datetime.utcnow(),
                    "stage_message_count": 0,  # сбрасываем счетчик сообщений для нового этапа
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        logger.info(f"Conversation {conversation_id} transitioned to stage: {new_stage.value}")
    
    async def trigger_handoff(self, conversation_id: str, reason: HandoffTrigger, message: str):
        """Передает диалог человеку"""
        await self.db.conversations.update_one(
            {"id": conversation_id},
            {
                "$set": {
                    "handoff_triggered": True,
                    "handoff_reason": reason.value if reason else None,
                    "handoff_at": datetime.utcnow(),
                    "current_stage": ConversationStage.HUMAN_TAKEOVER.value,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # TODO: Отправить уведомление в Telegram бот для операторов
        logger.info(f"Handoff triggered for conversation {conversation_id}: {reason}")
        
        # Отправляем уведомление в консоль (временно)
        print(f"🔄 HANDOFF ALERT: Conversation {conversation_id} - {message}")
    
    async def close_conversation(self, conversation_id: str, reason: str):
        """Закрывает диалог"""
        await self.db.conversations.update_one(
            {"id": conversation_id},
            {
                "$set": {
                    "is_active": False,
                    "current_stage": ConversationStage.CLOSED.value,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        logger.info(f"Conversation {conversation_id} closed: {reason}")
    
    async def update_conversation_stats(self, conversation_id: str, message: Message):
        """Обновляет статистику диалога"""
        conversation = await self.get_conversation(conversation_id)
        
        # Вычисляем время ответа если есть предыдущие сообщения
        response_time = None
        if conversation.last_ai_message_at and message.sender == "user":
            response_time = int((message.created_at - conversation.last_ai_message_at).total_seconds())
        
        # Обновляем среднее время ответа
        if response_time and conversation.avg_response_time:
            new_avg = (conversation.avg_response_time + response_time) / 2
        else:
            new_avg = response_time or conversation.avg_response_time
        
        # Вычисляем engagement score (простая метрика)
        engagement_score = min(100, conversation.total_messages * 2 + (50 if response_time and response_time < 300 else 0))
        
        await self.db.conversations.update_one(
            {"id": conversation_id},
            {
                "$set": {
                    "avg_response_time": new_avg,
                    "engagement_score": engagement_score,
                    "updated_at": datetime.utcnow()
                }
            }
        )
    
    async def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Получает диалог по ID"""
        conv_data = await self.db.conversations.find_one({"id": conversation_id})
        return Conversation(**conv_data) if conv_data else None
    
    async def get_user(self, user_id: str) -> Optional[User]:
        """Получает пользователя по ID"""
        user_data = await self.db.users.find_one({"id": user_id})
        return User(**user_data) if user_data else None
    
    async def get_recent_messages(self, conversation_id: str, limit: int = 10) -> List[Message]:
        """Получает последние сообщения диалога"""
        messages_data = await self.db.messages.find(
            {"conversation_id": conversation_id}
        ).sort("created_at", -1).limit(limit).to_list(limit)
        
        # Возвращаем в хронологическом порядке
        return [Message(**msg) for msg in reversed(messages_data)]
    
    async def check_proactive_messages(self):
        """Проверяет необходимость отправки проактивных сообщений"""
        try:
            # Получаем все активные диалоги
            active_conversations = await self.db.conversations.find({
                "is_active": True,
                "handoff_triggered": False
            }).to_list(100)
            
            for conv_data in active_conversations:
                conversation = Conversation(**conv_data)
                
                # Проверяем, нужно ли отправить проактивное сообщение
                proactive_check = await self.ai_engine.should_send_proactive_message(conversation)
                
                if proactive_check.get("should_send"):
                    # Отправляем проактивное сообщение
                    send_result = await self.telegram.send_message(
                        conversation.telegram_chat_id,
                        proactive_check["content"]
                    )
                    
                    if send_result["success"]:
                        # Сохраняем проактивное сообщение
                        proactive_message = Message(
                            conversation_id=conversation.id,
                            sender="stas",
                            content=proactive_check["content"],
                            telegram_message_id=send_result.get("message_id")
                        )
                        
                        await self.save_message(proactive_message)
                        
                        logger.info(f"Sent proactive message to conversation {conversation.id}")
                        
                        # Задержка между проактивными сообщениями
                        await asyncio.sleep(random.randint(60, 300))
                        
        except Exception as e:
            logger.error(f"Error checking proactive messages: {e}")
    
    async def start_background_tasks(self):
        """Запускает фоновые задачи"""
        # Задача для проверки проактивных сообщений каждые 30 минут
        async def proactive_checker():
            while True:
                await asyncio.sleep(1800)  # 30 минут
                await self.check_proactive_messages()
        
        asyncio.create_task(proactive_checker())
        logger.info("Background tasks started")
    
    # API методы для фронтенда
    async def get_conversations_list(self, limit: int = 50, skip: int = 0) -> List[Dict[str, Any]]:
        """Получает список диалогов для дашборда"""
        conversations = await self.db.conversations.find().sort("updated_at", -1).skip(skip).limit(limit).to_list(limit)
        
        result = []
        for conv_data in conversations:
            conv = Conversation(**conv_data)
            user = await self.get_user(conv.user_id)
            
            result.append({
                "id": conv.id,
                "user_name": f"{user.first_name or ''} {user.last_name or ''}".strip() if user else "Unknown",
                "current_stage": conv.current_stage.value,
                "is_active": conv.is_active,
                "total_messages": conv.total_messages,
                "engagement_score": conv.engagement_score,
                "last_message_at": conv.last_user_message_at or conv.last_ai_message_at,
                "handoff_triggered": conv.handoff_triggered,
                "created_at": conv.created_at
            })
        
        return result
    
    async def get_conversation_details(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Получает детали диалога"""
        conversation = await self.get_conversation(conversation_id)
        if not conversation:
            return None
            
        user = await self.get_user(conversation.user_id)
        messages = await self.get_recent_messages(conversation_id, limit=100)
        
        return {
            "conversation": conversation.dict(),
            "user": user.dict() if user else None,
            "messages": [msg.dict() for msg in messages]
        }