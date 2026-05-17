import pino from "pino";
import { config } from "./config.js";

// Baileys uses its own logger — silence internal noise, keep our INFO+ logs
export const log = pino({
  level: config.logLevel,
  // Emit level as a lowercase string ("info", "warn", "error", …) so log
  // viewers (Grafana Loki, Datadog, etc.) can classify entries correctly
  // instead of falling back to "Unknown" when they see a numeric level.
  formatters: {
    level(label) {
      return { level: label };
    },
  },
  transport:
    config.nodeEnv !== "production"
      ? { target: "pino-pretty", options: { colorize: true } }
      : undefined,
});

// A silent logger passed to Baileys so its verbose output stays suppressed
export const baileysLogger = pino({ level: "silent" });
