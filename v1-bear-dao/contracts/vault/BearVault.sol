// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/math/Math.sol";
import "../interfaces/IBearVault.sol";
import "../interfaces/ISwapAdapter.sol";
import "../token/BearToken.sol";

/// @dev Minimal WETH interface
interface IWETH {
    function deposit() external payable;
    function withdraw(uint256) external;
}

/// @title BearVault
/// @notice Core vault for BearDAO — accepts USDC/ETH, swaps to PAXG, issues BEAR shares
/// @dev Uses virtual shares/assets to prevent inflation attacks.
///      Two-phase withdrawals with timelock for sandwich attack protection.
///      Fee-on-transfer safe via balance-diff pattern.
contract BearVault is IBearVault, ReentrancyGuard, Pausable, AccessControl {
    using SafeERC20 for IERC20;
    using Math for uint256;

    // --- Roles ---
    bytes32 public constant PAUSER_ROLE = keccak256("PAUSER_ROLE");
    bytes32 public constant STRATEGIST_ROLE = keccak256("STRATEGIST_ROLE");

    // --- Virtual shares/assets for inflation attack protection ---
    uint256 private constant VIRTUAL_SHARES = 1e3;
    uint256 private constant VIRTUAL_ASSETS = 1;

    // --- Immutables ---
    BearToken public immutable bearToken;
    IERC20 public immutable paxg;
    IERC20 public immutable usdc;
    IWETH public immutable weth;

    // --- State ---
    ISwapAdapter public swapAdapter;
    uint256 public withdrawalTimelock = 24 hours;
    uint256 public totalPaxgPendingWithdrawal;

    // Fees (in basis points, max 500 = 5%)
    uint256 public depositFeeBps;
    uint256 public withdrawalFeeBps;
    uint256 public managementFeeBps;
    address public feeRecipient;
    uint256 public lastFeeAccrualTimestamp;

    // Withdrawal requests
    uint256 public nextRequestId = 1;
    mapping(uint256 => WithdrawalRequest) public withdrawalRequests;

    // --- Constants ---
    uint256 private constant BPS_DENOMINATOR = 10_000;
    uint256 private constant MAX_FEE_BPS = 500; // 5% max
    uint256 private constant SECONDS_PER_YEAR = 365.25 days;

    constructor(
        address _paxg,
        address _usdc,
        address _weth,
        address _swapAdapter,
        address _feeRecipient
    ) {
        require(_paxg != address(0), "Zero PAXG");
        require(_usdc != address(0), "Zero USDC");
        require(_weth != address(0), "Zero WETH");
        require(_swapAdapter != address(0), "Zero adapter");
        require(_feeRecipient != address(0), "Zero fee recipient");

        paxg = IERC20(_paxg);
        usdc = IERC20(_usdc);
        weth = IWETH(_weth);
        swapAdapter = ISwapAdapter(_swapAdapter);
        feeRecipient = _feeRecipient;
        lastFeeAccrualTimestamp = block.timestamp;

        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(PAUSER_ROLE, msg.sender);

        // Deploy the BEAR token with this vault as minter
        bearToken = new BearToken(address(this));
    }

    // ========================================================================
    // DEPOSITS
    // ========================================================================

    /// @inheritdoc IBearVault
    function depositUSDC(
        uint256 usdcAmount,
        uint256 minPaxgOut,
        address receiver
    ) external nonReentrant whenNotPaused returns (uint256 sharesOut) {
        require(usdcAmount > 0, "Zero deposit");
        require(receiver != address(0), "Zero receiver");

        _accrueManagementFee();

        // Transfer USDC from depositor
        usdc.safeTransferFrom(msg.sender, address(this), usdcAmount);

        // Deduct deposit fee
        uint256 feeAmount = (usdcAmount * depositFeeBps) / BPS_DENOMINATOR;
        uint256 netAmount = usdcAmount - feeAmount;
        if (feeAmount > 0) {
            usdc.safeTransfer(feeRecipient, feeAmount);
        }

        // Swap USDC → PAXG
        uint256 paxgReceived = _swapToPaxg(
            address(usdc),
            netAmount,
            minPaxgOut
        );

        // Calculate and mint shares
        sharesOut = _calculateShares(paxgReceived);
        bearToken.mint(receiver, sharesOut);

        emit Deposited(
            msg.sender,
            receiver,
            address(usdc),
            usdcAmount,
            paxgReceived,
            sharesOut
        );
    }

    /// @inheritdoc IBearVault
    function depositETH(
        uint256 minPaxgOut,
        address receiver
    ) external payable nonReentrant whenNotPaused returns (uint256 sharesOut) {
        require(msg.value > 0, "Zero deposit");
        require(receiver != address(0), "Zero receiver");

        _accrueManagementFee();

        // Wrap ETH → WETH
        weth.deposit{value: msg.value}();
        uint256 wethAmount = msg.value;

        // Deduct deposit fee
        uint256 feeAmount = (wethAmount * depositFeeBps) / BPS_DENOMINATOR;
        uint256 netAmount = wethAmount - feeAmount;
        if (feeAmount > 0) {
            IERC20(address(weth)).safeTransfer(feeRecipient, feeAmount);
        }

        // Swap WETH → PAXG
        uint256 paxgReceived = _swapToPaxg(
            address(weth),
            netAmount,
            minPaxgOut
        );

        // Calculate and mint shares
        sharesOut = _calculateShares(paxgReceived);
        bearToken.mint(receiver, sharesOut);

        emit Deposited(
            msg.sender,
            receiver,
            address(0),
            msg.value,
            paxgReceived,
            sharesOut
        );
    }

    // ========================================================================
    // WITHDRAWALS (Two-phase)
    // ========================================================================

    /// @inheritdoc IBearVault
    function requestWithdrawal(
        uint256 bearAmount,
        address assetOut,
        uint256 minAmountOut
    ) external nonReentrant whenNotPaused returns (uint256 requestId) {
        require(bearAmount > 0, "Zero amount");
        require(
            assetOut == address(paxg) ||
                assetOut == address(usdc) ||
                assetOut == address(0),
            "Invalid asset"
        );

        _accrueManagementFee();

        // Calculate PAXG owed for these shares
        uint256 paxgOwed = convertToAssets(bearAmount);
        require(paxgOwed > 0, "Zero PAXG owed");

        // Burn BEAR tokens immediately
        bearToken.burn(msg.sender, bearAmount);

        // Reserve PAXG for this withdrawal
        totalPaxgPendingWithdrawal += paxgOwed;

        // Create request
        requestId = nextRequestId++;
        withdrawalRequests[requestId] = WithdrawalRequest({
            user: msg.sender,
            paxgAmount: paxgOwed,
            bearAmount: bearAmount,
            assetOut: assetOut,
            minAmountOut: minAmountOut,
            requestTimestamp: block.timestamp,
            completed: false,
            cancelled: false
        });

        emit WithdrawalRequested(
            requestId,
            msg.sender,
            bearAmount,
            paxgOwed,
            assetOut
        );
    }

    /// @inheritdoc IBearVault
    function completeWithdrawal(
        uint256 requestId
    ) external nonReentrant returns (uint256 amountOut) {
        WithdrawalRequest storage req = withdrawalRequests[requestId];

        require(req.user == msg.sender, "Not your request");
        require(!req.completed && !req.cancelled, "Already processed");
        require(
            block.timestamp >= req.requestTimestamp + withdrawalTimelock,
            "Timelock active"
        );

        req.completed = true;
        totalPaxgPendingWithdrawal -= req.paxgAmount;

        // Apply withdrawal fee
        uint256 feeAmount = (req.paxgAmount * withdrawalFeeBps) /
            BPS_DENOMINATOR;
        uint256 netPaxg = req.paxgAmount - feeAmount;
        if (feeAmount > 0) {
            paxg.safeTransfer(feeRecipient, feeAmount);
        }

        if (req.assetOut == address(paxg)) {
            // Direct PAXG withdrawal
            paxg.safeTransfer(msg.sender, netPaxg);
            amountOut = netPaxg;
        } else if (req.assetOut == address(usdc)) {
            // Swap PAXG → USDC
            amountOut = _swapFromPaxg(
                address(usdc),
                netPaxg,
                req.minAmountOut
            );
            usdc.safeTransfer(msg.sender, amountOut);
        } else {
            // Swap PAXG → WETH → ETH
            uint256 wethOut = _swapFromPaxg(
                address(weth),
                netPaxg,
                req.minAmountOut
            );
            weth.withdraw(wethOut);
            (bool success, ) = msg.sender.call{value: wethOut}("");
            require(success, "ETH transfer failed");
            amountOut = wethOut;
        }

        emit WithdrawalCompleted(requestId, msg.sender, amountOut, req.assetOut);
    }

    /// @inheritdoc IBearVault
    function cancelWithdrawal(uint256 requestId) external nonReentrant {
        WithdrawalRequest storage req = withdrawalRequests[requestId];

        require(req.user == msg.sender, "Not your request");
        require(!req.completed && !req.cancelled, "Already processed");

        req.cancelled = true;
        totalPaxgPendingWithdrawal -= req.paxgAmount;

        // Re-mint the original BEAR amount
        bearToken.mint(msg.sender, req.bearAmount);

        emit WithdrawalCancelled(requestId);
    }

    /// @inheritdoc IBearVault
    function emergencyWithdraw(
        uint256 bearAmount
    ) external nonReentrant returns (uint256 paxgOut) {
        require(paused(), "Not paused");
        require(bearAmount > 0, "Zero amount");

        paxgOut = convertToAssets(bearAmount);
        require(paxgOut > 0, "Zero PAXG");

        bearToken.burn(msg.sender, bearAmount);
        paxg.safeTransfer(msg.sender, paxgOut);

        emit EmergencyWithdrawal(msg.sender, bearAmount, paxgOut);
    }

    // ========================================================================
    // STRATEGY
    // ========================================================================

    /// @notice Execute a swap of idle tokens to PAXG (called by StrategyManager)
    function executeSwap(
        address tokenIn,
        uint256 amountIn,
        uint256 minPaxgOut,
        bytes calldata swapPath
    )
        external
        onlyRole(STRATEGIST_ROLE)
        nonReentrant
        returns (uint256 paxgReceived)
    {
        paxgReceived = _swapToPaxgWithPath(tokenIn, amountIn, minPaxgOut, swapPath);
    }

    // ========================================================================
    // VIEW FUNCTIONS
    // ========================================================================

    /// @inheritdoc IBearVault
    function totalPaxgHeld() public view returns (uint256) {
        return paxg.balanceOf(address(this)) - totalPaxgPendingWithdrawal;
    }

    /// @inheritdoc IBearVault
    function convertToAssets(
        uint256 bearAmount
    ) public view returns (uint256) {
        uint256 supply = bearToken.totalSupply() + VIRTUAL_SHARES;
        uint256 assets = totalPaxgHeld() + VIRTUAL_ASSETS;
        return bearAmount.mulDiv(assets, supply, Math.Rounding.Floor);
    }

    /// @inheritdoc IBearVault
    function convertToShares(
        uint256 paxgAmount
    ) public view returns (uint256) {
        uint256 supply = bearToken.totalSupply() + VIRTUAL_SHARES;
        uint256 assets = totalPaxgHeld() + VIRTUAL_ASSETS;
        return paxgAmount.mulDiv(supply, assets, Math.Rounding.Floor);
    }

    /// @inheritdoc IBearVault
    function pricePerShare() public view returns (uint256) {
        uint256 supply = bearToken.totalSupply() + VIRTUAL_SHARES;
        uint256 assets = totalPaxgHeld() + VIRTUAL_ASSETS;
        return (assets * 1e18) / supply;
    }

    function getWithdrawalRequest(
        uint256 requestId
    ) external view returns (WithdrawalRequest memory) {
        return withdrawalRequests[requestId];
    }

    // ========================================================================
    // ADMIN
    // ========================================================================

    function setSwapAdapter(
        address newAdapter
    ) external onlyRole(DEFAULT_ADMIN_ROLE) {
        require(newAdapter != address(0), "Zero adapter");
        swapAdapter = ISwapAdapter(newAdapter);
        emit SwapAdapterUpdated(newAdapter);
    }

    function setWithdrawalTimelock(
        uint256 newTimelock
    ) external onlyRole(DEFAULT_ADMIN_ROLE) {
        require(newTimelock <= 7 days, "Timelock too long");
        withdrawalTimelock = newTimelock;
        emit WithdrawalTimelockUpdated(newTimelock);
    }

    function setFees(
        uint256 _depositFeeBps,
        uint256 _withdrawalFeeBps,
        uint256 _managementFeeBps
    ) external onlyRole(DEFAULT_ADMIN_ROLE) {
        require(
            _depositFeeBps <= MAX_FEE_BPS &&
                _withdrawalFeeBps <= MAX_FEE_BPS &&
                _managementFeeBps <= MAX_FEE_BPS,
            "Fee too high"
        );
        _accrueManagementFee();
        depositFeeBps = _depositFeeBps;
        withdrawalFeeBps = _withdrawalFeeBps;
        managementFeeBps = _managementFeeBps;
        emit FeesUpdated(_depositFeeBps, _withdrawalFeeBps, _managementFeeBps);
    }

    function setFeeRecipient(
        address newRecipient
    ) external onlyRole(DEFAULT_ADMIN_ROLE) {
        require(newRecipient != address(0), "Zero address");
        feeRecipient = newRecipient;
        emit FeeRecipientUpdated(newRecipient);
    }

    function pause() external onlyRole(PAUSER_ROLE) {
        _pause();
    }

    function unpause() external onlyRole(DEFAULT_ADMIN_ROLE) {
        _unpause();
    }

    // ========================================================================
    // INTERNAL
    // ========================================================================

    function _calculateShares(
        uint256 paxgReceived
    ) internal view returns (uint256) {
        uint256 supply = bearToken.totalSupply() + VIRTUAL_SHARES;
        uint256 assets = totalPaxgHeld() + VIRTUAL_ASSETS;
        // Subtract paxgReceived from assets because it's already in the vault balance
        // but hasn't been "accounted" to any shares yet
        return
            paxgReceived.mulDiv(
                supply,
                assets - paxgReceived + VIRTUAL_ASSETS,
                Math.Rounding.Floor
            );
    }

    function _swapToPaxg(
        address tokenIn,
        uint256 amountIn,
        uint256 minPaxgOut
    ) internal returns (uint256 paxgReceived) {
        bytes memory path = abi.encodePacked(
            tokenIn,
            uint24(3000),
            address(paxg)
        );
        paxgReceived = _swapToPaxgWithPath(tokenIn, amountIn, minPaxgOut, path);
    }

    function _swapToPaxgWithPath(
        address tokenIn,
        uint256 amountIn,
        uint256 minPaxgOut,
        bytes memory path
    ) internal returns (uint256 paxgReceived) {
        uint256 paxgBefore = paxg.balanceOf(address(this));

        IERC20(tokenIn).forceApprove(address(swapAdapter), amountIn);

        swapAdapter.swapExactInput(
            tokenIn,
            address(paxg),
            amountIn,
            minPaxgOut,
            path
        );

        // Fee-on-transfer safe: use balance diff
        paxgReceived = paxg.balanceOf(address(this)) - paxgBefore;
        require(paxgReceived >= minPaxgOut, "Slippage exceeded");
    }

    function _swapFromPaxg(
        address tokenOut,
        uint256 paxgAmountIn,
        uint256 minAmountOut
    ) internal returns (uint256 amountOut) {
        uint256 outBefore = IERC20(tokenOut).balanceOf(address(this));

        // Approve adapter
        paxg.forceApprove(address(swapAdapter), paxgAmountIn);

        bytes memory path = abi.encodePacked(
            address(paxg),
            uint24(3000),
            tokenOut
        );

        swapAdapter.swapExactInput(
            address(paxg),
            tokenOut,
            paxgAmountIn,
            minAmountOut,
            path
        );

        amountOut = IERC20(tokenOut).balanceOf(address(this)) - outBefore;
        require(amountOut >= minAmountOut, "Slippage exceeded");
    }

    /// @dev Accrue management fee via share dilution
    function _accrueManagementFee() internal {
        if (managementFeeBps == 0 || feeRecipient == address(0)) {
            lastFeeAccrualTimestamp = block.timestamp;
            return;
        }

        uint256 elapsed = block.timestamp - lastFeeAccrualTimestamp;
        if (elapsed == 0) return;

        uint256 supply = bearToken.totalSupply();
        if (supply == 0) {
            lastFeeAccrualTimestamp = block.timestamp;
            return;
        }

        uint256 feeShares = (supply * managementFeeBps * elapsed) /
            (BPS_DENOMINATOR * SECONDS_PER_YEAR);

        if (feeShares > 0) {
            bearToken.mint(feeRecipient, feeShares);
        }

        lastFeeAccrualTimestamp = block.timestamp;
    }

    /// @dev Accept ETH from WETH withdrawals
    receive() external payable {}
}
