package main

import (
	"agentic-ai-users/internal/config"
	"agentic-ai-users/internal/handler"
	"agentic-ai-users/internal/repository"
	"agentic-ai-users/internal/service"
	"agentic-ai-users/pkg/util"
	"agentic-ai-users/server"
	"os"

	"github.com/gin-gonic/gin"
)

// @title           Agentic AI Trading Portfolio User Module API
// @version         1.0
// @description     API documentation for Agentic AI Trading Portfolio - User Module
// @termsOfService  http://swagger.io/terms/

// @contact.name   Joshua
// @contact.url    https://joshydavid.com
// @contact.email  joshuadavidang@outlook.sg

// @license.name  Apache 2.0
// @license.url   http://www.apache.org/licenses/LICENSE-2.0.html

// @host      localhost:8080
// @BasePath  /

// @externalDocs.description  OpenAPI
// @externalDocs.url          https://swagger.io/resources/open-api/
func main() {
	util.LoadEnv()
	config.SetupOAuth()

	// 1. Set Up Database
	db := config.InitDB(config.LoadDBConfig())

	// 2. Dependency Injection
	userRepo := repository.NewUserRepository(db)
	userSvc := service.NewUserUseCase(userRepo, os.Getenv("JWT_SECRET"))

	// 3. Routers & Middleware
	router := gin.Default()
	router.SetTrustedProxies(nil)

	// 4. API Routes Handlers
	handler.SetupHealthRoutes(router)
	handler.SetUpAPIDocs(router)
	handler.NewUserHandler(router, userSvc)
	handler.UserProfile(router, userSvc)

	// 5. Start Server
	server.RunServer(router)
}
