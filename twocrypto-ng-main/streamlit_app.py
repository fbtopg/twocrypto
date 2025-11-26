import streamlit as st
import sys
import os
import copy
import requests
import time
from datetime import datetime
from decimal import Decimal
import pandas as pd
import numpy as np
import altair as alt

# Add tests/utils directory to path to allow importing simulator
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
        sim_trader = copy.deepcopy(trader)
        dy = sim_trader.buy(dx, i, j)
        return dy
    except Exception:
        return None

def solve_dx_for_dy(trader, target_dy, i, j):
    """
    Approximates required input `dx` to get `target_dy` using binary search.
    target_dy: in integer units (wei).
    i: from_token index.
    j: to_token index.
    Returns dx (int) or None if not found.
    """
    # 1. Estimate price to set bounds
    # Price is p[1] (price of 1 in terms of 0).
    # If i=1(USD), j=0(EUR). p is EUR/USD. dx ~ dy / p.
    # If i=0(EUR), j=1(USD). p is EUR/USD. dx ~ dy * p.
    
    price_oracle = Decimal(trader.price_oracle[1]) / Decimal(10**18) # coin1 price in coin0
    
    target_dy_dec = Decimal(target_dy)
    
    if i == 1 and j == 0: # USD -> EUR
        # Price is ~0.95. dy ~ dx * 0.95 => dx ~ dy / 0.95
        est_dx = target_dy_dec / price_oracle
    elif i == 0 and j == 1: # EUR -> USD
        # Price is ~0.95. dy ~ dx / 0.95 => dx ~ dy * 0.95
        est_dx = target_dy_dec * price_oracle
    else:
        return None

    # Set generous bounds for binary search
    low = 0
    high = int(est_dx * Decimal(2.0)) # Safe upper bound
    
    # Binary search
    best_dx = None
    min_diff = float('inf')
    
    # Iteration limit
    for _ in range(60):
        mid = (low + high) // 2
        sim = copy.deepcopy(trader)
        dy_mid = sim.buy(mid, i, j)
        
        if dy_mid is False:
            high = mid - 1
            continue
            
        diff = dy_mid - target_dy
        
        if abs(diff) < min_diff:
            min_diff = abs(diff)
            best_dx = mid
            
        if abs(diff) < 100: # Tolerance (wei)
            return mid
            
        if dy_mid < target_dy:
            low = mid + 1
        else:
            high = mid - 1
            
        if low > high:
            break
            
    return best_dx

# --- FX API Fetcher ---
@st.cache_data(ttl=600)
def fetch_eur_price():
    """
    Fetches the EUR rate (USD base) from ForexRateAPI.
    Refreshes every 10 minutes (600 seconds).
    Returns (rate, timestamp) tuple.
    """
    url = "https://api.forexrateapi.com/v1/latest"
    params = {
        "api_key": "34ea334656de7713cd5384a5a7718ceb",
        "base": "USD",
        "currencies": "EUR"
    }
    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        current_ts = time.time()
        if data.get("success"):
            # Rate is EUR per 1 USD. e.g. 0.95
            return data["rates"]["EUR"], current_ts
        else:
            return None, current_ts
    except Exception as e:
        return None, time.time()

st.set_page_config(page_title="Stablecoin DEX Simulator", layout="wide")

# Custom CSS for the card look and input styling
st.markdown("""
<style>
    /* Card Container */
    .swap-container {
        background-color: white;
        padding: 20px;
        border-radius: 16px;
        border: 1px solid #e0e0e0;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        max-width: 480px;
        margin: 0 auto;
    }
    
    /* Remove default number input arrows/spinners if possible (browser dependent) */
    input[type=number]::-webkit-inner-spin-button, 
    input[type=number]::-webkit-outer-spin-button { 
        -webkit-appearance: none; 
        margin: 0; 
    }
    
    /* Headers in the card */
    .swap-header {
        font-size: 14px;
        color: #666;
        margin-bottom: 5px;
        font-weight: 500;
    }
</style>
""", unsafe_allow_html=True)

# Navigation
page = st.sidebar.radio("Navigation", ["Simulator", "Documentation"])

if page == "Documentation":
    st.title("📚 Simulator Documentation")
    st.markdown("""
    ## Introduction
    This simulator is built upon the **Curve Twocrypto-ng** mathematical model. It demonstrates how a specialized decentralized exchange (DEX) functions for pairs of assets with variable prices, such as **USD** and **EUR**.

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

    ### 3. The Oracle Price & Recentering
    *   **What it is:** The pool's internal "belief" of what the fair market price is.
    *   **How it updates:** It is an Exponential Moving Average (EMA) of recent trades.
    *   **Why it matters:** The pool concentrates its liquidity around this price. If the market price moves away from the Oracle Price, the pool will automatically re-center itself over time (re-pegging), incurring a small loss to liquidity providers to ensure they are always selling the expensive asset and buying the cheap one.
    *   **In Simulator:** You can observe this process in the **Repagging Simulation** section.

    ### 4. Fees
    *   **Mid Fee:** The minimum fee charged when the pool is balanced.
    *   **Out Fee:** The maximum fee charged when the pool is imbalanced or under stress.
    *   **Dynamic Fees:** The actual fee fluctuates between these two values based on how far the current state is from the ideal balance.

    ## How to Use the Simulator

    ### Step 1: Initialize the Pool
    1.  Go to the **Sidebar**.
    2.  **Initial Price:** This is automatically fetched from a live FX API (ForexRateAPI) for the current **EUR/USD** rate. It refreshes every 10 minutes.
    3.  Set the **Total Liquidity** (e.g., $1,000,000 USD worth of tokens).
    4.  Click **Initialize / Reset Pool**.

    ### Step 2: Check Status
    Look at the **Pool Status** section to see:
    *   **Pool EUR Liquidity:** How much Euro is in the reserves.
    *   **Pool USD Liquidity:** How much Dollar is in the reserves.
    *   **Oracle Price:** The current internal exchange rate.

    ### Step 3: Perform Swaps
    The simulator features a unified swap card interface:
    1.  **Select Direction:** Use the ⬇ arrow button to toggle between selling USD or selling EUR.
    2.  **Enter Amount:** Type in the "From" field OR the "To" field.
    3.  **Bi-directional Calculation:** If you type in "From", it calculates "To". If you type in "To", it estimates the required "From".
    4.  **Swap:** Click the button to execute the trade.
    
    Observe how the **Oracle Price** shifts slightly after large trades, and how the **Liquidity** balances change. If you trade enough to push the ratio far from the center, you will see the exchange rate worsen (slippage).

    ## Source Code Reference
    This simulation imports the math directly from the official source code:
    *   `twocrypto-ng-main/tests/utils/simulator.py`
    
    It uses the `Trader` class to instantiate a curve and perform `buy` operations.
    """)

elif page == "Simulator":
    st.title("💱 Twocrypto-ng Simulator: USD/EUR")
    st.markdown("Simulate a decentralized exchange liquidity pool between **EUR** (Euro) and **USD** (US Dollar).")

    # Fetch Live Rate (for Sidebar Defaults)
    global_live_rate, global_fetched_ts = fetch_eur_price()

    # --- Live FX Widget Fragment ---
    @st.fragment(run_every=1)
    def show_live_rate_widget():
        # Fetches from cache (hits API only if TTL expired)
        live_rate, fetched_ts = fetch_eur_price()
        
        if live_rate:
            last_updated_str = datetime.fromtimestamp(fetched_ts).strftime('%H:%M:%S')
            now = time.time()
            elapsed = now - fetched_ts
            time_left = max(0, int(600 - elapsed))
            
            st.info(f"""
            **🟢 Live FX Rate Connected**
            
            **Rate:** 1 USD = €{live_rate:.4f} EUR
            **Last Updated:** {last_updated_str}
            **Next Update in:** {time_left} seconds
            """)
        else:
            st.warning("🔴 Live FX Rate Unavailable. Using fallback default (0.95).")

    show_live_rate_widget()

    # --- Sidebar: Configuration ---
    st.sidebar.header("1. Pool Configuration")

    # Defaults based on 'forex' preset in pool_presets.csv
    default_A = 20000000
    default_gamma = 1000000000000000 # 10^15 (0.001)
    default_mid_fee = 0.0005 # 0.05%
    default_out_fee = 0.0045 # 0.45%

    # Initial defaults
    default_peg = global_live_rate if global_live_rate else 0.95
    default_liquidity = 1000000 # 1 Million USD total

    # Inputs
    with st.sidebar.expander("Advanced Parameters", expanded=False):
        A = st.number_input("Amplification (A)", value=default_A)
        gamma = st.number_input("Gamma (int)", value=default_gamma, help="Gamma parameter in 10^18 scale (e.g. 10^15 = 0.001)")
        mid_fee = st.number_input("Mid Fee", value=default_mid_fee, format="%.6f")
        out_fee = st.number_input("Out Fee", value=default_out_fee, format="%.6f")

    st.sidebar.subheader("Market Parameters")
    # We use 1 USD = X EUR.
    price_peg = st.sidebar.number_input("Initial Price (EUR per USD)", value=default_peg, format="%.4f")
    liquidity_usd = st.sidebar.number_input("Total Liquidity ($ Value)", value=default_liquidity)

    if st.sidebar.button("Initialize / Reset Pool", type="primary"):
        D_base = int(liquidity_usd * price_peg * 10**18) # Rough approximation for init
        p0 = [10**18, int(price_peg * 10**18)]
        
        try:
            trader = Trader(
                A=int(A),
                gamma=int(gamma),
                D=D_base,
                p0=p0,
                mid_fee=mid_fee,
                out_fee=out_fee
            )
            
            # Initialize or reset session state
            st.session_state.trader = trader
            st.session_state.log = []
            st.session_state.initialized = True
            st.session_state.swap_from_token = "USD"
            
            # Tracking for Repagging
            st.session_state.sim_time = 0 # Start at time 0
            st.session_state.price_history = [] # List of dicts: {time, oracle_price, spot_price}
            
            # Initial tweak to set ma recorder state
            trader.tweak_price(0)
            
            st.rerun()
        except Exception as e:
            st.error(f"Failed to initialize pool: {e}")

    # --- Main Interface ---

    if 'trader' not in st.session_state:
        st.info("👈 Please configure and initialize the pool in the sidebar to start.")
    else:
        trader = st.session_state.trader

        # Calculate Balances & Price
        # Coin 0 = EUR, Coin 1 = USD
        bal_eur = Decimal(trader.curve.x[0]) / Decimal(10**18)
        bal_usd = Decimal(trader.curve.x[1]) / Decimal(10**18)
        
        # Price of Coin 1 (USD) in terms of Coin 0 (EUR)
        # Oracle Price
        current_oracle_price_eur = Decimal(trader.price_oracle[1]) / Decimal(10**18)
        
        # Spot Price (get_p)
        # get_p returns price of coin 1 in terms of coin 0
        current_spot_price_eur = Decimal(trader.curve.get_p()) / Decimal(10**18)

        # Display Metrics
        st.subheader("Pool Status")
        m1, m2, m3 = st.columns(3)
        m1.metric("Pool EUR Liquidity", f"€{bal_eur:,.2f}")
        m2.metric("Pool USD Liquidity", f"${bal_usd:,.2f}")
        m3.metric("Oracle Price (EUR/USD)", f"€{current_oracle_price_eur:,.4f}")

        st.divider()

        # --- Unified Swap Interface ---
        st.subheader("💱 Swap")

        # Initialize Swap State vars if they don't exist
        if 'swap_from_token' not in st.session_state:
            st.session_state.swap_from_token = "USD"
        if 'val_in' not in st.session_state:
            st.session_state.val_in = 0.0
        if 'val_out' not in st.session_state:
            st.session_state.val_out = 0.0

        def toggle_direction():
            if st.session_state.swap_from_token == "USD":
                st.session_state.swap_from_token = "EUR"
            else:
                st.session_state.swap_from_token = "USD"
            # Reset amounts on toggle to avoid confusion
            st.session_state.val_in = 0.0
            st.session_state.val_out = 0.0

        # Determine Current Direction
        from_token = st.session_state.swap_from_token
        to_token = "EUR" if from_token == "USD" else "USD"
        
        # Callbacks for bi-directional updating
        def update_output():
            # User changed Amount In. Calculate Amount Out.
            new_in = st.session_state.input_widget
            st.session_state.val_in = new_in
            
            if new_in > 0:
                dx = int(Decimal(new_in) * Decimal(10**18))
                dy_int = None
                if from_token == "USD": # USD->EUR
                    dy_int = get_trade_preview(trader, dx, 1, 0)
                else: # EUR->USD
                    dy_int = get_trade_preview(trader, dx, 0, 1)
                
                if dy_int:
                    val = float(Decimal(dy_int) / Decimal(10**18))
                    st.session_state.val_out = val
                    st.session_state.output_widget = val
                else:
                    st.session_state.val_out = 0.0
                    st.session_state.output_widget = 0.0
            else:
                st.session_state.val_out = 0.0
                st.session_state.output_widget = 0.0

        def update_input():
            # User changed Amount Out. Calculate required Amount In.
            new_out = st.session_state.output_widget
            st.session_state.val_out = new_out
            
            if new_out > 0:
                dy_target = int(Decimal(new_out) * Decimal(10**18))
                dx_int = None
                if from_token == "USD": # USD->EUR. target_dy is EUR. i=1, j=0.
                    dx_int = solve_dx_for_dy(trader, dy_target, 1, 0)
                else: # EUR->USD. target_dy is USD. i=0, j=1.
                    dx_int = solve_dx_for_dy(trader, dy_target, 0, 1)
                
                if dx_int:
                    val = float(Decimal(dx_int) / Decimal(10**18))
                    st.session_state.val_in = val
                    st.session_state.input_widget = val
                else:
                    # Could not solve (maybe impossible amount)
                    st.session_state.val_in = 0.0
                    st.session_state.input_widget = 0.0
            else:
                st.session_state.val_in = 0.0
                st.session_state.input_widget = 0.0

        # Centered Card Layout
        col_spacer_left, col_card, col_spacer_right = st.columns([1, 2, 1])
        
        with col_card:
            # Create a container that looks like a card
            with st.container(border=True):
                
                # --- FROM SECTION ---
                st.markdown(f"<div class='swap-header'>From</div>", unsafe_allow_html=True)
                col_input_from, col_token_from = st.columns([3, 1])
                
                with col_input_from:
                    st.number_input(
                        "Amount In", 
                        min_value=0.0, 
                        step=10.0,
                        value=st.session_state.val_in,
                        label_visibility="collapsed",
                        key="input_widget",
                        on_change=update_output
                    )
                
                with col_token_from:
                    st.selectbox("Token", [from_token], disabled=True, label_visibility="collapsed", key="token_in_select")

                # --- SWITCH BUTTON ---
                col_switch_left, col_switch_btn, col_switch_right = st.columns([4, 1, 4])
                with col_switch_btn:
                    st.button("⬇", on_click=toggle_direction, help="Switch Tokens", use_container_width=True)

                # --- TO SECTION ---
                st.markdown(f"<div class='swap-header'>To (Estimated)</div>", unsafe_allow_html=True)
                
                col_input_to, col_token_to = st.columns([3, 1])
                
                with col_input_to:
                    st.number_input(
                        "Amount Out",
                        min_value=0.0,
                        step=10.0,
                        value=st.session_state.val_out,
                        label_visibility="collapsed",
                        key="output_widget",
                        on_change=update_input
                    )
                
                with col_token_to:
                     st.selectbox("Token", [to_token], disabled=True, label_visibility="collapsed", key="token_out_select")

                # --- INFO PREVIEW SECTION (Inside Card) ---
                # Recalculate display stats based on current session state
                amount_in_disp = st.session_state.val_in
                amount_out_disp = st.session_state.val_out
                can_trade = amount_in_disp > 0 and amount_out_disp > 0
                
                if can_trade:
                    # Calc stats for display
                    if from_token == "USD": # In USD, Out EUR
                        effective_rate = amount_out_disp / amount_in_disp # EUR per USD
                    else: # In EUR, Out USD
                        effective_rate = amount_in_disp / amount_out_disp # EUR per USD (normalized)
                    
                    oracle_rate = float(current_price_eur)
                    expected_out_oracle = 0
                    price_impact_pct = 0.0
                    
                    if from_token == "USD":
                        # Sell USD for EUR
                        expected_out_oracle = amount_in_disp * oracle_rate
                        if expected_out_oracle > 0:
                            price_impact_pct = ((amount_out_disp - expected_out_oracle) / expected_out_oracle) * 100
                    else:
                        # Sell EUR for USD
                        if oracle_rate > 0:
                            expected_out_oracle = amount_in_disp / oracle_rate
                            if expected_out_oracle > 0:
                                price_impact_pct = ((amount_out_disp - expected_out_oracle) / expected_out_oracle) * 100

                    st.markdown("---")
                    st.markdown(f"""
                    <div style="display: flex; justify-content: space-between; font-size: 0.9em; color: #555;">
                        <span>Receive (Approx)</span>
                        <span style="font-weight: 500;">{'€' if from_token == 'USD' else '$'}{amount_out_disp:,.2f}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 0.9em; color: #555;">
                        <span>Price</span>
                        <span>1 USD = €{effective_rate:,.4f} EUR</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 0.9em; color: {('#d32f2f' if price_impact_pct < -0.1 else '#388e3c')};">
                        <span>Price Impact</span>
                        <span>{price_impact_pct:+.4f}%</span>
                    </div>
                    """, unsafe_allow_html=True)

                st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)

                # --- SWAP ACTION BUTTON ---
                if st.button("Swap", type="primary", use_container_width=True, disabled=not can_trade):
                    dx = int(Decimal(amount_in_disp) * Decimal(10**18))
                    result = None
                    
                    # Explicitly calling tweak_price before swap to simulate time passing?
                    # In reality, swap happens at time t.
                    # We can increment global sim time by 1 block (12s) per swap
                    if 'sim_time' not in st.session_state:
                        st.session_state.sim_time = 0
                    
                    st.session_state.sim_time += 12
                    trader.tweak_price(st.session_state.sim_time)
                    
                    if from_token == "USD":
                        result = trader.buy(dx, 1, 0) # Sell USD, Buy EUR
                        msg = f"SELL ${amount_in_disp:,.2f} USD -> BUY €{amount_out_disp:,.2f} EUR"
                    else:
                        result = trader.buy(dx, 0, 1) # Sell EUR, Buy USD
                        msg = f"SELL €{amount_in_disp:,.2f} EUR -> BUY ${amount_out_disp:,.2f} USD"
                    
                    # Post-swap tweak to update oracle with new price
                    trader.tweak_price(st.session_state.sim_time)
                    
                    if result:
                        st.session_state.log.append(msg)
                        
                        # Record data for graph
                        if 'price_history' not in st.session_state:
                            st.session_state.price_history = []
                            
                        st.session_state.price_history.append({
                            "time": st.session_state.sim_time,
                            "Oracle Price": float(Decimal(trader.price_oracle[1]) / Decimal(10**18)),
                            "Spot Price": float(Decimal(trader.curve.get_p()) / Decimal(10**18))
                        })
                        
                        st.success("Swap Successful!")
                        # Reset inputs
                        st.session_state.val_in = 0.0
                        st.session_state.val_out = 0.0
                        st.rerun()
                    else:
                        st.error("Swap Failed (Execution error)")

        st.markdown("<div style='margin-top: 30px;'></div>", unsafe_allow_html=True)
        st.subheader("💧 Liquidity Density")
        
        # Generate Data for Graph
        # Center around Oracle Price
        p_oracle = float(current_price_eur) 
        p_spot = float(Decimal(trader.curve.get_p()) / Decimal(10**18))
        
        # Gamma defines width. 
        # For visualization, we'll use a heuristic width based on gamma or fixed percentage
        
        x = np.linspace(p_oracle * 0.95, p_oracle * 1.05, 100)
        
        # Approx distribution (Gaussian-ish) centered at Oracle Price
        # Width factor: 1.5% relative width for viz
        sigma = p_oracle * 0.015 
        
        y = np.exp(-0.5 * ((x - p_oracle) / sigma) ** 2)
        
        df_chart = pd.DataFrame({'Price': x, 'Liquidity': y})
        
        # Split into Bid (Buy EUR) and Ask (Sell EUR)
        # Relative to current spot price
        df_chart['Side'] = np.where(df_chart['Price'] < p_spot, 'Bid (Buy EUR)', 'Ask (Sell EUR)')
        
        # Altair Chart
        c = alt.Chart(df_chart).mark_area(opacity=0.6).encode(
            x=alt.X('Price', axis=alt.Axis(format='€,.4f'), title='EUR/USD Price'),
            y=alt.Y('Liquidity', axis=None),
            color=alt.Color('Side', scale=alt.Scale(domain=['Bid (Buy EUR)', 'Ask (Sell EUR)'], range=['#6c8eef', '#4caf50'])),
            tooltip=[alt.Tooltip('Price', format='€,.4f'), alt.Tooltip('Liquidity', format='.2f')]
        ).properties(
            height=300
        )
        
        # Add line for Spot Price
        rule = alt.Chart(pd.DataFrame({'Price': [p_spot]})).mark_rule(color='red', strokeDash=[5, 5], strokeWidth=2).encode(
            x='Price'
        )
        
        # Text label for Spot Price
        text = alt.Chart(pd.DataFrame({'Price': [p_spot], 'y': [1.0]})).mark_text(
            align='center', baseline='bottom', color='red', dy=-10, fontSize=12, text=f"Current: €{p_spot:.4f}"
        ).encode(
            x='Price',
            y=alt.value(0)
        )

        st.altair_chart(c + rule + text, use_container_width=True)

        st.divider()
        
        # --- Repagging Simulation ---
        st.subheader("📈 Repagging Simulation")
        st.markdown("""
        **How Recentering Works:**
        If the **Spot Price** (derived from pool balances) deviates from the **Oracle Price** (EMA), the pool gradually adjusts its internal liquidity concentration (Price Scale) towards the Oracle Price.
        
        Use the buttons below to simulate time passing without trading, which allows the Oracle to catch up to the Spot price (or vice versa).
        """)
        
        col_sim_btns, col_sim_chart = st.columns([1, 2])
        
        with col_sim_btns:
            if st.button("⏳ Simulate 10 Minutes"):
                if 'sim_time' not in st.session_state:
                    st.session_state.sim_time = 0
                if 'price_history' not in st.session_state:
                    st.session_state.price_history = []
                    
                # Advance time by 600s
                step = 600
                current_t = st.session_state.sim_time
                target_t = current_t + step
                
                # We can step gradually to record points for the graph
                # Step every 60s
                for t in range(current_t + 60, target_t + 60, 60):
                    trader.tweak_price(t)
                    st.session_state.price_history.append({
                        "time": t,
                        "Oracle Price": float(Decimal(trader.price_oracle[1]) / Decimal(10**18)),
                        "Spot Price": float(Decimal(trader.curve.get_p()) / Decimal(10**18))
                    })
                
                st.session_state.sim_time = target_t
                st.success(f"Simulated {step}s. Oracle updated.")
                st.rerun()

            if st.button("⏳ Simulate 1 Hour"):
                if 'sim_time' not in st.session_state:
                    st.session_state.sim_time = 0
                if 'price_history' not in st.session_state:
                    st.session_state.price_history = []
                    
                # Advance time by 3600s
                step = 3600
                current_t = st.session_state.sim_time
                target_t = current_t + step
                
                # Step every 5 mins
                for t in range(current_t + 300, target_t + 300, 300):
                    trader.tweak_price(t)
                    st.session_state.price_history.append({
                        "time": t,
                        "Oracle Price": float(Decimal(trader.price_oracle[1]) / Decimal(10**18)),
                        "Spot Price": float(Decimal(trader.curve.get_p()) / Decimal(10**18))
                    })
                
                st.session_state.sim_time = target_t
                st.success(f"Simulated {step}s. Oracle updated.")
            st.rerun()

        with col_sim_chart:
            if 'price_history' in st.session_state and st.session_state.price_history:
                df = pd.DataFrame(st.session_state.price_history)
                # Plot simple line chart
                st.line_chart(df, x="time", y=["Oracle Price", "Spot Price"], color=["#FF4B4B", "#1C83E1"])
            else:
                st.info("Perform swaps or simulate time to see the price chart.")

# History
if st.session_state.log:
    st.divider()
    st.subheader("Transaction History")
    for msg in reversed(st.session_state.log):
        st.text(msg)
