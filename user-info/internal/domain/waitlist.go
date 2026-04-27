package domain

import (
	"context"
	"time"
)

type WaitlistEntry struct {
	ID        uint      `gorm:"primaryKey;autoIncrement" json:"id"`
	Email     string    `gorm:"uniqueIndex;not null" json:"email"`
	CreatedAt time.Time `json:"created_at"`
}

type WaitlistUseCase interface {
	RequestOTP(ctx context.Context, email string) error
	VerifyOTP(ctx context.Context, email, code string) error
}

type WaitlistRepository interface {
	IsVerified(ctx context.Context, email string) (bool, error)
	Save(ctx context.Context, email string) error
}
