FROM node:20-alpine

WORKDIR /app

# Install dependencies (including sharp native bindings)
COPY package.json package-lock.json* ./
RUN npm ci --only=production

# Build TypeScript
COPY tsconfig.json ./
COPY src/ ./src/
RUN npm run build

CMD ["node", "dist/index.js"]
