# Uniswap Unichain Swap Cautionary Tale

A real-world caution for developers working with large volumes on decentralized exchanges. I lost $40,000 due to a critical mistake in how swap routes were handled via internal Uniswap endpoints. This README is both a technical breakdown and a list of lessons learned.

## Background

In April, Uniswap launched a liquidity rewards program on Unichain. I had an existing codebase for LP strategies and quickly adapted it to participate, taking advantage of the low initial competition.

One part of my system involved performing token swaps. Instead of using official SDKs or building a custom routing system, I reverse-engineered the Uniswap web UI to extract internal endpoints used to generate swap calldata.

## What I Did

- Reverse-engineered Uniswap’s frontend to observe swap behavior  
- Identified and used internal APIs that return calldata for swap execution  
- Integrated those endpoints into a multithreaded bot, which ran for 7 days without issues

## Internal Endpoints Used

My implementation relied on two undocumented endpoints exposed by Uniswap's frontend:

- `POST https://trading-api-labs.interface.gateway.uniswap.org/v1/quote`  
  Used to generate swap quote and optional permit data (via `permitData` field)

- `POST https://trading-api-labs.interface.gateway.uniswap.org/v1/swap`  
  Used to retrieve calldata and transaction target for executing the swap

These endpoints were accessed by mimicking Uniswap frontend headers (e.g. `x-request-source: uniswap-web`, `x-universal-router-version: 2.0`), and the generated calldata was used directly in on-chain transactions.

## What Went Wrong

One morning, one of my wallets was completely drained. After investigation, here’s what I found:

- The API started routing swaps through pools with extremely low liquidity  
- Example: a $20,000 swap was routed through a pool holding just $5,000  
- This caused massive slippage and unrecoverable capital loss

## Unanswered Questions

I analyzed around 100 neighboring blocks to check for liquidity changes — nothing unusual.  
It's still unclear whether this was a random API issue, backend bug, or targeted manipulation.  
Uniswap support responded with generic answers, blaming poor route choice, without acknowledging that the route was API-generated.

## Key Lessons for Developers

1. **Never use reverse-engineered internal APIs for production logic.**  
   You can use ABI extraction to inspect contracts, but never rely on undocumented endpoints to manage funds.

2. **Swap Safety Guidelines:**

   - Use only trusted liquidity pools with verified TVL  
   - Always compare DEX swap prices with centralized exchanges like Binance or Bybit  
   - If the DEX price is significantly worse, wait for arbitrage bots to rebalance the pool  
   - Avoid large one-shot swaps. Break them into smaller chunks (e.g., $20k as 6x $3k)  
   - When using contract ABI, always specify `minAmountOut`  
   - If using SDKs or aggregator APIs, define `slippageTolerance` explicitly  
   - After every swap, compare your wallet's balance change with expected results. If it doesn't match — halt immediately
