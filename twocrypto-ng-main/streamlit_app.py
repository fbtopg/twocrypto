import streamlit as st
import sys
import os
import copy
from decimal import Decimal

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
    st.markdown("Simulate a decentralized exchange liquidity pool between **KRW** (Korean Won) and **USD** (US Dollar).")

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
        D_krw = int(liquidity_usd * price_peg * 10**18)
        p0 = [10**18, int(price_peg * 10**18)]
        
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
            # Reset swap state on re-init
            st.session_state.swap_from_token = "USD"
            st.rerun()
        except Exception as e:
            st.error(f"Failed to initialize pool: {e}")

    # --- Main Interface ---

    if 'trader' not in st.session_state:
        st.info("👈 Please configure and initialize the pool in the sidebar to start.")
    else:
        trader = st.session_state.trader

        # Calculate Balances & Price
        bal_krw = Decimal(trader.curve.x[0]) / Decimal(10**18)
        bal_usd = Decimal(trader.curve.x[1]) / Decimal(10**18)
        current_price_krw = Decimal(trader.price_oracle[1]) / Decimal(10**18)

        # Display Metrics
        st.subheader("Pool Status")
        m1, m2, m3 = st.columns(3)
        m1.metric("Pool KRW Liquidity", f"₩{bal_krw:,.0f}")
        m2.metric("Pool USD Liquidity", f"${bal_usd:,.2f}")
        m3.metric("Oracle Price (KRW/USD)", f"₩{current_price_krw:,.2f}")

        st.divider()

        # --- Unified Swap Interface ---
        st.subheader("💱 Swap")

        # Initialize Swap State
        if 'swap_from_token' not in st.session_state:
            st.session_state.swap_from_token = "USD"

        def toggle_direction():
            if st.session_state.swap_from_token == "USD":
                st.session_state.swap_from_token = "KRW"
            else:
                st.session_state.swap_from_token = "USD"

        # Determine Current Direction
        from_token = st.session_state.swap_from_token
        to_token = "KRW" if from_token == "USD" else "USD"
        
        # Centered Card Layout
        col_spacer_left, col_card, col_spacer_right = st.columns([1, 2, 1])
        
        with col_card:
            # Create a container that looks like a card
            with st.container(border=True):
                
                # --- FROM SECTION ---
                st.markdown(f"<div class='swap-header'>From</div>", unsafe_allow_html=True)
                col_input_from, col_token_from = st.columns([3, 1])
                
                with col_input_from:
                    # Clean input with no label (handled by custom header above)
                    amount_in = st.number_input(
                        "Amount In", 
                        min_value=0.0, 
                        value=0.0, 
                        step=1.0 if from_token == "KRW" else 0.1,
                        label_visibility="collapsed",
                        key="input_amount"
                    )
                
                with col_token_from:
                    # Static token display or selectbox (disabled for now as we only have 2)
                    st.selectbox("Token", [from_token], disabled=True, label_visibility="collapsed", key="token_in_select")

                # --- SWITCH BUTTON ---
                # Centered button to toggle direction
                col_switch_left, col_switch_btn, col_switch_right = st.columns([4, 1, 4])
                with col_switch_btn:
                    st.button("⬇", on_click=toggle_direction, help="Switch Tokens", use_container_width=True)

                # --- TO SECTION ---
                st.markdown(f"<div class='swap-header'>To (Estimated)</div>", unsafe_allow_html=True)
                
                # Calculate Preview
                preview_amount = 0.0
                price_impact_pct = 0.0
                effective_rate = 0.0
                can_trade = False
                
                if amount_in > 0:
                    dx = int(Decimal(amount_in) * Decimal(10**18))
                    # USD=1 (index 1), KRW=0 (index 0)
                    if from_token == "USD":
                        # USD -> KRW: buy(dx, 1, 0)
                        dy_int = get_trade_preview(trader, dx, 1, 0)
                    else:
                        # KRW -> USD: buy(dx, 0, 1)
                        dy_int = get_trade_preview(trader, dx, 0, 1)
                    
                    if dy_int:
                        preview_amount = float(Decimal(dy_int) / Decimal(10**18))
                        can_trade = True
                        
                        # Calc stats
                        if preview_amount > 0:
                            if from_token == "USD": # In USD, Out KRW
                                effective_rate = preview_amount / amount_in # KRW per USD
                            else: # In KRW, Out USD
                                # Effective rate usually normalized to KRW/USD
                                effective_rate = amount_in / preview_amount # KRW per USD
                                
                            oracle_rate = float(current_price_krw)
                            # Price impact relative to oracle
                            # If selling USD for KRW (getting less KRW than oracle says = negative impact)
                            # Expected KRW = amount_in * oracle_rate
                            # Actual KRW = preview_amount
                            
                            expected_out_oracle = 0
                            if from_token == "USD":
                                expected_out_oracle = amount_in * oracle_rate
                                price_impact_pct = ((preview_amount - expected_out_oracle) / expected_out_oracle) * 100
                            else:
                                # Selling KRW for USD. 
                                # Expected USD = amount_in / oracle_rate
                                expected_out_oracle = amount_in / oracle_rate
                                price_impact_pct = ((preview_amount - expected_out_oracle) / expected_out_oracle) * 100

                col_input_to, col_token_to = st.columns([3, 1])
                
                with col_input_to:
                    st.number_input(
                        "Amount Out",
                        value=preview_amount,
                        disabled=True, # Read-only
                        label_visibility="collapsed",
                        key="output_amount"
                    )
                
                with col_token_to:
                     st.selectbox("Token", [to_token], disabled=True, label_visibility="collapsed", key="token_out_select")

                # --- INFO PREVIEW SECTION (Inside Card) ---
                if can_trade and amount_in > 0:
                    st.markdown("---")
                    st.markdown(f"""
                    <div style="display: flex; justify-content: space-between; font-size: 0.9em; color: #555;">
                        <span>Price</span>
                        <span>1 USD = {effective_rate:,.2f} KRW</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 0.9em; color: {('#d32f2f' if price_impact_pct < -0.1 else '#388e3c')};">
                        <span>Price Impact</span>
                        <span>{price_impact_pct:+.4f}%</span>
                    </div>
                    """, unsafe_allow_html=True)

                st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)

                # --- SWAP ACTION BUTTON ---
                if st.button("Swap", type="primary", use_container_width=True, disabled=not can_trade):
                    dx = int(Decimal(amount_in) * Decimal(10**18))
                    result = None
                    
                    if from_token == "USD":
                        result = trader.buy(dx, 1, 0) # Sell USD, Buy KRW
                        msg = f"SELL ${amount_in:,.2f} USD -> BUY ₩{preview_amount:,.0f} KRW"
                    else:
                        result = trader.buy(dx, 0, 1) # Sell KRW, Buy USD
                        msg = f"SELL ₩{amount_in:,.0f} KRW -> BUY ${preview_amount:,.2f} USD"
                    
                    if result:
                        st.session_state.log.append(msg)
                        st.success("Swap Successful!")
                        st.rerun()
                    else:
                        st.error("Swap Failed (Execution error)")

        # History
        if st.session_state.log:
            st.divider()
            st.subheader("Transaction History")
            for msg in reversed(st.session_state.log):
                st.text(msg)
