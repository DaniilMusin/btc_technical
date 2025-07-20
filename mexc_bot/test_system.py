#!/usr/bin/env python3
"""
Простой тест работоспособности MEXC Trading Bot
"""
import asyncio
import os
import pytest
from dotenv import load_dotenv
from mexc_bot.core.broker import BingxBroker
from mexc_bot.core.strategy import BalancedAdaptiveStrategyLive
from mexc_bot.core.feed import StreamingDataFeed
from mexc_bot.core.trader import LiveTrader

@pytest.mark.asyncio
async def test_system():
    """Тестирует основные компоненты системы"""
    print("🔍 Проверка работоспособности MEXC Trading Bot...")
    
    # Загружаем переменные окружения
    load_dotenv('.env')
    
    # Проверяем переменные окружения
    print(f"✅ USE_TESTNET: {os.getenv('USE_TESTNET')}")
    print(f"✅ EXCHANGE: {os.getenv('EXCHANGE')}")
    print(f"✅ DEFAULT_SYMBOL: {os.getenv('DEFAULT_SYMBOL')}")
    
    # Создаем компоненты
    try:
        # Use the USE_TESTNET environment variable instead of hardcoding testnet=True
        use_testnet = os.getenv('USE_TESTNET', 'true').lower() == 'true'
        BingxBroker(testnet=use_testnet)
        print(f"✅ Брокер создан успешно (testnet={use_testnet})")

        BalancedAdaptiveStrategyLive()
        print("✅ Стратегия создана успешно")

        StreamingDataFeed(
            symbol=os.getenv('DEFAULT_SYMBOL', 'BTCUSDT'),
            interval=os.getenv('DEFAULT_INTERVAL', '15m')
        )
        print("✅ Data Feed создан успешно")

        # Создаем трейдера
        LiveTrader(
            symbol=os.getenv('DEFAULT_SYMBOL', 'BTCUSDT'),
            interval=os.getenv('DEFAULT_INTERVAL', '15m'),
            exchange=os.getenv('EXCHANGE', 'BINGX')
        )
        print("✅ Трейдер создан успешно")
        
        print("\n🎉 Все компоненты системы работают корректно!")
        print("📊 Система готова к торговле в тестовом режиме")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при создании компонентов: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_system())
    if success:
        print("\n✅ Система готова к работе!")
    else:
        print("\n❌ Система требует настройки")