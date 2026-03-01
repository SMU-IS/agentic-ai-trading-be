package config

import (
	"agentic-ai-users/internal/domain"
	"agentic-ai-users/pkg/util"
	"fmt"
	"log"
	"os"
	"time"

	"github.com/markbates/goth"
	"github.com/markbates/goth/providers/twitter"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

type DBConfig struct {
	Host        string
	Port        string
	User        string
	Password    string
	Name        string
	SSLMode     string
	SSLRootCert string
	TimeZone    string
}

func (c *DBConfig) DSN() string {
	return fmt.Sprintf(
		"host=%s user=%s password=%s dbname=%s port=%s sslmode=%s sslrootcert=%s TimeZone=%s",
		c.Host, c.User, c.Password, c.Name, c.Port, c.SSLMode, c.SSLRootCert, c.TimeZone,
	)
}

func LoadDBConfig() *DBConfig {
	util.LoadEnv()
	dbConfig := DBConfig{
		Host:        os.Getenv("HOST"),
		Port:        os.Getenv("DB_PORT"),
		User:        os.Getenv("POSTGRES_USER"),
		Password:    os.Getenv("POSTGRES_PASSWORD"),
		Name:        os.Getenv("POSTGRES_DB"),
		SSLMode:     os.Getenv("DB_SSL_MODE"),
		SSLRootCert: os.Getenv("DB_SSL_ROOT_CERT"),
		TimeZone:    os.Getenv("DB_TIMEZONE"),
	}

	if dbConfig.SSLMode == "" {
		dbConfig.SSLMode = "disable"
	}

	return &dbConfig
}

func InitDB(cfg *DBConfig) *gorm.DB {
	db, err := gorm.Open(postgres.Open(cfg.DSN()), &gorm.Config{})
	if err != nil {
		log.Fatalf("DB Connection failed: %v", err)
	}

	sqlDB, err := db.DB()
	if err == nil {
		sqlDB.SetMaxIdleConns(10)
		sqlDB.SetMaxOpenConns(100)
		sqlDB.SetConnMaxLifetime(time.Hour)
	}

	err = db.AutoMigrate(&domain.User{})
	if err != nil {
		log.Fatalf("DB Migration failed: %v", err)
	}

	log.Println("✅ Database connection established and migrated successfully")
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
