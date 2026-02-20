# apps/web/Dockerfile
FROM node:20-alpine

WORKDIR /app

# Install deps first (better cache)
COPY package.json package-lock.json* yarn.lock* pnpm-lock.yaml* ./
RUN \
  if [ -f package-lock.json ]; then npm ci; \
  elif [ -f yarn.lock ]; then yarn install --frozen-lockfile; \
  elif [ -f pnpm-lock.yaml ]; then corepack enable && pnpm i --frozen-lockfile; \
  else npm i; fi

# Copy app
COPY . .

# Build Next.js
RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "start"]
