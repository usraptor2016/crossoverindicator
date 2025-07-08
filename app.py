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
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global variable to store results
all_results = []

# Polygon.io API key
API_KEY = os.getenv('POLYGON_API_KEY')
if not API_KEY:
    logger.error('POLYGON_API_KEY environment variable is not set')
    raise ValueError('POLYGON_API_KEY environment variable is required')

logger.info('API key configured successfully')

# Initialize Polygon.io client
try:
    client = RESTClient(API_KEY)
    logger.info('Polygon.io client initialized successfully')
except Exception as e:
    logger.error(f'Failed to initialize Polygon.io client: {str(e)}')
    raise

app = Flask(__name__)

def fetch_stock_data(ticker):
    """Fetch stock data from Polygon.io API using SMA endpoint."""
    # Use today's date since it's a trading day
    end_date = datetime(2025, 7, 8)  # Current system date
    start_date = end_date - timedelta(days=5)  # Reduced from 30 to 5 days
    
    logging.info(f"Using date range: {start_date.date()} to {end_date.date()}")
    
    # Format dates as YYYY-MM-DD
    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')
    
    logging.info(f"Fetching data for {ticker} from {start_date_str} to {end_date_str}")
    
    max_retries = 3
    retry_wait = 30  # seconds
    
    try:
        # Log the API key being used (first 4 characters only)
        logging.info(f"Using API key starting with: {API_KEY[:4]}...")
        
        def fetch_aggs_with_retry():
            for attempt in range(max_retries):
                try:
                    return client.get_aggs(
                        ticker=ticker,
                        from_=start_date_str,
                        to=end_date_str,
                        multiplier=1,
                        timespan="day",
                        adjusted=True,
                        sort="desc",
                        limit=50000
                    )
                except Exception as e:
                    if attempt < max_retries - 1:
                        logging.error(f"Error fetching aggregates for {ticker} (attempt {attempt + 1}): {str(e)}")
                        time.sleep(retry_wait * (attempt + 1))  # Exponential backoff
                        continue
                    raise
        
        # Fetch aggregates with retry logic
        aggs_data = fetch_aggs_with_retry()
        if not aggs_data:
            logging.error(f"No aggregate data available for {ticker}")
            return pd.DataFrame()

        # Convert aggregates to DataFrame
        try:
            # Convert timestamp to Eastern time
            df = pd.DataFrame([{
                'Date': pd.to_datetime(agg.timestamp, unit='ms').tz_localize('UTC').tz_convert('US/Eastern').date(),
                'Price': agg.close,
                'Volume': agg.volume
            } for agg in aggs_data])
            
            if df.empty:
                logging.error(f"No data available for {ticker}")
                return df
            
            # Sort DataFrame by date
            df = df.sort_values('Date', ascending=True)
            
            # Calculate EMAs
            df['EMA8'] = df['Price'].ewm(span=8, adjust=False).mean()
            df['EMA21'] = df['Price'].ewm(span=21, adjust=False).mean()
            
            # Sort by date descending for display
            df = df.sort_values('Date', ascending=False).reset_index(drop=True)
            
            logging.info(f"Successfully processed {len(df)} days of data for {ticker}")
            return df
            
        except AttributeError as e:
            logging.error(f"Error processing data for {ticker}: {str(e)}")
            return pd.DataFrame()
        
        # Check if we have enough data
        if len(df) < 21:
            logging.error(f"Insufficient data for {ticker} (need at least 21 days, got {len(df)} days)")
            return pd.DataFrame()
        
        return df
    
    except Exception as e:
        logging.error(f"Error processing {ticker}: {str(e)}")
        return pd.DataFrame()

def scan_stocks():
    """Scan ETFs for crossover patterns using 8-day and 21-day EMAs."""
    # List of stocks to monitor
    stocks = [
        # ETFs
        'SPY', 'QQQ', 'IWM', 'DIA', 'VOO', 'XLF', 'XLE', 'XLK', 'EEM', 'GLD', 'VEA', 'SMH', 'XLV', 'XLI', 'XLP',
        # Individual Stocks
        'AAPL', 'ACHR', 'AMD', 'AMZN', 'AVGO', 'BRK.B', 'COIN', 'COKE', 'CPNG', 'CRWD',
        'GOOGL', 'HIMS', 'HOOD', 'IONQ', 'META', 'MSFT', 'MSTR', 'MU', 'NFLX', 'NOW',
        'NVDA', 'ORCL', 'PLTR', 'RBLX', 'RKLB', 'RTX', 'SHOP', 'SNOW', 'SOFI',
        'TSLA', 'TSM', 'VRT'
    ]
    
    # Clear previous results
    all_results.clear()
    
    for i, ticker in enumerate(stocks):
        print(f"\nProcessing {ticker}...")
        
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
        
        # Process all available data rows
        ticker_results = []
        for i in range(len(df) - 2):  # We need at least 3 consecutive days
            # Get three consecutive days of data
            today = df.iloc[i]
            yesterday = df.iloc[i + 1]
            day_before = df.iloc[i + 2]
            
            # Check conditions
            volume_condition = bool(today['Volume'] > 1000000)
            ema_crossover_condition = bool(
                yesterday['EMA8'] > yesterday['EMA21'] and  # Yesterday: 8 EMA above 21 EMA
                day_before['EMA21'] > day_before['EMA8']    # Day before: 21 EMA above 8 EMA
            )
            
            # Check for crossover points
            crossover_points = {
                'today': bool(today['EMA8'] > today['EMA21'] and yesterday['EMA8'] <= yesterday['EMA21']),
                'yesterday': bool(yesterday['EMA8'] > yesterday['EMA21'] and day_before['EMA8'] <= day_before['EMA21']),
                'day_before': bool(day_before['EMA8'] > day_before['EMA21'] and (i + 3 < len(df) and df.iloc[i + 3]['EMA8'] <= df.iloc[i + 3]['EMA21']))
            }
            
            result = {
                'symbol': str(ticker),
                'date': today['Date'].strftime('%Y-%m-%d'),
                'price': float(round(today['Price'], 2)),
                'volume': int(today['Volume']),
                'ema8': float(round(today['EMA8'], 2)),
                'ema21': float(round(today['EMA21'], 2)),
                'yesterday_date': yesterday['Date'].strftime('%Y-%m-%d'),
                'yesterday_price': float(round(yesterday['Price'], 2)),
                'yesterday_ema8': float(round(yesterday['EMA8'], 2)),
                'yesterday_ema21': float(round(yesterday['EMA21'], 2)),
                'day_before_date': day_before['Date'].strftime('%Y-%m-%d'),
                'day_before_price': float(round(day_before['Price'], 2)),
                'day_before_ema8': float(round(day_before['EMA8'], 2)),
                'day_before_ema21': float(round(day_before['EMA21'], 2)),
                'matched': bool(volume_condition and ema_crossover_condition),
                'crossover_points': crossover_points,
                'timestamp': datetime.now()
            }
            
            ticker_results.append(result)
            all_results.append(result)
        
        print(f"Found {len(ticker_results)} data points for {ticker}")
    
    # Sort results by timestamp in descending order and limit to 20 most recent entries
    all_results.sort(key=lambda x: x['date'], reverse=True)
    return all_results[:20]  # Reduced from 100 to 20 entries

@app.route('/')
def home():
    html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Stock Crossover Scanner</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            table { border-collapse: collapse; width: 100%; margin-top: 20px; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #f5f5f5; }
            .matched { background-color: #90EE90; }
            .crossover { background-color: pink; }
            .data-row:hover { background-color: #f5f5f5; }
            #loading { display: none; margin: 20px 0; }
        </style>
    </head>
    <body>
        <h1>Stock Crossover Scanner</h1>
        <div id="loading">Loading data...</div>
        <table id="results">
            <thead>
                <tr>
                    <th>Symbol</th>
                    <th colspan="3">Today</th>
                    <th colspan="3">Yesterday</th>
                    <th colspan="3">Day Before</th>
                </tr>
                <tr>
                    <th></th>
                    <th>Date</th>
                    <th>Price</th>
                    <th>Volume</th>
                    <th>Date</th>
                    <th>Price</th>
                    <th>Volume</th>
                    <th>Date</th>
                    <th>Price</th>
                    <th>Volume</th>
                </tr>
            </thead>
            <tbody></tbody>
        </table>

        <script>
        function fetchData() {
            document.getElementById('loading').style.display = 'block';
            fetch('/scan')
                .then(response => response.json())
                .then(data => {
                    const tbody = document.querySelector('#results tbody');
                    tbody.innerHTML = '';
                    
                    data.forEach(item => {
                        const row = document.createElement('tr');
                        row.className = 'data-row' + (item.matched ? ' matched' : '');
                        
                        // Add symbol
                        row.innerHTML = `<td>${item.symbol}</td>`;
                        
                        // Add today's data
                        row.innerHTML += `
                            <td>${item.date}</td>
                            <td class="${item.crossover_points.today ? 'crossover' : ''}">${item.price}</td>
                            <td>${item.volume}</td>
                        `;
                        
                        // Add yesterday's data
                        row.innerHTML += `
                            <td>${item.yesterday_date}</td>
                            <td class="${item.crossover_points.yesterday ? 'crossover' : ''}">${item.yesterday_price}</td>
                            <td>${item.volume}</td>
                        `;
                        
                        // Add day before's data
                        row.innerHTML += `
                            <td>${item.day_before_date}</td>
                            <td class="${item.crossover_points.day_before ? 'crossover' : ''}">${item.day_before_price}</td>
                            <td>${item.volume}</td>
                        `;
                        
                        tbody.appendChild(row);
                    });
                    document.getElementById('loading').style.display = 'none';
                })
                .catch(error => {
                    console.error('Error:', error);
                    document.getElementById('loading').style.display = 'none';
                });
        }

        // Fetch data immediately and then every 5 minutes
        fetchData();
        setInterval(fetchData, 300000);
        </script>
    </body>
    </html>
    '''
    return render_template_string(html)

@app.route('/scan')
def scan():
    results = scan_stocks()
    return jsonify(results)

@app.errorhandler(500)
def handle_500_error(error):
    logger.error(f'Internal Server Error: {error}')
    return jsonify({'error': 'Internal Server Error', 'message': str(error)}), 500

@app.errorhandler(Exception)
def handle_exception(error):
    logger.error(f'Unhandled Exception: {error}')
    return jsonify({'error': 'Server Error', 'message': str(error)}), 500

if __name__ == '__main__':
    try:
        port = int(os.environ.get('PORT', 8080))
        logger.info(f'Starting server on port {port}')
        app.run(host='0.0.0.0', port=port, debug=False)
    except Exception as e:
        logger.error(f'Failed to start server: {str(e)}')
        raise