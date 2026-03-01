package handler

import (
	"agentic-ai-users/constant"
	"agentic-ai-users/internal/domain"
	"net/http"
	"os"
	"strconv"

	"github.com/gin-gonic/gin"
	"github.com/markbates/goth/gothic"
)

type RegisterReq struct {
	Email    string `json:"email" binding:"required,email"`
	Password string `json:"password" binding:"required,min=8"`
	FullName string `json:"full_name" binding:"required"`
}

type LoginReq struct {
	Email    string `json:"email" binding:"required,email"`
	Password string `json:"password" binding:"required"`
}

type UserHandler struct {
	UseCase domain.UserUseCase
}

func NewUserHandler(r *gin.Engine, uc domain.UserUseCase) {
	h := &UserHandler{UseCase: uc}
	{
		r.POST(constant.Register, h.Register)
		r.POST(constant.Login, h.Login)

		// OAuth Routes
		r.GET(constant.Provider, h.StartAuth)
		r.GET(constant.ProviderCallBack, h.CompleteAuth)
	}
}

// Register godoc
// @Summary      Register a new user
// @Description  Create a new retail investor account
// @Tags         auth
// @Accept       json
// @Produce      json
// @Param        request  body      RegisterReq  true  "Registration Details"
// @Success      201      {object}  domain.User
// @Failure      400      {object}  map[string]string
// @Failure      409      {object}  map[string]string
// @Router       /api/v1/auth/register [post]
func (h *UserHandler) Register(c *gin.Context) {
	var req RegisterReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	user, err := h.UseCase.Register(c.Request.Context(), req.Email, req.Password, req.FullName)
	if err != nil {
		c.JSON(http.StatusConflict, gin.H{"error": err.Error()})
		return
	}

	token, err := h.UseCase.Login(c.Request.Context(), req.Email, req.Password)
	if err == nil {
		h.setAuthCookie(c, token)
	}
	c.JSON(http.StatusCreated, user)
}

// Login godoc
// @Summary      User Login
// @Description  Authenticate user and return JWT token
// @Tags         auth
// @Accept       json
// @Produce      json
// @Param        request  body      LoginReq  true  "Login Credentials"
// @Success      200      {object}  map[string]string "returns {token: string}"
// @Failure      401      {object}  map[string]string
// @Router       /api/v1/auth/login [post]
func (h *UserHandler) Login(c *gin.Context) {
	var req LoginReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	token, err := h.UseCase.Login(c.Request.Context(), req.Email, req.Password)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": err.Error()})
		return
	}

	h.setAuthCookie(c, token)
	c.JSON(http.StatusOK, gin.H{"token": token})
}

// UserProfile godoc
// @Summary      Get User Profile
// @Description  Get details of the currently authenticated user
// @Tags         user
// @Produce      json
// @Security     BearerAuth
// @Success      200      {object}  domain.User
// @Failure      401      {object}  map[string]string
// @Router       /api/v1/user/profile [get]
func UserProfile(r *gin.Engine, uc domain.UserUseCase) {
	r.GET(constant.Profile, func(c *gin.Context) {
		consumerID := c.GetHeader("X-Consumer-Custom-ID")
		if consumerID == "" {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized by Gateway"})
			return
		}

		uid64, err := strconv.ParseUint(consumerID, 10, 32)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid User ID"})
			return
		}

		user, err := uc.GetProfile(c.Request.Context(), uint(uid64))
		if err != nil {
			c.JSON(http.StatusNotFound, gin.H{"error": "User not found"})
			return
		}

		c.JSON(http.StatusOK, user)
	})
}

// StartAuth godoc
// @Summary      Start OAuth
// @Description  Redirects user to Social Provider (Google/Twitter)
// @Tags         auth
// @Param        provider  path  string  true  "Provider name (google, x)"
// @Success      302       "Redirect to Provider"
// @Router       /api/v1/auth/{provider} [get]
func (h *UserHandler) StartAuth(c *gin.Context) {
	provider := c.Param("provider")
	if provider == "x" {
		provider = "twitter"
	}

	q := c.Request.URL.Query()
	q.Add("provider", provider)
	c.Request.URL.RawQuery = q.Encode()
	gothic.BeginAuthHandler(c.Writer, c.Request)
}

func (h *UserHandler) CompleteAuth(c *gin.Context) {
	provider := c.Param("provider")
	if provider == "x" {
		provider = "twitter"
	}

	q := c.Request.URL.Query()
	q.Add("provider", provider)
	c.Request.URL.RawQuery = q.Encode()

	gothUser, err := gothic.CompleteUserAuth(c.Writer, c.Request)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Auth failed"})
		return
	}

	profile := domain.OAuthProfile{
		Email:      gothUser.Email,
		Name:       gothUser.Name,
		ProviderID: gothUser.UserID,
		AvatarURL:  gothUser.AvatarURL,
	}

	token, err := h.UseCase.LoginOrRegisterOAuth(c.Request.Context(), provider, profile)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Login failed"})
		return
	}

	xRedirectFrontend := os.Getenv("X_REDIRECT_FRONTEND")
	c.Redirect(http.StatusFound, xRedirectFrontend+token)
}

func (h *UserHandler) setAuthCookie(c *gin.Context, token string) {
	c.SetCookie(
		"auth_token",
		token,
		3600*24, // 1 day
		"/",
		os.Getenv("FRONT_END_DOMAIN"),
		os.Getenv("SECURE_COOKIE") == "true",
		true,
	)
}
