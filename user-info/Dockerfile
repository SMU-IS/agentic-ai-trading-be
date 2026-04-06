FROM golang:1.24-alpine AS builder

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -trimpath -o main ./cmd/main.go

FROM alpine:3.19

RUN apk --no-cache add ca-certificates

WORKDIR /root/

COPY --from=builder /app/main .

ENV GIN_MODE=release

EXPOSE 8080

CMD ["./main"]
