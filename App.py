import math
import os

import streamlit as st
from groq import Groq
import yfinance as yf
import plotly.graph_objects as go
from ta.momentum import RSIIndicator

# =====================================
# FIXES APPLIED (see chat for details)
# - Removed hardcoded API key; reads from st.secrets / env var instead
# - Fixed crash: comparison block used `ticker` before it was defined
# - Removed duplicated Metrics/Performance/Company Info/AI Analysis blocks
#   (everything was being rendered + the Groq API called twice)
# - History/EMA/RSI now fetched once and reused (was fetched 3x separately)
# - Added None/NaN guards for RSI, chart, support/resistance, missing fields
# - Added regularMarketPrice/regularMarketPreviousClose fallbacks (some
#   tickers don't expose currentPrice/previousClose)
# - Consistent price formatting + a market cap formatter (e.g. $3.02T)
# =====================================

try:
    _secret_key = st.secrets.get("GROQ_API_KEY", "")
except Exception:
    _secret_key = ""

GROQ_API_KEY = _secret_key or os.environ.get("GROQ_API_KEY", "")

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

st.set_page_config(
    page_title="AI Stock Market Assistant",
    page_icon="📈",
    layout="wide"
)
st.markdown("""
<style>

.main {
    padding-top: 1rem;
}

div[data-testid="metric-container"] {
    border: 1px solid #262730;
    padding: 15px;
    border-radius: 12px;
    background-color: #111827;
}

div[data-testid="stMetricValue"] {
    font-size: 26px;
}

.block-container {
    padding-top: 1rem;
}

</style>
""", unsafe_allow_html=True)

if not GROQ_API_KEY:
    st.sidebar.warning(
        "No Groq API key found. Set GROQ_API_KEY in `.streamlit/secrets.toml` "
        "or as an environment variable to enable AI analysis."
    )

# =====================================
# WATCHLIST
# =====================================

st.sidebar.markdown("""
# 🚀 Dashboard

AI Powered Stock Analysis
""")

watchlist = [
    "AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "GOOGL", "META",
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "BTC-USD", "ETH-USD"
]

selected_stock = st.sidebar.selectbox("Quick Select", watchlist)

st.sidebar.divider()
st.sidebar.subheader("⚔️ Stock Comparison")
compare_stock = st.sidebar.text_input("Compare With", placeholder="MSFT").strip()

# =====================================
# HELPERS
# =====================================

def get_currency_symbol(currency):
    symbols = {"USD": "$", "INR": "₹", "EUR": "€", "GBP": "£", "JPY": "¥"}
    return symbols.get(currency, (currency or "") + " ")


def format_large_number(num):
    if num is None:
        return "N/A"
    abs_num = abs(num)
    if abs_num >= 1e12:
        return f"{num / 1e12:.2f}T"
    if abs_num >= 1e9:
        return f"{num / 1e9:.2f}B"
    if abs_num >= 1e6:
        return f"{num / 1e6:.2f}M"
    return f"{num:,.0f}"


def fmt_price(value, currency_symbol):
    if value is None:
        return "N/A"
    return f"{currency_symbol}{value:,.2f}"


# =====================================
# STOCK DATA
# =====================================

def get_stock_data(symbol):
    stock = yf.Ticker(symbol)
    info = stock.info

    current_price = info.get("currentPrice") or info.get("regularMarketPrice")
    previous_close = info.get("previousClose") or info.get("regularMarketPreviousClose")

    if current_price is not None and previous_close:
        change = current_price - previous_close
        change_percent = (change / previous_close) * 100
    else:
        change = 0
        change_percent = 0

    return {
        "company": info.get("longName", symbol),
        "symbol": symbol.upper(),
        "currency": info.get("currency", "USD"),
        "current_price": current_price,
        "previous_close": previous_close,
        "day_high": info.get("dayHigh") or info.get("regularMarketDayHigh"),
        "day_low": info.get("dayLow") or info.get("regularMarketDayLow"),
        "market_cap": info.get("marketCap"),
        "change": change,
        "change_percent": change_percent
    }


def get_compare_data(symbol):

    stock = yf.Ticker(symbol)

    info = stock.info

    return {
        "Company": info.get("longName", symbol),
        "Price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "Market Cap": info.get("marketCap"),
        "Day High": info.get("dayHigh") or info.get("regularMarketDayHigh"),
        "Day Low": info.get("dayLow") or info.get("regularMarketDayLow"),
        "Currency": info.get("currency", "USD")
    }


# =====================================
# HISTORY + INDICATORS
# Fetched once per analysis and reused for the chart, RSI and trend section
# (previously this data was pulled from yfinance three separate times)
# =====================================

def get_history_with_indicators(symbol, period="6mo"):
    stock = yf.Ticker(symbol)
    hist = stock.history(period=period)

    if hist.empty:
        return None

    hist["EMA20"] = hist["Close"].ewm(span=20, adjust=False).mean()
    hist["EMA50"] = hist["Close"].ewm(span=50, adjust=False).mean()

    if len(hist) >= 15:
        hist["RSI"] = RSIIndicator(close=hist["Close"]).rsi()

    return hist


def create_chart(symbol, hist):
    support = round(hist["Low"].tail(30).min(), 2)
    resistance = round(hist["High"].tail(30).max(), 2)

    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=hist.index,
        open=hist["Open"],
        high=hist["High"],
        low=hist["Low"],
        close=hist["Close"],
        name="Price"
    ))

    fig.add_trace(go.Scatter(
        x=hist.index, y=hist["EMA20"], mode="lines", name="EMA 20", line=dict(width=2)
    ))
    fig.add_trace(go.Scatter(
        x=hist.index, y=hist["EMA50"], mode="lines", name="EMA 50", line=dict(width=2)
    ))

    fig.add_hline(y=support, line_dash="dash", annotation_text=f"Support {support}")
    fig.add_hline(y=resistance, line_dash="dash", annotation_text=f"Resistance {resistance}")

    fig.update_layout(
        template="plotly_dark",
        title=f"📈 {symbol} Market Dashboard",
        height=700,
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        legend_title="Indicators",
        yaxis_title="Price",
        margin=dict(l=20, r=20, t=50, b=20)
    )

    return fig, support, resistance


# =====================================
# AI ANALYSIS
# =====================================

def analyze_stock(stock_data, rsi):
    if client is None:
        return "AI analysis unavailable — no Groq API key is configured."

    prompt = f"""
    You are a professional stock analyst.

    Company: {stock_data['company']}
    Symbol: {stock_data['symbol']}
    Current Price: {stock_data['current_price']}
    Previous Close: {stock_data['previous_close']}
    Day High: {stock_data['day_high']}
    Day Low: {stock_data['day_low']}
    Market Cap: {stock_data['market_cap']}
    RSI: {rsi if rsi is not None else "N/A"}

    Provide:

    1. Market Sentiment
    2. Opportunities
    3. Risks
    4. Short-Term Outlook
    5. Buy / Hold / Sell Opinion

    Keep response concise and professional.
    """

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=500
    )

    return response.choices[0].message.content


# =====================================
# UI
# =====================================

st.markdown("""
# 📈 AI Stock Market Assistant

### Real-Time Market Intelligence Powered by Groq AI

Analyze stocks, compare companies, detect trends, and get AI-powered insights.
""")
st.success(
    "🟢 Live Market Data Connected"
)
ticker = st.text_input("Enter Stock Symbol", value=selected_stock).strip()

# =====================================
# STOCK COMPARISON
# =====================================

if compare_stock:

    st.divider()
    st.markdown("## ⚔️ Stock Comparison")

    try:

        stock1 = get_compare_data(ticker)
        stock2 = get_compare_data(compare_stock)

        symbol1 = get_currency_symbol(
            stock1["Currency"]
        )

        symbol2 = get_currency_symbol(
            stock2["Currency"]
        )

        left, right = st.columns(2)

        # =====================
        # STOCK 1
        # =====================

        with left:

            st.markdown(
                f"### 📈 {ticker.upper()}"
            )

            st.caption(
                stock1["Company"]
            )

            st.metric(
                "Price",
                fmt_price(
                    stock1["Price"],
                    symbol1
                )
            )

            st.metric(
                "Market Cap",
                format_large_number(
                    stock1["Market Cap"]
                )
            )

            st.metric(
                "Day High",
                fmt_price(
                    stock1["Day High"],
                    symbol1
                )
            )

            st.metric(
                "Day Low",
                fmt_price(
                    stock1["Day Low"],
                    symbol1
                )
            )

        # =====================
        # STOCK 2
        # =====================

        with right:

            st.markdown(
                f"### 📈 {compare_stock.upper()}"
            )

            st.caption(
                stock2["Company"]
            )

            st.metric(
                "Price",
                fmt_price(
                    stock2["Price"],
                    symbol2
                )
            )

            st.metric(
                "Market Cap",
                format_large_number(
                    stock2["Market Cap"]
                )
            )

            st.metric(
                "Day High",
                fmt_price(
                    stock2["Day High"],
                    symbol2
                )
            )

            st.metric(
                "Day Low",
                fmt_price(
                    stock2["Day Low"],
                    symbol2
                )
            )

    except Exception as e:

        st.warning(
            f"Comparison Error: {str(e)}"
        )

# =====================================
# MAIN
# =====================================

if st.button("Analyze Stock"):

    try:
        with st.spinner("Fetching stock data..."):
            data = get_stock_data(ticker)

        if data["current_price"] is None:
            st.error("Invalid stock symbol.")
            st.stop()

        currency_symbol = get_currency_symbol(data["currency"])

        with st.spinner("Loading price history..."):
            hist = get_history_with_indicators(ticker)

        rsi = None
        ema20 = ema50 = None
        support = resistance = None
        chart = None

        if hist is not None:
            chart, support, resistance = create_chart(ticker, hist)
            ema20 = hist["EMA20"].iloc[-1]
            ema50 = hist["EMA50"].iloc[-1]

            if "RSI" in hist.columns:
                last_rsi = hist["RSI"].iloc[-1]
                if last_rsi is not None and not math.isnan(last_rsi):
                    rsi = round(last_rsi, 2)
        # ==========================
        # MARKET OVERVIEW
        # ==========================

        st.markdown("---")
        st.markdown("## 📊 Market Overview")

        overview1, overview2, overview3, overview4 = st.columns(4)

        with overview1:
            st.metric(
                "Price",
                fmt_price(
                    data["current_price"],
                    currency_symbol
                )
            )

        with overview2:
            st.metric(
                "Change %",
                f"{data['change_percent']:.2f}%"
            )

        with overview3:
            st.metric(
                "RSI",
                str(rsi) if rsi else "N/A"
            )

        with overview4:
            st.metric(
                "Market Cap",
                format_large_number(
                    data["market_cap"]
                )
            )


        # ==========================
        # CHART
        # ==========================

        if chart is not None:
            st.plotly_chart(chart, use_container_width=True)
        else:
            st.warning("Not enough historical data to build a chart for this symbol.")

        # ==========================
        # QUICK STATS
        # ==========================

        quick1, quick2, quick3 = st.columns(3)

        with quick1:
            st.metric(
                "EMA20",
                f"{ema20:.2f}" if ema20 else "N/A"
            )

        with quick2:
            st.metric(
                "EMA50",
                f"{ema50:.2f}" if ema50 else "N/A"
            )

        with quick3:
            st.metric(
                "RSI",
                str(rsi) if rsi else "N/A"
            )
        # ==========================
        # RSI
        # ==========================

        st.markdown("---")
        st.markdown("## 📈 Technical Indicators")
        if rsi is not None:
            if rsi >= 70:
                st.error(f"RSI: {rsi} 🔴 Overbought")
            elif rsi <= 30:
                st.success(f"RSI: {rsi} 🟢 Oversold")
            else:
                st.info(f"RSI: {rsi} 🟡 Neutral")
        else:
            st.info("RSI unavailable (not enough price history).")

        # ==========================
        # TREND ANALYSIS
        # ==========================

        if support is not None and resistance is not None:

            st.markdown("---")
            st.markdown("## 📊 Trend Analysis")

            trend_col1, trend_col2, trend_col3 = st.columns(3)

            with trend_col1:
                st.metric("Support", fmt_price(support, currency_symbol))

            with trend_col2:
                st.metric("Resistance", fmt_price(resistance, currency_symbol))

            with trend_col3:
                if ema20 is not None and ema50 is not None:
                    if ema20 > ema50:
                        st.success("🟢 Bullish Trend")
                    else:
                        st.error("🔴 Bearish Trend")

        # ==========================
        # METRICS
        # ==========================

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "Current Price",
                fmt_price(data['current_price'], currency_symbol),
                f"{data['change_percent']:.2f}%"
            )

        with col2:
            st.metric("Day High", fmt_price(data['day_high'], currency_symbol))

        with col3:
            st.metric("Day Low", fmt_price(data['day_low'], currency_symbol))

        with col4:
            st.metric("Previous Close", fmt_price(data['previous_close'], currency_symbol))

        # ==========================
        # PERFORMANCE
        # ==========================

        st.markdown("---")
        st.markdown("## 📊 Today's Performance")

        if data["change_percent"] > 0:
            st.success(f"🟢 Up {data['change_percent']:.2f}% Today")
        elif data["change_percent"] < 0:
            st.error(f"🔴 Down {abs(data['change_percent']):.2f}% Today")
        else:
            st.info("🟡 No Change Today")

        # ==========================
        # COMPANY INFO
        # ==========================

        st.markdown("---")
        st.markdown("## 🏢 Company Information")

        col1, col2 = st.columns(2)

        with col1:
            st.metric("Company", data["company"])
            st.metric("Symbol", data["symbol"])

        with col2:
            st.metric("Currency", data["currency"])
            st.metric(
                "Market Cap",
                format_large_number(data["market_cap"])
            )

        # ==========================
        # AI ANALYSIS
        # ==========================
        st.markdown("---")
        st.markdown("## 🤖 AI Stock Analysis")

        with st.spinner("Generating AI Analysis..."):
            analysis = analyze_stock(data, rsi)

        with st.container(border=True):
            st.markdown(analysis)

    except Exception as e:
        st.error(f"Error: {str(e)}")