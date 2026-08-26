.PHONY: proto build run test

proto:
	PATH="$(PATH):$(shell go env GOPATH)/bin" protoc \
	  --go_out=. --go_opt=module=github.com/single-pass-recon/ingest-svc \
	  --go-grpc_out=. --go-grpc_opt=module=github.com/single-pass-recon/ingest-svc \
	  proto/ingest/v1/ingest.proto

build:
	go build -o bin/ingest-svc ./cmd/server

run: build
	./bin/ingest-svc

test:
	go test ./...
