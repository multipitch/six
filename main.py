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
JERSEY_POSITIONS = {
    1: "Prop",
    2: "Hooker",
    3: "Prop",
    4: "Second-Row",
    5: "Second-Row",
    6: "Back-Row",
    7: "Back-Row",
    8: "Back-Row",
    9: "Scrum-Half",
    10: "Fly-Half",
    11: "Back Three",
    12: "Centre",
    13: "Centre",
    14: "Back Three",
    15: "Back Three",
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

        self.players_by_country = defaultdict(list)
        self.predicted_player_points = {}
        for player_name, player in self.dataset.starting_players.items():
            self.players_by_country[player.country].append(player_name)
            self.predicted_player_points[player_name] = (
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
        self.players_in_jerseys: dict[tuple[str, int], LpVariable]
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
        self.constrain_jerseys_per_player()
        self.constrain_jerseys_per_country()
        self.constrain_number_of_captains()
        self.constrain_players_per_jersey()

    def define_decision_variables(self) -> None:
        """Define decision variables."""
        self.players_in_jerseys = {
            (player_name, jersey): (
                LpVariable(name=f"{player_name} wears number {jersey}", cat=LpBinary)
                if player.position == position
                else 0
            )
            for player_name, player in self.dataset.starting_players.items()
            for jersey, position in JERSEY_POSITIONS.items()
        }
        self.players_are_captain = {
            player_name: LpVariable(name=f"{player_name} is captain", cat=LpBinary)
            for player_name in self.dataset.starting_players
        }

    def define_objective(self) -> None:
        """Define objective function; total points for selected team."""
        self.problem += (
            self.predicted_supersub_points * SUPERSUB_MULTIPLIER
            + sum(
                self.predicted_player_points[player_name]
                * self.players_in_jerseys[player_name, jersey]
                for player_name in self.dataset.starting_players
                for jersey in JERSEY_POSITIONS
            )
            + sum(
                self.predicted_player_points[player_name]
                * self.players_are_captain[player_name]
                for player_name in self.dataset.starting_players
            )
            * (CAPTAIN_MULTIPLIER - 1)
        )

    def constrain_budget(self) -> None:
        """Ensure selection is within budget limit."""
        self.problem += self.dataset.budget - self.supersub_cost >= sum(
            self.dataset.starting_players[player_name].cost
            * self.players_in_jerseys[player_name, jersey]
            for player_name in self.dataset.starting_players
            for jersey in JERSEY_POSITIONS
        )

    def constrain_jerseys_per_player(self) -> None:
        """Ensure every player wears at most one jersey."""
        for player_name in self.dataset.starting_players:
            self.problem += 1 >= sum(
                self.players_in_jerseys[player_name, jersey]
                for jersey in JERSEY_POSITIONS
            )

    def constrain_jerseys_per_country(self) -> None:
        """Apply a limit on jerseys per team (include supersub)."""
        for country in self.dataset.country_weights:
            self.problem += sum(
                self.players_in_jerseys[player_name, jersey]
                for jersey in JERSEY_POSITIONS
                for player_name in self.players_by_country[country]
            ) <= MAX_PLAYERS_FROM_ANY_COUNTRY - (self.supersub_country == country)

    def constrain_number_of_captains(self) -> None:
        """Ensure there is exactly one captain."""
        # Zero captains is allowed, but can never be optimal.
        self.problem += sum(self.players_are_captain.values()) == 1

    def constrain_players_per_jersey(self) -> None:
        """Ensure each jersey is assigned to at most one player."""
        for jersey in JERSEY_POSITIONS:
            self.problem += 1 >= sum(
                self.players_in_jerseys[player_name, jersey]
                for player_name in self.dataset.starting_players
            )

    def solve(self) -> None:
        """Solve the problem."""
        self.problem.solve(PULP_CBC_CMD(msg=0))
        self.team = {
            jersey: player_name
            for (player_name, jersey), v in self.players_in_jerseys.items()
            if isinstance(v, LpVariable) and v.value()
        }
        self.captain = [k for k, v in self.players_are_captain.items() if v.value()][0]
        self.score = self.problem.objective.value()
        self.cost = self.supersub_cost + sum(
            self.dataset.starting_players[player_name].cost
            for player_name in self.team.values()
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
        for jersey in JERSEY_POSITIONS:
            name = self.team.get(jersey)
            player_str = f"{name or "---"}{" [C]" if name == self.captain else ""}"
            country_str = (
                f" ({self.dataset.starting_players[name].country})" if name else ""
            )
            print(f"{jersey:>2}:  {player_str:<24}{country_str}")
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
