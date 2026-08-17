"""Demonstração totalmente offline do Company Registry."""

from tempfile import TemporaryDirectory
from pathlib import Path

from .company_registry import CompanyRegistry
from .repository import JobRepository


def main() -> None:
    with TemporaryDirectory() as directory:
        with JobRepository(Path(directory) / "company-registry-demo.db") as repository:
            repository.add_company("scaleops", "ScaleOps", "greenhouse", "scaleops")
            repository.add_company("future-ashby", "Future Ashby", "ashby", "future")
            repository.add_company("disabled", "Disabled Co", "greenhouse", "disabled")
            repository.disable_company("disabled")

            registry = CompanyRegistry(repository)
            definitions, snapshot = registry.source_definitions()
            print("Company Registry offline demo")
            for company in repository.list_companies():
                if not company.enabled:
                    state = "skipped (disabled)"
                elif company.ats_family != "greenhouse":
                    state = "skipped (unsupported)"
                else:
                    state = f"generated {company.ats_family}:{company.company_key}"
                print(f"- {company.company_name}: {state}")
            print(
                f"Tracked: {snapshot.tracked} | Enabled: {snapshot.enabled} | "
                f"Generated: {len(definitions)} | "
                f"Unsupported: {len(snapshot.unsupported)}"
            )


if __name__ == "__main__":
    main()
