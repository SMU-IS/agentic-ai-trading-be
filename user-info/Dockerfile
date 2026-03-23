FROM golang:1.25-alpine
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o main ./cmd/main.go

FROM alpine:3.21
WORKDIR /app
COPY --from=builder /app/main .
CMD ["./main"]
