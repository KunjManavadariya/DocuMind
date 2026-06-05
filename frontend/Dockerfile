FROM node:22-alpine AS build

WORKDIR /app

ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM node:22-alpine AS runtime

WORKDIR /app

ENV NODE_ENV=production

COPY package*.json ./
RUN npm ci --omit=dev
COPY --from=build /app/vite.config.js ./vite.config.js
COPY --from=build /app/dist ./dist

EXPOSE 4173

CMD ["sh", "-c", "printf 'window.__DOCUMIND_API_BASE_URL__=%s;\\n' \"$(node -e 'process.stdout.write(JSON.stringify(process.env.VITE_API_BASE_URL || \"http://localhost:8000\"))')\" > dist/config.js && npm run preview -- --host 0.0.0.0 --port ${PORT:-4173}"]
