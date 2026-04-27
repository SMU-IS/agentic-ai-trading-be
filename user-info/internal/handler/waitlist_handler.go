package handler

import (
	"agentic-ai-users/constant"
	"agentic-ai-users/internal/domain"
	"net/http"

	"github.com/gin-gonic/gin"
)

type WaitlistHandler struct {
	UseCase domain.WaitlistUseCase
}

func NewWaitlistHandler(r *gin.Engine, uc domain.WaitlistUseCase) {
	h := &WaitlistHandler{UseCase: uc}
	r.POST(constant.WaitlistRequest, h.RequestOTP)
	r.POST(constant.WaitlistVerify, h.VerifyOTP)
}

type waitlistRequestBody struct {
	Email string `json:"email" binding:"required,email"`
}

type waitlistVerifyBody struct {
	Email string `json:"email" binding:"required,email"`
	Code  string `json:"code" binding:"required,len=4"`
}

// RequestOTP godoc
// @Summary      Request waitlist OTP
// @Description  Send a 4-digit verification code to the provided email
// @Tags         waitlist
// @Accept       json
// @Produce      json
// @Param        request  body  waitlistRequestBody  true  "Email"
// @Success      200  {object}  map[string]string
// @Failure      400  {object}  map[string]string
// @Failure      409  {object}  map[string]string
// @Router       /api/v1/waitlist/request [post]
func (h *WaitlistHandler) RequestOTP(c *gin.Context) {
	var req waitlistRequestBody
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := h.UseCase.RequestOTP(c.Request.Context(), req.Email); err != nil {
		if err.Error() == "email already on waitlist" {
			c.JSON(http.StatusConflict, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Code sent"})
}

// VerifyOTP godoc
// @Summary      Verify waitlist OTP
// @Description  Confirm the 4-digit code and add email to the waitlist
// @Tags         waitlist
// @Accept       json
// @Produce      json
// @Param        request  body  waitlistVerifyBody  true  "Email and code"
// @Success      200  {object}  map[string]string
// @Failure      400  {object}  map[string]string
// @Router       /api/v1/waitlist/verify [post]
func (h *WaitlistHandler) VerifyOTP(c *gin.Context) {
	var req waitlistVerifyBody
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := h.UseCase.VerifyOTP(c.Request.Context(), req.Email, req.Code); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Email verified and added to waitlist"})
}
