import asyncio
import os
from typing import Dict, Any, Optional, Callable
from telethon import TelegramClient, events
from telethon.tl.types import User as TelegramUser
import logging
from datetime import datetime
import random

from models import Message, MessageType, Conversation, User

logger = logging.getLogger(__name__)

class TelegramManager:
    """Менеджер для работы с Telegram Client API"""
    
    def __init__(self, api_id: int, api_hash: str, phone: str, session_name: str = "stas_bot"):
        self.api_id = api_id
        self.api_hash = api_hash  
        self.phone = phone
        self.session_name = session_name
        
        self.client = None
        self.is_connected = False
        
        # Колбэки для обработки событий
        self.message_handlers: Dict[str, Callable] = {}
        
        # Анти-бан настройки
        self.last_message_time: Dict[int, datetime] = {}
        self.min_delay = 30  # минимальная задержка между сообщениями (сек)
        self.max_delay = 180  # максимальная задержка
        
    async def initialize(self):
        """Инициализация и подключение к Telegram"""
        try:
            self.client = TelegramClient(
                f'/app/backend/sessions/{self.session_name}', 
                self.api_id, 
                self.api_hash
            )
            
            await self.client.start(phone=self.phone)
            self.is_connected = True
            
            # Регистрируем обработчики событий
            self.client.add_event_handler(self._handle_new_message, events.NewMessage(incoming=True))
            
            logger.info("Telegram client successfully initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize Telegram client: {e}")
            raise
    
    async def _handle_new_message(self, event):
        """Обработчик входящих сообщений"""
        try:
            # Получаем информацию о сообщении
            message = event.message
            sender = await event.get_sender()
            chat = await event.get_chat()
            
            if not isinstance(sender, TelegramUser):
                return
                
            # Создаем объект сообщения
            msg_data = {
                'telegram_user_id': sender.id,
                'telegram_chat_id': chat.id,
                'telegram_message_id': message.id,
                'content': message.text or '',
                'message_type': self._determine_message_type(message),
                'sender_username': sender.username,
                'sender_first_name': sender.first_name,
                'sender_last_name': sender.last_name,
                'timestamp': message.date
            }
            
            # Вызываем обработчик сообщений если есть
            if 'new_message' in self.message_handlers:
                await self.message_handlers['new_message'](msg_data)
                
        except Exception as e:
            logger.error(f"Error handling new message: {e}")
    
    def _determine_message_type(self, message) -> MessageType:
        """Определяет тип сообщения"""
        if message.photo:
            return MessageType.PHOTO
        elif message.voice:
            return MessageType.VOICE
        elif message.video:
            return MessageType.VIDEO
        elif message.sticker:
            return MessageType.STICKER
        else:
            return MessageType.TEXT
    
    async def send_message(self, chat_id: int, content: str, reply_to_msg_id: Optional[int] = None) -> Dict[str, Any]:
        """Отправляет сообщение с защитой от бана"""
        try:
            if not self.is_connected:
                raise Exception("Telegram client not connected")
            
            # Проверяем анти-бан задержку
            await self._apply_anti_ban_delay(chat_id)
            
            # Имитируем набор текста
            await self._simulate_typing(chat_id, content)
            
            # Отправляем сообщение
            sent_message = await self.client.send_message(
                entity=chat_id,
                message=content,
                reply_to=reply_to_msg_id
            )
            
            # Обновляем время последнего сообщения
            self.last_message_time[chat_id] = datetime.utcnow()
            
            logger.info(f"Message sent to {chat_id}: {content[:50]}...")
            
            return {
                'success': True,
                'message_id': sent_message.id,
                'sent_at': sent_message.date
            }
            
        except Exception as e:
            logger.error(f"Failed to send message to {chat_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _apply_anti_ban_delay(self, chat_id: int):
        """Применяет задержку для защиты от бана"""
        if chat_id in self.last_message_time:
            last_time = self.last_message_time[chat_id]
            time_passed = (datetime.utcnow() - last_time).total_seconds()
            
            if time_passed < self.min_delay:
                delay = self.min_delay - time_passed + random.randint(0, 30)
                logger.info(f"Anti-ban delay: {delay:.1f} seconds")
                await asyncio.sleep(delay)
    
    async def _simulate_typing(self, chat_id: int, content: str):
        """Имитирует набор текста"""
        try:
            # Включаем индикатор набора текста
            async with self.client.action(chat_id, 'typing'):
                # Задержка пропорциональная длине сообщения (1-3 сек на 100 символов)
                typing_duration = min(len(content) / 50, 5.0) + random.uniform(0.5, 2.0)
                await asyncio.sleep(typing_duration)
                
        except Exception as e:
            logger.warning(f"Could not simulate typing: {e}")
    
    async def get_chat_info(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """Получает информацию о чате"""
        try:
            entity = await self.client.get_entity(chat_id)
            
            return {
                'id': entity.id,
                'username': getattr(entity, 'username', None),
                'first_name': getattr(entity, 'first_name', None),
                'last_name': getattr(entity, 'last_name', None),
                'phone': getattr(entity, 'phone', None),
                'is_self': getattr(entity, 'is_self', False)
            }
            
        except Exception as e:
            logger.error(f"Failed to get chat info for {chat_id}: {e}")
            return None
    
    async def mark_as_read(self, chat_id: int, message_ids: list = None):
        """Отмечает сообщения как прочитанные"""
        try:
            await self.client.send_read_acknowledge(chat_id, message_ids)
            logger.debug(f"Marked messages as read in chat {chat_id}")
            
        except Exception as e:
            logger.warning(f"Could not mark messages as read: {e}")
    
    async def get_message_history(self, chat_id: int, limit: int = 50) -> list:
        """Получает историю сообщений"""
        try:
            messages = []
            async for message in self.client.iter_messages(chat_id, limit=limit):
                messages.append({
                    'id': message.id,
                    'content': message.text or '',
                    'date': message.date,
                    'from_id': message.from_id.user_id if message.from_id else None,
                    'is_outgoing': message.out
                })
            
            return messages
            
        except Exception as e:
            logger.error(f"Failed to get message history for {chat_id}: {e}")
            return []
    
    def add_message_handler(self, handler_name: str, callback: Callable):
        """Добавляет обработчик сообщений"""
        self.message_handlers[handler_name] = callback
    
    async def disconnect(self):
        """Отключение от Telegram"""
        try:
            if self.client and self.is_connected:
                await self.client.disconnect()
                self.is_connected = False
                logger.info("Telegram client disconnected")
                
        except Exception as e:
            logger.error(f"Error disconnecting Telegram client: {e}")
    
    async def run_until_disconnected(self):
        """Запуск клиента до отключения"""
        if self.client and self.is_connected:
            await self.client.run_until_disconnected()

class TelegramConfig:
    """Конфигурация Telegram API"""
    
    @staticmethod
    def from_env() -> Dict[str, Any]:
        """Загружает конфигурацию из переменных окружения"""
        return {
            'api_id': int(os.environ.get('TELEGRAM_API_ID', '0')),
            'api_hash': os.environ.get('TELEGRAM_API_HASH', ''),
            'phone': os.environ.get('TELEGRAM_PHONE', ''),
            'session_name': os.environ.get('TELEGRAM_SESSION', 'stas_bot')
        }
    
    @staticmethod
    def is_valid(config: Dict[str, Any]) -> bool:
        """Проверяет валидность конфигурации"""
        required_fields = ['api_id', 'api_hash', 'phone']
        return all(config.get(field) for field in required_fields) and config['api_id'] > 0