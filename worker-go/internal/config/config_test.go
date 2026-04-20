package config

import "testing"

func TestSanitizeDatabaseURLAddsDisableSSLModeWhenMissing(t *testing.T) {
	got, err := sanitizeDatabaseURL("postgresql+psycopg://purelink:purelink@db:5432/purelink")
	if err != nil {
		t.Fatalf("sanitizeDatabaseURL returned error: %v", err)
	}

	want := "postgres://purelink:purelink@db:5432/purelink?sslmode=disable"
	if got != want {
		t.Fatalf("unexpected sanitized url: got %q want %q", got, want)
	}
}

func TestSanitizeDatabaseURLPreservesExplicitSSLMode(t *testing.T) {
	got, err := sanitizeDatabaseURL("postgres://purelink:purelink@db:5432/purelink?sslmode=require")
	if err != nil {
		t.Fatalf("sanitizeDatabaseURL returned error: %v", err)
	}

	want := "postgres://purelink:purelink@db:5432/purelink?sslmode=require"
	if got != want {
		t.Fatalf("unexpected sanitized url: got %q want %q", got, want)
	}
}
