package config

import (
	"agentic-ai-users/internal/domain"
	"agentic-ai-users/pkg/util"
	"fmt"
	"log"
	"os"

	"github.com/markbates/goth"
	"github.com/markbates/goth/providers/twitter"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

type DBConfig struct {
	Host     string
	Port     string
	User     string
	Password string
	Name     string
	SSLMode  string
	TimeZone string
}

func (c *DBConfig) DSN() string {
	return fmt.Sprintf(
		"host=%s user=%s password=%s dbname=%s port=%s sslmode=%s TimeZone=%s",
		c.Host, c.User, c.Password, c.Name, c.Port, c.SSLMode, c.TimeZone,
	)
}

func LoadDBConfig() *DBConfig {
	util.LoadEnv()
	dbConfig := DBConfig{
		Host:     os.Getenv("HOST"),
		Port:     os.Getenv("DB_PORT"),
		User:     os.Getenv("DB_USERNAME"),
		Password: os.Getenv("DB_PASSWORD"),
		Name:     os.Getenv("DB_NAME"),
		SSLMode:  "disable",
		TimeZone: "Asia/Singapore",
	}

	return &dbConfig
}

func InitDB(cfg *DBConfig) *gorm.DB {
	db, err := gorm.Open(postgres.Open(cfg.DSN()), &gorm.Config{})
	if err != nil {
		log.Fatalf("DB Connection failed: %v", err)
	}

	err = db.AutoMigrate(&domain.User{})
	if err != nil {
		log.Fatalf("DB Migration failed: %v", err)
	}

	log.Println("Database connection established and migrated successfully")
	return db
}

func SetupOAuth() {
	twitterProvider := twitter.New(
		os.Getenv("X_KEY"),
		os.Getenv("X_SECRET"),
		os.Getenv("X_CALL_BACK"),
	)
	goth.UseProviders(
		twitterProvider,
	)
}
