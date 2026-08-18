"""Demonstração totalmente offline do Company Registry."""

from tempfile import TemporaryDirectory
from pathlib import Path

from .company_registry import CompanyRegistry, seed_ashby_wave1
from .repository import JobRepository


def main() -> None:
    with TemporaryDirectory() as directory:
        with JobRepository(Path(directory) / "company-registry-demo.db") as repository:
            repository.add_company("scaleops", "ScaleOps", "greenhouse", "scaleops")
            seed_ashby_wave1(repository)
            repository.add_company("fake-lever", "Fake Lever", "lever", "fake")
            repository.add_company("disabled", "Disabled Co", "greenhouse", "disabled")
            repository.disable_company("disabled")

            registry = CompanyRegistry(repository)
            definitions, snapshot = registry.source_definitions()
            print("Company Registry offline demo")
            for company in repository.list_companies():
                if not company.enabled:
                    state = "skipped (disabled)"
                elif company.ats_family not in {"greenhouse", "ashby"}:
                    state = "skipped (unsupported)"
                else:
                    source_id = (
                        company.company_key
                        if company.ats_family == "ashby"
                        else f"greenhouse:{company.company_key}"
                    )
                    state = f"generated {source_id}"
                print(
                    f"- {company.company_name} [{company.publisher_model}]: {state}"
                )
            print(
                f"Tracked: {snapshot.tracked} | Enabled: {snapshot.enabled} | "
                f"Generated: {len(definitions)} | "
                f"Unsupported: {len(snapshot.unsupported)}"
            )


if __name__ == "__main__":
    main()
