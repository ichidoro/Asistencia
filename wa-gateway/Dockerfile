FROM node:22-alpine
WORKDIR /app
COPY package.json ./
RUN apk add --no-cache git && npm install --omit=dev && apk del git
COPY index.js ./
# La sesión vive en un volumen: la carpeta debe ser de «node» antes de crearlo, o el volumen nace de root y no se puede escribir.
RUN mkdir -p /data/auth && chown -R node:node /data
USER node
EXPOSE 3000
CMD ["node", "index.js"]
