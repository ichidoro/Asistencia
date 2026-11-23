FROM node:22-alpine
WORKDIR /app
COPY package.json ./
RUN apk add --no-cache git && npm install --omit=dev && apk del git
COPY index.js ./
USER node
EXPOSE 3000
CMD ["node", "index.js"]
