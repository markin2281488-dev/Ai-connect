from fastapi import FastAPI, APIRouter, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime
import asyncio

# Импорты наших модулей
from models import (
    Conversation, User, Message, ConversationContext, 
    ConversationStage, MessageType, HandoffTrigger
)
from conversation_service import ConversationService
from telegram_client import TelegramManager, TelegramConfig
from ai_engine import AIConversationEngine

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Подключение к MongoDB
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Создание приложения FastAPI
app = FastAPI(title="AI Conversation System", version="1.0.0")
api_router = APIRouter(prefix="/api")

# Глобальные сервисы
conversation_service: Optional[ConversationService] = None
telegram_manager: Optional[TelegramManager] = None

# CORS настройки
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# API модели
class TelegramConfigModel(BaseModel):
    api_id: int
    api_hash: str
    phone: str
    session_name: str = "stas_bot"

class MessageSendModel(BaseModel):
    conversation_id: str
    content: str

class ConversationUpdateModel(BaseModel):
    stage: Optional[str] = None
    is_active: Optional[bool] = None

# API эндпоинты
@api_router.get("/")
async def root():
    return {"message": "AI Conversation System API", "status": "running"}

@api_router.post("/telegram/configure")
async def configure_telegram(config: TelegramConfigModel):
    """Настройка подключения к Telegram"""
    global telegram_manager, conversation_service
    
    try:
        # Создаем менеджер Telegram
        telegram_manager = TelegramManager(
            api_id=config.api_id,
            api_hash=config.api_hash,
            phone=config.phone,
            session_name=config.session_name
        )
        
        # Инициализируем подключение
        await telegram_manager.initialize()
        
        # Создаем сервис диалогов
        conversation_service = ConversationService(db, telegram_manager)
        
        # Запускаем фоновые задачи
        await conversation_service.start_background_tasks()
        
        return {"success": True, "message": "Telegram configured successfully"}
        
    except Exception as e:
        logger.error(f"Failed to configure Telegram: {e}")
        raise HTTPException(status_code=500, detail=f"Configuration failed: {str(e)}")

@api_router.get("/telegram/status")
async def get_telegram_status():
    """Статус подключения к Telegram"""
    if telegram_manager is None:
        return {"connected": False, "message": "Not configured"}
    
    return {
        "connected": telegram_manager.is_connected,
        "session_name": telegram_manager.session_name
    }

@api_router.get("/conversations")
async def get_conversations(limit: int = 50, skip: int = 0):
    """Получить список диалогов"""
    if conversation_service is None:
        raise HTTPException(status_code=400, detail="System not configured")
    
    try:
        conversations = await conversation_service.get_conversations_list(limit, skip)
        return {"conversations": conversations, "total": len(conversations)}
        
    except Exception as e:
        logger.error(f"Failed to get conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/conversations/{conversation_id}")
async def get_conversation_details(conversation_id: str):
    """Получить детали диалога"""
    if conversation_service is None:
        raise HTTPException(status_code=400, detail="System not configured")
    
    try:
        details = await conversation_service.get_conversation_details(conversation_id)
        if not details:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        return details
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get conversation details: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/conversations/{conversation_id}/message")
async def send_manual_message(conversation_id: str, message: MessageSendModel):
    """Отправить сообщение вручную (от оператора)"""
    if conversation_service is None:
        raise HTTPException(status_code=400, detail="System not configured")
    
    try:
        # Получаем диалог
        conversation = await conversation_service.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Отправляем сообщение
        send_result = await telegram_manager.send_message(
            conversation.telegram_chat_id,
            message.content
        )
        
        if not send_result["success"]:
            raise HTTPException(status_code=500, detail=send_result.get("error"))
        
        # Сохраняем сообщение как от человека-оператора
        manual_message = Message(
            conversation_id=conversation_id,
            sender="operator",
            content=message.content,
            telegram_message_id=send_result.get("message_id")
        )
        
        await conversation_service.save_message(manual_message)
        
        return {"success": True, "message_id": send_result.get("message_id")}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to send manual message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.patch("/conversations/{conversation_id}")
async def update_conversation(conversation_id: str, update: ConversationUpdateModel):
    """Обновить параметры диалога"""
    if conversation_service is None:
        raise HTTPException(status_code=400, detail="System not configured")
    
    try:
        update_data = {}
        
        if update.stage is not None:
            update_data["current_stage"] = update.stage
            
        if update.is_active is not None:
            update_data["is_active"] = update.is_active
            
        if update_data:
            update_data["updated_at"] = datetime.utcnow()
            
            result = await db.conversations.update_one(
                {"id": conversation_id},
                {"$set": update_data}
            )
            
            if result.matched_count == 0:
                raise HTTPException(status_code=404, detail="Conversation not found")
        
        return {"success": True, "updated_fields": list(update_data.keys())}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/conversations/{conversation_id}/handoff")
async def trigger_manual_handoff(conversation_id: str):
    """Ручная передача диалога человеку"""
    if conversation_service is None:
        raise HTTPException(status_code=400, detail="System not configured")
    
    try:
        await conversation_service.trigger_handoff(
            conversation_id,
            HandoffTrigger.WORK_INTEREST,  # По умолчанию
            "Ручная передача оператором"
        )
        
        return {"success": True, "message": "Conversation handed off to human"}
        
    except Exception as e:
        logger.error(f"Failed to trigger handoff: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/stats/overview")
async def get_stats_overview():
    """Общая статистика системы"""
    try:
        total_conversations = await db.conversations.count_documents({})
        active_conversations = await db.conversations.count_documents({"is_active": True})
        handoff_conversations = await db.conversations.count_documents({"handoff_triggered": True})
        total_users = await db.users.count_documents({})
        
        # Статистика по стадиям
        stage_stats = {}
        for stage in ConversationStage:
            count = await db.conversations.count_documents({"current_stage": stage.value})
            stage_stats[stage.value] = count
        
        return {
            "total_conversations": total_conversations,
            "active_conversations": active_conversations,
            "handoff_conversations": handoff_conversations,
            "total_users": total_users,
            "stage_distribution": stage_stats,
            "system_status": {
                "telegram_connected": telegram_manager.is_connected if telegram_manager else False,
                "ai_engine_ready": True  # TODO: добавить проверку ИИ
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/system/check-proactive")
async def trigger_proactive_check():
    """Ручная проверка проактивных сообщений"""
    if conversation_service is None:
        raise HTTPException(status_code=400, detail="System not configured")
    
    try:
        await conversation_service.check_proactive_messages()
        return {"success": True, "message": "Proactive messages check completed"}
        
    except Exception as e:
        logger.error(f"Failed to check proactive messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Подключаем роутер
app.include_router(api_router)

# События приложения
@app.on_event("startup")
async def startup_event():
    """Инициализация при запуске"""
    logger.info("AI Conversation System starting up...")
    
    # Создаем директорию для сессий Telegram
    sessions_dir = Path('/app/backend/sessions')
    sessions_dir.mkdir(exist_ok=True)
    
    # Проверяем конфигурацию Telegram
    telegram_config = TelegramConfig.from_env()
    if TelegramConfig.is_valid(telegram_config):
        logger.info("Valid Telegram config found in environment, auto-configuring...")
        try:
            # Автоматическая настройка, если есть все данные
            config = TelegramConfigModel(**telegram_config)
            await configure_telegram(config)
            logger.info("Auto-configuration successful")
        except Exception as e:
            logger.warning(f"Auto-configuration failed: {e}")
            logger.info("Manual configuration will be required via API")
    else:
        logger.info("Telegram configuration not found, manual setup required")

@app.on_event("shutdown")
async def shutdown_event():
    """Очистка при завершении"""
    global telegram_manager, conversation_service
    
    logger.info("AI Conversation System shutting down...")
    
    if telegram_manager:
        await telegram_manager.disconnect()
    
    if client:
        client.close()
        
    logger.info("Shutdown complete")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)