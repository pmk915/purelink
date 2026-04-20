FROM golang:1.23-alpine AS builder

WORKDIR /src/worker-go

COPY worker-go/go.mod worker-go/go.sum ./
RUN go mod download

COPY worker-go ./
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /out/purelink-document-worker ./cmd/parse-worker

FROM alpine:3.20

RUN apk add --no-cache ca-certificates

WORKDIR /app

COPY --from=builder /out/purelink-document-worker /usr/local/bin/purelink-document-worker

RUN mkdir -p /app/data /app/logs

CMD ["purelink-document-worker"]
