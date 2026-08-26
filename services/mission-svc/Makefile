.PHONY: proto build run test

proto:
	PATH="$(PATH):$(shell go env GOPATH)/bin" protoc \
	  --go_out=. --go_opt=module=github.com/single-pass-recon/mission-svc \
	  --go-grpc_out=. --go-grpc_opt=module=github.com/single-pass-recon/mission-svc \
	  proto/mission/v1/mission.proto

build:
	go build -o bin/mission-svc ./cmd/server

run: build
	./bin/mission-svc

test:
	go test ./...
