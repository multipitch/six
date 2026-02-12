"""
data_parser.py

Make sense of raw 6 nations JSON data.
"""

import json
from collections import Counter
from typing import Annotated, Any, TypedDict

from pydantic import BaseModel, BeforeValidator, Field, RootModel, field_validator

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
    "Kicks recovered": "kicks_recovered",
}

APPEARANCE_TYPES = {
    "R": "on_as_sub",
    "N": "did_not_play",
    "T": "started",
}

DEFAULT_PREV_APPEARANCES = ["did_not_play"] * (WEEK - 1)
# TODO: What do we do before first weekend?

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

CoercedStr = Annotated[str, BeforeValidator(str)]

# TODO: What do we do with players who did not play before?


class PlayerData(BaseModel):
    """Relevant raw data on a single player."""

    player_id: CoercedStr = Field(alias="id")  # coerce int to str
    name: str = Field(alias="nomcomplet")
    name_short: str = Field(alias="nom")
    country: str = Field(alias="trgclub")
    position: str = Field(alias="id_position")
    upcoming_appearance_type: str = Field(alias="formeprev", default="undefined")
    cost: float = Field(alias="valeur")
    prev_appearance_types: list[str] = Field(
        alias="forme", default=DEFAULT_PREV_APPEARANCES
    )
    stats: list[PlayerMatchStatsData]

    @field_validator("upcoming_appearance_type", mode="before")
    def _get_upcoming_appearance_type(cls, v: dict[str, str]) -> str:
        return APPEARANCE_TYPES[v["status"]]

    @field_validator("prev_appearance_types", mode="before")
    def _flatten_form(cls, v: dict[str, list[str]]) -> list[str]:
        return [APPEARANCE_TYPES[t] for t in v["items"]]

    @field_validator("position", mode="before")
    def _get_position(cls, v: int) -> str:
        return POSITION_CODES[v]

    @field_validator("stats", mode="before")
    def _get_stats(cls, v: dict[str, Any]) -> Any:
        return v["detail"]


class PlayersData(RootModel[dict[str, PlayerData]]):
    """Relevant raw data on players."""

    root: dict[str, PlayerData]


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


def main() -> int:
    """Parse raw stats to create a data file to use with main.py"""

    with open("data/raw_stats.json", encoding="utf-8") as fp:
        raw_stats = json.load(fp)

    players_data = PlayersData.model_validate_json(json.dumps(raw_stats)).root

    starters_by_team = Counter(
        p.country
        for p in players_data.values()
        if p.upcoming_appearance_type == "started"
    )

    for team in TEAMS:
        if starters_by_team[team] == 0:
            print(f"No team announced yet for {team}.")
        elif starters_by_team[team] != 15:
            msg = f"Some number of players other than 15 announced for {team}."
            raise ValueError(msg)

    data = {
        "budget": 200,
        "country_weights": {t: 1 for t in TEAMS},
        "players": {
            p_id: {
                "name": p.name_short,
                "country": p.country,
                "position": p.position,
                "cost": p.cost,
                "points": p.stats[-1].points,
                "upcoming_appearance_type": p.upcoming_appearance_type,
            }
            for p_id, p in players_data.items()
        },
    }
    with open("data/data.json", mode="w", encoding="utf-8") as fp:
        json.dump(data, fp=fp, indent=4)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
