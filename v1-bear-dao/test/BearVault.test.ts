import { expect } from "chai";
import { ethers } from "hardhat";
import { loadFixture, time } from "@nomicfoundation/hardhat-network-helpers";
import { SignerWithAddress } from "@nomicfoundation/hardhat-ethers/signers";

describe("BearVault", function () {
  let owner: SignerWithAddress;
  let user: SignerWithAddress;
  let feeRecipient: SignerWithAddress;

  async function deployFixture() {
    [owner, user, feeRecipient] = await ethers.getSigners();

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
      feeRecipient.address
    );
    await vault.waitForDeployment();

    const bearTokenAddr = await vault.bearToken();
    const bearToken = await ethers.getContractAt("BearToken", bearTokenAddr);

    // Mint USDC to user for testing
    await mockUsdc.mint(user.address, 100_000n * 10n ** 6n); // 100k USDC

    return { vault, bearToken, mockPaxg, mockUsdc, mockWeth, mockAdapter };
  }

  describe("Deployment", function () {
    it("should deploy BearToken with correct name and symbol", async function () {
      const { bearToken } = await loadFixture(deployFixture);
      expect(await bearToken.name()).to.equal("BearDAO");
      expect(await bearToken.symbol()).to.equal("BEAR");
    });

    it("should start with zero PAXG held", async function () {
      const { vault } = await loadFixture(deployFixture);
      expect(await vault.totalPaxgHeld()).to.equal(0);
    });

    it("should have 24h default withdrawal timelock", async function () {
      const { vault } = await loadFixture(deployFixture);
      expect(await vault.withdrawalTimelock()).to.equal(24 * 60 * 60);
    });

    it("should revert with zero PAXG address", async function () {
      const BearVault = await ethers.getContractFactory("BearVault");
      await expect(
        BearVault.deploy(
          ethers.ZeroAddress,
          ethers.ZeroAddress,
          ethers.ZeroAddress,
          ethers.ZeroAddress,
          ethers.ZeroAddress
        )
      ).to.be.revertedWith("Zero PAXG");
    });
  });

  describe("USDC Deposit", function () {
    it("should accept USDC deposits and mint BEAR tokens", async function () {
      const { vault, bearToken, mockUsdc } = await loadFixture(deployFixture);
      const depositAmount = 1000n * 10n ** 6n; // 1000 USDC

      // Approve vault
      await mockUsdc.connect(user).approve(await vault.getAddress(), depositAmount);

      // Deposit
      await vault.connect(user).depositUSDC(depositAmount, 0, user.address);

      // Check BEAR minted
      const bearBalance = await bearToken.balanceOf(user.address);
      expect(bearBalance).to.be.gt(0);

      // Check vault holds PAXG
      expect(await vault.totalPaxgHeld()).to.be.gt(0);
    });

    it("should revert on zero deposit", async function () {
      const { vault } = await loadFixture(deployFixture);
      await expect(
        vault.connect(user).depositUSDC(0, 0, user.address)
      ).to.be.revertedWith("Zero deposit");
    });

    it("should revert on zero receiver", async function () {
      const { vault, mockUsdc } = await loadFixture(deployFixture);
      await mockUsdc.connect(user).approve(await vault.getAddress(), 1000);
      await expect(
        vault.connect(user).depositUSDC(1000, 0, ethers.ZeroAddress)
      ).to.be.revertedWith("Zero receiver");
    });

    it("should deduct deposit fee when set", async function () {
      const { vault, bearToken, mockUsdc } = await loadFixture(deployFixture);

      // Set 1% deposit fee
      await vault.setFees(100, 0, 0);

      const depositAmount = 10_000n * 10n ** 6n;
      await mockUsdc.connect(user).approve(await vault.getAddress(), depositAmount);
      await vault.connect(user).depositUSDC(depositAmount, 0, user.address);

      // Fee recipient should have received 1% of USDC
      const feeBalance = await mockUsdc.balanceOf(feeRecipient.address);
      expect(feeBalance).to.equal(100n * 10n ** 6n); // 100 USDC = 1% of 10k
    });
  });

  describe("ETH Deposit", function () {
    it("should accept ETH deposits and mint BEAR tokens", async function () {
      const { vault, bearToken } = await loadFixture(deployFixture);
      const depositAmount = ethers.parseEther("1");

      await vault.connect(user).depositETH(0, user.address, { value: depositAmount });

      const bearBalance = await bearToken.balanceOf(user.address);
      expect(bearBalance).to.be.gt(0);
      expect(await vault.totalPaxgHeld()).to.be.gt(0);
    });

    it("should revert on zero ETH deposit", async function () {
      const { vault } = await loadFixture(deployFixture);
      await expect(
        vault.connect(user).depositETH(0, user.address, { value: 0 })
      ).to.be.revertedWith("Zero deposit");
    });
  });

  describe("Withdrawal Flow", function () {
    async function depositFixture() {
      const fixture = await deployFixture();
      const { vault, mockUsdc } = fixture;

      const depositAmount = 10_000n * 10n ** 6n;
      await mockUsdc.connect(user).approve(await vault.getAddress(), depositAmount);
      await vault.connect(user).depositUSDC(depositAmount, 0, user.address);

      return fixture;
    }

    it("should allow requesting a withdrawal for PAXG", async function () {
      const { vault, bearToken, mockPaxg } = await loadFixture(depositFixture);
      const bearBalance = await bearToken.balanceOf(user.address);

      await vault
        .connect(user)
        .requestWithdrawal(bearBalance, await mockPaxg.getAddress(), 0);

      const req = await vault.getWithdrawalRequest(1);
      expect(req.user).to.equal(user.address);
      expect(req.bearAmount).to.equal(bearBalance);
      expect(req.completed).to.be.false;
      expect(req.cancelled).to.be.false;

      // BEAR tokens should be burned
      expect(await bearToken.balanceOf(user.address)).to.equal(0);
    });

    it("should reject completing before timelock expires", async function () {
      const { vault, bearToken, mockPaxg } = await loadFixture(depositFixture);
      const bearBalance = await bearToken.balanceOf(user.address);

      await vault
        .connect(user)
        .requestWithdrawal(bearBalance, await mockPaxg.getAddress(), 0);

      await expect(
        vault.connect(user).completeWithdrawal(1)
      ).to.be.revertedWith("Timelock active");
    });

    it("should allow completing after timelock (PAXG out)", async function () {
      const { vault, bearToken, mockPaxg } = await loadFixture(depositFixture);
      const bearBalance = await bearToken.balanceOf(user.address);

      await vault
        .connect(user)
        .requestWithdrawal(bearBalance, await mockPaxg.getAddress(), 0);

      // Fast forward past timelock
      await time.increase(24 * 60 * 60 + 1);

      const paxgBefore = await mockPaxg.balanceOf(user.address);
      await vault.connect(user).completeWithdrawal(1);
      const paxgAfter = await mockPaxg.balanceOf(user.address);

      expect(paxgAfter).to.be.gt(paxgBefore);
    });

    it("should allow cancelling a withdrawal and re-mint BEAR", async function () {
      const { vault, bearToken, mockPaxg } = await loadFixture(depositFixture);
      const bearBalance = await bearToken.balanceOf(user.address);

      await vault
        .connect(user)
        .requestWithdrawal(bearBalance, await mockPaxg.getAddress(), 0);

      expect(await bearToken.balanceOf(user.address)).to.equal(0);

      await vault.connect(user).cancelWithdrawal(1);

      // Original BEAR amount should be re-minted
      expect(await bearToken.balanceOf(user.address)).to.equal(bearBalance);
    });

    it("should reject double completion", async function () {
      const { vault, bearToken, mockPaxg } = await loadFixture(depositFixture);
      const bearBalance = await bearToken.balanceOf(user.address);

      await vault
        .connect(user)
        .requestWithdrawal(bearBalance, await mockPaxg.getAddress(), 0);

      await time.increase(24 * 60 * 60 + 1);
      await vault.connect(user).completeWithdrawal(1);

      await expect(
        vault.connect(user).completeWithdrawal(1)
      ).to.be.revertedWith("Already processed");
    });

    it("should reject withdrawal request from wrong user", async function () {
      const { vault, bearToken, mockPaxg } = await loadFixture(depositFixture);
      const bearBalance = await bearToken.balanceOf(user.address);

      await vault
        .connect(user)
        .requestWithdrawal(bearBalance, await mockPaxg.getAddress(), 0);

      await time.increase(24 * 60 * 60 + 1);
      await expect(
        vault.connect(owner).completeWithdrawal(1)
      ).to.be.revertedWith("Not your request");
    });
  });

  describe("Share Math", function () {
    it("pricePerShare should be positive initially", async function () {
      const { vault } = await loadFixture(deployFixture);
      const pps = await vault.pricePerShare();
      expect(pps).to.be.gt(0);
    });

    it("convertToAssets and convertToShares should be inverse", async function () {
      const { vault, mockUsdc } = await loadFixture(deployFixture);

      // Deposit first
      const depositAmount = 10_000n * 10n ** 6n;
      await mockUsdc.connect(user).approve(await vault.getAddress(), depositAmount);
      await vault.connect(user).depositUSDC(depositAmount, 0, user.address);

      const shares = ethers.parseEther("1");
      const assets = await vault.convertToAssets(shares);
      const sharesBack = await vault.convertToShares(assets);

      // Allow rounding from virtual shares/assets (up to 0.1% difference)
      const tolerance = shares / 1000n;
      expect(sharesBack).to.be.closeTo(shares, tolerance);
    });

    it("multiple deposits should not dilute existing holders unfairly", async function () {
      const { vault, bearToken, mockUsdc } = await loadFixture(deployFixture);
      const [, , , user2] = await ethers.getSigners();
      await mockUsdc.mint(user2.address, 100_000n * 10n ** 6n);

      // First deposit: user deposits 10k USDC
      const deposit1 = 10_000n * 10n ** 6n;
      await mockUsdc.connect(user).approve(await vault.getAddress(), deposit1);
      await vault.connect(user).depositUSDC(deposit1, 0, user.address);
      const shares1 = await bearToken.balanceOf(user.address);

      // Second deposit: user2 deposits 10k USDC
      await mockUsdc.connect(user2).approve(await vault.getAddress(), deposit1);
      await vault.connect(user2).depositUSDC(deposit1, 0, user2.address);
      const shares2 = await bearToken.balanceOf(user2.address);

      // Shares should be approximately equal (same deposit amount, same price)
      const diff = shares1 > shares2 ? shares1 - shares2 : shares2 - shares1;
      const tolerance = shares1 / 100n; // 1% tolerance for rounding
      expect(diff).to.be.lte(tolerance);
    });
  });

  describe("Admin Functions", function () {
    it("should allow admin to set fees", async function () {
      const { vault } = await loadFixture(deployFixture);
      await vault.setFees(50, 50, 200);
      expect(await vault.depositFeeBps()).to.equal(50);
      expect(await vault.withdrawalFeeBps()).to.equal(50);
      expect(await vault.managementFeeBps()).to.equal(200);
    });

    it("should reject fees above 5%", async function () {
      const { vault } = await loadFixture(deployFixture);
      await expect(vault.setFees(501, 0, 0)).to.be.revertedWith("Fee too high");
    });

    it("should allow admin to set withdrawal timelock", async function () {
      const { vault } = await loadFixture(deployFixture);
      await vault.setWithdrawalTimelock(3600);
      expect(await vault.withdrawalTimelock()).to.equal(3600);
    });

    it("should reject timelock above 7 days", async function () {
      const { vault } = await loadFixture(deployFixture);
      await expect(
        vault.setWithdrawalTimelock(8 * 24 * 60 * 60)
      ).to.be.revertedWith("Timelock too long");
    });

    it("should allow admin to update swap adapter", async function () {
      const { vault } = await loadFixture(deployFixture);
      const [, , , , newAdapter] = await ethers.getSigners();
      await vault.setSwapAdapter(newAdapter.address);
    });

    it("should reject non-admin from setting fees", async function () {
      const { vault } = await loadFixture(deployFixture);
      await expect(vault.connect(user).setFees(50, 50, 50)).to.be.reverted;
    });

    it("should allow pausing and unpausing", async function () {
      const { vault } = await loadFixture(deployFixture);
      await vault.pause();
      expect(await vault.paused()).to.be.true;

      await vault.unpause();
      expect(await vault.paused()).to.be.false;
    });

    it("should reject deposits when paused", async function () {
      const { vault, mockUsdc } = await loadFixture(deployFixture);
      await vault.pause();

      await mockUsdc.connect(user).approve(await vault.getAddress(), 1000);
      await expect(
        vault.connect(user).depositUSDC(1000, 0, user.address)
      ).to.be.reverted;
    });
  });

  describe("Emergency Withdraw", function () {
    async function depositFixture() {
      const fixture = await deployFixture();
      const { vault, mockUsdc } = fixture;

      const depositAmount = 10_000n * 10n ** 6n;
      await mockUsdc.connect(user).approve(await vault.getAddress(), depositAmount);
      await vault.connect(user).depositUSDC(depositAmount, 0, user.address);

      return fixture;
    }

    it("should only work when paused", async function () {
      const { vault, bearToken } = await loadFixture(depositFixture);
      const bearBalance = await bearToken.balanceOf(user.address);

      await expect(
        vault.connect(user).emergencyWithdraw(bearBalance)
      ).to.be.revertedWith("Not paused");
    });

    it("should allow PAXG withdrawal when paused", async function () {
      const { vault, bearToken, mockPaxg } = await loadFixture(depositFixture);
      const bearBalance = await bearToken.balanceOf(user.address);

      await vault.pause();

      const paxgBefore = await mockPaxg.balanceOf(user.address);
      await vault.connect(user).emergencyWithdraw(bearBalance);
      const paxgAfter = await mockPaxg.balanceOf(user.address);

      expect(paxgAfter).to.be.gt(paxgBefore);
      expect(await bearToken.balanceOf(user.address)).to.equal(0);
    });
  });

  describe("Management Fee Accrual", function () {
    it("should dilute shares over time when management fee is set", async function () {
      const { vault, bearToken, mockUsdc } = await loadFixture(deployFixture);

      // Set 2% management fee
      await vault.setFees(0, 0, 200);

      // Deposit
      const depositAmount = 10_000n * 10n ** 6n;
      await mockUsdc.connect(user).approve(await vault.getAddress(), depositAmount);
      await vault.connect(user).depositUSDC(depositAmount, 0, user.address);

      const sharesBefore = await bearToken.totalSupply();

      // Fast forward 1 year
      await time.increase(365.25 * 24 * 60 * 60);

      // Trigger fee accrual with another small deposit
      await mockUsdc.mint(owner.address, 10n * 10n ** 6n);
      await mockUsdc.connect(owner).approve(await vault.getAddress(), 10n * 10n ** 6n);
      await vault.connect(owner).depositUSDC(10n * 10n ** 6n, 0, owner.address);

      const sharesAfter = await bearToken.totalSupply();

      // Total supply should have increased due to fee shares minted
      expect(sharesAfter).to.be.gt(sharesBefore);

      // Fee recipient should have BEAR tokens
      const feeShares = await bearToken.balanceOf(feeRecipient.address);
      expect(feeShares).to.be.gt(0);
    });
  });
});
