# Image de développement. L'image de production (multi-stage, utilisateur non-root) viendra en P19.
FROM node:22-slim

WORKDIR /app

# Dépendances d'abord : cette couche est mise en cache tant que package*.json ne change pas
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0", "--port", "3000"]
