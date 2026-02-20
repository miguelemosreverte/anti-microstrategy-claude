// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";
import "../interfaces/ISwapAdapter.sol";

/// @dev Minimal interface for Uniswap V3 SwapRouter02's exactInput
interface ISwapRouter02 {
    struct ExactInputParams {
        bytes path;
        address recipient;
        uint256 amountIn;
        uint256 amountOutMinimum;
    }

    function exactInput(
        ExactInputParams calldata params
    ) external payable returns (uint256 amountOut);
}

/// @title UniswapV3SwapAdapter
/// @notice Wraps Uniswap V3 SwapRouter02 for BearVault swap operations
/// @dev Only callable by addresses with VAULT_ROLE
contract UniswapV3SwapAdapter is ISwapAdapter, AccessControl {
    using SafeERC20 for IERC20;

    bytes32 public constant VAULT_ROLE = keccak256("VAULT_ROLE");

    ISwapRouter02 public immutable swapRouter;

    event SwapExecuted(
        address indexed tokenIn,
        address indexed tokenOut,
        uint256 amountIn,
        uint256 amountOut
    );

    constructor(address _swapRouter) {
        require(_swapRouter != address(0), "Zero router");
        swapRouter = ISwapRouter02(_swapRouter);
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
    }

    /// @inheritdoc ISwapAdapter
    function swapExactInput(
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 amountOutMinimum,
        bytes calldata path
    ) external override onlyRole(VAULT_ROLE) returns (uint256 amountOut) {
        require(amountIn > 0, "Zero amount");

        // Transfer tokens from caller (vault) to this adapter
        IERC20(tokenIn).safeTransferFrom(msg.sender, address(this), amountIn);

        // Approve router to spend tokens
        IERC20(tokenIn).forceApprove(address(swapRouter), amountIn);

        // Execute swap
        amountOut = swapRouter.exactInput(
            ISwapRouter02.ExactInputParams({
                path: path,
                recipient: msg.sender, // Send output back to vault
                amountIn: amountIn,
                amountOutMinimum: amountOutMinimum
            })
        );

        emit SwapExecuted(tokenIn, tokenOut, amountIn, amountOut);
    }
}
