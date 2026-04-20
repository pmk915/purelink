package config

import (
	"bufio"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"
)

type Config struct {
	BaseDir        string
	DatabaseURL    string
	UploadDir      string
	ParsedDir      string
	ChunksDir      string
	VectorStoreDir string
	PollInterval   time.Duration
}

func Load() (Config, error) {
	baseDir, err := resolveBaseDir()
	if err != nil {
		return Config{}, err
	}

	envFile := os.Getenv("PURELINK_ENV_FILE")
	if envFile == "" {
		envFile = filepath.Join(baseDir, ".env")
	}
	if err := loadEnvFile(envFile); err != nil {
		return Config{}, err
	}

	databaseURL, err := sanitizeDatabaseURL(os.Getenv("DATABASE_URL"))
	if err != nil {
		return Config{}, err
	}

	pollInterval, err := time.ParseDuration(getEnv("WORKER_POLL_INTERVAL", "5s"))
	if err != nil {
		return Config{}, fmt.Errorf("invalid WORKER_POLL_INTERVAL: %w", err)
	}

	return Config{
		BaseDir:        baseDir,
		DatabaseURL:    databaseURL,
		UploadDir:      resolvePath(baseDir, getEnv("UPLOAD_DIR", "data/uploads")),
		ParsedDir:      resolvePath(baseDir, getEnv("PARSED_DIR", "data/parsed")),
		ChunksDir:      resolvePath(baseDir, getEnv("CHUNK_DIR", "data/chunks")),
		VectorStoreDir: resolvePath(baseDir, getEnv("VECTOR_STORE_DIR", "data/vector_store")),
		PollInterval:   pollInterval,
	}, nil
}

func resolveBaseDir() (string, error) {
	baseDir := os.Getenv("PURELINK_BASE_DIR")
	if baseDir == "" {
		var err error
		baseDir, err = os.Getwd()
		if err != nil {
			return "", fmt.Errorf("failed to resolve current working directory: %w", err)
		}
	}

	absoluteBaseDir, err := filepath.Abs(baseDir)
	if err != nil {
		return "", fmt.Errorf("failed to resolve base directory: %w", err)
	}
	return absoluteBaseDir, nil
}

func loadEnvFile(path string) error {
	file, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return fmt.Errorf("failed to open env file: %w", err)
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") || !strings.Contains(line, "=") {
			continue
		}

		key, value, found := strings.Cut(line, "=")
		if !found {
			continue
		}

		key = strings.TrimSpace(key)
		value = strings.TrimSpace(value)
		value = strings.Trim(value, `"'`)
		if key == "" {
			continue
		}
		if _, exists := os.LookupEnv(key); exists {
			continue
		}
		if err := os.Setenv(key, value); err != nil {
			return fmt.Errorf("failed to set env %s: %w", key, err)
		}
	}

	if err := scanner.Err(); err != nil {
		return fmt.Errorf("failed to read env file: %w", err)
	}
	return nil
}

func sanitizeDatabaseURL(raw string) (string, error) {
	raw = strings.TrimSpace(raw)
	var databaseURL string
	switch {
	case raw == "":
		return "", fmt.Errorf("DATABASE_URL is required")
	case strings.HasPrefix(raw, "postgresql+psycopg://"):
		databaseURL = "postgres://" + strings.TrimPrefix(raw, "postgresql+psycopg://")
	case strings.HasPrefix(raw, "postgresql://"):
		databaseURL = "postgres://" + strings.TrimPrefix(raw, "postgresql://")
	case strings.HasPrefix(raw, "postgres://"):
		databaseURL = raw
	default:
		return "", fmt.Errorf("Go document worker only supports PostgreSQL DATABASE_URL")
	}

	parsedURL, err := url.Parse(databaseURL)
	if err != nil {
		return "", fmt.Errorf("invalid DATABASE_URL: %w", err)
	}

	query := parsedURL.Query()
	if query.Get("sslmode") == "" {
		query.Set("sslmode", "disable")
		parsedURL.RawQuery = query.Encode()
	}

	return parsedURL.String(), nil
}

func resolvePath(baseDir string, value string) string {
	clean := filepath.Clean(value)
	if filepath.IsAbs(clean) {
		return clean
	}
	return filepath.Join(baseDir, clean)
}

func getEnv(name string, defaultValue string) string {
	value := strings.TrimSpace(os.Getenv(name))
	if value == "" {
		return defaultValue
	}
	return value
}
