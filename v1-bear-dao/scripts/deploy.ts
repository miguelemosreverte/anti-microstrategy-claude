import { ethers } from "hardhat";

// Ethereum Mainnet addresses
const PAXG = "0x45804880De22913dAFE09f4980848ECE6EcbAf78";
const USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48";
const WETH = "0xC02aaA39b223FE8D0A0e5FaC6B7E78ad3AcF3bfF";
const UNISWAP_V3_SWAP_ROUTER_02 = "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45";

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("Deploying with account:", deployer.address);
  console.log(
    "Balance:",
    ethers.formatEther(await ethers.provider.getBalance(deployer.address)),
    "ETH"
  );

  // 1. Deploy SwapAdapter
  console.log("\n1. Deploying UniswapV3SwapAdapter...");
  const SwapAdapter = await ethers.getContractFactory("UniswapV3SwapAdapter");
  const swapAdapter = await SwapAdapter.deploy(UNISWAP_V3_SWAP_ROUTER_02);
  await swapAdapter.waitForDeployment();
  const swapAdapterAddr = await swapAdapter.getAddress();
  console.log("   SwapAdapter deployed to:", swapAdapterAddr);

  // 2. Deploy BearVault (this also deploys BearToken internally)
  console.log("\n2. Deploying BearVault (+ BearToken)...");
  const BearVault = await ethers.getContractFactory("BearVault");
  const bearVault = await BearVault.deploy(
    PAXG,
    USDC,
    WETH,
    swapAdapterAddr,
    deployer.address // feeRecipient (set to deployer initially, change via governance later)
  );
  await bearVault.waitForDeployment();
  const bearVaultAddr = await bearVault.getAddress();
  console.log("   BearVault deployed to:", bearVaultAddr);

  const bearTokenAddr = await bearVault.bearToken();
  console.log("   BearToken deployed to:", bearTokenAddr);

  // 3. Deploy StrategyManager
  console.log("\n3. Deploying StrategyManager...");
  const StrategyManager =
    await ethers.getContractFactory("StrategyManager");
  const strategyManager = await StrategyManager.deploy(
    bearVaultAddr,
    USDC,
    PAXG
  );
  await strategyManager.waitForDeployment();
  const strategyManagerAddr = await strategyManager.getAddress();
  console.log("   StrategyManager deployed to:", strategyManagerAddr);

  // 4. Configure roles
  console.log("\n4. Configuring roles...");

  // Grant VAULT_ROLE to BearVault on the SwapAdapter
  const VAULT_ROLE = ethers.keccak256(ethers.toUtf8Bytes("VAULT_ROLE"));
  await swapAdapter.grantRole(VAULT_ROLE, bearVaultAddr);
  console.log("   Granted VAULT_ROLE to BearVault on SwapAdapter");

  // Grant STRATEGIST_ROLE to StrategyManager on BearVault
  const STRATEGIST_ROLE = ethers.keccak256(
    ethers.toUtf8Bytes("STRATEGIST_ROLE")
  );
  await bearVault.grantRole(STRATEGIST_ROLE, strategyManagerAddr);
  console.log("   Granted STRATEGIST_ROLE to StrategyManager on BearVault");

  // Grant KEEPER_ROLE to deployer on StrategyManager (change to automation later)
  const KEEPER_ROLE = ethers.keccak256(ethers.toUtf8Bytes("KEEPER_ROLE"));
  await strategyManager.grantRole(KEEPER_ROLE, deployer.address);
  console.log("   Granted KEEPER_ROLE to deployer on StrategyManager");

  // Summary
  console.log("\n=== Deployment Complete ===");
  console.log("SwapAdapter:     ", swapAdapterAddr);
  console.log("BearVault:       ", bearVaultAddr);
  console.log("BearToken:       ", bearTokenAddr);
  console.log("StrategyManager: ", strategyManagerAddr);
  console.log(
    "\nNext steps:"
  );
  console.log("  1. Verify contracts on Etherscan");
  console.log("  2. Transfer DEFAULT_ADMIN_ROLE to a multisig");
  console.log("  3. Set fees via bearVault.setFees()");
  console.log(
    "  4. Set up Chainlink Automation or Gelato for DCA execution"
  );
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
