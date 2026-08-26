.PHONY: proto build run test

proto:
	mkdir -p gen/telemetry/v1
	PATH="$(PATH):$(shell go env GOPATH)/bin" protoc -I proto \
	  --go_out=gen --go_opt=paths=source_relative \
	  proto/telemetry/v1/telemetry.proto

build:
	go build -o bin/telemetry-worker ./cmd/telemetry-worker

run: build
	./bin/telemetry-worker

test:
	go test ./...
