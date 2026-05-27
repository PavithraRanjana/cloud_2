# Stage 1: Build React app
FROM node:20-alpine AS builder

# Cognito / Hosted UI env vars — baked into the JS bundle at build time
ARG VITE_COGNITO_DOMAIN
ARG VITE_COGNITO_CLIENT_ID
ENV VITE_COGNITO_DOMAIN=$VITE_COGNITO_DOMAIN
ENV VITE_COGNITO_CLIENT_ID=$VITE_COGNITO_CLIENT_ID

WORKDIR /app

# Copy OpenAPI specs so generate-types can fall back to local files
COPY OpenAPI/ ./OpenAPI/

# Install dependencies
COPY frontend/package*.json ./frontend/
WORKDIR /app/frontend
RUN npm ci

# Copy source and build (skip prebuild generate-types — types already committed)
COPY frontend/ ./
RUN npx vite build

# Stage 2: Serve with nginx
FROM nginx:alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/frontend/dist /usr/share/nginx/html
EXPOSE 80
