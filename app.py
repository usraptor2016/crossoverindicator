from polygon import RESTClient
import pandas as pd
from flask import Flask, jsonify
from flask.templating import render_template_string
import time
from datetime import datetime, timedelta, timezone
import pytz
import logging
import os
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)

# Polygon.io API key
API_KEY = "ViZJrQ3dvC5DhhuJ32ZPp7WC6qVTPtC4"

# Initialize Polygon.io client
client = RESTClient(API_KEY)

app = Flask(__name__)



def fetch_stock_data(ticker):
    """Fetch stock data from Polygon.io API using EMA endpoint."""
    # Get today's date
    end_date = datetime.now()
    # Get date 30 days ago
    start_date = end_date - timedelta(days=30)
    
    # Format dates as YYYY-MM-DD
    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')
    
    try:
        # Fetch 8-day EMA
        ema8_url = f"https://api.polygon.io/v1/indicators/ema/{ticker}?timestamp.gte={start_date_str}&timestamp.lte={end_date_str}&timespan=day&adjusted=true&window=8&series_type=close&order=desc&expand_underlying=true&limit=30&apiKey={API_KEY}"
        ema8_response = requests.get(ema8_url)
        ema8_data = ema8_response.json()
        
        # Fetch 21-day EMA
        ema21_url = f"https://api.polygon.io/v1/indicators/ema/{ticker}?timestamp.gte={start_date_str}&timestamp.lte={end_date_str}&timespan=day&adjusted=true&window=21&series_type=close&order=desc&expand_underlying=true&limit=30&apiKey={API_KEY}"
        ema21_response = requests.get(ema21_url)
        ema21_data = ema21_response.json()
        
        if ema8_response.status_code != 200 or ema21_response.status_code != 200:
            print(f"Error fetching EMA data for {ticker}: {ema8_data.get('error', 'Unknown error')}")
            return pd.DataFrame()
        
        if not ema8_data.get('results', {}).get('values') or not ema21_data.get('results', {}).get('values'):
            print(f"No EMA data available for {ticker}")
            return pd.DataFrame()
        
        # Extract EMA values and timestamps
        ema8_values = {pd.to_datetime(v['timestamp'], unit='ms').date(): v['value'] 
                      for v in ema8_data['results']['values']}
        ema21_values = {pd.to_datetime(v['timestamp'], unit='ms').date(): v['value'] 
                       for v in ema21_data['results']['values']}
        
        # Get the underlying data from the expanded response
        underlying_data = ema8_data['results'].get('underlying', {}).get('aggregates', [])
        
        if not underlying_data:
            print(f"No underlying data available for {ticker}")
            return pd.DataFrame()
        
        # Create DataFrame with underlying data
        daily_data = []
        for agg in underlying_data:
            date = pd.to_datetime(agg['t'], unit='ms').date()
            if date in ema8_values and date in ema21_values:
                daily_data.append({
                    'Date': date,
                    'Price': agg['c'],  # Closing price
                    'Volume': agg['v'],  # Volume
                    'EMA8': ema8_values[date],
                    'EMA21': ema21_values[date]
                })
        
        # Convert to DataFrame and sort
        df = pd.DataFrame(daily_data)
        if df.empty:
            print(f"No matching data found for {ticker}")
            return df
            
        df = df.sort_values('Date', ascending=False).reset_index(drop=True)
        
        # Check if we have enough data
        if len(df) < 21:
            print(f"Insufficient data for {ticker} (need at least 21 days, got {len(df)} days)")
            return pd.DataFrame()
        
        print(f"Successfully fetched {len(df)} days of data for {ticker}")
        return df
    
    except Exception as e:
        print(f"Error processing {ticker}: {str(e)}")
        return pd.DataFrame()

def scan_etfs():
    """Scan ETFs for crossover patterns using 8-day and 21-day EMAs."""
    # List of popular and actively traded ETFs
    etfs = [
        'SPY',   # SPDR S&P 500 ETF Trust
        'QQQ',   # Invesco QQQ Trust
        'IWM',   # iShares Russell 2000 ETF
        'DIA',   # SPDR Dow Jones Industrial Average ETF
        'VOO',   # Vanguard S&P 500 ETF
        'XLF',   # Financial Select Sector SPDR Fund
        'XLE',   # Energy Select Sector SPDR Fund
        'XLK',   # Technology Select Sector SPDR Fund
        'EEM',   # iShares MSCI Emerging Markets ETF
        'GLD',   # SPDR Gold Trust
        'VEA',   # Vanguard FTSE Developed Markets ETF
        'SMH',   # VanEck Semiconductor ETF
        'XLV',   # Health Care Select Sector SPDR Fund
        'XLI',   # Industrial Select Sector SPDR Fund
        'XLP'    # Consumer Staples Select Sector SPDR Fund
    ]
    results = []
    
    for i, ticker in enumerate(etfs):
        print(f"\nProcessing {ticker}...")
        
        # Add delay between each request to respect rate limits
        if i > 0:  # Wait after first request
            delay = 30  # 30 seconds delay between requests (2 requests per minute to stay well within limits)
            print(f"Rate limit pause: waiting {delay} seconds...")
            time.sleep(delay)
        
        # Try up to 3 times with exponential backoff
        for attempt in range(3):
            if attempt > 0:
                backoff = 2 ** attempt * 5  # 5, 10, 20 seconds
                print(f"Retry attempt {attempt + 1}, waiting {backoff} seconds...")
                time.sleep(backoff)
            
            df = fetch_stock_data(ticker)
            
            if not df.empty:
                break
        
        if df.empty:
            print(f"Skipping {ticker} after {attempt + 1} attempts")
            continue
        
        # Get the last three days of data
        last_three_days = df.head(3)
        
        if len(last_three_days) < 3:
            print(f"Skipping {ticker} due to insufficient data")
            continue
        
        # Today's data
        today = last_three_days.iloc[0]
        # Yesterday's data
        yesterday = last_three_days.iloc[1]
        # Day before yesterday's data
        day_before = last_three_days.iloc[2]
        
        print(f"Analyzing {ticker} crossover pattern:")
        print(f"Today - Price: {today['Price']:.2f}, EMA8: {today['EMA8']:.2f}, EMA21: {today['EMA21']:.2f}")
        print(f"Yesterday - Price: {yesterday['Price']:.2f}, EMA8: {yesterday['EMA8']:.2f}, EMA21: {yesterday['EMA21']:.2f}")
        print(f"Day Before - Price: {day_before['Price']:.2f}, EMA8: {day_before['EMA8']:.2f}, EMA21: {day_before['EMA21']:.2f}")
        
        # Check conditions
        volume_condition = bool(today['Volume'] > 1000000)
        ema_crossover_condition = bool(
            yesterday['EMA8'] > yesterday['EMA21'] and  # Yesterday: 8 EMA above 21 EMA
            day_before['EMA21'] > day_before['EMA8']    # Day before: 21 EMA above 8 EMA
        )
        
        result = {
            'symbol': str(ticker),
            'price': float(round(today['Price'], 2)),
            'volume': int(today['Volume']),
            'ema8': float(round(today['EMA8'], 2)),
            'ema21': float(round(today['EMA21'], 2)),
            'yesterday_price': float(round(yesterday['Price'], 2)),
            'yesterday_ema8': float(round(yesterday['EMA8'], 2)),
            'yesterday_ema21': float(round(yesterday['EMA21'], 2)),
            'day_before_price': float(round(day_before['Price'], 2)),
            'day_before_ema8': float(round(day_before['EMA8'], 2)),
            'day_before_ema21': float(round(day_before['EMA21'], 2)),
            'matched': bool(volume_condition and ema_crossover_condition)
        }
        
        results.append(result)
        
        if volume_condition and ema_crossover_condition:
            print(f"Found match: {ticker}")
        else:
            if not volume_condition:
                print(f"Failed volume condition: {today['Volume']:.0f} < 1,000,000")
            if not ema_crossover_condition:
                print("Failed EMA crossover condition")
    
    print(f"\nScan complete. Found {len([r for r in results if r['matched']])} matching ETFs.")
    return results

@app.route('/')
def home():
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>ETF Crossover Scanner</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            table { border-collapse: collapse; width: 100%; margin-top: 20px; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #f2f2f2; }
            button { padding: 10px 20px; margin: 10px 0; cursor: pointer; }
            #loading { display: none; margin: 10px 0; }
            tr.matched { background-color: #90EE90; }
        </style>
    </head>
    <body>
        <h1>ETF Crossover Scanner</h1>
        <button onclick="fetchData()">Refresh Data</button>
        <div id="loading">Loading...</div>
        <div id="results">
            <table>
                <thead>
                    <tr>
                        <th rowspan="2">Symbol</th>
                        <th colspan="4">Today</th>
                        <th colspan="3">Yesterday</th>
                        <th colspan="3">Day Before</th>
                    </tr>
                    <tr>
                        <th>Price</th>
                        <th>Volume</th>
                        <th>8 EMA</th>
                        <th>21 EMA</th>
                        <th>Price</th>
                        <th>8 EMA</th>
                        <th>21 EMA</th>
                        <th>Price</th>
                        <th>8 EMA</th>
                        <th>21 EMA</th>
                    </tr>
                </thead>
                <tbody id="resultsBody"></tbody>
            </table>
            <p><i>Note: Rows highlighted in green indicate ETFs that match the crossover pattern.</i></p>
        </div>

        <script>
        function fetchData() {
            const loading = document.getElementById('loading');
            const resultsBody = document.getElementById('resultsBody');
            
            loading.style.display = 'block';
            resultsBody.innerHTML = '';
            
            fetch('/scan')
                .then(response => response.json())
                .then(data => {
                    loading.style.display = 'none';
                    data.forEach(etf => {
                        const rowClass = etf.matched ? 'matched' : '';
                        resultsBody.innerHTML += `
                            <tr class="${rowClass}">
                                <td>${etf.symbol}</td>
                                <td>${etf.price}</td>
                                <td>${etf.volume.toLocaleString()}</td>
                                <td>${etf.ema8}</td>
                                <td>${etf.ema21}</td>
                                <td>${etf.yesterday_price}</td>
                                <td>${etf.yesterday_ema8}</td>
                                <td>${etf.yesterday_ema21}</td>
                                <td>${etf.day_before_price}</td>
                                <td>${etf.day_before_ema8}</td>
                                <td>${etf.day_before_ema21}</td>
                            </tr>
                        `;
                    });
                    if (data.length === 0) {
                        resultsBody.innerHTML = '<tr><td colspan="11">No ETFs match the criteria</td></tr>';
                    }
                })
                .catch(error => {
                    loading.style.display = 'none';
                    resultsBody.innerHTML = '<tr><td colspan="11">Error fetching data</td></tr>';
                    console.error('Error:', error);
                });
        }

        // Initial load
        fetchData();
        </script>
    </body>
    </html>
    ''')

@app.route('/scan')
def scan():
    results = scan_etfs()
    return jsonify(results)

if __name__ == '__main__':
    app.run(debug=True)