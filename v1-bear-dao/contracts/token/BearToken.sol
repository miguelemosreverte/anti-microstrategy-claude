// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Permit.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";

/// @title BearToken
/// @notice ERC-20 share token for BearDAO vault depositors
/// @dev Minting and burning restricted to the vault contract via MINTER_ROLE
contract BearToken is ERC20, ERC20Permit, AccessControl {
    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");

    constructor(
        address vault
    ) ERC20("BearDAO", "BEAR") ERC20Permit("BearDAO") {
        require(vault != address(0), "Zero vault address");
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(MINTER_ROLE, vault);
    }

    /// @notice Mint shares to a recipient (vault only)
    function mint(address to, uint256 amount) external onlyRole(MINTER_ROLE) {
        _mint(to, amount);
    }

    /// @notice Burn shares from a holder (vault only)
    function burn(address from, uint256 amount) external onlyRole(MINTER_ROLE) {
        _burn(from, amount);
    }
}
