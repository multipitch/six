"""
data_parser.py

Make sense of raw 6 nations JSON data.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, TypedDict

import pandas as pd
from pydantic import BaseModel, Field, RootModel, field_validator

# TODO: This code seems pretty repetitive - i.e. creating Pydantic
#       objects to then create other classes that are quite similar.
#       Need to figure out what the end goal is - perhaps a
#       big dataframe or CSV file, rather than an OOP approach.
#       - Consider more concise code at
#         https://github.com/david-sykes/fantasy-rugby-streamlit.
#         and have a think of what can be gleaned from that approach
#       - A table with each row being a player would have a large and
#         variable number of columns with weekly stats expanding it.
#       - A table with each row being a player on a week, there would be
#         fewer columns, but more rows, but this might not map as well
#         onto the task of predicting player scores

# Update this every week.
WEEK = int(input("Week: "))

STAT_NAMES = {
    "Man of the match": "man_of_the_match",
    "Penalty": "penalty",
    "Assists": "assist",
    "Kick 50-22": "fifty_twenty_two",
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

APPEARANCE_TYPES = {
    "R": "on_as_sub",
    "N": "did_not_play",
    "T": "started",
}

DEFAULT_PREV_APPEARANCES = ["did_not_play"] * (WEEK - 1)

POSITION_CODES = {
    6: "back_three",
    7: "centre",
    8: "fly_half",
    9: "scrum_half",
    10: "back_row",
    11: "second_row",
    12: "prop",
    13: "hooker",
}

TEAMS = ["IRE", "ENG", "FRA", "SCO", "ITA", "WAL"]


# TODO: Flatten this as it's an unnecessary layer
class PlayersData(BaseModel):
    """Relevant raw data on players."""

    players: dict[int, PlayerData] = Field(alias="joueurs")
    total: int

    @field_validator("players", mode="before")
    def _get_players(cls, v: list[PlayerData]) -> dict[str, PlayerData]:
        return {d["id"]: d for d in v}  # type: ignore


class PlayerData(BaseModel):
    """Relevant raw data on a single player."""

    player_id: int = Field(alias="id")
    name: str = Field(alias="nomcomplet")
    name_short: str = Field(alias="nom")
    country: str = Field(alias="trgclub")
    position: str = Field(alias="id_position")
    upcoming_appearance_type: str = Field(alias="formeprev", default="undefined")
    cost: float = Field(alias="valeur")
    prev_appearance_types: list[str] = Field(
        alias="forme", default=DEFAULT_PREV_APPEARANCES
    )
    # TODO: Not working where player hasn't previously appeared.

    @field_validator("upcoming_appearance_type", mode="before")
    def _get_upcoming_appearance_type(cls, v: dict[str, str]) -> str:
        return APPEARANCE_TYPES[v["status"]]

    @field_validator("prev_appearance_types", mode="before")
    def _flatten_form(cls, v: dict[str, list[str]]) -> list[str]:
        return [APPEARANCE_TYPES[t] for t in v["items"]]

    @field_validator("position", mode="before")
    def _get_position(cls, v: int) -> str:
        return POSITION_CODES[v]


class PlayerStatsData(BaseModel):
    """Relevant raw statistics on a single player."""

    player_id: int = Field(alias="idf")
    match_stats: list[PlayerMatchStatsData] = Field(alias="detail")


StatDict = TypedDict("StatDict", {"libelle": str, "total": int})


class PlayerMatchStatsData(BaseModel):
    """Stats for a single player in a single match."""

    match_no: int = Field(alias="numero")
    score: tuple[int, int]
    played: bool = Field(alias="joue")
    stats: dict[str, int]
    away: bool = Field(alias="club")
    opposition: str = Field(alias="adversaire")
    minutes_played: int = Field(alias="minutes", default=0)
    cost_before: float = Field(alias="valeuravant", default=0)
    cost_after: float = Field(alias="valeurapres", default=0)
    points: float = 0

    @field_validator("score", mode="before")
    def _get_score(cls, v: str) -> tuple[int, int]:
        scores = v.split("-", maxsplit=2)
        return int(scores[0]), int(scores[1])

    @field_validator("away", mode="before")
    def _get_away_staus(cls, v: dict[str, bool]) -> bool:
        return not v["domicile"]

    @field_validator("opposition", mode="before")
    def _get_opposition(cls, v: dict[str, str]) -> str:
        return v["trg"]

    @field_validator("stats", mode="before")
    def _get_stats(cls, v: list[StatDict]) -> dict[str, int]:
        return {STAT_NAMES[stat_dict["libelle"]]: stat_dict["total"] for stat_dict in v}


class PlayersStatsData(RootModel[dict[int, PlayerStatsData]]):
    """Relevant raw statsitics for all players."""

    def __getitem__(self, key: int) -> PlayerStatsData:
        return self.root[key]


class Player:
    """A player."""

    def __init__(self, data: PlayerData, stats: PlayerStatsData) -> None:
        self.player_id = data.player_id
        self.name = data.name
        self.name_short = data.name_short
        self.country = data.country
        self.position = data.position
        self.upcoming_appearance_type = data.upcoming_appearance_type
        self.cost = data.cost
        self.match_stats: dict[int, PlayerMatchStats] = {}

        self.get_match_stats(data, stats)

    def get_match_stats(self, data: PlayerData, stats: PlayerStatsData) -> None:
        """Get stats for all matches."""
        if len(data.prev_appearance_types) != len(stats.match_stats):
            print(f"Prev stats error: {self.name}")
        else:
            for i, player_match_stats_data in enumerate(stats.match_stats):
                self.match_stats[i] = PlayerMatchStats(
                    data.prev_appearance_types[i], player_match_stats_data
                )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for entry into a dataframe."""
        dict_: dict[str, Any] = {}
        dict_["player_id"] = self.player_id
        dict_["name"] = self.name
        dict_["name_short"] = self.name_short
        dict_["country"] = self.country
        dict_["position"] = self.position
        dict_["upcoming_appearance_type"] = self.upcoming_appearance_type
        dict_["cost"] = self.cost
        for match_no, stats in self.match_stats.items():
            for stat_name, stat_value in stats.__dict__.items():
                dict_[f"{stat_name}_{match_no}"] = stat_value
        return dict_


class PlayerMatchStats:
    """Statistics for a single match for a player."""

    def __init__(self, appearance_type: str, data: PlayerMatchStatsData) -> None:
        self.appearance_type = appearance_type
        self.away = data.away
        self.team_score = data.score[int(self.away)]
        self.opposition = data.opposition
        self.opposition_score = data.score[int(not self.away)]
        self.played = data.played
        self.minutes_played = data.minutes_played
        self.cost_before = data.cost_before
        self.cost_after = data.cost_after
        self.points = data.points
        self.man_of_the_match = data.stats["man_of_the_match"]
        self.penalty = data.stats["penalty"]
        self.assist = data.stats["assist"]
        self.fifty_twenty_two = data.stats["fifty_twenty_two"]
        self.tackle = data.stats["tackle"]
        self.drop_goal = data.stats["drop_goal"]
        self.scrum_win = data.stats.get("scrum_win", 0)
        self.try_ = data.stats["try"]
        self.red_card = data.stats["red_card"]
        self.metres_carried = data.stats["metres_carried"]
        self.yellow_card = data.stats["yellow_card"]
        self.conversion = data.stats["conversion"]
        self.offload = data.stats["offload"]
        self.lineout_steal = data.stats["lineout_steal"]
        self.breakdown_steal = data.stats["breakdown_steal"]
        self.conceded_penalty = data.stats["conceded_penalty"]
        self.defenders_beaten = data.stats["defenders_beaten"]


if __name__ == "__main__":
    import json

    with open("data/players.json", encoding="utf-8") as fp:
        players_json = json.load(fp)

    with open("data/stats.json", encoding="utf-8") as fp:
        stats_json = json.load(fp)

    PLAYERS_DATA = PlayersData.model_validate_json(json.dumps(players_json))
    STATS_DATA = PlayersStatsData.model_validate_json(json.dumps(stats_json))

    with open("data/players_clean.json", mode="w", encoding="utf-8") as fp:
        fp.write(PLAYERS_DATA.model_dump_json(indent=4))
    with open("data/stats_clean.json", mode="w", encoding="utf-8") as fp:
        fp.write(STATS_DATA.model_dump_json(indent=4))

    PLAYERS = {k: Player(v, STATS_DATA[k]) for k, v in PLAYERS_DATA.players.items()}

    STARTERS_BY_TEAM: dict[str, int] = defaultdict(int)
    for p in PLAYERS.values():
        if p.upcoming_appearance_type == "started":
            STARTERS_BY_TEAM[p.country] += 1

    for team in TEAMS:
        if STARTERS_BY_TEAM[team] == 0:
            print(f"No team announced yet for {team}.")
        elif STARTERS_BY_TEAM[team] != 15:
            MSG = f"Some number of players other than 15 announced for {team}."
            raise ValueError(MSG)

    PLAYERS_DF = pd.DataFrame([p.to_dict() for p in PLAYERS.values()])
    PLAYERS_DF.to_csv("data/data.csv")
