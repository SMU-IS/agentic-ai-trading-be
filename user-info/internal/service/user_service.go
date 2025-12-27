package service

import (
	"agentic-ai-users/internal/domain"
	"context"
	"errors"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"golang.org/x/crypto/bcrypt"
)

type userUseCase struct {
	userRepo  domain.UserRepository
	jwtSecret []byte
}

func NewUserUseCase(ur domain.UserRepository, secret string) domain.UserUseCase {
	return &userUseCase{
		userRepo:  ur,
		jwtSecret: []byte(secret),
	}
}

func (s *userUseCase) generateToken(userID uint) (string, error) {
	claims := jwt.MapClaims{
		"sub": userID,
		"exp": time.Now().Add(24 * time.Hour).Unix(),
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

	return s.generateToken(user.ID)
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

	return s.generateToken(user.ID)
}

func (s *userUseCase) GetProfile(ctx context.Context, userID uint) (*domain.User, error) {
	return s.userRepo.GetByID(ctx, userID)
}
