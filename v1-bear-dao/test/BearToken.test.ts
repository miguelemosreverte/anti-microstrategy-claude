import { expect } from "chai";
import { ethers } from "hardhat";
import { BearToken } from "../typechain-types";
import { SignerWithAddress } from "@nomicfoundation/hardhat-ethers/signers";

describe("BearToken", function () {
  let bearToken: BearToken;
  let owner: SignerWithAddress;
  let vault: SignerWithAddress;
  let user: SignerWithAddress;

  const MINTER_ROLE = ethers.keccak256(ethers.toUtf8Bytes("MINTER_ROLE"));

  beforeEach(async function () {
    [owner, vault, user] = await ethers.getSigners();

    const BearTokenFactory = await ethers.getContractFactory("BearToken");
    bearToken = await BearTokenFactory.deploy(vault.address);
    await bearToken.waitForDeployment();
  });

  describe("Deployment", function () {
    it("should set name and symbol correctly", async function () {
      expect(await bearToken.name()).to.equal("BearDAO");
      expect(await bearToken.symbol()).to.equal("BEAR");
    });

    it("should grant MINTER_ROLE to vault", async function () {
      expect(await bearToken.hasRole(MINTER_ROLE, vault.address)).to.be.true;
    });

    it("should grant DEFAULT_ADMIN_ROLE to deployer", async function () {
      const DEFAULT_ADMIN_ROLE = await bearToken.DEFAULT_ADMIN_ROLE();
      expect(await bearToken.hasRole(DEFAULT_ADMIN_ROLE, owner.address)).to.be
        .true;
    });

    it("should revert on zero vault address", async function () {
      const BearTokenFactory = await ethers.getContractFactory("BearToken");
      await expect(
        BearTokenFactory.deploy(ethers.ZeroAddress)
      ).to.be.revertedWith("Zero vault address");
    });
  });

  describe("Minting", function () {
    it("should allow vault to mint", async function () {
      await bearToken.connect(vault).mint(user.address, ethers.parseEther("100"));
      expect(await bearToken.balanceOf(user.address)).to.equal(
        ethers.parseEther("100")
      );
    });

    it("should prevent non-vault from minting", async function () {
      await expect(
        bearToken.connect(user).mint(user.address, ethers.parseEther("100"))
      ).to.be.reverted;
    });
  });

  describe("Burning", function () {
    beforeEach(async function () {
      await bearToken
        .connect(vault)
        .mint(user.address, ethers.parseEther("100"));
    });

    it("should allow vault to burn", async function () {
      await bearToken
        .connect(vault)
        .burn(user.address, ethers.parseEther("50"));
      expect(await bearToken.balanceOf(user.address)).to.equal(
        ethers.parseEther("50")
      );
    });

    it("should prevent non-vault from burning", async function () {
      await expect(
        bearToken.connect(user).burn(user.address, ethers.parseEther("50"))
      ).to.be.reverted;
    });
  });
});
