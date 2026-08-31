"""Run the synthetic data loader."""

from argparse import ArgumentParser, ArgumentTypeError
from datetime import date

from app.db import SessionLocal
from app.synth.generator import generate
from app.synth.loader import load


def _parse_date(value: str) -> date:
    """Parse an ISO calendar date."""

    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ArgumentTypeError("end date must use ISO format") from error


def main() -> None:
    """Generate and load synthetic data."""

    parser = ArgumentParser(description="Generate and load synthetic data.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument("--days", type=int, default=90, help="Days to generate.")
    parser.add_argument(
        "--end-date",
        type=_parse_date,
        default=date.today(),
        help="Last generated date in ISO format (default: today).",
    )
    arguments = parser.parse_args()
    dataset = generate(
        seed=arguments.seed, days=arguments.days, end_date=arguments.end_date
    )
    with SessionLocal() as session:
        load(session, dataset)
        session.commit()
    print(
        f"users=4 finance={len(dataset.finance)} "
        f"environment={len(dataset.environment)} "
        f"health={len(dataset.health)}"
    )


if __name__ == "__main__":
    main()
