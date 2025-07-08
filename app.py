from polygon import RESTClient
import pandas as pd
from flask import Flask, jsonify, request
from flask.templating import render_template_string
import time
from datetime import datetime, timedelta, timezone
import pytz
import logging
import os
import requests
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global variable to store results
all_results = []

# Polygon.io API key (hardcoded)
# Get a free API key from https://polygon.io/
API_KEY = 'Jr2cmNAEts41lLiOIKVx0YgLo494ow67'  # Replace with your actual Polygon.io API key

logger.info('API key configured successfully')

# Initialize Polygon.io client
try:
    client = RESTClient(API_KEY)
    logger.info('Polygon.io client initialized successfully')
except Exception as e:
    logger.error(f'Failed to initialize Polygon.io client: {str(e)}')
    raise

app = Flask(__name__)

def get_most_recent_trading_day():
    """Get the most recent trading day using Polygon.io API."""
    today = datetime.now(pytz.timezone('US/Eastern'))
    
    # Try up to 5 previous days to find the most recent trading day
    for i in range(5):
        test_date = today - timedelta(days=i)
        # Format date as YYYY-MM-DD
        date_str = test_date.strftime('%Y-%m-%d')
        
        try:
            # Try to get market status for this date
            market_data = client.get_aggs('AAPL', date_str, date_str, 1, 'day')
            if market_data:
                logger.info(f'Most recent trading day found: {date_str}')
                return test_date
        except Exception as e:
            logger.debug(f'Not a trading day: {date_str}, error: {str(e)}')
            continue
    
    # If no trading day found in last 5 days, use today's date
    logger.warning('No recent trading day found, using current date')
    return today

def fetch_stock_data(ticker):
    """Fetch stock data from Polygon.io API using SMA endpoint."""
    # Get the most recent trading day
    end_date = get_most_recent_trading_day()
    start_date = end_date - timedelta(days=30)  # Fetch 30 days of data for better analysis
    
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
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'TSM', 'AMD', 'INTC',
        'NFLX', 'ADBE', 'CSCO', 'QCOM', 'AVGO', 'TXN', 'ORCL', 'CRM', 'IBM', 'UBER',
        'VRT', 'PLTR', 'SNOW', 'NET', 'CRWD', 'DDOG', 'ZS', 'TEAM', 'OKTA', 'DOCN'
        ,'RDDT','TEM'
    ]
    
    logger.info(f"Starting scan for {len(stocks)} stocks")
    
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
        ticker_count = 0
        logger.info(f"Processing {len(df) - 2} possible data points for {ticker}")
        
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
            
            all_results.append(result)
            ticker_count += 1
        
        logger.info(f"Added {ticker_count} results for {ticker}")
        logger.info(f"Current total results: {len(all_results)}")

        
        print(f"Added {len(df) - 2} data points for {ticker}")
    
    # Sort results by timestamp in descending order
    all_results.sort(key=lambda x: x['date'], reverse=True)
    return all_results  # Return all results for pagination

@app.route('/')
def home():
    html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Stock Crossover Scanner</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background-color: #f8f9fa; }
            .container { max-width: 1200px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            table { border-collapse: collapse; width: 100%; margin-top: 20px; background-color: white; }
            th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
            th { background-color: #f8f9fa; font-weight: 600; }
            .matched { background-color: rgba(144, 238, 144, 0.3); }
            .crossover { background-color: rgba(255, 192, 203, 0.3); }
            .data-row:hover { background-color: #f8f9fa; }
            #loading { display: none; margin: 20px 0; color: #666; text-align: center; padding: 20px; }
            #loading:after { content: ''; display: inline-block; width: 20px; height: 20px; border: 2px solid #666; border-radius: 50%; border-top-color: transparent; animation: spin 1s linear infinite; }
            @keyframes spin { to { transform: rotate(360deg); } }
            .no-data { text-align: center; padding: 20px; color: #666; font-style: italic; }
            #pagination { margin: 20px 0; text-align: center; }
            #pagination button { padding: 8px 16px; margin: 0 5px; border: 1px solid #ddd; background-color: white; border-radius: 4px; cursor: pointer; }
            #pagination button:hover { background-color: #f8f9fa; }
            #pagination button:disabled { background-color: #eee; cursor: not-allowed; }
            #pageInfo { margin: 0 10px; color: #666; }
            h1 { color: #333; margin-bottom: 20px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Stock Crossover Scanner</h1>
        <div id="loading">Loading stock data and calculating crossovers...</div>
        <div id="stats" style="text-align: center; margin: 10px 0; color: #666;">Total Results: <span id="totalResults">0</span></div>
            <div id="pagination">
                <button onclick="previousPage()" id="prevButton" disabled>Previous</button>
                <span id="pageInfo">Page 1</span>
                <button onclick="nextPage()" id="nextButton" disabled>Next</button>
            </div>
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
        let currentPage = 1;
        let totalPages = 1;

        function fetchData() {
            document.getElementById('loading').style.display = 'block';
            fetch(`/scan?page=${currentPage}`)
                .then(response => response.json())
                .then(data => {
                    const tbody = document.querySelector('#results tbody');
                    if (data.total === 0) {
                        tbody.innerHTML = '<tr><td colspan="10" class="no-data">No data available. Please wait while we fetch the stock data...</td></tr>';
                        return;
                    }
                    tbody.innerHTML = '';
                    totalPages = data.total_pages;
                    
                    document.getElementById('pageInfo').textContent = `Page ${currentPage} of ${totalPages}`;
                    document.getElementById('prevButton').disabled = currentPage <= 1;
                    document.getElementById('nextButton').disabled = currentPage >= totalPages;
                    document.getElementById('totalResults').textContent = data.total;
                    
                    data.results.forEach(item => {
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
                    const tbody = document.querySelector('#results tbody');
                    tbody.innerHTML = '<tr><td colspan="10" class="no-data">Error loading data. Please try again later.</td></tr>';
                    console.error('Error:', error);
                    document.getElementById('loading').style.display = 'none';
                });
        }

        function previousPage() {
            if (currentPage > 1) {
                currentPage--;
                fetchData();
            }
        }

        function nextPage() {
            if (currentPage < totalPages) {
                currentPage++;
                fetchData();
            }
        }

        // Fetch data immediately and then every 5 minutes
        fetchData();
        setInterval(fetchData, 300000);
        </script>
        </div>
    </body>
    </html>
    '''
    return render_template_string(html)

@app.route('/scan')
def scan():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    results = scan_stocks()
    
    # Calculate pagination
    total_results = len(results)
    logger.info(f"Total results before pagination: {total_results}")
    
    if total_results == 0:
        logger.info("No results available")
        return jsonify({
            'results': [],
            'total': 0,
            'page': page,
            'per_page': per_page,
            'total_pages': 0
        })
    
    # Ensure page number is valid
    total_pages = (total_results + per_page - 1) // per_page
    page = min(max(1, page), total_pages)
    
    # Calculate slice indices
    start_idx = (page - 1) * per_page
    end_idx = min(start_idx + per_page, total_results)
    
    logger.info(f"Pagination details: page={page}, per_page={per_page}, total_pages={total_pages}")
    logger.info(f"Returning results from index {start_idx} to {end_idx} (total: {total_results})")
    
    paginated_results = results[start_idx:end_idx]
    logger.info(f"Number of results in current page: {len(paginated_results)}")
    
    return jsonify({
        'results': paginated_results,
        'total': total_results,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages
    })

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