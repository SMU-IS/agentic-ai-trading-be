package service

import (
	"agentic-ai-users/constant"
	"agentic-ai-users/internal/domain"
	"context"
	"crypto/rand"
	"errors"
	"fmt"
	"math/big"
	"net/smtp"
	"os"
	"time"

	"github.com/redis/go-redis/v9"
)

type waitlistUseCase struct {
	repo        domain.WaitlistRepository
	redisClient *redis.Client
}

func NewWaitlistUseCase(repo domain.WaitlistRepository, rc *redis.Client) domain.WaitlistUseCase {
	return &waitlistUseCase{repo: repo, redisClient: rc}
}

func (s *waitlistUseCase) RequestOTP(ctx context.Context, email string) error {
	verified, err := s.repo.IsVerified(ctx, email)
	if err != nil {
		return err
	}
	if verified {
		return errors.New("email already on waitlist")
	}

	code, err := generateOTP()
	if err != nil {
		return err
	}

	key := fmt.Sprintf(constant.WaitlistOTPCacheKey, email)
	if err := s.redisClient.Set(ctx, key, code, 10*time.Minute).Err(); err != nil {
		return err
	}

	return sendOTPEmail(email, code)
}

func (s *waitlistUseCase) VerifyOTP(ctx context.Context, email, code string) error {
	key := fmt.Sprintf(constant.WaitlistOTPCacheKey, email)
	stored, err := s.redisClient.Get(ctx, key).Result()
	if errors.Is(err, redis.Nil) {
		return errors.New("code expired or not found")
	}
	if err != nil {
		return err
	}
	if stored != code {
		return errors.New("invalid code")
	}

	if err := s.repo.Save(ctx, email); err != nil {
		return err
	}

	s.redisClient.Del(ctx, key)
	return nil
}

func generateOTP() (string, error) {
	n, err := rand.Int(rand.Reader, big.NewInt(10000))
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("%04d", n.Int64()), nil
}

func sendOTPEmail(to, code string) error {
	host := os.Getenv("SMTP_HOST")
	port := os.Getenv("SMTP_PORT")
	user := os.Getenv("SMTP_USER")
	password := os.Getenv("SMTP_PASSWORD")
	from := os.Getenv("SMTP_FROM")

	if from == "" {
		from = user
	}

	auth := smtp.PlainAuth("", user, password, host)
	addr := host + ":" + port

	subject := "Your Agent M waitlist code"
	body := fmt.Sprintf("Your verification code is: %s\n\nThis code expires in 10 minutes.", code)
	msg := []byte("From: " + from + "\r\n" +
		"To: " + to + "\r\n" +
		"Subject: " + subject + "\r\n" +
		"\r\n" +
		body)

	return smtp.SendMail(addr, auth, from, []string{to}, msg)
}
