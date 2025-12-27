package constant

const (
	HealthCheck      = "/healthcheck"
	BasePath         = "/api/v1"
	Doc              = "/docs/*any"
	Auth             = BasePath + "/auth"
	Register         = "/register"
	Login            = "/login"
	Provider         = "/:provider"
	ProviderCallBack = "/:provider/callback"
	User             = BasePath + "/user"
	Profile          = "/profile"
)
