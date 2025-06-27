# ETF Crossover Scanner

A web application that scans ETFs for EMA crossover signals using real-time market data from Polygon.io.

## Setup

1. Get a free API key from [Polygon.io](https://polygon.io/)
2. Set up your Polygon.io API key as an environment variable:
   ```bash
   export POLYGON_API_KEY='your_api_key_here'
   ```
3. Install dependencies:
   ```bash
   pip3 install -r requirements.txt
   ```
4. Run the application:
   ```bash
   python3 app.py
   ```
5. Open http://localhost:5000 in your browser

## Features

- Fetches real-time ETF data from Polygon.io
- Calculates 8-day and 21-day EMAs
- Identifies potential trading signals based on EMA crossovers
- Filters for high-volume ETFs (>1M daily volume)
- Displays results in a clean web interface

## Note

This application requires a valid Polygon.io API key. The free tier includes:
- Real-time market data
- 5 API calls per minute
- 2 years of historical data