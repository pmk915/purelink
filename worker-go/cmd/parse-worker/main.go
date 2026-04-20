package main

import (
	"context"
	"database/sql"
	"errors"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	_ "github.com/lib/pq"

	"purelink/worker-go/internal/config"
	"purelink/worker-go/internal/tasks"
)

func main() {
	logger := log.New(os.Stdout, "document-worker ", log.LstdFlags|log.LUTC)

	cfg, err := config.Load()
	if err != nil {
		logger.Fatalf("failed to load config: %v", err)
	}

	db, err := sql.Open("postgres", cfg.DatabaseURL)
	if err != nil {
		logger.Fatalf("failed to open database: %v", err)
	}
	defer db.Close()

	db.SetMaxOpenConns(4)
	db.SetMaxIdleConns(4)
	db.SetConnMaxLifetime(30 * time.Minute)

	pingCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := db.PingContext(pingCtx); err != nil {
		logger.Fatalf("failed to ping database: %v", err)
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	logger.Printf(
		"starting document worker poll_interval=%s upload_dir=%s parsed_dir=%s chunks_dir=%s vector_store_dir=%s",
		cfg.PollInterval,
		cfg.UploadDir,
		cfg.ParsedDir,
		cfg.ChunksDir,
		cfg.VectorStoreDir,
	)

	worker := tasks.NewWorker(
		db,
		cfg.UploadDir,
		cfg.ParsedDir,
		cfg.ChunksDir,
		cfg.VectorStoreDir,
		cfg.PollInterval,
		logger,
	)

	err = worker.Run(ctx)
	if err != nil && !errors.Is(err, context.Canceled) {
		logger.Fatalf("worker stopped with error: %v", err)
	}

	logger.Println("document worker stopped")
}
