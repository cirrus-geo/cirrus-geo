#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

from collections.abc import Callable, Sequence
from enum import StrEnum
from pathlib import Path

SYSTEM_TARGET = "manylinux2014"
PROJECT_DIR = Path(__file__).parent.parent

# Add packages we don't need in the zip to slim it down
PACKAGE_EXCLUDES = ("pip",)


# Patches to apply to specific files in the zip
PATCHES: dict[str, Callable[[Path], bytes]] = {
    "stactask/__init__.py": lambda x: b"",
}


class Architecture(StrEnum):
    AARCH64 = "aarch64"
    X86_64 = "x86_64"
    ARM64 = "arm64"

    def target_platform(self) -> str:
        val = Architecture.AARCH64 if self == Architecture.ARM64 else self
        return f"{val.value}-{SYSTEM_TARGET}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build lambda zip for Cirrus functions",
    )
    parser.add_argument(
        "-a",
        "--cpu-arch",
        type=Architecture,
        choices=list(Architecture),
        help="CPU architecture build target",
        required=True,
    )
    parser.add_argument(
        "-p",
        "--python-version",
        help="Python version build target, e.g., 3.13",
        required=True,
    )
    parser.add_argument(
        "-o",
        "--output-zip",
        type=Path,
        help="Output zip file path",
        required=True,
    )
    parser.add_argument(
        "--project",
        type=Path,
        help="Path to project directory containing uv.lock",
        default=PROJECT_DIR,
    )
    return parser


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def setup_venv(
    venv_path: Path,
    python_version: str,
    platform: str,
    project_dir: Path,
) -> None:
    """Set up virtual environment and install dependencies."""
    cmd = [
        "uv",
        "venv",
        "--python",
        python_version,
        str(venv_path),
    ]

    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    cmd = [
        "uv",
        "sync",
        "--python-platform",
        platform,
        "--locked",
        "--no-dev",
        "--project",
        str(project_dir),
        "--no-editable",
        "--active",
        "--no-cache",
    ]

    print(f"Running: {' '.join(cmd)}")
    env = dict(os.environ)
    env["VIRTUAL_ENV"] = str(venv_path)
    subprocess.run(cmd, check=True, env=env)


def get_site_packages_path(venv_path: Path) -> Path:
    """Get the site-packages directory from the virtual environment."""
    python_exe = venv_path / "bin" / "python"
    result = subprocess.run(
        [str(python_exe), "-c", "import sysconfig as s; print(s.get_path('purelib'))"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip())


def create_base_zip(site_packages: Path, zip_path: Path) -> None:
    """Create base zip file from site-packages directory."""
    print(f"Creating zip from {site_packages}")
    packages = set()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in site_packages.rglob("*"):
            if not file_path.is_file():
                continue

            arcname = file_path.relative_to(site_packages)
            package_name = arcname.parts[0]

            if arcname.parts[0] in PACKAGE_EXCLUDES:
                if package_name not in packages:
                    packages.add(package_name)
                    print(f"Skipping excluded package: {package_name}")
                continue

            if package_name not in packages:
                packages.add(package_name)
                print(f"Copying package to zip: {package_name}")

            name = str(arcname)
            if name in PATCHES:
                print(f"Patching file {arcname}")
                info = zipfile.ZipInfo.from_file(file_path, arcname)
                zf.writestr(info, PATCHES[name](file_path))
                continue

            zf.write(file_path, arcname)


def get_lambda_handlers(venv_path: Path) -> list[Path]:
    """Discover lambda handler files from the cirrus package."""
    python_exe = venv_path / "bin" / "python"
    script = """
from pathlib import Path
from cirrus import lambda_functions

reader = lambda_functions.__loader__.get_resource_reader()

for path in map(lambda x: reader.path / Path(x), reader.contents()):
    if path.suffix not in ('.py', '.pyc'):
        continue
    if path.stem == '__init__':
        continue
    print(path)
"""
    print("Discovering lambda handlers")

    env = dict(os.environ)
    env["VIRTUAL_ENV"] = str(venv_path)

    result = subprocess.run(
        [str(python_exe), "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    if result.returncode != 0:
        print("Lambda handler discovery failed!", file=sys.stderr)
        sys.exit(1)

    handlers = [
        Path(line.strip()) for line in result.stdout.strip().split("\n") if line.strip()
    ]

    print(f"Found {len(handlers)} lambda handlers")
    return handlers


def add_handlers_to_zip(zip_path: Path, handlers: list[Path]) -> None:
    """Add lambda handler files to the zip."""
    with zipfile.ZipFile(zip_path, "a") as zf:
        for handler_path in handlers:
            print(f"Adding handler: {handler_path.name}")
            zf.write(handler_path, handler_path.name)


def build_lambda_zip(
    cpu_arch: Architecture,
    python_version: str,
    output_zip: Path,
    project_dir: Path,
) -> None:
    """Build a lambda deployment zip for the specified configuration."""
    platform = cpu_arch.target_platform()

    print(f"Building for Python {python_version} on {cpu_arch}")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        venv_path = temp / "venv"
        temp_zip = temp / "temp.zip"

        setup_venv(
            venv_path,
            python_version,
            platform,
            project_dir,
        )
        site_packages = get_site_packages_path(venv_path)
        create_base_zip(site_packages, temp_zip)
        handlers = get_lambda_handlers(venv_path)
        add_handlers_to_zip(temp_zip, handlers)
        shutil.move(temp_zip, output_zip)

        print(f"Created {output_zip}")


def main(argv: Sequence[str]) -> None:
    args = parse_args(argv)

    build_lambda_zip(
        args.cpu_arch,
        args.python_version,
        args.output_zip,
        args.project,
    )


if __name__ == "__main__":
    main(sys.argv[1:])
