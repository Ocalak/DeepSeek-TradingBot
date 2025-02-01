import requests
import sqlite3
import pandas as pd
import json
import asyncio
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from sklearn.ensemble import IsolationForest

# Load configuration
CONFIG = {
    "telegram": {
        "bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
        "chat_id": "YOUR_TELEGRAM_CHAT_ID"
    },
    "filters": {
        "min_liquidity": 10000,
        "max_price_change_24h": 100,
        "min_volume": 50000
    },
    "blacklist": {
        "coins": ["RugCoin", "ScamToken"],
        "devs": ["0xBadDevAddress1", "0xBadDevAddress2"]
    },
    "bonkbot": {
        "api_key": "YOUR_BONKBOT_API_KEY",
        "trade_size": 0.1  # ETH
    }
}

# Database setup
def init_db():
    conn = sqlite3.connect('crypto_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dex_data (
            pair_address TEXT PRIMARY KEY,
            base_token TEXT,
            quote_token TEXT,
            price REAL,
            volume REAL,
            liquidity REAL,
            market_cap REAL,
            price_change_24h REAL,
            dev_address TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# DexScreener API interactions
def fetch_dexscreener_data(pair_address):
    url = f"https://api.dexscreener.com/latest/dex/pairs/{pair_address}"
    response = requests.get(url)
    return response.json() if response.status_code == 200 else None

def parse_data(data):
    return {
        "pair_address": data["pairAddress"],
        "base_token": data["baseToken"]["name"],
        "quote_token": data["quoteToken"]["name"],
        "price": data["priceUsd"],
        "volume": data["volume"]["h24"],
        "liquidity": data["liquidity"]["usd"],
        "market_cap": data["fdv"],
        "price_change_24h": data["priceChange"]["h24"],
        "dev_address": data["baseToken"]["address"]
    }

# Security checks
def rugcheck(token_address):
    url = f"https://rugcheck.xyz/api/tokens/{token_address}"
    response = requests.get(url)
    return response.json().get("status", "").lower() == "good" if response.status_code == 200 else False

def check_supply(token_address):
    url = f"https://api.example.com/supply-distribution/{token_address}"
    response = requests.get(url)
    if response.status_code == 200:
        return max(response.json().values()) < 50
    return False

# Trading engine
async def execute_trade(action, token, amount):
    """Execute trade through BonkBot"""
    url = "https://api.bonkbot.com/trade"
    headers = {"Authorization": f"Bearer {CONFIG['bonkbot']['api_key']}"}
    payload = {
        "action": action,
        "token": token,
        "amount": amount,
        "slippage": 2
    }
    response = requests.post(url, headers=headers, json=payload)
    return response.json()

# Telegram bot handlers
async def start(update: Update, context):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="BonkBot Trader Active\nCommands:\n/status - Check bot status\n/buy <token> - Execute buy order\n/sell <token> - Execute sell order"
    )

async def handle_buy(update: Update, context):
    token = ' '.join(context.args)
    result = await execute_trade("buy", token, CONFIG['bonkbot']['trade_size'])
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🟢 BUY ORDER EXECUTED\nToken: {token}\nAmount: {CONFIG['bonkbot']['trade_size']} ETH\nTxHash: {result['tx_hash']}"
    )

async def handle_sell(update: Update, context):
    token = ' '.join(context.args)
    result = await execute_trade("sell", token, CONFIG['bonkbot']['trade_size'])
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🔴 SELL ORDER EXECUTED\nToken: {token}\nAmount: {CONFIG['bonkbot']['trade_size']} ETH\nTxHash: {result['tx_hash']}"
    )

# Analysis and monitoring
def analyze_data():
    conn = sqlite3.connect("crypto_data.db")
    df = pd.read_sql_query("SELECT * FROM dex_data", conn)
    conn.close()

    model = IsolationForest(contamination=0.1)
    df["anomaly"] = model.fit_predict(df[["price_change_24h", "volume", "liquidity"]])
    return df[df["anomaly"] == -1]

async def monitor_markets():
    bot = Bot(token=CONFIG['telegram']['bot_token'])
    while True:
        pairs = ["0x...pair1", "0x...pair2"]  # Add pair addresses to monitor
        for pair in pairs:
            data = fetch_dexscreener_data(pair)
            if data and rugcheck(data['baseToken']['address']) and check_supply(data['baseToken']['address']):
                parsed = parse_data(data)
                anomalies = analyze_data()
                
                if not anomalies.empty:
                    message = f"🚨 TRADE SIGNAL DETECTED\nToken: {parsed['base_token']}\nPrice: ${parsed['price']}\nVolume: {parsed['volume']}"
                    await bot.send_message(chat_id=CONFIG['telegram']['chat_id'], text=message)
                    await execute_trade("buy", parsed['base_token'], CONFIG['bonkbot']['trade_size'])
        
        await asyncio.sleep(300)  # Check every 5 minutes

# Main application
if __name__ == '__main__':
    application = Application.builder().token(CONFIG['telegram']['bot_token']).build()
    
    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("buy", handle_buy))
    application.add_handler(CommandHandler("sell", handle_sell))
    
    # Start market monitoring
    loop = asyncio.get_event_loop()
    loop.create_task(monitor_markets())
    
    # Run bot
    application.run_polling()
