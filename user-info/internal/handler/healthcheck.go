package handler

import (
	"agentic-ai-users/constant"

	"github.com/gin-gonic/gin"
)

func SetupHealthRoutes(r *gin.Engine) {
	r.GET(constant.HealthCheck, func(c *gin.Context) {
		c.JSON(200, gin.H{"message": "Instance is healthy ✅"})
	})
}
