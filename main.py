"""
main.py

Creates optimal team based on budget, player cost and predicted player points.
Allows weighting of teams and forced selection of players.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Literal, Self

from pulp import LpBinary, LpMaximize, LpProblem, LpVariable
from pulp.apis import PULP_CBC_CMD
from pulp.constants import LpStatusOptimal
from pydantic import BaseModel

MAX_PLAYERS_FROM_ANY_COUNTRY = 4
SUPERSUB_MULTIPLIER = 3
STARTING_SUPERSUB_MULTIPLIER = 0.5
CAPTAIN_MULTIPLIER = 2
POSITIONS = {
    "prop": [1, 3],
    "hooker": [2],
    "second_row": [4, 5],
    "back_row": [6, 7, 8],
    "scrum_half": [9],
    "fly_half": [10],
    "centre": [12, 13],
    "back_three": [11, 14, 15],
}

# TODO: Decide whether unconfirmed players are not selectable
# TODO: Only pick from starters or unconfirmed for starters, captain
# TODO: Only pick from subs or unconfirmed for supersubs


class Dataset(BaseModel):
    """Dataset."""

    country_weights: dict[str, float]
    budget: float
    players: dict[str, Player]


class Player(BaseModel):
    """A player."""

    name: str
    country: str
    position: str
    points: float
    cost: float
    upcoming_appearance_type: Literal[
        "started", "on_as_sub", "did_not_play", "undefined"
    ]
    adjust: float | None = 0
    note: str | None = None


class Model:
    """A model."""

    def __init__(self, dataset: Dataset) -> None:
        self.dataset = dataset

        self.players = self.dataset.players
        self.players_by_country = defaultdict(list)
        self.players_by_position = defaultdict(list)
        self.predicted_player_points = {}
        for name, player in self.players.items():
            self.players_by_country[player.country].append(name)
            self.players_by_position[player.position].append(name)
            self.predicted_player_points[name] = (
                player.points + (player.adjust or 0)
            ) * self.dataset.country_weights[player.country]

        self.problem: LpProblem
        self.players_are_selected: dict[str, LpVariable]
        self.players_are_captain: dict[str, LpVariable]
        self.players_are_supersub: dict[str, LpVariable]
        self.team: dict[int, str]
        self.captain: str
        self.supersub: str | None
        self.score: float
        self.cost: float

        self.build()

    def build(self) -> None:
        """Build the problem."""

        self.problem = LpProblem(sense=LpMaximize)
        self.define_decision_variables()
        self.define_objective()
        self.constrain_budget()
        self.constrain_players_per_country()
        self.constrain_players_per_position()
        self.constrain_number_of_captains()
        self.constrain_number_of_supersubs()

    def define_decision_variables(self) -> None:
        """Define decision variables."""
        self.players_are_selected = {
            name: LpVariable(name=f"{name.replace(" ", "_")}_is_selected", cat=LpBinary)
            for name, p in self.players.items()
            if p.upcoming_appearance_type in ("started", "undefined")
        }
        self.players_are_captain = {
            name: LpVariable(name=f"{name.replace(" ", "_")}_is_captain", cat=LpBinary)
            for name, p in self.players.items()
            if p.upcoming_appearance_type in ("started", "undefined")
        }
        self.players_are_supersub = {
            name: LpVariable(name=f"{name.replace(" ", "_")}_is_supersub", cat=LpBinary)
            for name, p in self.players.items()
            if p.upcoming_appearance_type in ("on_as_sub", "undefined")
        }

    def constrain_select_player(self, name: str, select: bool = True) -> None:
        """Force selection of a player."""
        uat = self.players[name].upcoming_appearance_type
        if uat == "on_as_sub":
            print(
                f"You are trying to enforce selection of {name} as a starter "
                "but he is due to come on as a sub."
            )
        elif uat == "did_not_play":
            print(
                f"You are trying to enforce selection of {name} as a started "
                "but he is not due to play."
            )
        self.problem += self.players_are_selected[name] == int(select)

    def constrain_select_captain(self, name: str) -> None:
        """Force selection of captain."""
        for name_ in self.players:
            self.problem += self.players_are_captain[name_] == int(name_ == name)

    def constrain_select_supersub(self, name: str) -> None:
        """Force selection of supersub."""
        uat = self.players[name].upcoming_appearance_type
        if uat == "started":
            print(
                f"You are trying to enforce selection of {name} as a supersub "
                "but he is due to start."
            )
        for name_ in self.players:
            self.problem += self.players_are_supersub[name_] == int(name_ == name)

    # TODO: Constraints to force deselection

    def define_objective(self) -> None:
        """Define objective function; total points for selected team."""
        self.problem += (
            sum(
                self.predicted_player_points[name] * self.players_are_selected[name]
                for name in self.players
            )
            + sum(
                self.predicted_player_points[name] * self.players_are_captain[name]
                for name in self.players
            )
            * (CAPTAIN_MULTIPLIER - 1)  # already counted once in sum above
            + sum(
                self.predicted_player_points[name]
                * self.players_are_supersub[name]
                * (
                    SUPERSUB_MULTIPLIER
                    if self.players[name].upcoming_appearance_type != "started"
                    else STARTING_SUPERSUB_MULTIPLIER
                )
                for name in self.players
            )
        )

    def constrain_budget(self) -> None:
        """Ensure selection is within budget limit."""
        self.problem += self.dataset.budget >= sum(
            self.players[name].cost
            * (self.players_are_selected[name] + self.players_are_supersub[name])
            for name in self.players
        )

    def constrain_players_per_country(self) -> None:
        """Apply a limit on players per country (include supersub)."""
        for country in self.dataset.country_weights:
            self.problem += (
                sum(
                    (self.players_are_selected[name] + self.players_are_supersub[name])
                    for name in self.players_by_country[country]
                )
                <= MAX_PLAYERS_FROM_ANY_COUNTRY
            )

    def constrain_players_per_position(self) -> None:
        """Can't have too many players in any position."""
        for position, numbers in POSITIONS.items():
            self.problem += len(numbers) >= sum(
                self.players_are_selected[name]
                for name in self.players_by_position[position]
            )

    def constrain_number_of_captains(self) -> None:
        """Ensure there is exactly one captain."""
        # Zero captains is allowed, but can never be optimal.
        self.problem += sum(self.players_are_captain.values()) == 1

    def constrain_number_of_supersubs(self) -> None:
        """Ensure there is zero or one supersub"""
        self.problem += sum(self.players_are_supersub.values()) <= 1

    def solve(self) -> None:
        """Solve the problem."""
        self.problem.solve(PULP_CBC_CMD(msg=0))
        selected_players = {
            k: self.players[k].position
            for k, v in self.players_are_selected.items()
            if v
        }
        positions = POSITIONS.copy()
        self.team = {
            positions[self.players[name].position].pop(): name
            for name, position in selected_players.items()
        }
        self.captain = [k for k, v in self.players_are_captain.items() if v.value()][0]
        supersubs = [k for k, v in self.players_are_supersub.items() if v.value()]
        self.supersub = supersubs[0] if supersubs else None
        self.score = self.problem.objective.value()
        self.cost = sum(self.players[name].cost for name in selected_players) + (
            self.players[self.supersub].cost if self.supersub else 0
        )
        if self.problem.status != LpStatusOptimal:
            raise ValueError("Optimal solution not found.")

    def print(self) -> None:
        """Print the results of an optimized model."""
        if self.problem.status != LpStatusOptimal:
            print("Model has not been solved.")
            return
        print("Team optimised.")
        print("\nTeam Sheet:")
        for number, name in sorted(self.team.items()):
            player_str = f"{name or "---"}{" [C]" if name == self.captain else ""}"
            country_str = f" ({self.players[name].country})" if name else ""
            print(f"{number:>2}:  {player_str:<24}{country_str}")
        if self.supersub:
            ss_country = self.players[self.supersub].country
            print(f"\nSupersub:        {self.supersub} ({ss_country})")
        print(f"Expected score:  {self.score:.2f}")
        print(f"Budget:          {self.dataset.budget:.2f}")
        print(f"Team Cost:       {self.cost:.2f}")

    @classmethod
    def from_json(cls, file: str | Path) -> Self:
        """Build a class from JSON data."""
        with open(file, encoding="utf-8") as f:
            data = f.read()
        dataset = Dataset.model_validate_json(data)
        return cls(dataset)


if __name__ == "__main__":

    # TODO: Have some parameter on selecting players of unknown status
    #       - all players from unannounced teams are currently avaialable
    #         as both supersubs and starting players.
    model = Model.from_json("data/data.json")
    # model.constrain_select_player("J. Lowe")
    # model.constrain_select_captain("J. Lowe")
    model.constrain_select_supersub("N. Timoney")
    model.solve()
    model.print()
