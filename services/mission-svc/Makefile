.PHONY: proto build run test

proto:
	mkdir -p gen/mission/v1
	PATH="$(PATH):$(shell go env GOPATH)/bin" protoc -I proto -I third_party/googleapis \
	  --go_out=gen --go_opt=paths=source_relative \
	  --go-grpc_out=gen --go-grpc_opt=paths=source_relative \
	  proto/mission/v1/mission.proto

build:
	go build -o bin/mission-svc ./cmd/server

run: build
	./bin/mission-svc

test:
	go test ./...
