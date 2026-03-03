package domain

import (
	"context"
	"time"

	"gorm.io/gorm"
)

// User Model
type User struct {
	UserID     string         `gorm:"primaryKey;type:uuid;default:gen_random_uuid()" json:"user_id"`
	Email      string         `gorm:"uniqueIndex;not null" json:"email"`
	Password   string         `json:"-"` // Empty for OAuth users
	FullName   string         `json:"full_name"`
	Provider   string         `json:"provider"` // e.g., "email", "google", "twitter"
	ProviderID string         `json:"-"`        // External ID from OAuth
	AvatarURL  string         `json:"avatar_url"`
	CreatedAt  time.Time      `json:"created_at"`
	UpdatedAt  time.Time      `json:"updated_at"`
	DeletedAt  gorm.DeletedAt `gorm:"index" json:"-"`
}

// Helper for OAuth data
type OAuthProfile struct {
	Email      string
	Name       string
	ProviderID string
	AvatarURL  string
}

// UserUseCase (Service Interface)
type UserUseCase interface {
	Register(ctx context.Context, email, password, fullName string) (*User, error)
	Login(ctx context.Context, email, password string) (string, error)
	LoginOrRegisterOAuth(ctx context.Context, provider string, profile OAuthProfile) (string, error)
	GetProfile(ctx context.Context, userID string) (*User, error)
}

// UserRepository (Data Interface)
type UserRepository interface {
	Create(ctx context.Context, user *User) error
	GetByEmail(ctx context.Context, email string) (*User, error)
	GetByID(ctx context.Context, userID string) (*User, error)
}
