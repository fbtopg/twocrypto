import streamlit as st
import sys
import os
from decimal import Decimal

# Add tests/utils directory to path to allow importing simulator
# This assumes website.py is in the same directory as the 'tests' folder
current_dir = os.path.dirname(os.path.abspath(__file__))
simulator_path = os.path.join(current_dir, "tests", "utils")
if simulator_path not in sys.path:
    sys.path.append(simulator_path)

try:
    from simulator import Trader
except ImportError as e:
    st.error(f"Error importing 'simulator.py': {e}")
    st.info("Make sure you are running this file from the 'twocrypto-ng-main/twocrypto-ng-main' directory.")
    st.stop()

st.set_page_config(page_title="Stablecoin DEX Simulator", layout="wide")

st.title("💱 Twocrypto-ng Simulator: USD/KRW")
st.markdown("""
This website simulates a decentralized exchange using the **Curve Twocrypto-ng** mathematical model. 
It simulates a liquidity pool between **KRW** (Korean Won) and **USD** (US Dollar).

**Strictly based on:** `twocrypto-ng-main/tests/utils/simulator.py`
""")

# --- Sidebar: Configuration ---
st.sidebar.header("1. Pool Configuration")

# Defaults based on 'forex' preset in pool_presets.csv
default_A = 20000000
default_gamma = 1000000000000000 # 10^15 (0.001)
default_mid_fee = 0.0005 # 0.05%
default_out_fee = 0.0045 # 0.45%

# Initial defaults
default_peg = 1350.0 # 1 USD = 1350 KRW
default_liquidity = 1000000 # 1 Million USD total

# Inputs
with st.sidebar.expander("Advanced Parameters", expanded=False):
    A = st.number_input("Amplification (A)", value=default_A)
    gamma = st.number_input("Gamma (int)", value=default_gamma, help="Gamma parameter in 10^18 scale (e.g. 10^15 = 0.001)")
    mid_fee = st.number_input("Mid Fee", value=default_mid_fee, format="%.6f")
    out_fee = st.number_input("Out Fee", value=default_out_fee, format="%.6f")

st.sidebar.subheader("Market Parameters")
price_peg = st.sidebar.number_input("Initial Price (KRW per USD)", value=default_peg)
liquidity_usd = st.sidebar.number_input("Total Liquidity ($ Value)", value=default_liquidity)

if st.sidebar.button("Initialize / Reset Pool", type="primary"):
    # Logic:
    # Coin 0 = KRW (Base, price=1 relative to itself)
    # Coin 1 = USD (Price = 1350 relative to KRW)
    # D (Invariant) is calculated in KRW units.
    
    D_krw = int(liquidity_usd * price_peg * 10**18)
    p0 = [10**18, int(price_peg * 10**18)]
    
    # Initialize Trader from simulator.py
    # fees in Trader are floats (e.g. 1e-3)
    try:
        trader = Trader(
            A=int(A),
            gamma=int(gamma),
            D=D_krw,
            p0=p0,
            mid_fee=mid_fee,
            out_fee=out_fee
        )
        st.session_state.trader = trader
        st.session_state.log = []
        st.session_state.initialized = True
        st.rerun()
    except Exception as e:
        st.error(f"Failed to initialize pool: {e}")

# --- Main Interface ---

if 'trader' not in st.session_state:
    st.info("👈 Please configure and initialize the pool in the sidebar to start.")
    st.stop()

trader = st.session_state.trader

# Calculate Balances
# curve.x is raw balance in 18 decimals
bal_krw = Decimal(trader.curve.x[0]) / Decimal(10**18)
bal_usd = Decimal(trader.curve.x[1]) / Decimal(10**18)

# Calculate Price from Oracle
# price_oracle[1] is price of Coin 1 (USD) in terms of Coin 0 (KRW) scaled by 10^18
current_price_krw = Decimal(trader.price_oracle[1]) / Decimal(10**18)

# Display Metrics
st.subheader("Pool Status")
m1, m2, m3 = st.columns(3)
m1.metric("Pool KRW Liquidity", f"₩{bal_krw:,.0f}")
m2.metric("Pool USD Liquidity", f"${bal_usd:,.2f}")
m3.metric("Oracle Price (KRW/USD)", f"₩{current_price_krw:,.2f}")

st.divider()

# Swap Section
st.subheader("💱 Swap Tokens")

col_buy_krw, col_buy_usd = st.columns(2)

with col_buy_krw:
    st.markdown("#### Buy KRW (Sell USD)")
    sell_usd_amt = st.number_input("Amount USD to sell", min_value=0.0, value=100.0, step=10.0, key="sell_usd")
    
    # Quote
    if sell_usd_amt > 0:
        # Simulate swap to get quote without executing?
        # Trader.buy modifies state. We can't easily "peek" without implementing get_dy logic separate from buy.
        # But we can copy the curve? Or just rely on 'buy' action.
        # For simplicity in this demo, we just show the button.
        pass

    if st.button("Sell USD"):
        dx = int(Decimal(sell_usd_amt) * Decimal(10**18))
        # buy(dx, i, j) -> User sends dx of i, gets dy of j
        # i=1 (USD), j=0 (KRW)
        dy = trader.buy(dx, 1, 0)
        
        if dy:
            got_krw = Decimal(dy) / Decimal(10**18)
            st.success(f"Swapped ${sell_usd_amt:,.2f} USD for ₩{got_krw:,.0f} KRW")
            st.session_state.log.append(f"SELL ${sell_usd_amt} USD -> BUY ₩{got_krw:,.2f} KRW @ {got_krw/Decimal(sell_usd_amt):.2f}")
            st.rerun()
        else:
            st.error("Swap failed (Slippage or Limits)")

with col_buy_usd:
    st.markdown("#### Buy USD (Sell KRW)")
    sell_krw_amt = st.number_input("Amount KRW to sell", min_value=0.0, value=100000.0, step=1000.0, key="sell_krw")
    
    if st.button("Sell KRW"):
        dx = int(Decimal(sell_krw_amt) * Decimal(10**18))
        # i=0 (KRW), j=1 (USD)
        dy = trader.buy(dx, 0, 1)
        
        if dy:
            got_usd = Decimal(dy) / Decimal(10**18)
            st.success(f"Swapped ₩{sell_krw_amt:,.0f} KRW for ${got_usd:,.2f} USD")
            st.session_state.log.append(f"SELL ₩{sell_krw_amt} KRW -> BUY ${got_usd:,.2f} USD @ {Decimal(sell_krw_amt)/got_usd:.2f}")
            st.rerun()
        else:
            st.error("Swap failed (Slippage or Limits)")

# History
if st.session_state.log:
    st.divider()
    st.subheader("Transaction History")
    for msg in reversed(st.session_state.log):
        st.text(msg)

