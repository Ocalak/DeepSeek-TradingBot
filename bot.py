import requests
import sqlite3
import pandas as pd
from sklearn.ensemble import IsolationForest
import json

# Load config
def load_config():
    with open("config.json", "r") as f:
        return json.load(f)

# Fetch data from DexScreener
def fetch_dexscreener_data(pair_address):
    url = f"https://api.dexscreener.com/latest/dex/pairs/{pair_address}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Failed to fetch data: {response.status_code}")

# Parse data
def parse_data(data):
    parsed = {
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
    return parsed

# Fetch token data from rugcheck.xyz
def fetch_rugcheck_data(token_address):
    url = f"https://rugcheck.xyz/api/tokens/{token_address}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Failed to fetch rugcheck data: {response.status_code}")

# Check if token is marked as "Good" on rugcheck.xyz
def is_token_good(token_address):
    rugcheck_data = fetch_rugcheck_data(token_address)
    return rugcheck_data.get("status", "").lower() == "good"

# Check if token supply is bundled
def is_supply_bundled(token_address):
    url = f"https://api.example.com/supply-distribution/{token_address}"
    response = requests.get(url)
    if response.status_code == 200:
        supply_data = response.json()
        for address, percentage in supply_data.items():
            if percentage > 50:
                return True
    return False

# Apply filters and blacklists
def apply_filters_and_blacklists(data, config):
    if data["liquidity"] < config["filters"]["min_liquidity"]:
        return False
    if abs(data["price_change_24h"]) > config["filters"]["max_price_change_24h"]:
        return False
    if data["volume"] < config["filters"]["min_volume"]:
        return False
    if data["base_token"] in config["blacklist"]["coins"]:
        return False
    if data["dev_address"] in config["blacklist"]["devs"]:
        return False
    if not is_token_good(data["pair_address"]):
        config["blacklist"]["coins"].append(data["base_token"])
        config["blacklist"]["devs"].append(data["dev_address"])
        return False
    if is_supply_bundled(data["pair_address"]):
        config["blacklist"]["coins"].append(data["base_token"])
        config["blacklist"]["devs"].append(data["dev_address"])
        return False
    return True

# Save to database
def save_to_db(data):
    conn = sqlite3.connect("crypto_data.db")
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
    cursor.execute('''
        INSERT OR REPLACE INTO dex_data VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data["pair_address"], data["base_token"], data["quote_token"],
        data["price"], data["volume"], data["liquidity"],
        data["market_cap"], data["price_change_24h"], data["dev_address"]
    ))
    conn.commit()
    conn.close()

# Analyze data
def analyze_data():
    conn = sqlite3.connect("crypto_data.db")
    df = pd.read_sql_query("SELECT * FROM dex_data", conn)
    conn.close()

    model = IsolationForest(contamination=0.1)
    df["anomaly"] = model.fit_predict(df[["price_change_24h", "volume", "liquidity"]])
    anomalies = df[df["anomaly"] == -1]
    return anomalies

# Send alerts
def send_alert(anomalies):
    for _, row in anomalies.iterrows():
        print(f"ALERT: Anomaly detected for {row['base_token']}/{row['quote_token']}!")
        print(f"Price Change: {row['price_change_24h']}%, Volume: {row['volume']}, Liquidity: {row['liquidity']}")

# Main function
def main():
    config = load_config()
    pair_address = "0x...your_pair_address_here..."  # Replace with actual pair address
    data = fetch_dexscreener_data(pair_address)
    parsed_data = parse_data(data)

    if apply_filters_and_blacklists(parsed_data, config):
        save_to_db(parsed_data)
        anomalies = analyze_data()
        send_alert(anomalies)
    else:
        print(f"Skipping {parsed_data['base_token']} due to filters, blacklists, rugcheck, or bundled supply.")

if __name__ == "__main__":
    main()
