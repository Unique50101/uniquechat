"""Local chat with Hugging Face models."""
import argparse


def launch(model=None, *, offline=False, inbrowser=True):
    """Open the picker, or load a selected Hugging Face chat model."""
    from .server import serve
    return serve(model, offline=offline, inbrowser=inbrowser)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", nargs="?", help="Hugging Face repository ID")
    parser.add_argument("--offline", action="store_true", help="Use cached files only")
    args = parser.parse_args()
    launch(args.model, offline=args.offline)
