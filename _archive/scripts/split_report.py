#!/usr/bin/env python3
"""Split the large report into smaller category-based reports"""

with open('test_100_report.md', 'r') as f:
    content = f.read()

# Get header (everything before first ## 📁)
header_end = content.find('## 📁')
header = content[:header_end].strip()

# Split content into sections by "## 📁"
parts = content[header_end:].split('## 📁')
sections = {}

for part in parts:
    if part.strip():
        lines = part.split('\n', 1)
        section_name = lines[0].strip()
        section_content = lines[1] if len(lines) > 1 else ''
        sections[section_name] = section_content

# Map section names to groups (use partial matching)
groups = [
    ('report_part1_happy_price.md', 'Parte 1: Happy Path y Precio',
     ['Happy Path', 'Precio']),
    ('report_part2_time_doubt.md', 'Parte 2: Tiempo y Dudas',
     ['Tiempo', 'Duda']),
    ('report_part3_leadmagnet_booking.md', 'Parte 3: Lead Magnet y Booking',
     ['Lead Magnet', 'Booking']),
    ('report_part4_escalation_product.md', 'Parte 4: Escalaciones y Producto',
     ['Escalación', 'Producto']),
    ('report_part5_short_edge.md', 'Parte 5: Cortas y Edge Cases',
     ['Cortas', 'Edge']),
]

print("Available sections:")
for name in sections.keys():
    print(f"  - {name}")
print()

# Create files
for filename, title, search_terms in groups:
    with open(filename, 'w') as f:
        f.write(f"# 📊 Test de 100 Conversaciones - {title}\n\n")
        f.write("**Endpoint:** `https://web-production-9f69.up.railway.app/dm/process`\n")
        f.write("**Creator:** `stefano_bonanno`\n\n")
        f.write("---\n\n")

        for search_term in search_terms:
            # Find matching section (partial match)
            found = False
            for key, content_section in sections.items():
                if search_term.lower() in key.lower():
                    f.write(f"## 📁 {key}\n")
                    f.write(content_section)
                    f.write("\n---\n\n")
                    found = True
                    break
            if not found:
                print(f"  ⚠️ No section matches: {search_term}")

    import os
    size = os.path.getsize(filename)
    print(f"✅ {filename}: {size:,} bytes")

print("\n🎉 Done! 5 report files created.")
