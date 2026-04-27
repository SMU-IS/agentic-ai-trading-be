package repository

import (
	"agentic-ai-users/internal/domain"
	"context"
	"errors"

	"gorm.io/gorm"
)

type waitlistRepository struct {
	db *gorm.DB
}

func NewWaitlistRepository(db *gorm.DB) domain.WaitlistRepository {
	return &waitlistRepository{db: db}
}

func (r *waitlistRepository) IsVerified(ctx context.Context, email string) (bool, error) {
	var entry domain.WaitlistEntry
	err := r.db.WithContext(ctx).Where("email = ?", email).First(&entry).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return true, nil
}

func (r *waitlistRepository) Save(ctx context.Context, email string) error {
	entry := domain.WaitlistEntry{Email: email}
	return r.db.WithContext(ctx).Create(&entry).Error
}
