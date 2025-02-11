"""
stats_scraper.py

Scrape Six Nations stats from fantasy website.
Based on https://github.com/david-sykes/fantasy-rugby-streamlit.
"""

import json
import math
from typing import Any

import requests

# TOKEN is obtained by logging in on browser.
with open("TOKEN", encoding="utf-8") as f:
    TOKEN = f.read()

WEEK = 3
TIMEOUT = 5
HEADERS = {  # Some of these could possibly be omitted.
    "accept": "application/json",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
    "authorization": f"Token {TOKEN}",
    "cache-control": "no-cache",
    "content-length": "37",
    "content-type": "application/json",
    "origin": "https://fantasy.sixnationsrugby.com",
    "pragma": "no-cache",
    "referer": "https://fantasy.sixnationsrugby.com/",
    "sec-ch-ua": '"Not_A Brand";v="99", "Google Chrome";v="109", "Chromium";v="109"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36"
    ),
    "x-access-key": "600@14.05@",
}
STATS_URL = "https://fantasy.sixnationsrugby.com/v1/private/statsjoueur"
PLAYER_URL = "https://fantasy.sixnationsrugby.com/v1/private/searchjoueurs"
PARAMS = {"lg": "en"}
STAT_NAME_DICT = {
    "Man of the match": "man_of_the_match",
    "Penalty": "penalty",
    "Assists": "assist",
    "Kick 50-22": "50_22",
    "Tackles": "tackle",
    "Drop goal": "drop_goal",
    "Attacking scrum win": "scrum_win",
    "Try": "try",
    "Red cards ": "red_card",  # sic
    "Metres carried": "metres_carried",
    "Yellow cards": "yellow_card",
    "Conversion": "conversion",
    "Offloads": "offload",
    "Lineout steal": "lineout_steal",
    "Breakdown steal": "breakdown_steal",
    "Conceded penalty": "conceded_penalty",
    "Defenders beaten": "defenders_beaten",
}
POSITION_CODES = {
    6: "back-three",
    7: "centres",
    8: "fly-half",
    9: "scrum-half",
    10: "back-row",
    11: "second-row",
    12: "front-row",
    13: "hooker",
}


def get_data() -> None:
    """Get all data."""
    players_request_json = {
        "filters": {
            "nom": "",
            "club": "",
            "position": "",
            "budget_ok": False,
            "engage": "false",
            "partant": False,
            "dreamteam": False,
            "quota": "",
            "idj": f"{WEEK}",
            "pageIndex": 0,
            "loadSelect": 0,
            "searchonly": 1,
        }
    }
    # Run once to get number of players
    players_request_json["filters"]["pageSize"] = 1
    response = requests.post(
        PLAYER_URL,
        headers=HEADERS,
        json=players_request_json,
        params=PARAMS,
        timeout=TIMEOUT,
    )
    player_count = int(response.json()["total"])
    # Run again to get all results in one go.
    players_request_json["filters"]["pageSize"] = math.ceil(player_count / 10.0) * 10
    response = requests.post(
        PLAYER_URL,
        headers=HEADERS,
        json=players_request_json,
        params=PARAMS,
        timeout=TIMEOUT,
    )
    players_dict = response.json()
    with open("players.json", "w", encoding="utf-8") as fp:
        json.dump(obj=players_dict, fp=fp, indent=4)

    stats_dict: dict[int, Any] = {}
    for player in players_dict["joueurs"]:
        player_id = player["id"]
        stats_request_json = {
            "credentials": {"idj": f"{WEEK}", "idf": player_id, "detail": True}
        }
        response = requests.post(
            STATS_URL,
            json=stats_request_json,
            headers=HEADERS,
            params=PARAMS,
            timeout=TIMEOUT,
        )
        stats_dict[player_id] = response.json()

    with open("stats.json", "w", encoding="utf-8") as fp:
        json.dump(obj=stats_dict, fp=fp, indent=4)


get_data()
