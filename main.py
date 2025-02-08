"""
main.py

Creates optimal team based on points and costs.
Does not consider substitute players - the user needs to explicitly select a
supersub, if required.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Self

from pulp import LpBinary, LpMaximize, LpProblem, LpVariable
from pulp.apis import PULP_CBC_CMD
from pulp.constants import LpStatusOptimal
from pydantic import BaseModel

MAX_PLAYERS_FROM_ANY_COUNTRY = 4
SUPERSUB_MULTIPLIER = 3
CAPTAIN_MULTIPLIER = 2
# JERSEY_POSITIONS = {
#     1: "Prop",
#     2: "Hooker",
#     3: "Prop",
#     4: "Second-Row",
#     5: "Second-Row",
#     6: "Back-Row",
#     7: "Back-Row",
#     8: "Back-Row",
#     9: "Scrum-Half",
#     10: "Fly-Half",
#     11: "Back Three",
#     12: "Centre",
#     13: "Centre",
#     14: "Back Three",
#     15: "Back Three",
# }
POSITIONS = {
    "Prop": [1, 3],
    "Hooker": [2],
    "Second-Row": [4, 5],
    "Back-Row": [6, 7, 8],
    "Scrum-Half": [9],
    "Fly-Half": [10],
    "Centre": [12, 13],
    "Back Three": [11, 14, 15],
}


class Dataset(BaseModel):
    """Dataset."""

    country_weights: dict[str, float]
    budget: float
    supersub: SuperSub | None = None
    starting_players: dict[str, Player]


class Player(BaseModel):
    """A player."""

    country: str
    position: str
    points: float
    cost: float
    adjust: float | None = 0
    note: str | None = None


class SuperSub(Player):
    """A supersub."""

    # Players are in a dict, keyed by player name.
    # Since a supersub is not in such a dict, need to include its name
    # within the SuperSub class.

    name: str


class Model:
    """A model."""

    def __init__(self, dataset: Dataset) -> None:
        self.dataset = dataset

        self.players = self.dataset.starting_players
        self.players_by_country = defaultdict(list)
        self.players_by_position = defaultdict(list)
        self.predicted_player_points = {}
        for name, player in self.players.items():
            self.players_by_country[player.country].append(name)
            self.players_by_position[player.position].append(name)
            self.predicted_player_points[name] = (
                player.points + (player.adjust or 0)
            ) * self.dataset.country_weights[player.country]

        if self.dataset.supersub is None:
            self.supersub_cost: float = 0.0
            self.supersub_country: str | None = None
            self.supersub_points: float = 0.0
            self.supersub_adjust: float | None = 0.0
            self.supersub_name: str | None = None
            self.predicted_supersub_points: float = 0.0
        else:
            self.supersub_cost = self.dataset.supersub.cost
            self.supersub_country = self.dataset.supersub.country
            self.supersub_points = self.dataset.supersub.points
            self.supersub_adjust = self.dataset.supersub.adjust
            self.supersub_name = self.dataset.supersub.name
            self.predicted_supersub_points = (
                self.supersub_points + (self.supersub_adjust or 0)
            ) * self.dataset.country_weights[self.supersub_country]

        self.problem: LpProblem
        self.players_are_selected: dict[str, LpVariable]
        self.players_are_captain: dict[str, LpVariable]
        self.team: dict[int, str]
        self.captain: str
        self.score: float
        self.cost: float

        self.build()
        self.solve()
        self.print()

    def build(self) -> None:
        """Build the problem."""

        self.problem = LpProblem(sense=LpMaximize)
        self.define_decision_variables()
        self.define_objective()
        self.constrain_budget()
        self.constrain_players_per_country()
        self.constrain_players_per_position()
        self.constrain_number_of_captains()

    def define_decision_variables(self) -> None:
        """Define decision variables."""
        self.players_are_selected = {
            name: LpVariable(name=f"{name} is selected", cat=LpBinary)
            for name in self.players
        }
        self.players_are_captain = {
            name: LpVariable(name=f"{name} is captain", cat=LpBinary)
            for name in self.players
        }

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
            * (CAPTAIN_MULTIPLIER - 1)
            + self.predicted_supersub_points * SUPERSUB_MULTIPLIER
        )

    def constrain_budget(self) -> None:
        """Ensure selection is within budget limit."""
        self.problem += self.dataset.budget - self.supersub_cost >= sum(
            self.players[name].cost * self.players_are_selected[name]
            for name in self.players
        )

    def constrain_players_per_country(self) -> None:
        """Apply a limit on players per country (include supersub)."""
        for country in self.dataset.country_weights:
            self.problem += sum(
                self.players_are_selected[name]
                for name in self.players_by_country[country]
            ) <= MAX_PLAYERS_FROM_ANY_COUNTRY - (self.supersub_country == country)

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
        self.score = self.problem.objective.value()
        self.cost = self.supersub_cost + sum(
            self.players[name].cost for name in selected_players
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
        if self.supersub_name:
            print(f"\nSupersub:        {self.supersub_name} ({self.supersub_country})")
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
    model = Model.from_json("data.json")
