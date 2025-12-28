package handler

import (
	"agentic-ai-users/constant"
	"agentic-ai-users/docs"

	"github.com/gin-gonic/gin"
	swaggerfiles "github.com/swaggo/files"
	ginSwagger "github.com/swaggo/gin-swagger"
)

func SetUpAPIDocs(router *gin.Engine) {
	docs.SwaggerInfo.BasePath = "/"
	router.GET(constant.Doc, ginSwagger.WrapHandler(swaggerfiles.Handler))
}
