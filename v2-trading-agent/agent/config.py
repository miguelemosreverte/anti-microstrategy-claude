import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Anthropic
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

    # Deribit
    DERIBIT_CLIENT_ID = os.getenv("DERIBIT_CLIENT_ID", "")
    DERIBIT_CLIENT_SECRET = os.getenv("DERIBIT_CLIENT_SECRET", "")
    DERIBIT_LIVE = os.getenv("DERIBIT_LIVE", "false").lower() == "true"

    DERIBIT_BASE_URL = (
        "https://www.deribit.com/api/v2"
        if DERIBIT_LIVE
        else "https://test.deribit.com/api/v2"
    )
    DERIBIT_WS_URL = (
        "wss://www.deribit.com/ws/api/v2"
        if DERIBIT_LIVE
        else "wss://test.deribit.com/ws/api/v2"
    )

    # Optional API keys
    COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")
    FRED_API_KEY = os.getenv("FRED_API_KEY", "")
    CRYPTOCOMPARE_API_KEY = os.getenv("CRYPTOCOMPARE_API_KEY", "")

    # Database
    DB_PATH = os.path.join(os.path.dirname(__file__), "..", "trading.db")

    # Reports
    REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")
