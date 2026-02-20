import { HardhatUserConfig } from "hardhat/config";
import "@nomicfoundation/hardhat-toolbox";
import * as dotenv from "dotenv";

dotenv.config();

const MAINNET_RPC = process.env.MAINNET_RPC_URL || "";

const config: HardhatUserConfig = {
  solidity: {
    version: "0.8.20",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200,
      },
    },
  },
  networks: {
    hardhat: {
      // Forking is enabled only when MAINNET_RPC_URL is set
      ...(MAINNET_RPC
        ? {
            forking: {
              url: MAINNET_RPC,
            },
          }
        : {}),
    },
    mainnet: {
      url: MAINNET_RPC,
      accounts: process.env.DEPLOYER_PRIVATE_KEY
        ? [process.env.DEPLOYER_PRIVATE_KEY]
        : [],
    },
  },
  etherscan: {
    apiKey: process.env.ETHERSCAN_API_KEY || "",
  },
};

export default config;
