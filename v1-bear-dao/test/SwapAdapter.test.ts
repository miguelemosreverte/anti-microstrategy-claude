import { expect } from "chai";
import { ethers } from "hardhat";
import { loadFixture } from "@nomicfoundation/hardhat-network-helpers";
import { SignerWithAddress } from "@nomicfoundation/hardhat-ethers/signers";

describe("UniswapV3SwapAdapter", function () {
  let owner: SignerWithAddress;
  let vaultSigner: SignerWithAddress;

  const VAULT_ROLE = ethers.keccak256(ethers.toUtf8Bytes("VAULT_ROLE"));
  // Use a non-zero address as a placeholder for the router in unit tests
  const FAKE_ROUTER = "0x0000000000000000000000000000000000000001";

  async function deployFixture() {
    [owner, vaultSigner] = await ethers.getSigners();

    const SwapAdapter = await ethers.getContractFactory("UniswapV3SwapAdapter");
    const adapter = await SwapAdapter.deploy(FAKE_ROUTER);
    await adapter.waitForDeployment();

    await adapter.grantRole(VAULT_ROLE, vaultSigner.address);

    return { adapter };
  }

  describe("Deployment", function () {
    it("should set the swap router", async function () {
      const { adapter } = await loadFixture(deployFixture);
      expect(await adapter.swapRouter()).to.equal(FAKE_ROUTER);
    });

    it("should revert on zero router address", async function () {
      const SwapAdapter = await ethers.getContractFactory("UniswapV3SwapAdapter");
      await expect(SwapAdapter.deploy(ethers.ZeroAddress)).to.be.revertedWith(
        "Zero router"
      );
    });

    it("should grant DEFAULT_ADMIN_ROLE to deployer", async function () {
      const { adapter } = await loadFixture(deployFixture);
      const DEFAULT_ADMIN = await adapter.DEFAULT_ADMIN_ROLE();
      expect(await adapter.hasRole(DEFAULT_ADMIN, owner.address)).to.be.true;
    });
  });

  describe("Access Control", function () {
    it("should reject swaps from non-vault addresses", async function () {
      const { adapter } = await loadFixture(deployFixture);
      const fakeToken = "0x0000000000000000000000000000000000000002";
      const path = ethers.solidityPacked(
        ["address", "uint24", "address"],
        [fakeToken, 3000, fakeToken]
      );

      await expect(
        adapter.connect(owner).swapExactInput(fakeToken, fakeToken, 1000, 0, path)
      ).to.be.reverted;
    });

    it("should allow vault role to be granted", async function () {
      const { adapter } = await loadFixture(deployFixture);
      expect(await adapter.hasRole(VAULT_ROLE, vaultSigner.address)).to.be.true;
    });
  });
});
