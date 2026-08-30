"""Explicitly prepare the official non-commercial MeTRAbs SavedModel."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import tensorflow as tf
import tensorflow_hub as hub


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default="https://bit.ly/metrabs_s",
        help="Official MeTRAbs small SavedModel URL",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    output = args.output.resolve()
    if (output / "saved_model.pb").is_file():
        print("MeTRAbs SavedModel is already prepared")
        return

    temporary = output.with_name(f"{output.name}.partial")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.parent.mkdir(parents=True, exist_ok=True)

    model = hub.load(args.url)
    tf.saved_model.save(model, str(temporary))
    if output.exists():
        shutil.rmtree(output)
    temporary.replace(output)
    print("MeTRAbs SavedModel prepared successfully")


if __name__ == "__main__":
    main()
