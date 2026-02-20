// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface ISwapAdapter {
    /// @notice Swap exact amount of tokenIn for PAXG (or any tokenOut)
    /// @param tokenIn Address of input token
    /// @param tokenOut Address of output token
    /// @param amountIn Exact amount of tokenIn to swap
    /// @param amountOutMinimum Minimum acceptable output (slippage protection)
    /// @param path Encoded Uniswap V3 multi-hop path
    /// @return amountOut Actual amount of tokenOut received
    function swapExactInput(
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 amountOutMinimum,
        bytes calldata path
    ) external returns (uint256 amountOut);
}
