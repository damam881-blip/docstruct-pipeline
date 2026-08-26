from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Install the three files required by an EasyOCR custom recognition "
            "network into this project's configured model directories."
        )
    )
    parser.add_argument("--name", required=True, help="Custom recog_network name")
    parser.add_argument("--weights", required=True, help="Trained .pth file")
    parser.add_argument("--network-yaml", required=True, help="Network .yaml file")
    parser.add_argument("--network-py", required=True, help="Network .py file")
    parser.add_argument("--model-dir", default="models/easyocr/model")
    parser.add_argument("--user-network-dir", default="models/easyocr/user_network")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    name = args.name.strip()
    if not name:
        raise SystemExit("--name cannot be empty")

    sources = {
        ".pth": Path(args.weights),
        ".yaml": Path(args.network_yaml),
        ".py": Path(args.network_py),
    }
    for suffix, source in sources.items():
        if not source.exists():
            raise FileNotFoundError(source)
        if source.suffix.lower() != suffix:
            raise ValueError(f"Expected a {suffix} file, got: {source}")

    model_dir = Path(args.model_dir)
    user_dir = Path(args.user_network_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    user_dir.mkdir(parents=True, exist_ok=True)

    installed = []
    for suffix, source in sources.items():
        destination = (model_dir if suffix == ".pth" else user_dir) / f"{name}{suffix}"
        shutil.copy2(source, destination)
        installed.append(str(destination.resolve()))

    print({"recog_network": name, "installed": installed})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
