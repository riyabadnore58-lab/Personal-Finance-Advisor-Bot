import os
import sys
import logging
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

from app import app
from pyngrok import ngrok, conf

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # Retrieve authtoken from .env or placeholder
    auth_token = os.environ.get("NGROK_AUTHTOKEN", "").strip()

    if auth_token and auth_token != "your_ngrok_authtoken_here":
        try:
            ngrok.set_auth_token(auth_token)
            logger.info("Configured Ngrok authtoken from environment.")
        except Exception as e:
            logger.warning(f"Could not set Ngrok authtoken: {e}")
    else:
        logger.info("No explicit NGROK_AUTHTOKEN found in .env. Attempting tunnel start with default local client...")

    port = 5000
    try:
        # Start an HTTP tunnel on port 5000
        public_url = ngrok.connect(port)
        print("\n" + "="*70)
        print(f"YOUR PUBLIC WEBSITE URL IS LIVE! URL: {public_url.public_url}")
        print("="*70 + "\n")
        logger.info(f"Ngrok tunnel opened successfully at: {public_url.public_url}")
    except Exception as err:
        print(f"\n[Warning] Could not start Ngrok tunnel automatically: {err}")
        print("Running Flask app locally at http://127.0.0.1:5000/\n")

    # Important: debug=False is required to prevent Flask reloader process from spawning multiple tunnels
    app.run(host='0.0.0.0', port=port, debug=False)

if __name__ == '__main__':
    main()
