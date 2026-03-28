# import jwt  # PyJWT
# from fastapi import Request


# def get_current_user(request: Request) -> dict:
#     auth_header = request.headers.get("authorization", "")
#     if not auth_header.startswith("Bearer "):
#         raise HTTPException(status_code=401)

#     token = auth_header.split(" ")[1]
#     # Kong already verified it - just decode without verification
#     payload = jwt.decode(token, options={"verify_signature": False})
#     return payload  # contains user_id, exp, etc.
