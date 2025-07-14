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
    """Fetch stock data and EMAs from Polygon.io API."""
    # Get the most recent trading day
    end_date = get_most_recent_trading_day()
    start_date = end_date - timedelta(days=30)  # Fetch 30 days of data for better analysis
    
    logging.info(f"Using date range: {start_date.date()} to {end_date.date()}")
    
    # Format dates as YYYY-MM-DD
    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')
    
    logging.info(f"Fetching data for {ticker} from {start_date_str} to {end_date_str}")
    
    try:
        # Fetch aggregates data first
        aggs = client.get_aggs(
            ticker=ticker,
            from_=start_date_str,
            to=end_date_str,
            multiplier=1,
            timespan="day",
            adjusted=True
        )
        
        if not aggs:
            logging.error(f"No aggregate data available for {ticker}")
            return pd.DataFrame()
            
        # Create base DataFrame with price and volume data
        df = pd.DataFrame([
            {
                'Date': pd.to_datetime(agg.timestamp, unit='ms').tz_localize('UTC').tz_convert('US/Eastern').date(),
                'Price': agg.close,
                'Volume': agg.volume,
                'timestamp': agg.timestamp
            }
            for agg in aggs
        ])
        
        # Calculate date range for EMA data
        ema_start_date = end_date - timedelta(days=60)  # Fetch 60 days for better EMA calculation
        end_timestamp = int(end_date.timestamp() * 1000)  # Convert to milliseconds
        # Fetch EMA8 data
        ema8_response = client.get_ema(
            ticker=ticker,
            timespan="day",
            adjusted=True,
            window=8,
            series_type="close",
            order="desc",
            limit=120,
            expand_underlying=True
        )
        
        # Fetch EMA21 data
        ema21_response = client.get_ema(
            ticker=ticker,
            timespan="day",
            adjusted=True,
            window=21,
            series_type="close",
            order="desc",
            limit=120,
            expand_underlying=True
        )
        
        if not ema8_response or not ema21_response:
            logging.error(f"No EMA data available for {ticker}")
            return pd.DataFrame()
        
        # Log EMA response details
        logging.info(f"EMA8 response for {ticker}: {ema8_response}")
        logging.info(f"EMA21 response for {ticker}: {ema21_response}")
        
        # Add EMA values to DataFrame with error handling
        try:
            # Create dictionaries for EMA values
            ema8_dict = {}
            ema21_dict = {}
            
            # Extract values from responses
            if hasattr(ema8_response, 'values') and ema8_response.values:
                for r in ema8_response.values:
                    if hasattr(r, 'timestamp') and hasattr(r, 'value'):
                        ema8_dict[r.timestamp] = r.value
            
            if hasattr(ema21_response, 'values') and ema21_response.values:
                for r in ema21_response.values:
                    if hasattr(r, 'timestamp') and hasattr(r, 'value'):
                        ema21_dict[r.timestamp] = r.value
            
            # Map values to DataFrame
            df['EMA8'] = df['timestamp'].map(ema8_dict)
            df['EMA21'] = df['timestamp'].map(ema21_dict)
            
            # Fill NaN values with previous values or 0
            df['EMA8'] = df['EMA8'].fillna(method='ffill').fillna(0)
            df['EMA21'] = df['EMA21'].fillna(method='ffill').fillna(0)
            
        except Exception as e:
            logging.error(f"Error mapping EMA values for {ticker}: {str(e)}")
            return pd.DataFrame()
        
        # Drop timestamp column as it's no longer needed
        df = df.drop('timestamp', axis=1)
        
        if df.empty:
            logging.error(f"Failed to process data for {ticker}")
            return df
        
        # Sort by date descending for display
        df = df.sort_values('Date', ascending=False).reset_index(drop=True)
        
        logging.info(f"Successfully processed {len(df)} days of data for {ticker}")
        return df
        
    except Exception as e:
        logging.error(f"Error processing {ticker}: {str(e)}")
        return pd.DataFrame()

def scan_stocks():
    """Scan ETFs for crossover patterns using 8-day and 21-day EMAs."""
    # List of stocks to monitor
    stocks = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'TEM', 'META', 'TSLA', 'TSM', 'AMD', 'INTC',
        'NFLX', 'ADBE', 'CSCO', 'QCOM', 'AVGO', 'TXN', 'ORCL', 'CRM', 'IBM', 'UBER',
        'VRT', 'PLTR', 'SNOW', 'NET', 'CRWD', 'DDOG', 'ZS', 'TEAM', 'OKTA', 'DOCN'
        ,'RDDT'
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
            
            # Check for crossover points (both upward and downward crossings)
            crossover_points = {
                'today_up': bool(today['EMA8'] > today['EMA21'] and yesterday['EMA8'] <= yesterday['EMA21']),
                'today_down': bool(today['EMA8'] < today['EMA21'] and yesterday['EMA8'] >= yesterday['EMA21']),
                'yesterday_up': bool(yesterday['EMA8'] > yesterday['EMA21'] and day_before['EMA8'] <= day_before['EMA21']),
                'yesterday_down': bool(yesterday['EMA8'] < yesterday['EMA21'] and day_before['EMA8'] >= day_before['EMA21'])
            }
            
            # Determine if this is a valid crossover pattern
            ema_crossover_condition = any([
                crossover_points['today_up'],
                crossover_points['today_down'],
                crossover_points['yesterday_up'],
                crossover_points['yesterday_down']
            ])
            
            def safe_float(value):
                try:
                    return float(round(value, 2)) if pd.notna(value) else 0.0
                except:
                    return 0.0

            def safe_int(value):
                try:
                    return int(value) if pd.notna(value) else 0
                except:
                    return 0

            result = {
                'symbol': str(ticker),
                'date': today['Date'].strftime('%Y-%m-%d'),
                'price': safe_float(today['Price']),
                'volume': safe_int(today['Volume']),
                'ema8': safe_float(today['EMA8']),
                'ema21': safe_float(today['EMA21']),
                'yesterday_date': yesterday['Date'].strftime('%Y-%m-%d'),
                'yesterday_price': safe_float(yesterday['Price']),
                'yesterday_volume': safe_int(yesterday['Volume']),
                'yesterday_ema8': safe_float(yesterday['EMA8']),
                'yesterday_ema21': safe_float(yesterday['EMA21']),
                'day_before_date': day_before['Date'].strftime('%Y-%m-%d'),
                'day_before_price': safe_float(day_before['Price']),
                'day_before_volume': safe_int(day_before['Volume']),
                'day_before_ema8': safe_float(day_before['EMA8']),
                'day_before_ema21': safe_float(day_before['EMA21']),
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
            table { border-collapse: collapse; width: 100%; margin-top: 20px; background-color: white; font-size: 14px; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: right; }
            th { background-color: #f8f9fa; font-weight: 600; text-align: center; }
            td:first-child { text-align: left; font-weight: 600; }
            td:nth-child(5n+2) { text-align: center; }
            .ema { color: #666; }
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
        <div id="loading" style="display: none;">Loading stock data and calculating crossovers...</div>
        <div id="error" style="display: none; text-align: center; margin: 10px 0; color: #dc3545;"></div>
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
                    <th colspan="5">Today</th>
                    <th colspan="5">Yesterday</th>
                    <th colspan="5">Day Before</th>
                </tr>
                <tr>
                    <th></th>
                    <th>Date</th>
                    <th>Price</th>
                    <th>Volume</th>
                    <th>EMA8</th>
                    <th>EMA21</th>
                    <th>Date</th>
                    <th>Price</th>
                    <th>Volume</th>
                    <th>EMA8</th>
                    <th>EMA21</th>
                    <th>Date</th>
                    <th>Price</th>
                    <th>Volume</th>
                    <th>EMA8</th>
                    <th>EMA21</th>
                </tr>
            </thead>
            <tbody></tbody>
        </table>

        <script>
        let currentPage = 1;
        let totalPages = 1;

        function fetchData() {
            document.getElementById('loading').style.display = 'block';
            document.getElementById('error').style.display = 'none';
            document.getElementById('stats').style.display = 'none';
            document.getElementById('pagination').style.display = 'none';
            document.querySelector('#results tbody').innerHTML = '';
            const fetchTimeout = setTimeout(() => {
                const errorDiv = document.getElementById('error');
                errorDiv.textContent = 'Request timeout. Please try again.';
                errorDiv.style.display = 'block';
                document.getElementById('loading').style.display = 'none';
            }, 30000);

            fetch(`/scan?page=${currentPage}`, {
                headers: {
                    'Accept': 'application/json',
                    'Cache-Control': 'no-cache'
                }
            })
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    const tbody = document.querySelector('#results tbody');
                    if (data.total === 0) {
                        tbody.innerHTML = '<tr><td colspan="16" class="no-data">No data available. Please wait while we fetch the stock data...</td></tr>';
                        document.getElementById('loading').style.display = 'none';
                        document.getElementById('stats').style.display = 'block';
                        document.getElementById('pagination').style.display = 'block';
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
                            <td class="${item.crossover_points.today_up || item.crossover_points.today_down ? 'crossover' : ''}">${Number(item.price || 0).toFixed(2)}</td>
                            <td>${(item.volume || 0).toLocaleString()}</td>
                            <td class="ema">${Number(item.ema8 || 0).toFixed(2)}</td>
                            <td class="ema">${Number(item.ema21 || 0).toFixed(2)}</td>
                        `;
                        
                        // Add yesterday's data
                        row.innerHTML += `
                            <td>${item.yesterday_date}</td>
                            <td class="${item.crossover_points.yesterday_up || item.crossover_points.yesterday_down ? 'crossover' : ''}">${Number(item.yesterday_price || 0).toFixed(2)}</td>
                            <td>${(item.yesterday_volume || 0).toLocaleString()}</td>
                            <td class="ema">${Number(item.yesterday_ema8 || 0).toFixed(2)}</td>
                            <td class="ema">${Number(item.yesterday_ema21 || 0).toFixed(2)}</td>
                        `;
                        
                        // Add day before's data
                        row.innerHTML += `
                            <td>${item.day_before_date}</td>
                            <td>${Number(item.day_before_price || 0).toFixed(2)}</td>
                            <td>${(item.day_before_volume || 0).toLocaleString()}</td>
                            <td class="ema">${Number(item.day_before_ema8 || 0).toFixed(2)}</td>
                            <td class="ema">${Number(item.day_before_ema21 || 0).toFixed(2)}</td>
                        `;
                        
                        tbody.appendChild(row);
                    });
                    clearTimeout(fetchTimeout);
                    document.getElementById('loading').style.display = 'none';
                    document.getElementById('stats').style.display = 'block';
                    document.getElementById('pagination').style.display = 'block';
                })
                .catch(error => {
                    const tbody = document.querySelector('#results tbody');
                    const errorDiv = document.getElementById('error');
                    errorDiv.textContent = error.message || 'Error loading data. Please try again later.';
                    errorDiv.style.display = 'block';
                    tbody.innerHTML = '';
                    console.error('Error:', error);
                    clearTimeout(fetchTimeout);
                    document.getElementById('loading').style.display = 'none';
                    document.getElementById('stats').style.display = 'none';
                    document.getElementById('pagination').style.display = 'none';
                    
                    // 自动重试
                    setTimeout(() => {
                        fetchData();
                    }, 5000);
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
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        if page < 1:
            return jsonify({'error': 'Invalid page number'}), 400
            
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
    except Exception as e:
        logger.error(f"Error in scan endpoint: {str(e)}")
        return jsonify({'error': 'Internal server error', 'message': str(e)}), 500

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