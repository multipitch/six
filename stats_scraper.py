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

TIMEOUT = 5
STATS_URL = "https://fantasy.sixnationsrugby.com/v1/private/statsjoueur"
PLAYER_URL = "https://fantasy.sixnationsrugby.com/v1/private/searchjoueurs"
PARAMS = {"lg": "en"}


def get_data(token: str, week: int) -> None:
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
            "idj": f"{week}",
            "pageIndex": 0,
            "loadSelect": 0,
            "searchonly": 1,
        }
    }
    headers = {  # Some of these could possibly be omitted.
        "accept": "application/json",
        "accept-encoding": "gzip, deflate, br",
        "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
        "authorization": f"Token {token}",
        "cache-control": "no-cache",
        "content-length": "37",
        "content-type": "application/json",
        "origin": "https://fantasy.sixnationsrugby.com",
        "pragma": "no-cache",
        "referer": "https://fantasy.sixnationsrugby.com/",
        "sec-ch-ua": (
            '"Not_A Brand";v="99", "Google Chrome";v="109", "Chromium";v="109"'
        ),
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

    # First request to PLAYER_URL is to get the number of players in the league.
    players_request_json["filters"]["pageSize"] = 1
    single_player_response = requests.post(
        PLAYER_URL,
        headers=headers,
        json=players_request_json,
        params=PARAMS,
        timeout=TIMEOUT,
    )
    player_count = int(single_player_response.json()["total"])

    # Second request to PLAYER_URL  is to get data for all players.
    players_request_json["filters"]["pageSize"] = math.ceil(player_count / 10.0) * 10
    all_players_response = requests.post(
        PLAYER_URL,
        headers=headers,
        json=players_request_json,
        params=PARAMS,
        timeout=TIMEOUT,
    )
    players_dict = all_players_response.json()
    with open("data/players.json", "w", encoding="utf-8") as fp:
        json.dump(obj=players_dict, fp=fp, indent=4)

    # For each player, request statistics from STATS_URL.
    stats_dict: dict[int, Any] = {}
    for player in players_dict["joueurs"]:
        player_id = player["id"]
        stats_request_json = {
            "credentials": {"idj": f"{week}", "idf": player_id, "detail": True}
        }
        stats_response = requests.post(
            STATS_URL,
            json=stats_request_json,
            headers=headers,
            params=PARAMS,
            timeout=TIMEOUT,
        )
        stats_dict[player_id] = stats_response.json()
    with open("data/stats.json", "w", encoding="utf-8") as fp:
        json.dump(obj=stats_dict, fp=fp, indent=4)


if __name__ == "__main__":
    # Get token by logging in with Firefox, going to developer settings
    # (Ctrl+Shift+I), and then going to Network and copying the token from a
    # request. Save it to data/TOKEN (just the code).
    with open("data/TOKEN", encoding="utf-8") as f:
        TOKEN = f.read().strip()
    WEEK = int(input("Enter Week to be Optimised: "))

    get_data(TOKEN, WEEK)
