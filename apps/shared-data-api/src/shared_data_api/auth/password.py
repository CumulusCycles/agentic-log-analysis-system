import bcrypt

# A real bcrypt hash of an arbitrary string, used as a constant-work target
# when verify_password is called against a non-existent user. Equalizes the
# elapsed time of failed-login responses so request timing cannot be used to
# probe for valid usernames.
DUMMY_HASH = bcrypt.hashpw(b"never-a-real-password", bcrypt.gensalt()).decode("utf-8")


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False
