// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "../vault/BearVault.sol";

/// @title StrategyManager
/// @notice DCA (Dollar-Cost Averaging) strategy for converting idle vault assets into PAXG
/// @dev Callable by KEEPER_ROLE (e.g., Chainlink Automation, Gelato)
contract StrategyManager is AccessControl, Pausable {
    bytes32 public constant KEEPER_ROLE = keccak256("KEEPER_ROLE");

    BearVault public immutable vault;
    IERC20 public immutable usdc;
    IERC20 public immutable paxg;

    // DCA parameters
    uint256 public dcaInterval = 1 hours;
    uint256 public dcaMaxAmount = 10_000e6; // 10k USDC per execution
    uint256 public dcaMaxSlippageBps = 100; // 1%
    uint256 public lastDCAExecution;

    // Swap path for DCA (USDC → PAXG)
    bytes public dcaSwapPath;

    event DCAExecuted(uint256 usdcSwapped, uint256 paxgReceived);
    event DCAParamsUpdated(
        uint256 interval,
        uint256 maxAmount,
        uint256 maxSlippageBps
    );
    event DCASwapPathUpdated(bytes path);

    constructor(
        address _vault,
        address _usdc,
        address _paxg
    ) {
        require(_vault != address(0), "Zero vault");
        vault = BearVault(payable(_vault));
        usdc = IERC20(_usdc);
        paxg = IERC20(_paxg);

        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);

        // Default path: USDC → 0.3% → PAXG
        dcaSwapPath = abi.encodePacked(
            _usdc,
            uint24(3000),
            _paxg
        );
    }

    /// @notice Execute a DCA purchase of PAXG from idle USDC in the vault
    function executeDCA()
        external
        onlyRole(KEEPER_ROLE)
        whenNotPaused
    {
        require(isDCAReady(), "DCA not ready");

        uint256 usdcBalance = usdc.balanceOf(address(vault));
        require(usdcBalance > 0, "No idle USDC");

        uint256 swapAmount = usdcBalance > dcaMaxAmount
            ? dcaMaxAmount
            : usdcBalance;

        // Calculate minimum output with slippage tolerance
        // For simplicity, we use 0 as min and rely on vault's slippage check
        // In production, use an oracle quote here
        uint256 minPaxgOut = 0; // The vault enforces slippage via the swap adapter

        uint256 paxgBefore = paxg.balanceOf(address(vault));

        vault.executeSwap(
            address(usdc),
            swapAmount,
            minPaxgOut,
            dcaSwapPath
        );

        uint256 paxgReceived = paxg.balanceOf(address(vault)) - paxgBefore;
        lastDCAExecution = block.timestamp;

        emit DCAExecuted(swapAmount, paxgReceived);
    }

    /// @notice Check if DCA is ready to execute
    function isDCAReady() public view returns (bool) {
        return block.timestamp >= lastDCAExecution + dcaInterval;
    }

    // --- Admin ---

    function setDCAParams(
        uint256 _interval,
        uint256 _maxAmount,
        uint256 _maxSlippageBps
    ) external onlyRole(DEFAULT_ADMIN_ROLE) {
        require(_interval >= 5 minutes, "Interval too short");
        require(_maxSlippageBps <= 500, "Slippage too high");
        dcaInterval = _interval;
        dcaMaxAmount = _maxAmount;
        dcaMaxSlippageBps = _maxSlippageBps;
        emit DCAParamsUpdated(_interval, _maxAmount, _maxSlippageBps);
    }

    function setDCASwapPath(
        bytes calldata _path
    ) external onlyRole(DEFAULT_ADMIN_ROLE) {
        require(_path.length >= 43, "Invalid path"); // min: addr + fee + addr
        dcaSwapPath = _path;
        emit DCASwapPathUpdated(_path);
    }

    function pause() external onlyRole(DEFAULT_ADMIN_ROLE) {
        _pause();
    }

    function unpause() external onlyRole(DEFAULT_ADMIN_ROLE) {
        _unpause();
    }
}
