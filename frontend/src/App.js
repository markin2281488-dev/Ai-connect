import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './App.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

function App() {
  const [systemStatus, setSystemStatus] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [stats, setStats] = useState(null);
  const [telegramConfig, setTelegramConfig] = useState({
    api_id: '',
    api_hash: '',
    phone: ''
  });
  const [loading, setLoading] = useState(false);
  const [selectedConversation, setSelectedConversation] = useState(null);
  const [activeTab, setActiveTab] = useState('dashboard');

  useEffect(() => {
    loadSystemData();
  }, []);

  const loadSystemData = async () => {
    try {
      setLoading(true);
      
      // Загружаем статус системы
      const statusRes = await axios.get(`${API}/telegram/status`);
      setSystemStatus(statusRes.data);
      
      // Загружаем статистику
      const statsRes = await axios.get(`${API}/stats/overview`);
      setStats(statsRes.data);
      
      // Если Telegram подключен, загружаем диалоги
      if (statusRes.data.connected) {
        const conversationsRes = await axios.get(`${API}/conversations`);
        setConversations(conversationsRes.data.conversations);
      }
      
    } catch (error) {
      console.error('Ошибка загрузки данных:', error);
    } finally {
      setLoading(false);
    }
  };

  const configureTelegram = async () => {
    try {
      setLoading(true);
      await axios.post(`${API}/telegram/configure`, {
        api_id: parseInt(telegramConfig.api_id),
        api_hash: telegramConfig.api_hash,
        phone: telegramConfig.phone
      });
      
      alert('Telegram успешно настроен!');
      await loadSystemData();
      
    } catch (error) {
      console.error('Ошибка настройки Telegram:', error);
      alert('Ошибка настройки: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  const loadConversationDetails = async (conversationId) => {
    try {
      const response = await axios.get(`${API}/conversations/${conversationId}`);
      setSelectedConversation(response.data);
    } catch (error) {
      console.error('Ошибка загрузки диалога:', error);
    }
  };

  const triggerHandoff = async (conversationId) => {
    try {
      await axios.post(`${API}/conversations/${conversationId}/handoff`);
      alert('Диалог передан человеку');
      await loadSystemData();
    } catch (error) {
      console.error('Ошибка передачи диалога:', error);
      alert('Ошибка: ' + error.message);
    }
  };

  const sendManualMessage = async (conversationId, content) => {
    try {
      await axios.post(`${API}/conversations/${conversationId}/message`, { content });
      alert('Сообщение отправлено');
      await loadConversationDetails(conversationId);
    } catch (error) {
      console.error('Ошибка отправки сообщения:', error);
      alert('Ошибка: ' + error.message);
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'Нет данных';
    return new Date(dateString).toLocaleString('ru-RU');
  };

  const getStageLabel = (stage) => {
    const labels = {
      'introduction': '🔵 Знакомство',
      'father_incident': '🟡 История с отцом',
      'work_offer': '🟠 Предложение работы',
      'human_takeover': '🔴 У человека',
      'closed': '⚫ Закрыт'
    };
    return labels[stage] || stage;
  };

  if (loading && !stats) {
    return (
      <div className="min-h-screen bg-gray-100 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Загрузка системы...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center py-4">
            <h1 className="text-2xl font-bold text-gray-900">
              🤖 Система ИИ Диалогов
            </h1>
            <div className="flex items-center space-x-4">
              <div className="flex items-center">
                <div className={`w-3 h-3 rounded-full mr-2 ${
                  systemStatus?.connected ? 'bg-green-500' : 'bg-red-500'
                }`}></div>
                <span className="text-sm text-gray-600">
                  Telegram: {systemStatus?.connected ? 'Подключен' : 'Не настроен'}
                </span>
              </div>
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Navigation Tabs */}
        <div className="mb-6">
          <nav className="flex space-x-8">
            {[
              { id: 'dashboard', label: '📊 Дашборд' },
              { id: 'conversations', label: '💬 Диалоги' },
              { id: 'settings', label: '⚙️ Настройки' }
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`py-2 px-1 border-b-2 font-medium text-sm ${
                  activeTab === tab.id
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </nav>
        </div>

        {/* Dashboard Tab */}
        {activeTab === 'dashboard' && (
          <div className="space-y-6">
            {/* Stats Cards */}
            {stats && (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <div className="bg-white overflow-hidden shadow rounded-lg">
                  <div className="p-5">
                    <div className="flex items-center">
                      <div className="flex-shrink-0">
                        <div className="w-8 h-8 bg-blue-500 rounded-md flex items-center justify-center">
                          <span className="text-white text-sm font-medium">👥</span>
                        </div>
                      </div>
                      <div className="ml-5 w-0 flex-1">
                        <dl>
                          <dt className="text-sm font-medium text-gray-500 truncate">
                            Всего пользователей
                          </dt>
                          <dd className="text-lg font-medium text-gray-900">
                            {stats.total_users}
                          </dd>
                        </dl>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="bg-white overflow-hidden shadow rounded-lg">
                  <div className="p-5">
                    <div className="flex items-center">
                      <div className="flex-shrink-0">
                        <div className="w-8 h-8 bg-green-500 rounded-md flex items-center justify-center">
                          <span className="text-white text-sm font-medium">💬</span>
                        </div>
                      </div>
                      <div className="ml-5 w-0 flex-1">
                        <dl>
                          <dt className="text-sm font-medium text-gray-500 truncate">
                            Активные диалоги
                          </dt>
                          <dd className="text-lg font-medium text-gray-900">
                            {stats.active_conversations}
                          </dd>
                        </dl>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="bg-white overflow-hidden shadow rounded-lg">
                  <div className="p-5">
                    <div className="flex items-center">
                      <div className="flex-shrink-0">
                        <div className="w-8 h-8 bg-orange-500 rounded-md flex items-center justify-center">
                          <span className="text-white text-sm font-medium">🔄</span>
                        </div>
                      </div>
                      <div className="ml-5 w-0 flex-1">
                        <dl>
                          <dt className="text-sm font-medium text-gray-500 truncate">
                            Передано людям
                          </dt>
                          <dd className="text-lg font-medium text-gray-900">
                            {stats.handoff_conversations}
                          </dd>
                        </dl>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="bg-white overflow-hidden shadow rounded-lg">
                  <div className="p-5">
                    <div className="flex items-center">
                      <div className="flex-shrink-0">
                        <div className="w-8 h-8 bg-purple-500 rounded-md flex items-center justify-center">
                          <span className="text-white text-sm font-medium">📊</span>
                        </div>
                      </div>
                      <div className="ml-5 w-0 flex-1">
                        <dl>
                          <dt className="text-sm font-medium text-gray-500 truncate">
                            Всего диалогов
                          </dt>
                          <dd className="text-lg font-medium text-gray-900">
                            {stats.total_conversations}
                          </dd>
                        </dl>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Stage Distribution */}
            {stats && (
              <div className="bg-white shadow rounded-lg">
                <div className="px-4 py-5 sm:p-6">
                  <h3 className="text-lg leading-6 font-medium text-gray-900 mb-4">
                    Распределение по стадиям
                  </h3>
                  <div className="space-y-3">
                    {Object.entries(stats.stage_distribution).map(([stage, count]) => (
                      <div key={stage} className="flex justify-between items-center">
                        <span className="text-sm text-gray-600">{getStageLabel(stage)}</span>
                        <span className="text-sm font-medium text-gray-900">{count}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Conversations Tab */}
        {activeTab === 'conversations' && (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <h2 className="text-xl font-semibold text-gray-900">Диалоги</h2>
              <button
                onClick={loadSystemData}
                disabled={loading}
                className="px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
              >
                {loading ? 'Загрузка...' : 'Обновить'}
              </button>
            </div>

            {!systemStatus?.connected ? (
              <div className="text-center py-12">
                <p className="text-gray-500 mb-4">Telegram не настроен</p>
                <button
                  onClick={() => setActiveTab('settings')}
                  className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
                >
                  Перейти к настройкам
                </button>
              </div>
            ) : (
              <div className="bg-white shadow overflow-hidden sm:rounded-md">
                <ul className="divide-y divide-gray-200">
                  {conversations.length === 0 ? (
                    <li className="px-6 py-4 text-center text-gray-500">
                      Диалоги не найдены
                    </li>
                  ) : (
                    conversations.map((conversation) => (
                      <li key={conversation.id}>
                        <div className="px-6 py-4 flex items-center justify-between">
                          <div className="flex-1">
                            <div className="flex items-center justify-between">
                              <p className="text-sm font-medium text-gray-900">
                                {conversation.user_name || 'Пользователь'}
                              </p>
                              <div className="ml-2 flex-shrink-0 flex">
                                <p className="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-green-100 text-green-800">
                                  {getStageLabel(conversation.current_stage)}
                                </p>
                              </div>
                            </div>
                            <div className="mt-2 flex">
                              <div className="flex items-center text-sm text-gray-500">
                                <p>
                                  Сообщений: {conversation.total_messages} • 
                                  Engagement: {Math.round(conversation.engagement_score)}% • 
                                  Создан: {formatDate(conversation.created_at)}
                                </p>
                              </div>
                            </div>
                          </div>
                          <div className="ml-6 flex space-x-2">
                            <button
                              onClick={() => loadConversationDetails(conversation.id)}
                              className="px-3 py-1 text-xs font-medium text-blue-600 hover:text-blue-500"
                            >
                              Открыть
                            </button>
                            {!conversation.handoff_triggered && (
                              <button
                                onClick={() => triggerHandoff(conversation.id)}
                                className="px-3 py-1 text-xs font-medium text-orange-600 hover:text-orange-500"
                              >
                                Передать
                              </button>
                            )}
                          </div>
                        </div>
                      </li>
                    ))
                  )}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Settings Tab */}
        {activeTab === 'settings' && (
          <div className="space-y-6">
            <h2 className="text-xl font-semibold text-gray-900">Настройки Telegram</h2>
            
            <div className="bg-white shadow sm:rounded-lg">
              <div className="px-4 py-5 sm:p-6">
                <h3 className="text-lg leading-6 font-medium text-gray-900 mb-4">
                  Подключение к Telegram API
                </h3>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700">
                      API ID
                    </label>
                    <input
                      type="text"
                      value={telegramConfig.api_id}
                      onChange={(e) => setTelegramConfig({...telegramConfig, api_id: e.target.value})}
                      className="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                      placeholder="Получить на my.telegram.org"
                    />
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700">
                      API Hash
                    </label>
                    <input
                      type="text"
                      value={telegramConfig.api_hash}
                      onChange={(e) => setTelegramConfig({...telegramConfig, api_hash: e.target.value})}
                      className="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                      placeholder="Получить на my.telegram.org"
                    />
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700">
                      Номер телефона
                    </label>
                    <input
                      type="text"
                      value={telegramConfig.phone}
                      onChange={(e) => setTelegramConfig({...telegramConfig, phone: e.target.value})}
                      className="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                      placeholder="+7XXXXXXXXXX"
                    />
                  </div>
                  
                  <button
                    onClick={configureTelegram}
                    disabled={loading || !telegramConfig.api_id || !telegramConfig.api_hash || !telegramConfig.phone}
                    className="px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
                  >
                    {loading ? 'Настройка...' : 'Настроить Telegram'}
                  </button>
                </div>
                
                <div className="mt-6 p-4 bg-yellow-50 border border-yellow-200 rounded-md">
                  <h4 className="text-sm font-medium text-yellow-800">Инструкции:</h4>
                  <ol className="mt-2 text-sm text-yellow-700 list-decimal list-inside space-y-1">
                    <li>Перейдите на <a href="https://my.telegram.org" target="_blank" rel="noopener noreferrer" className="underline">my.telegram.org</a></li>
                    <li>Войдите в свой аккаунт Telegram</li>
                    <li>Создайте новое приложение в разделе "API development tools"</li>
                    <li>Скопируйте API ID и API Hash</li>
                    <li>Введите данные выше и нажмите "Настроить"</li>
                  </ol>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Conversation Details Modal */}
      {selectedConversation && (
        <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50">
          <div className="relative top-20 mx-auto p-5 border w-11/12 md:w-3/4 lg:w-1/2 shadow-lg rounded-md bg-white">
            <div className="mt-3">
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-medium text-gray-900">
                  Диалог с {selectedConversation.user?.first_name || 'пользователем'}
                </h3>
                <button
                  onClick={() => setSelectedConversation(null)}
                  className="text-gray-400 hover:text-gray-600"
                >
                  ✕
                </button>
              </div>
              
              <div className="max-h-96 overflow-y-auto mb-4">
                <div className="space-y-2">
                  {selectedConversation.messages?.map((message, index) => (
                    <div
                      key={index}
                      className={`p-3 rounded-lg ${
                        message.sender === 'user' 
                          ? 'bg-gray-100 ml-8' 
                          : 'bg-blue-100 mr-8'
                      }`}
                    >
                      <div className="flex justify-between items-start">
                        <div className="flex-1">
                          <p className="text-sm">{message.content}</p>
                        </div>
                        <span className="text-xs text-gray-500 ml-2">
                          {message.sender === 'user' ? 'Она' : 'Стас'}
                        </span>
                      </div>
                      <div className="text-xs text-gray-400 mt-1">
                        {formatDate(message.created_at)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              
              <div className="flex space-x-2">
                <input
                  type="text"
                  placeholder="Написать сообщение от имени оператора..."
                  className="flex-1 border border-gray-300 rounded-md px-3 py-2 text-sm"
                  onKeyPress={(e) => {
                    if (e.key === 'Enter' && e.target.value.trim()) {
                      sendManualMessage(selectedConversation.conversation.id, e.target.value);
                      e.target.value = '';
                    }
                  }}
                />
                <button
                  onClick={() => triggerHandoff(selectedConversation.conversation.id)}
                  className="px-4 py-2 bg-orange-600 text-white text-sm rounded-md hover:bg-orange-700"
                >
                  Передать мне
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;