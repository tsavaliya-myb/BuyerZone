import "dotenv/config";

function required(key: string): string {
  const val = process.env[key];
  if (!val) throw new Error(`Missing required env var: ${key}`);
  return val;
}

export const config = {
  // Internal HTTP server
  port: parseInt(process.env.WA_INTERNAL_PORT ?? "3001", 10),
  internalSecret: required("WA_INTERNAL_SECRET"),

  // Redis (ARQ queue)
  redisHost: process.env.REDIS_HOST ?? "redis",
  redisPort: parseInt(process.env.REDIS_PORT ?? "6379", 10),
  redisPassword: process.env.REDIS_PASSWORD ?? undefined,
  redisSsl: process.env.REDIS_SSL === "true",
  arqQueue: "arq:queue:process_message",

  // FastAPI internal (for session-update callback)
  fastapiUrl: process.env.FASTAPI_INTERNAL_URL ?? "http://api:8000",

  // App
  nodeEnv: process.env.NODE_ENV ?? "development",
  logLevel: (process.env.WA_LOG_LEVEL ?? "info").toLowerCase(),
} as const;
