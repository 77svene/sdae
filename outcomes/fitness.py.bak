"""
FitnessTracker — the only metric that matters.
fitness = revenue / compute_hours × (1 + deploy_success_rate × 2)
This is the signal. Everything else is noise.
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from loguru import logger
from memory.cold import COLD


@dataclass
class FitnessMetrics:
    total_projects: int = 0
    successful_builds: int = 0
    successful_deploys: int = 0
    total_revenue: float = 0.0
    total_compute_hours: float = 0.0
    fitness_score: float = 0.0
    build_success_rate: float = 0.0
    deploy_success_rate: float = 0.0

    def summary(self) -> str:
        return (
            f"Projects: {self.total_projects} | "
            f"Builds: {self.successful_builds}/{self.total_projects} | "
            f"Deploys: {self.successful_deploys}/{self.total_projects} | "
            f"Revenue: ${self.total_revenue:.2f} | "
            f"Fitness: {self.fitness_score:.4f}"
        )


class FitnessTracker:
    def record_build(
        self,
        project_name: str,
        goal: str,
        build_success: bool,
        deploy_success: bool,
        compute_hours: float,
        revenue: float = 0.0,
        deploy_url: str = "",
    ):
        COLD.record_outcome(
            project_name=project_name,
            goal=goal,
            success=build_success and deploy_success,
            revenue=revenue,
            compute_hours=compute_hours,
            deploy_url=deploy_url,
        )
        logger.info(
            f"Recorded: {project_name} | build={'OK' if build_success else 'FAIL'} | "
            f"deploy={'OK' if deploy_success else 'FAIL'} | "
            f"revenue=${revenue:.2f} | compute={compute_hours:.3f}h"
        )

    def get_metrics(self) -> FitnessMetrics:
        outcomes = COLD.get_outcomes(limit=1000)
        if not outcomes:
            return FitnessMetrics()

        total = len(outcomes)
        wins = sum(1 for o in outcomes if o["success"])
        rev = sum(o["revenue"] or 0 for o in outcomes)
        compute = sum(o["compute_hours"] or 0 for o in outcomes)

        # Count deploys (those with a deploy_url)
        deploys = sum(1 for o in outcomes if o.get("deploy_url"))

        build_rate = wins / total if total else 0
        deploy_rate = deploys / total if total else 0

        # Core fitness formula
        if compute > 0:
            fitness = (rev / compute) * (1 + deploy_rate * 2)
        else:
            fitness = 0.0

        return FitnessMetrics(
            total_projects=total,
            successful_builds=wins,
            successful_deploys=deploys,
            total_revenue=rev,
            total_compute_hours=compute,
            fitness_score=fitness,
            build_success_rate=build_rate,
            deploy_success_rate=deploy_rate,
        )

    def print_dashboard(self):
        m = self.get_metrics()
        from rich.console import Console
        from rich.table import Table
        console = Console()
        table = Table(title="SDAE Fitness Dashboard")
        table.add_column("Metric")
        table.add_column("Value")
        table.add_row("Total Projects", str(m.total_projects))
        table.add_row("Build Success Rate", f"{m.build_success_rate:.1%}")
        table.add_row("Deploy Success Rate", f"{m.deploy_success_rate:.1%}")
        table.add_row("Total Revenue", f"${m.total_revenue:.2f}")
        table.add_row("Compute Hours", f"{m.total_compute_hours:.2f}h")
        table.add_row("Fitness Score", f"{m.fitness_score:.4f}")
        console.print(table)


FITNESS = FitnessTracker()
