import yfinance as yf
from datetime import datetime, time
import pytz


# =========================================================
# NSE MARKET HOURS
# =========================================================

IST = pytz.timezone("Asia/Kolkata")

MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)


def is_market_open() -> bool:
    """
    Check whether the NSE market is currently open.

    Rules for now:
    - Monday to Friday
    - 09:15 AM to 03:30 PM IST

    NSE holidays are not handled yet.
    """

    now = datetime.now(IST)

    # Saturday = 5, Sunday = 6
    if now.weekday() >= 5:
        return False

    current_time = now.time()

    return MARKET_OPEN <= current_time <= MARKET_CLOSE

# =========================================================
# SYMBOL MAPPING
# =========================================================

SYMBOL_TO_YAHOO_TICKER = {
    "TCS": "TCS.NS",
    "INFY": "INFY.NS",
    "RELIANCE": "RELIANCE.NS",
    "HDFCBANK": "HDFCBANK.NS",
    "WIPRO": "WIPRO.NS",
}


# =========================================================
# CUSTOM ERROR
# =========================================================

class PriceFetchError(Exception):
    """Raised when a stock price cannot be fetched."""
    pass


# =========================================================
# CONVERT OUR SYMBOL → YAHOO FINANCE TICKER
# =========================================================

def get_yahoo_ticker(symbol: str) -> str:

    ticker = SYMBOL_TO_YAHOO_TICKER.get(symbol.upper())

    if ticker is None:
        raise PriceFetchError(
            f"No Yahoo Finance ticker mapped for symbol '{symbol}'."
        )

    return ticker


# =========================================================
# FETCH PRICE FOR ONE STOCK
# =========================================================

def fetch_live_price(symbol: str) -> float:

    ticker_symbol = get_yahoo_ticker(symbol)

    ticker = yf.Ticker(ticker_symbol)

    # -----------------------------------------------------
    # Try fast_info first
    # -----------------------------------------------------

    try:
        price = ticker.fast_info["last_price"]

        if price:
            return round(float(price), 2)

    except Exception:
        pass

    # -----------------------------------------------------
    # Fallback: use recent price history
    # -----------------------------------------------------

    try:
        history = ticker.history(period="1d")

        if history.empty:
            raise PriceFetchError(
                f"No price data available for '{ticker_symbol}'."
            )

        last_close = history["Close"].iloc[-1]

        return round(float(last_close), 2)

    except PriceFetchError:
        raise

    except Exception as error:
        raise PriceFetchError(
            f"Failed to fetch price for '{ticker_symbol}': {error}"
        )


# =========================================================
# FETCH PRICES FOR MULTIPLE STOCKS
# =========================================================

def fetch_live_prices(symbols: list[str]) -> tuple[dict[str, float], dict[str, str]]:

    prices = {}
    errors = {}

    for symbol in symbols:

        try:
            prices[symbol] = fetch_live_price(symbol)

        except PriceFetchError as error:
            errors[symbol] = str(error)

    return prices, errors