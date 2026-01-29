"""Spanish names and username generation for demo data."""

import random
from typing import List, Tuple

# Spanish first names
SPANISH_FIRST_NAMES: List[str] = [
    # Female names
    "María", "Carmen", "Ana", "Laura", "Isabel", "Lucía", "Elena", "Sofía",
    "Paula", "Marta", "Sara", "Alba", "Andrea", "Claudia", "Patricia",
    "Cristina", "Raquel", "Beatriz", "Nuria", "Silvia", "Rosa", "Pilar",
    "Teresa", "Alicia", "Mónica", "Eva", "Inés", "Irene", "Julia", "Diana",
    "Natalia", "Rocío", "Marina", "Carolina", "Lorena", "Verónica", "Sandra",
    "Esther", "Adriana", "Victoria", "Noelia", "Miriam", "Yolanda", "Susana",
    "Lidia", "Maite", "Olga", "Vanessa", "Lourdes", "Amparo",
    # Male names
    "Carlos", "Pedro", "Diego", "Pablo", "Javier", "Miguel", "Antonio",
    "Francisco", "José", "Manuel", "David", "Daniel", "Alejandro", "Rafael",
    "Fernando", "Jorge", "Luis", "Sergio", "Álvaro", "Adrián", "Rubén",
    "Iván", "Óscar", "Alberto", "Enrique", "Víctor", "Roberto", "Marcos",
    "Andrés", "Mario", "Raúl", "Gonzalo", "Guillermo", "Ignacio", "Eduardo",
    "Héctor", "Nicolás", "Jaime", "Gabriel", "Tomás", "Ricardo", "Hugo",
    "Martín", "Samuel", "Emilio", "Felipe", "Ramón", "Alfonso", "Salvador",
]

# Spanish last names
SPANISH_LAST_NAMES: List[str] = [
    "García", "Rodríguez", "Martínez", "López", "González", "Hernández",
    "Pérez", "Sánchez", "Ramírez", "Torres", "Flores", "Rivera", "Gómez",
    "Díaz", "Reyes", "Moreno", "Jiménez", "Ruiz", "Álvarez", "Romero",
    "Navarro", "Domínguez", "Vega", "Ramos", "Gil", "Serrano", "Blanco",
    "Molina", "Morales", "Suárez", "Ortega", "Delgado", "Castro", "Ortiz",
    "Rubio", "Marín", "Sanz", "Iglesias", "Núñez", "Medina", "Garrido",
    "Cortés", "Castillo", "Santos", "Lozano", "Guerrero", "Cano", "Prieto",
    "Méndez", "Cruz", "Calvo", "Gallego", "Vidal", "León", "Márquez",
    "Herrera", "Peña", "Cabrera", "Campos", "Vargas", "Fuentes", "Carrasco",
]

# Username patterns
USERNAME_PATTERNS: List[str] = [
    "{first}_{topic}",
    "{first}_{topic}_{num}",
    "{first}.{topic}",
    "{topic}_{first}",
    "{first}_{adj}",
    "{first}{num}_{topic}",
    "soy_{first}_{topic}",
    "{first}_life",
    "{first}_oficial",
    "{first}_{year}",
]

# Topics for usernames
USERNAME_TOPICS: List[str] = [
    "fit", "fitness", "gym", "healthy", "wellness", "strong", "active",
    "nutri", "nutrition", "vida_sana", "salud", "training", "sport",
    "running", "yoga", "pilates", "crossfit", "cardio", "muscle",
    "lifestyle", "health", "bienestar", "deporte", "entreno", "coach",
]

# Adjectives for usernames
USERNAME_ADJECTIVES: List[str] = [
    "happy", "strong", "fit", "healthy", "active", "motivated", "focused",
    "real", "true", "official", "daily", "lifestyle", "journey", "goals",
]

# Email domains
EMAIL_DOMAINS: List[str] = [
    "gmail.com", "hotmail.com", "outlook.com", "yahoo.es", "icloud.com",
    "live.com", "mail.com", "protonmail.com",
]


def generate_full_name() -> Tuple[str, str]:
    """Generate a random Spanish full name."""
    first_name = random.choice(SPANISH_FIRST_NAMES)
    last_name = random.choice(SPANISH_LAST_NAMES)
    return first_name, last_name


def generate_username(first_name: str, index: int = 0) -> str:
    """Generate a realistic Instagram username."""
    first = first_name.lower().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    topic = random.choice(USERNAME_TOPICS)
    adj = random.choice(USERNAME_ADJECTIVES)
    num = random.randint(1, 99)
    year = random.randint(90, 99)

    pattern = random.choice(USERNAME_PATTERNS)
    username = pattern.format(
        first=first,
        topic=topic,
        adj=adj,
        num=num,
        year=year,
    )

    # Add index to ensure uniqueness
    if index > 0 and random.random() > 0.5:
        username = f"{username}_{index}"

    return username.replace(" ", "_").lower()[:30]  # Instagram max 30 chars


def generate_email(first_name: str, last_name: str) -> str:
    """Generate a realistic email address."""
    first = first_name.lower().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    last = last_name.lower().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    domain = random.choice(EMAIL_DOMAINS)

    patterns = [
        f"{first}.{last}@{domain}",
        f"{first}{last}@{domain}",
        f"{first}_{last}@{domain}",
        f"{first}{random.randint(1, 99)}@{domain}",
        f"{first}.{last}{random.randint(1, 99)}@{domain}",
    ]

    return random.choice(patterns)


def generate_phone() -> str:
    """Generate a Spanish mobile phone number."""
    prefix = random.choice(["6", "7"])
    number = "".join([str(random.randint(0, 9)) for _ in range(8)])
    return f"+34{prefix}{number}"


# Pre-generated list of 200 names for consistency
SPANISH_NAMES: List[Tuple[str, str]] = [
    generate_full_name() for _ in range(250)  # Generate extra for uniqueness
]
