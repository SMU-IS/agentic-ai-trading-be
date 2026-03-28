package handler

import (
	"github.com/gin-gonic/gin"
)

func SetupHealthRoutes(r *gin.Engine) {
	r.GET("/", func(c *gin.Context) {
		c.JSON(200, gin.H{"message": "Instance is healthy ✅"})
	})
}
