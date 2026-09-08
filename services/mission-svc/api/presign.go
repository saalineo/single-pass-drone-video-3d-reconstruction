package api

import (
	"context"
	"fmt"
	"net/url"
	"time"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

type StoragePresigner struct {
	client *minio.Client
	secure bool
}

func NewStoragePresigner(endpoint, accessKey, secretKey string, secure bool) (*StoragePresigner, error) {
	mc, err := minio.New(endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(accessKey, secretKey, ""),
		Secure: secure,
	})
	if err != nil {
		return nil, fmt.Errorf("minio client: %w", err)
	}
	return &StoragePresigner{client: mc, secure: secure}, nil
}

// GeneratePresignedGet generates a time-limited GET URL for reading objects.
func (p *StoragePresigner) GeneratePresignedGet(ctx context.Context, bucket, objectKey string, expires time.Duration) (string, error) {
	reqParams := make(url.Values)
	u, err := p.client.PresignedGetObject(ctx, bucket, objectKey, expires, reqParams)
	if err != nil {
		return "", fmt.Errorf("presign get %s/%s: %w", bucket, objectKey, err)
	}
	return u.String(), nil
}

// GeneratePresignedPut generates a time-limited PUT URL for uploading artifacts.
func (p *StoragePresigner) GeneratePresignedPut(ctx context.Context, bucket, objectKey string, expires time.Duration) (string, error) {
	u, err := p.client.PresignedPutObject(ctx, bucket, objectKey, expires)
	if err != nil {
		return "", fmt.Errorf("presign put %s/%s: %w", bucket, objectKey, err)
	}
	return u.String(), nil
}
