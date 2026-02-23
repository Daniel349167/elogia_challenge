FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .
RUN npm run build

ENV NEXT_TELEMETRY_DISABLED=1

CMD ["npm", "run", "start"]
