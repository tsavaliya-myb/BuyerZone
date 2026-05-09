import pino from "pino";
import { config } from "./config.js";

// Baileys uses its own logger — silence internal noise, keep our INFO+ logs
export const log = pino({
  level: config.logLevel,
  transport:
    config.nodeEnv !== "production"
      ? { target: "pino-pretty", options: { colorize: true } }
      : undefined,
});

// A silent logger passed to Baileys so its verbose output stays suppressed
export const baileysLogger = pino({ level: "silent" });
