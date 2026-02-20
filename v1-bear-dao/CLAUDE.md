# BearDAO - Inverse MicroStrategy Gold Accumulation DAO

## Project Overview
Smart contract system where users pool funds (USDC or ETH) to accumulate PAXG (tokenized gold) as a bet against Bitcoin. Inspired by MicroStrategy but inverse — instead of accumulating BTC, we accumulate gold.

## Tech Stack
- Solidity ^0.8.20
- Hardhat 2.x + TypeScript
- OpenZeppelin contracts
- Target: Ethereum Mainnet
- DEX: Uniswap V3 for swaps to PAXG

## Contracts
1. **BearToken** (`contracts/token/BearToken.sol`) - ERC-20 share token
2. **BearVault** (`contracts/vault/BearVault.sol`) - Core vault: deposits, withdrawals, share math
3. **UniswapV3SwapAdapter** (`contracts/adapters/UniswapV3SwapAdapter.sol`) - Uniswap V3 swap wrapper
4. **StrategyManager** (`contracts/strategy/StrategyManager.sol`) - DCA rebalancing logic

## Key Addresses (Ethereum Mainnet)
- PAXG: `0x45804880De22913dAFE09f4980848ECE6EcbAf78`
- USDC: `0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48`
- WETH: `0xC02aaA39b223FE8D0A0e5FaC6B7E78ad3AcF3bfF`
- Uniswap V3 SwapRouter02: `0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45`
- Chainlink ETH/USD: `0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419`
- Chainlink XAU/USD: `0x214eD9Da11D2fbe465a6fc601a91E62EbEc1a0D6`

## Architecture
- Users deposit USDC/ETH → Vault swaps to PAXG via SwapAdapter → Mint BEAR tokens
- Withdrawal: 2-phase (request → timelock → complete) for sandwich attack protection
- Share math: virtual shares/assets pattern for inflation attack protection
- Fee-on-transfer safe: balance-diff pattern for PAXG
