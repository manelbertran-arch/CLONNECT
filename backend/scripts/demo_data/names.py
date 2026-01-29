"""
Spanish names and username generation
"""
import random

SPANISH_NAMES = {
    "female": [
        "María", "Carmen", "Ana", "Laura", "Marta", "Lucía", "Paula", "Sara",
        "Elena", "Cristina", "Isabel", "Raquel", "Silvia", "Nuria", "Patricia",
        "Andrea", "Alba", "Irene", "Beatriz", "Rosa", "Pilar", "Teresa", "Julia",
        "Rocío", "Natalia", "Eva", "Mónica", "Sonia", "Alicia", "Lorena",
        "Claudia", "Marina", "Esther", "Verónica", "Ángela", "Sandra", "Yolanda",
        "Miriam", "Noelia", "Lidia", "Carolina", "Victoria", "Diana", "Vanessa",
        "Inés", "Olga", "Adriana", "Susana", "Rebeca", "Gloria",
    ],
    "male": [
        "Antonio", "Manuel", "José", "Francisco", "David", "Juan", "Carlos",
        "Javier", "Daniel", "Miguel", "Rafael", "Pedro", "Pablo", "Alejandro",
        "Fernando", "Luis", "Sergio", "Jorge", "Alberto", "Ángel", "Diego",
        "Adrián", "Rubén", "Iván", "Raúl", "Marcos", "Enrique", "Vicente",
        "Ramón", "Andrés", "Jesús", "Mario", "Guillermo", "Salvador", "Joaquín",
        "Óscar", "Roberto", "Eduardo", "Álvaro", "Víctor", "Gonzalo", "Nicolás",
        "Hugo", "Ignacio", "Jaime", "Tomás", "Lucas", "Héctor", "Martín", "Emilio",
    ],
}

SPANISH_SURNAMES = [
    "García", "Rodríguez", "Martínez", "López", "González", "Hernández",
    "Pérez", "Sánchez", "Ramírez", "Torres", "Flores", "Rivera", "Gómez",
    "Díaz", "Reyes", "Moreno", "Jiménez", "Ruiz", "Álvarez", "Romero",
    "Alonso", "Gutiérrez", "Navarro", "Domínguez", "Vázquez", "Ramos",
    "Gil", "Serrano", "Blanco", "Molina", "Morales", "Suárez", "Ortega",
    "Delgado", "Castro", "Ortiz", "Rubio", "Marín", "Sanz", "Iglesias",
    "Medina", "Garrido", "Cortés", "Castillo", "Santos", "Lozano", "Guerrero",
    "Cano", "Prieto", "Méndez", "Cruz", "Calvo", "Gallego", "Herrera", "Peña",
]


def get_random_name() -> tuple[str, str]:
    """Returns (first_name, full_name) tuple"""
    gender = random.choice(["female", "male"])
    first_name = random.choice(SPANISH_NAMES[gender])
    surname = random.choice(SPANISH_SURNAMES)
    full_name = f"{first_name} {surname}"
    return first_name, full_name


def generate_username(first_name: str, index: int) -> str:
    """Generate realistic Instagram-style username"""
    patterns = [
        lambda n, i: f"{n.lower()}{random.randint(80, 99)}",
        lambda n, i: f"{n.lower()}_{random.choice(['fit', 'healthy', 'life', 'real', 'oficial'])}",
        lambda n, i: f"{n.lower()}.{random.choice(['es', 'spain', 'bcn', 'mad'])}",
        lambda n, i: f"soy{n.lower()}",
        lambda n, i: f"{n.lower()}_{random.randint(1, 99):02d}",
        lambda n, i: f"la_{n.lower()}" if random.random() > 0.5 else f"el_{n.lower()}",
        lambda n, i: f"{n.lower()}{random.choice(['xo', 'xx', '_ok', '_go'])}",
    ]

    # Remove accents for username
    name_clean = first_name.lower()
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'ñ': 'n', 'ü': 'u'
    }
    for accent, plain in replacements.items():
        name_clean = name_clean.replace(accent, plain)

    pattern = random.choice(patterns)
    return pattern(name_clean, index)


def generate_email(username: str, first_name: str) -> str:
    """Generate realistic email from username"""
    domains = ["gmail.com", "hotmail.com", "outlook.es", "yahoo.es", "icloud.com"]
    # 70% use gmail
    domain = "gmail.com" if random.random() < 0.7 else random.choice(domains)

    # Sometimes use username, sometimes first name
    if random.random() < 0.6:
        local = username.replace("_", ".")
    else:
        local = first_name.lower()
        for accent, plain in {'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ñ': 'n'}.items():
            local = local.replace(accent, plain)
        local = f"{local}{random.randint(1, 99)}"

    return f"{local}@{domain}"


def generate_phone() -> str:
    """Generate Spanish mobile phone number"""
    # Spanish mobiles start with 6 or 7
    prefix = random.choice(["6", "7"])
    # Generate 8 more digits
    number = "".join([str(random.randint(0, 9)) for _ in range(8)])
    # Format: +34 6XX XXX XXX
    return f"+34 {prefix}{number[:2]} {number[2:5]} {number[5:]}"


# Team members for assignment
TEAM_MEMBERS = [
    "Maria García",
    "Carlos López",
    "Ana Martínez",
    None,  # Unassigned
    None,
    None,
]


def get_assigned_to() -> str | None:
    """Get random team member for assignment (60% unassigned)"""
    return random.choice(TEAM_MEMBERS)
