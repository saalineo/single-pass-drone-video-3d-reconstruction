.PHONY: proto build run test

proto:
	mkdir -p gen/ingest/v1
	PATH="$(PATH):$(shell go env GOPATH)/bin" protoc -I proto \
	  --go_out=gen --go_opt=paths=source_relative \
	  --go-grpc_out=gen --go-grpc_opt=paths=source_relative \
	  proto/ingest/v1/ingest.proto

build:
	go build -o bin/ingest-svc ./cmd/server

run: build
	./bin/ingest-svc

test:
	go test ./...
