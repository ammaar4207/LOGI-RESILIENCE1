# Build stage
FROM node:18-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm install

COPY . .
# Build the highly optimized static bundle
RUN npm run build

# Production stage
FROM nginx:alpine

# Copy custom Nginx configuration if needed, otherwise use default and copy dist to html
# We will copy the built assets to Nginx's default serving directory
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose port 80 for Nginx
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]