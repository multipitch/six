"""
constants.py
"""

from enum import StrEnum


class Team(StrEnum):
    """Team names."""

    IRE = "Ireland"
    FRA = "France"
    ENG = "England"
    SCO = "Scotland"
    ITA = "Italy"
    WAL = "Wales"


class Selection(StrEnum):
    """Player selection category."""

    R = "substitute"
    T = "starter"
    N = "non-starter"
    U = "undefined"


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
