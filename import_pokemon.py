import json
import requests
import time

def normalize_pokemon_name(name):
    return "".join(
        char for char in name.lower()
        if char.isalnum()
    )


API_BASE = "https://pokeapi.co/api/v2"


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


def stat_range(base):
    minimum = (2 * base) + 5
    maximum = (2 * base) + 31 + 94

    return f"{minimum}–{maximum}"


def stat_bar(base):
    if base >= 100:
        return "■■■■■"
    elif base >= 80:
        return "■■■■□"
    elif base >= 60:
        return "■■■□□"
    elif base >= 40:
        return "■■□□□"
    else:
        return "■□□□□"


def format_name(name):
    return name.replace("-", " ").title()


def get_move_method(details):
    methods = []

    for detail in details:
        method = detail.get("move_learn_method", {}).get("name")

        if method:
            methods.append(method)

    if not methods:
        return "Unknown"

    method = methods[0]

    if method == "level-up":
        return "Level Up"

    if method == "machine":
        return "Machine"

    if method == "egg":
        return "Egg"

    if method == "tutor":
        return "Tutor"

    return format_name(method)


def get_move_level(details):
    for detail in details:
        level = detail.get("level_learned_at")

        if level:
            return level

    return None


def get_ev_yield(pokemon):
    parts = []

    stat_names = {
        "hp": "HP",
        "attack": "Attack",
        "defense": "Defense",
        "special-attack": "Sp. Attack",
        "special-defense": "Sp. Defense",
        "speed": "Speed"
    }

    for stat in pokemon["stats"]:
        effort = stat["effort"]

        if effort > 0:
            name = stat_names.get(
                stat["stat"]["name"],
                stat["stat"]["name"]
            )

            parts.append(f"{name} +{effort}")

    if not parts:
        return "None"

    return ", ".join(parts)


def get_move_data(move_url):
    move = get_json(move_url)

    move_type = move.get("type", {}).get("name", "normal")

    category = (
        move.get("damage_class", {}).get("name")
        or "status"
    )

    return {
        "name": move["name"],
        "type": move_type,
        "method": None,
        "power": move.get("power"),
        "accuracy": move.get("accuracy"),
        "category": category
    }


def get_evolution_details(details):
    if not details:
        return "Unknown", None

    detail = details[0]

    trigger = detail.get("trigger", {}).get("name")

    if trigger == "level-up":
        method = "Level up"
    elif trigger:
        method = format_name(trigger)
    else:
        method = "Unknown"

    level = detail.get("min_level")

    item = detail.get("item")

    if item:
        method = f"Use {format_name(item['name'])}"

    if detail.get("known_move"):
        method = (
            f"Know {format_name(detail['known_move']['name'])}"
        )

    if detail.get("time_of_day"):
        method += f" ({detail['time_of_day']})"

    if detail.get("min_happiness") is not None:
        method = f"High friendship"

    if detail.get("min_beauty") is not None:
        method = f"Beauty"

    if detail.get("trade_species"):
        method = (
            f"Trade for "
            f"{format_name(detail['trade_species']['name'])}"
        )

    return method, level


def collect_evolution_chain(chain, result):

    from_name = chain["species"]["name"]

    for evolution in chain.get("evolves_to", []):

        to_name = evolution["species"]["name"]

        method, level = get_evolution_details(
            evolution.get("evolution_details", [])
        )

        result.append({
            "from": format_name(from_name),
            "to": format_name(to_name),
            "method": method,
            "level": level
        })

        collect_evolution_chain(
            evolution,
            result
        )


def get_evolutions(species_url):

    species = get_json(species_url)

    chain_url = species["evolution_chain"]["url"]

    chain_data = get_json(chain_url)

    result = []

    collect_evolution_chain(
        chain_data["chain"],
        result
    )

    return result


TYPE_CACHE = {}


def get_weakness(types):
    type_data = {}

    for type_name in types:
        url = f"{API_BASE}/type/{type_name}"
        type_data[type_name] = get_json(url)

    multipliers = {}

    attacking_types = [
        "normal",
        "fire",
        "water",
        "electric",
        "grass",
        "ice",
        "fighting",
        "poison",
        "ground",
        "flying",
        "psychic",
        "bug",
        "rock",
        "ghost",
        "dragon",
        "dark",
        "steel",
        "fairy"
    ]

    for attacking_type in attacking_types:
        multiplier = 1.0

        for defending_type in types:
            relations = type_data[
                defending_type
            ]["damage_relations"]

            no_effect = [
                item["name"]
                for item in relations["no_damage_from"]
            ]

            double_damage = [
                item["name"]
                for item in relations["double_damage_from"]
            ]

            half_damage = [
                item["name"]
                for item in relations["half_damage_from"]
            ]

            if attacking_type in no_effect:
                multiplier *= 0

            elif attacking_type in double_damage:
                multiplier *= 2

            elif attacking_type in half_damage:
                multiplier *= 0.5

        multipliers[attacking_type] = multiplier

    weakness = {
        "4X Weak To": [],
        "2X Weak To": [],
        "▪️Resist To": [],
        "▪️▪️ Double Resist": [],
        "🚫 No Effect": []
    }

    for type_name, multiplier in multipliers.items():

        if multiplier == 4:
            weakness["4X Weak To"].append(type_name)

        elif multiplier == 2:
            weakness["2X Weak To"].append(type_name)

        elif multiplier == 0.5:
            weakness["▪️Resist To"].append(type_name)

        elif multiplier == 0.25:
            weakness["▪️▪️ Double Resist"].append(type_name)

        elif multiplier == 0:
            weakness["🚫 No Effect"].append(type_name)

    return weakness


def get_moves(pokemon):
    moves = []

    for move_entry in pokemon["moves"]:
        move_data = get_move_data(
            move_entry["move"]["url"]
        )

        details = move_entry.get(
            "version_group_details",
            []
        )

        method = get_move_method(details)
        level = get_move_level(details)

        if method == "Level Up" and level is not None:
            method = f"Level {level}"

        move_data["method"] = method

        if move_data["power"] is None:
            move_data["power"] = "None"

        if move_data["accuracy"] is None:
            move_data["accuracy"] = "None"

        moves.append(move_data)

    return moves


def get_stats(pokemon):
    stats = {}

    stat_map = {
        "hp": "hp",
        "attack": "attack",
        "defense": "defense",
        "special-attack": "sp_attack",
        "special-defense": "sp_defense",
        "speed": "speed"
    }

    for stat in pokemon["stats"]:
        name = stat["stat"]["name"]

        if name not in stat_map:
            continue

        key = stat_map[name]
        base = stat["base_stat"]

        if key == "hp":
            minimum = (2 * base) + 110
            maximum = (2 * base) + 204
        else:
            minimum = (2 * base) + 5
            maximum = (2 * base) + 99

        stats[key] = {
            "base": base,
            "range": f"{minimum}–{maximum}",
            "bar": stat_bar(base)
        }

    return stats


def build_pokemon_data(name, existing_data=None, file_id=""):
    pokemon = get_json(
        f"{API_BASE}/pokemon/{name.lower()}"
    )

    species = get_json(
        pokemon["species"]["url"]
    )

    pokemon_id = pokemon["id"]

    types = [
        item["type"]["name"]
        for item in pokemon["types"]
    ]

    abilities = []

    hidden_ability = None

    for ability in pokemon["abilities"]:
        ability_name = format_name(
            ability["ability"]["name"]
        )

        if ability["is_hidden"]:
            hidden_ability = ability_name
        else:
            abilities.append(ability_name)

    capture_rate = species.get(
        "capture_rate",
        0
    )

    catch_percent = (
        f"{(capture_rate / 255) * 100:.3f}%"
    )

    entry = {
        "name": format_name(pokemon["name"]),
        "id": pokemon_id,
        "region": get_region(pokemon_id),
        "types": types,
        "rarity": "Unknown",
        "catch_rate": capture_rate,
        "catch_percent": catch_percent,
        "abilities": abilities,
        "hidden_ability": hidden_ability or "None",
        "ev_yield": get_ev_yield(pokemon),
        "stats": get_stats(pokemon),
        "weakness": get_weakness(types),
        "evolutions": get_evolutions(
            pokemon["species"]["url"]
        ),
        "alternate_forms": [],
        "file_id": "",
        "moves": get_moves(pokemon)
    }

    if existing_data:
        entry.update(existing_data)

    if file_id:
        entry["file_id"] = file_id
    
    return entry


def load_json(filename, default):
    try:
        with open(filename, "r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def get_file_ids():
    return load_json(
        "pokemon_file_ids.json",
        {}
    )


def save_json(filename, data):
    with open(
        filename,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            data,
            file,
            indent=4,
            ensure_ascii=False
        )


def main():
    selected = load_json(
        "selected_pokemon.json",
        []
    )

    existing = load_json(
        "/data/pokemon_data.json",
        {}
    )

    file_ids = get_file_ids()
    
    if not selected:
        print("No Pokémon selected.")
        return

    total = len(selected)

    print(
        f"Starting import of {total} Pokémon..."
    )

    for index, name in enumerate(
        selected,
        start=1
    ):
        key = normalize_pokemon_name(name)

        try:
            print(
                f"[{index}/{total}] "
                f"Importing {name}..."
            )

            entry = build_pokemon_data(
                name,
                existing.get(key),
                file_ids.get(key, "")
            )

            existing[key] = entry

            save_json(
                "/data/pokemon_data.json",
                existing
            )

            print(
                f"✓ {entry['name']} imported"
            )

            time.sleep(0.2)

        except Exception as error:
            print(
                f"✗ Failed: {name}"
            )
            print(
                f"  Error: {error}"
            )

    print(
        "\nImport completed."
    )

    print(
        f"Total Pokémon in database: "
        f"{len(existing)}"
    )


if __name__ == "__main__":
    main()
