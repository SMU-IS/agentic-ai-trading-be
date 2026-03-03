package service

import (
	"agentic-ai-users/constant"
	"agentic-ai-users/internal/domain"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"os"
	"strconv"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/redis/go-redis/v9"
	"golang.org/x/crypto/bcrypt"
)

type userUseCase struct {
	userRepo    domain.UserRepository
	redisClient *redis.Client
	cacheTTL    time.Duration
	jwtSecret   []byte
}

func NewUserUseCase(ur domain.UserRepository, rc *redis.Client, ttl time.Duration, secret string) domain.UserUseCase {
	return &userUseCase{
		userRepo:    ur,
		redisClient: rc,
		cacheTTL:    ttl,
		jwtSecret:   []byte(secret),
	}
}

func (s *userUseCase) generateToken(userID string) (string, error) {
	jwtExpiration := os.Getenv("JWT_EXPIRATION_HOURS")
	jwtExpirationInt, err := strconv.Atoi(jwtExpiration)
	if err != nil {
		jwtExpirationInt = 24
	}
	expirationDuration := time.Duration(jwtExpirationInt) * time.Hour

	claims := jwt.MapClaims{
		"sub": userID,
		"exp": time.Now().Add(expirationDuration).Unix(),
		"iss": "agentic-ai-user-service",
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString(s.jwtSecret)
}

func (s *userUseCase) Register(ctx context.Context, email, password, fullName string) (*domain.User, error) {
	existing, err := s.userRepo.GetByEmail(ctx, email)
	if err != nil {
		return nil, err
	}
	if existing != nil {
		return nil, errors.New("email already in use")
	}

	hashed, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return nil, err
	}

	user := &domain.User{
		Email:    email,
		Password: string(hashed),
		FullName: fullName,
		Provider: "email",
	}

	if err := s.userRepo.Create(ctx, user); err != nil {
		return nil, err
	}
	return user, nil
}

func (s *userUseCase) Login(ctx context.Context, email, password string) (string, error) {
	user, err := s.userRepo.GetByEmail(ctx, email)
	if err != nil || user == nil {
		return "", errors.New("invalid credentials")
	}

	if user.Provider != "email" {
		return "", errors.New("please login with " + user.Provider)
	}

	if err := bcrypt.CompareHashAndPassword([]byte(user.Password), []byte(password)); err != nil {
		return "", errors.New("invalid credentials")
	}

	return s.generateToken(user.UserID)
}

func (s *userUseCase) LoginOrRegisterOAuth(ctx context.Context, provider string, profile domain.OAuthProfile) (string, error) {
	user, err := s.userRepo.GetByEmail(ctx, profile.Email)
	if err != nil {
		return "", err
	}

	if user == nil {
		user = &domain.User{
			Email:      profile.Email,
			FullName:   profile.Name,
			Provider:   provider,
			ProviderID: profile.ProviderID,
			AvatarURL:  profile.AvatarURL,
		}
		if err := s.userRepo.Create(ctx, user); err != nil {
			return "", err
		}
	}

	return s.generateToken(user.UserID)
}

func (s *userUseCase) GetProfile(ctx context.Context, userID string) (*domain.User, error) {
	cacheKey := fmt.Sprintf(constant.UserProfileCacheKey, userID)
	val, err := s.redisClient.Get(ctx, cacheKey).Result()
	if err == nil {
		// Cache Hit
		var user domain.User
		if err := json.Unmarshal([]byte(val), &user); err == nil {
			return &user, nil
		}
	} else if err != redis.Nil {
		log.Printf("Redis error: %v\n", err)
	}

	// Cache Miss
	user, err := s.userRepo.GetByID(ctx, userID)
	if err != nil {
		return nil, err
	}

	data, err := json.Marshal(user)
	if err == nil {
		s.redisClient.Set(ctx, cacheKey, data, s.cacheTTL)
	}

	return user, nil
}
