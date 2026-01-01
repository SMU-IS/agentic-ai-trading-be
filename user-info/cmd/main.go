package main

import (
	"agentic-ai-users/internal/config"
	"agentic-ai-users/internal/domain"
	"agentic-ai-users/internal/handler"
	"agentic-ai-users/internal/repository"
	"agentic-ai-users/internal/service"
	"agentic-ai-users/pkg/util"
	"agentic-ai-users/server"
	"log"
	"os"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/redis/go-redis/v9"
	"gorm.io/gorm"
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

	db := config.InitDB(config.LoadDBConfig())
	redisDb := config.InitRedis()
	defer redisDb.Close()

	userSvc := initUserUseCase(db, redisDb)

	router := setupRouter(userSvc)
	server.RunServer(router)
}

func initUserUseCase(db *gorm.DB, redisDb *redis.Client) domain.UserUseCase {
	cacheHoursStr := os.Getenv("CACHE_EXPIRATION_HOURS")
	cacheHours, err := strconv.Atoi(cacheHoursStr)
	log.Println("LOGGGGG", cacheHours)
	if err != nil {
		cacheHours = 1
	}

	redisTtl := time.Duration(cacheHours) * time.Hour
	jwtSecret := os.Getenv("JWT_SECRET")

	userRepo := repository.NewUserRepository(db)
	return service.NewUserUseCase(userRepo, redisDb, redisTtl, jwtSecret)
}

func setupRouter(userSvc domain.UserUseCase) *gin.Engine {
	router := gin.Default()
	router.SetTrustedProxies(nil)

	handler.SetupHealthRoutes(router)
	handler.SetUpAPIDocs(router)
	handler.NewUserHandler(router, userSvc)
	handler.UserProfile(router, userSvc)

	return router
}
