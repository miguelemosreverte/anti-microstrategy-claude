// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IBearVault {
    // --- Structs ---

    struct WithdrawalRequest {
        address user;
        uint256 paxgAmount;
        uint256 bearAmount;
        address assetOut; // PAXG, USDC, or address(0) for ETH
        uint256 minAmountOut;
        uint256 requestTimestamp;
        bool completed;
        bool cancelled;
    }

    // --- Events ---

    event Deposited(
        address indexed depositor,
        address indexed receiver,
        address tokenIn,
        uint256 amountIn,
        uint256 paxgReceived,
        uint256 sharesMinted
    );

    event WithdrawalRequested(
        uint256 indexed requestId,
        address indexed user,
        uint256 bearAmount,
        uint256 paxgAmount,
        address assetOut
    );

    event WithdrawalCompleted(
        uint256 indexed requestId,
        address indexed user,
        uint256 amountOut,
        address assetOut
    );

    event WithdrawalCancelled(uint256 indexed requestId);

    event EmergencyWithdrawal(
        address indexed user,
        uint256 bearAmount,
        uint256 paxgOut
    );

    event FeesUpdated(
        uint256 depositFeeBps,
        uint256 withdrawalFeeBps,
        uint256 managementFeeBps
    );

    event SwapAdapterUpdated(address indexed newAdapter);
    event WithdrawalTimelockUpdated(uint256 newTimelock);
    event FeeRecipientUpdated(address indexed newRecipient);

    // --- Deposit Functions ---

    function depositUSDC(
        uint256 usdcAmount,
        uint256 minPaxgOut,
        address receiver
    ) external returns (uint256 sharesOut);

    function depositETH(
        uint256 minPaxgOut,
        address receiver
    ) external payable returns (uint256 sharesOut);

    // --- Withdrawal Functions ---

    function requestWithdrawal(
        uint256 bearAmount,
        address assetOut,
        uint256 minAmountOut
    ) external returns (uint256 requestId);

    function completeWithdrawal(
        uint256 requestId
    ) external returns (uint256 amountOut);

    function cancelWithdrawal(uint256 requestId) external;

    function emergencyWithdraw(
        uint256 bearAmount
    ) external returns (uint256 paxgOut);

    // --- View Functions ---

    function totalPaxgHeld() external view returns (uint256);
    function convertToAssets(uint256 bearAmount) external view returns (uint256);
    function convertToShares(uint256 paxgAmount) external view returns (uint256);
    function pricePerShare() external view returns (uint256);
}
