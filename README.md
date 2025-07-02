# ETF Crossover Scanner

A web application that scans ETFs for EMA crossover signals using real-time market data from Polygon.io, with data persistence using Firebase.

## Features

- Fetches real-time ETF data from Polygon.io
- Calculates 8-day and 21-day EMAs
- Identifies potential trading signals based on EMA crossovers
- Filters for high-volume ETFs (>1M daily volume)
- Displays results in a clean web interface
- Stores historical data in Firebase

## Local Development Setup

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
5. Open http://localhost:8080 in your browser

## Cloud Run Deployment

### Prerequisites

1. Install [Google Cloud SDK](https://cloud.google.com/sdk/docs/install)
2. Create a Google Cloud Project
3. Enable required APIs:
   ```bash
   gcloud services enable run.googleapis.com
   gcloud services enable cloudbuild.googleapis.com
   gcloud services enable firestore.googleapis.com
   ```

### Deployment Steps

1. Set environment variables:
   ```bash
   export PROJECT_ID=your-project-id
   gcloud config set project $PROJECT_ID
   export POLYGON_API_KEY=your-polygon-api-key
   ```

2. Initialize Firestore:
   ```bash
   gcloud firestore databases create --region=us-east1
   ```

3. Deploy to Cloud Run:
   ```bash
   gcloud run deploy etf-scanner \
     --source . \
     --platform managed \
     --region us-east1 \
     --allow-unauthenticated \
     --set-env-vars POLYGON_API_KEY=$POLYGON_API_KEY
   ```

## Note

- This application requires a valid Polygon.io API key. The free tier includes:
  - Real-time market data
  - 5 API calls per minute
  - 2 years of historical data
- Firebase Firestore is used for data persistence
- The application is configured to run on Cloud Run with automatic scaling