PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 50


def validate_password(value: str) -> str:
    """Política de contraseñas."""
    if len(value) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Debe tener al menos {PASSWORD_MIN_LENGTH} caracteres")
    if len(value) > PASSWORD_MAX_LENGTH:
        raise ValueError(f"Debe tener como máximo {PASSWORD_MAX_LENGTH} caracteres")
    if value.strip() != value:
        raise ValueError("No puede empezar ni terminar con espacios")
    if not any(char.isdigit() for char in value):
        raise ValueError("Debe incluir al menos un número")
    if not any(char.isalpha() for char in value):
        raise ValueError("Debe incluir al menos una letra")
    return value


def validate_username(value: str) -> str:
    """Normaliza a minúsculas y valida el nombre de usuario: ASCII, sin caracteres confusos."""
    value = value.strip().lower()
    if len(value) < USERNAME_MIN_LENGTH:
        raise ValueError(f"Debe tener al menos {USERNAME_MIN_LENGTH} caracteres")
    if len(value) > USERNAME_MAX_LENGTH:
        raise ValueError(f"Debe tener como máximo {USERNAME_MAX_LENGTH} caracteres")
    if not value.isascii() or not all(char.isalnum() or char in "._-" for char in value):
        raise ValueError("Solo letras sin acentos, números, punto, guion y guion bajo")
    return value
