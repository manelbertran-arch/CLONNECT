# Build stage
FROM node:20-alpine AS builder
WORKDIR /app

# Cache bust: 2026-01-26-v1
ENV BUILD_VERSION="2026-01-26-v1"

COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Production stage with nginx
FROM nginx:alpine
# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf
# Copy our config and built files
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
