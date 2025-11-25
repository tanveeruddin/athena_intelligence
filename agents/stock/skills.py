"""
Skills for the Stock Agent.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import yfinance as yf
from cachetools import TTLCache

from models.schemas import StockDataInput, StockDataOutput
from utils.logging import get_logger
from utils.db_logger import log_to_db

logger = get_logger()
cache = TTLCache(maxsize=1000, ttl=3600)

async def get_stock_data(input_data: StockDataInput) -> StockDataOutput:
    """
    Fetches stock market data including price, market cap, and performance metrics.

    Args:
        input_data: The input parameters for the stock data skill.

    Returns:
        The output of the stock data skill.
    """
    task_id = input_data.task_id
    asx_code = input_data.asx_code
    log_to_db(task_id, "stock", f"Fetching stock data for {asx_code}")
    logger.info(f"Fetching stock data for {asx_code}")

    cache_key = f"stock_data_{asx_code}"
    if cache_key in cache:
        log_to_db(task_id, "stock", f"Returning cached stock data for {asx_code}")
        logger.debug(f"Returning cached stock data for {asx_code}")
        return cache[cache_key]

    ticker_symbol = f"{asx_code}.AX"

    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        
        # Fetching historical data to ensure we can calculate performance
        end_date = datetime.now()
        start_date = end_date - timedelta(days=200) # Buffer for 6 months
        hist = ticker.history(start=start_date, end=end_date)

        if hist.empty:
            raise ValueError("No historical data found for the ticker.")

        current_price = info.get('currentPrice') or info.get('regularMarketPrice') or hist['Close'].iloc[-1]

        stock_data = StockDataOutput(
            asx_code=asx_code,
            price=float(current_price) if current_price else None,
            market_cap=float(info.get('marketCap')) if info.get('marketCap') else None,
            performance_1m_pct=_calculate_performance(hist, days=30),
            performance_3m_pct=_calculate_performance(hist, days=90),
            performance_6m_pct=_calculate_performance(hist, days=180),
        )

        log_to_db(task_id, "stock", f"Successfully fetched stock data for {asx_code}")
        logger.info(f"Successfully fetched stock data for {asx_code}")
        cache[cache_key] = stock_data
        return stock_data

    except Exception as e:
        log_to_db(task_id, "stock", f"Failed to fetch stock data for {asx_code}: {e}")
        logger.error(f"Failed to fetch stock data for {asx_code}: {e}")
        return StockDataOutput(
            asx_code=asx_code,
            price=None,
            market_cap=None,
            performance_1m_pct=None,
            performance_3m_pct=None,
            performance_6m_pct=None,
        )

def _calculate_performance(hist, days: int) -> Optional[float]:
    """Calculates performance over a given number of days."""
    if len(hist) < 2:
        return None
        
    end_date = hist.index[-1]
    start_date = end_date - timedelta(days=days)
    
    try:
        # Find the closest available trading day to the start date
        past_price_series = hist['Close'][hist.index <= start_date]
        if past_price_series.empty:
            # If no data before start date, use the earliest available price
            past_price = hist['Close'].iloc[0]
        else:
            past_price = past_price_series.iloc[-1]

        current_price = hist['Close'].iloc[-1]

        if past_price and current_price and past_price > 0:
            performance = ((current_price - past_price) / past_price) * 100
            return round(float(performance), 2)
    except Exception as e:
        logger.warning(f"Could not calculate {days}-day performance: {e}")
    
    return None
