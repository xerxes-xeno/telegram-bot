import json
import requests


API_URL = "https://pokeapi.co/api/v2/pokemon?limit=1000"


def get_json(url):
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def get_region(pokemon_id):
    if pokemon_id <= 151:
        return "I"
    elif pokemon_id <= 251:
        return "II"
    elif pokemon_id <= 386:
        return "III"
    elif pokemon_id <= 493:
        return "IV"
    elif pokemon_id <= 649:
        return "V"
    elif pokemon_id <= 721:
        return "VI"
    elif pokemon_id <= 809:
        return "VII"
    elif pokemon_id <= 905:
        return "VIII"
    else:
        return "IX"


def main():

    print("Fetching Pokémon list...")

    pokemon_list = get_json(API_URL)["results"]

    pokemon_data = {}

    for index, pokemon in enumerate(pokemon_list, start=1):

        print(f"[{index}/{len(pokemon_list)}] {pokemon['name']}")

        data = get_json(pokemon["url"])

        pokemon_id = data["id"]

        types = [
            item["type"]["name"]
            for item in sorted(
                data["types"],
                key=lambda x: x["slot"]
            )
        ]

        abilities = []
        hidden_ability = None

        for ability in data["abilities"]:

            name = ability["ability"]["name"]

            if ability["is_hidden"]:
                hidden_ability = name
            else:
                abilities.append(name)

        stats = {}

        stat_map = {
            "hp": "hp",
            "attack": "attack",
            "defense": "defense",
            "special-attack": "sp_attack",
            "special-defense": "sp_defense",
            "speed": "speed"
        }

        for stat in data["stats"]:

            key = stat_map[stat["stat"]["name"]]

            stats[key] = {
                "base": stat["base_stat"],
                "range": "",
                "bar": ""
            }

        pokemon_data[pokemon["name"]] = {
            "name": pokemon["name"].title(),
            "id": pokemon_id,
            "region": get_region(pokemon_id),
            "types": types,
            "rarity": "Unknown",
            "catch_rate": 0,
            "catch_percent": "0%",
            "abilities": abilities,
            "hidden_ability": hidden_ability or "None",
            "ev_yield": "",
            "stats": stats,
            "weakness": {
                "4X Weak To": [],
                "2X Weak To": [],
                "▪️Resist To": [],
                "▪️▪️ Double Resist": [],
                "🚫 No Effect": []
            },
            "evolutions": [],
            "alternate_forms": [],
            "file_id": "",
            "moves": []
        }

    with open(
        "pokemon_data.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            pokemon_data,
            file,
            ensure_ascii=False,
            indent=4
        )

    print()
    print("✅ Pokémon data generated successfully!")
    print(f"Total Pokémon: {len(pokemon_data)}")


if __name__ == "__main__":
    main()
