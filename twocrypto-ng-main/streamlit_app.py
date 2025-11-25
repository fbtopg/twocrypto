import streamlit as st
import sys
import os
import copy
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
    st.info("Make sure you are running this file from the 'twocrypto-ng-main' directory.")
    st.stop()

def get_trade_preview(trader, dx, i, j):
    """
    Simulates a trade without modifying the actual trader state.
    Returns dy (amount received) or None if trade fails.
    """
    try:
        # Create a deep copy to ensure no state leaks
        sim_trader = copy.deepcopy(trader)
        dy = sim_trader.buy(dx, i, j)
        return dy
    except Exception:
        return None

st.set_page_config(page_title="Stablecoin DEX Simulator", layout="wide")

# Navigation
page = st.sidebar.radio("Navigation", ["Simulator", "Documentation"])

if page == "Documentation":
    st.title("📚 Simulator Documentation")
    st.markdown("""
    ## Introduction
    This simulator is built upon the **Curve Twocrypto-ng** mathematical model. It demonstrates how a specialized decentralized exchange (DEX) functions for pairs of assets with variable prices, such as **USD** and **KRW**.

    Unlike standard constant product pools (Uniswap V2), this model concentrates liquidity around the current "Oracle Price" to provide better exchange rates with lower slippage, similar to how order books work on centralized exchanges, but fully automated.

    ## Key Concepts

    ### 1. Amplification Coefficient (A)
    *   **What it is:** A parameter that determines how "flat" the pricing curve is.
    *   **Effect:** 
        *   **Higher A:** The pool behaves like a stable swap (Curve V1), assuming prices won't change much. This is good for pegged assets (e.g., USDC/USDT) or when the exchange rate is very stable.
        *   **Lower A:** The pool behaves more like a standard product pool (Uniswap V2), allowing for larger price deviations but with higher slippage.
    *   **In this sim:** Default is `20,000,000`.

    ### 2. Gamma (γ)
    *   **What it is:** A parameter that controls the width of the liquidity concentration area.
    *   **Effect:** 
        *   **Small Gamma:** Liquidity is very tightly concentrated around the Oracle Price. Good for low volatility.
        *   **Large Gamma:** Liquidity is spread out. Good for high volatility.
    *   **In this sim:** Default is `10^15` (or 0.001).

    ### 3. The Oracle Price
    *   **What it is:** The pool's internal "belief" of what the fair market price is.
    *   **How it updates:** It is an Exponential Moving Average (EMA) of recent trades.
    *   **Why it matters:** The pool concentrates its liquidity around this price. If the market price moves away from the Oracle Price, the pool will automatically re-center itself over time (re-pegging), incurring a small loss to liquidity providers to ensure they are always selling the expensive asset and buying the cheap one.

    ### 4. Fees
    *   **Mid Fee:** The minimum fee charged when the pool is balanced.
    *   **Out Fee:** The maximum fee charged when the pool is imbalanced or under stress.
    *   **Dynamic Fees:** The actual fee fluctuates between these two values based on how far the current state is from the ideal balance.

    ## How to Use the Simulator

    ### Step 1: Initialize the Pool
    1.  Go to the **Sidebar**.
    2.  Set the **Initial Price** (e.g., 1350 KRW = 1 USD).
    3.  Set the **Total Liquidity** (e.g., $1,000,000 USD worth of tokens).
    4.  Click **Initialize / Reset Pool**.

    ### Step 2: Check Status
    Look at the **Pool Status** section to see:
    *   **Pool KRW Liquidity:** How much Won is in the reserves.
    *   **Pool USD Liquidity:** How much Dollar is in the reserves.
    *   **Oracle Price:** The current internal exchange rate.

    ### Step 3: Perform Swaps
    *   **Buy KRW:** Enter the amount of USD you want to sell. Click "Sell USD".
    *   **Buy USD:** Enter the amount of KRW you want to sell. Click "Sell KRW".
    
    Observe how the **Oracle Price** shifts slightly after large trades, and how the **Liquidity** balances change. If you trade enough to push the ratio far from the center, you will see the exchange rate worsen (slippage).

    ## Source Code Reference
    This simulation imports the math directly from the official source code:
    *   `twocrypto-ng-main/tests/utils/simulator.py`
    
    It uses the `Trader` class to instantiate a curve and perform `buy` operations.
    """)

elif page == "Simulator":
    st.title("💱 Twocrypto-ng Simulator: USD/KRW")
    st.markdown("""
    This website simulates a decentralized exchange using the **Curve Twocrypto-ng** mathematical model. 
    It simulates a liquidity pool between **KRW** (Korean Won) and **USD** (US Dollar).
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
    else:
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
            
            # Preview Logic
            if sell_usd_amt > 0:
                dx = int(Decimal(sell_usd_amt) * Decimal(10**18))
                preview_dy = get_trade_preview(trader, dx, 1, 0) # 1 (USD) -> 0 (KRW)
                
                if preview_dy:
                    got_krw = Decimal(preview_dy) / Decimal(10**18)
                    effective_rate = got_krw / Decimal(sell_usd_amt)
                    oracle_rate = current_price_krw
                    price_impact = ((effective_rate - oracle_rate) / oracle_rate) * 100
                    
                    st.info(f"""
                    **📊 Trade Preview**
                    * **Expected Output:** ₩{got_krw:,.2f}
                    * **Exchange Rate:** 1 USD = ₩{effective_rate:,.2f}
                    * **Price Impact:** {price_impact:+.4f}%
                    """)
                else:
                    st.warning("⚠️ Trade likely to fail (too large or pool empty)")

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
            
            # Preview Logic
            if sell_krw_amt > 0:
                dx = int(Decimal(sell_krw_amt) * Decimal(10**18))
                preview_dy = get_trade_preview(trader, dx, 0, 1) # 0 (KRW) -> 1 (USD)
                
                if preview_dy:
                    got_usd = Decimal(preview_dy) / Decimal(10**18)
                    effective_rate = Decimal(sell_krw_amt) / got_usd # KRW per USD
                    oracle_rate = current_price_krw
                    price_impact = ((effective_rate - oracle_rate) / oracle_rate) * 100
                    
                    st.info(f"""
                    **📊 Trade Preview**
                    * **Expected Output:** ${got_usd:,.2f}
                    * **Exchange Rate:** 1 USD = ₩{effective_rate:,.2f}
                    * **Price Impact:** {price_impact:+.4f}%
                    """)
                else:
                    st.warning("⚠️ Trade likely to fail (too large or pool empty)")

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
