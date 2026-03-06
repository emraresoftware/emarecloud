#!/usr/bin/env python3
"""Seed portlarini tum proje .env dosyalarina yazar."""
import re, pathlib

BASE = pathlib.Path("/Users/emre/Desktop/Emare")
SEED = [
    (5555,  "emarecloud",                         "PORT"),
    (8000,  "emareapi",                           "PORT"),
    (8080,  "emaresuperapp",                      "PORT"),
    (8100,  "Emare Finance",                      "APP_PORT"),
    (8101,  "Emarebot",                           "PORT"),
    (8102,  "Emaremakale",                        "PORT"),
    (8103,  "emare code",                         "PORT"),
    (8104,  "emare desk",                         "PORT"),
    (8105,  "emare_dashboard",                    "PORT"),
    (8106,  "emareads",                           "PORT"),
    (8107,  "emareasistan",                       "PORT"),
    (8108,  "emarecc",                            "PORT"),
    (8109,  "emaredatabase",                      "PORT"),
    (8110,  "emareflux",                          "PORT"),
    (8111,  "emarefree",                          "PORT"),
    (8112,  "emaregithup",                        "PORT"),
    (8113,  "emaregoogle",                        "PORT"),
    (8114,  "emarekatip",                         "PORT"),
    (8115,  "emarepazar",                         "PORT"),
    (8116,  "emarepos",                           "PORT"),
    (8117,  "emaresebil",                         "PORT"),
    (8118,  "emaresetup",                         "PORT"),
    (8119,  "emareteam",                          "PORT"),
    (8120,  "emareulak",                          "PORT"),
    (8121,  "emarevscodeasistan",                 "PORT"),
    (8122,  "emarework/koordinasyon-sistemi",     "PORT"),
    (8123,  "Emare os",                           "PORT"),
    (8124,  "EmareHup",                           "PORT"),
    (8125,  "Emaresiber/siberemare-multiagent-v2","PORT"),
    (8126,  "Emare Hosting",                      "PORT"),
    (8127,  "Emare Log",                          "PORT"),
    (8128,  "emareaplincedesk",                   "PORT"),
    (8129,  "sosyal medya yonetim araci",         "PORT"),
    (8130,  "girhup",                             "PORT"),
    (8200,  "Emareintranet",                      "APP_PORT"),
    (8300,  "emarecripto",                        "APP_PORT"),
    (8400,  "emareidi",                           "APP_PORT"),
    (8600,  "emaretedarik",                       "APP_PORT"),
    (8700,  "emareaimusic",                       "APP_PORT"),
    (8800,  "emareflow",                          "APP_PORT"),
    (8888,  "emareai",                            "PORT"),
    (8900,  "emarewebdizayn",                     "APP_PORT"),
    (3002,  "emare-token",                        "PORT"),
]

# Türkçe klasör adı için: "sosyal medya yönetim aracı" — disk adıyla dene
ALIASES = {
    "sosyal medya yonetim araci": "sosyal medya y\u00f6netim arac\u0131",
}


def uygula(env_file, var_name, port):
    text = env_file.read_text(encoding="utf-8", errors="replace")
    pat = re.compile(r'^' + re.escape(var_name) + r'\s*=.*$', re.MULTILINE)
    yeni = f"{var_name}={port}"
    if pat.search(text):
        eski = pat.search(text).group()
        if eski == yeni:
            return "SKIP"
        env_file.write_text(pat.sub(yeni, text), encoding="utf-8")
        return f"EDIT  {eski} -> {yeni}"
    else:
        env_file.write_text(f"{yeni}\n" + text, encoding="utf-8")
        return f"ADD   {yeni}"


updated = skipped = missing = 0

for port, rel_dir, var_name in SEED:
    proj_path = BASE / rel_dir
    if not proj_path.exists():
        alt = ALIASES.get(rel_dir)
        if alt:
            proj_path = BASE / alt
        if not proj_path.exists():
            print(f"MISS  {rel_dir}")
            missing += 1
            continue

    env_files = list(proj_path.glob(".env")) + list(proj_path.glob(".env.example"))

    if not env_files:
        ep = proj_path / ".env"
        ep.write_text(f"# Port EmareCloud panelinden tahsis edildi.\n{var_name}={port}\n", encoding="utf-8")
        print(f"NEW   {ep.relative_to(BASE)}")
        updated += 1
        continue

    for ef in env_files:
        r = uygula(ef, var_name, port)
        rel = str(ef.relative_to(BASE))
        if r == "SKIP":
            print(f"SKIP  {rel}")
            skipped += 1
        else:
            print(f"OK    {rel}  ({r})")
            updated += 1

print()
print("=" * 50)
print(f"Guncellenen : {updated}")
print(f"Zaten dogru : {skipped}")
print(f"Dizin yok   : {missing}")
