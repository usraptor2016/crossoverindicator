import firebase_admin
from firebase_admin import credentials, firestore

def initialize_firebase():
    """Initialize Firebase Admin SDK and return Firestore client."""
    try:
        # Check if already initialized
        app = firebase_admin.get_app()
    except ValueError:
        # Initialize with service account
        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred, {
            'projectId': 'YOUR_PROJECT_ID',  # Replace with your GCP project ID
        })
    
    # Return Firestore client
    return firestore.client()

# Initialize Firestore client
db = initialize_firebase()