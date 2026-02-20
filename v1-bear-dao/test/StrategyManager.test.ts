import { expect } from "chai";
import { ethers } from "hardhat";
import { loadFixture, time } from "@nomicfoundation/hardhat-network-helpers";
import { SignerWithAddress } from "@nomicfoundation/hardhat-ethers/signers";

describe("StrategyManager", function () {
  let owner: SignerWithAddress;
  let keeper: SignerWithAddress;

  const KEEPER_ROLE = ethers.keccak256(ethers.toUtf8Bytes("KEEPER_ROLE"));
  const STRATEGIST_ROLE = ethers.keccak256(ethers.toUtf8Bytes("STRATEGIST_ROLE"));

  async function deployFixture() {
    [owner, keeper] = await ethers.getSigners();

    // Deploy mock tokens
    const MockERC20 = await ethers.getContractFactory("MockERC20");
    const mockPaxg = await MockERC20.deploy("Pax Gold", "PAXG", 18);
    const mockUsdc = await MockERC20.deploy("USD Coin", "USDC", 6);

    const MockWETH = await ethers.getContractFactory("MockWETH");
    const mockWeth = await MockWETH.deploy();

    // Deploy mock swap adapter
    const MockSwapAdapter = await ethers.getContractFactory("MockSwapAdapter");
    const mockAdapter = await MockSwapAdapter.deploy(
      await mockPaxg.getAddress(),
      await mockUsdc.getAddress(),
      await mockWeth.getAddress()
    );

    // Deploy BearVault
    const BearVault = await ethers.getContractFactory("BearVault");
    const vault = await BearVault.deploy(
      await mockPaxg.getAddress(),
      await mockUsdc.getAddress(),
      await mockWeth.getAddress(),
      await mockAdapter.getAddress(),
      owner.address
    );

    // Deploy StrategyManager
    const SM = await ethers.getContractFactory("StrategyManager");
    const strategy = await SM.deploy(
      await vault.getAddress(),
      await mockUsdc.getAddress(),
      await mockPaxg.getAddress()
    );

    // Grant STRATEGIST_ROLE to strategy manager on vault
    await vault.grantRole(STRATEGIST_ROLE, await strategy.getAddress());

    // Grant KEEPER_ROLE to keeper on strategy manager
    await strategy.grantRole(KEEPER_ROLE, keeper.address);

    return { vault, strategy, mockPaxg, mockUsdc, mockWeth, mockAdapter };
  }

  describe("Deployment", function () {
    it("should set vault reference", async function () {
      const { vault, strategy } = await loadFixture(deployFixture);
      expect(await strategy.vault()).to.equal(await vault.getAddress());
    });

    it("should have default DCA parameters", async function () {
      const { strategy } = await loadFixture(deployFixture);
      expect(await strategy.dcaInterval()).to.equal(3600);
      expect(await strategy.dcaMaxAmount()).to.equal(10_000n * 10n ** 6n);
      expect(await strategy.dcaMaxSlippageBps()).to.equal(100);
    });

    it("should revert with zero vault address", async function () {
      const SM = await ethers.getContractFactory("StrategyManager");
      const MockERC20 = await ethers.getContractFactory("MockERC20");
      const mockUsdc = await MockERC20.deploy("USDC", "USDC", 6);
      const mockPaxg = await MockERC20.deploy("PAXG", "PAXG", 18);

      await expect(
        SM.deploy(ethers.ZeroAddress, await mockUsdc.getAddress(), await mockPaxg.getAddress())
      ).to.be.revertedWith("Zero vault");
    });
  });

  describe("DCA Ready Check", function () {
    it("should be ready initially (no previous execution)", async function () {
      const { strategy } = await loadFixture(deployFixture);
      expect(await strategy.isDCAReady()).to.be.true;
    });
  });

  describe("DCA Execution", function () {
    it("should execute DCA when USDC is available in vault", async function () {
      const { vault, strategy, mockUsdc, mockPaxg } = await loadFixture(deployFixture);

      // Put USDC directly in the vault (simulating deposits that haven't been swapped)
      await mockUsdc.mint(await vault.getAddress(), 5000n * 10n ** 6n);

      const paxgBefore = await mockPaxg.balanceOf(await vault.getAddress());

      await strategy.connect(keeper).executeDCA();

      const paxgAfter = await mockPaxg.balanceOf(await vault.getAddress());
      expect(paxgAfter).to.be.gt(paxgBefore);
    });

    it("should revert if no idle USDC in vault", async function () {
      const { strategy } = await loadFixture(deployFixture);
      await expect(strategy.connect(keeper).executeDCA()).to.be.revertedWith(
        "No idle USDC"
      );
    });

    it("should respect DCA interval", async function () {
      const { vault, strategy, mockUsdc } = await loadFixture(deployFixture);

      await mockUsdc.mint(await vault.getAddress(), 20_000n * 10n ** 6n);

      // First execution
      await strategy.connect(keeper).executeDCA();

      // Second execution should fail (too soon)
      await expect(strategy.connect(keeper).executeDCA()).to.be.revertedWith(
        "DCA not ready"
      );

      // Fast forward past interval
      await time.increase(3601);

      // Now it should work
      await strategy.connect(keeper).executeDCA();
    });
  });

  describe("Admin Functions", function () {
    it("should allow admin to update DCA params", async function () {
      const { strategy } = await loadFixture(deployFixture);
      await strategy.setDCAParams(7200, 50_000n * 10n ** 6n, 200);
      expect(await strategy.dcaInterval()).to.equal(7200);
      expect(await strategy.dcaMaxAmount()).to.equal(50_000n * 10n ** 6n);
      expect(await strategy.dcaMaxSlippageBps()).to.equal(200);
    });

    it("should reject interval below 5 minutes", async function () {
      const { strategy } = await loadFixture(deployFixture);
      await expect(
        strategy.setDCAParams(60, 10_000n * 10n ** 6n, 100)
      ).to.be.revertedWith("Interval too short");
    });

    it("should reject slippage above 5%", async function () {
      const { strategy } = await loadFixture(deployFixture);
      await expect(
        strategy.setDCAParams(3600, 10_000n * 10n ** 6n, 501)
      ).to.be.revertedWith("Slippage too high");
    });

    it("should allow pausing", async function () {
      const { strategy } = await loadFixture(deployFixture);
      await strategy.pause();
      expect(await strategy.paused()).to.be.true;
    });

    it("should reject DCA when paused", async function () {
      const { vault, strategy, mockUsdc } = await loadFixture(deployFixture);
      await mockUsdc.mint(await vault.getAddress(), 5000n * 10n ** 6n);

      await strategy.pause();
      await expect(strategy.connect(keeper).executeDCA()).to.be.reverted;
    });
  });

  describe("Access Control", function () {
    it("should reject DCA execution from non-keeper", async function () {
      const { strategy } = await loadFixture(deployFixture);
      await expect(strategy.connect(owner).executeDCA()).to.be.reverted;
    });

    it("should reject param updates from non-admin", async function () {
      const { strategy } = await loadFixture(deployFixture);
      await expect(
        strategy.connect(keeper).setDCAParams(3600, 10_000n * 10n ** 6n, 100)
      ).to.be.reverted;
    });
  });
});
